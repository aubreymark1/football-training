"""WebAuthn passkey endpoints. The database stores public keys, never private keys."""
import hashlib, hmac, json, os, secrets, sqlite3, time, urllib.parse
from flask import request, session, jsonify
from werkzeug.security import check_password_hash
from webauthn import (generate_registration_options, verify_registration_response,
                      generate_authentication_options, verify_authentication_response,
                      options_to_json, base64url_to_bytes)
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.structs import (AuthenticatorSelectionCriteria, ResidentKeyRequirement,
                                      UserVerificationRequirement, PublicKeyCredentialDescriptor)


def setup(app, db, current, login_required, now):
    def relying_party():
        url=urllib.parse.urlsplit(os.environ.get('TEAM_PUBLIC_URL','http://localhost:5050'))
        if not url.hostname or url.username or url.password or (url.scheme!='https' and not (url.scheme=='http' and url.hostname=='localhost' and os.environ.get('TEAM_HTTPS')!='1')):
            raise ValueError('Passkey origin is not configured')
        return url.hostname, url.scheme+'://'+url.netloc

    def digest(token):
        return hmac.new(app.config['SECRET_KEY'].encode(),token.encode(),hashlib.sha256).hexdigest()

    def save_challenge(kind, challenge, user=None):
        token=secrets.token_urlsafe(32); session['pk_'+kind]=token
        with db() as c:
            c.execute('DELETE FROM passkey_challenges WHERE expires<?',(int(time.time()),))
            c.execute('INSERT INTO passkey_challenges(token,purpose,challenge,user_id,session_version,expires) VALUES(?,?,?,?,?,?)',
                      (digest(token),kind,challenge,user['id'] if user else None,user['session_version'] if user else None,int(time.time())+180))

    def take_challenge(kind):
        token=session.pop('pk_'+kind,None)
        if not token:return None
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT * FROM passkey_challenges WHERE token=? AND purpose=?',(digest(token),kind)).fetchone()
            c.execute('DELETE FROM passkey_challenges WHERE token=?',(digest(token),))
        return row if row and row['expires']>=int(time.time()) else None

    def password_ok(user):
        stamp=int(time.time()); ip=request.remote_addr or 'unknown'; key='passkey-password:'+ip+':'+str(user['id'])
        with db() as c:
            c.execute('DELETE FROM login_failures WHERE happened<?',(stamp-900,))
            tries=c.execute('SELECT count(*) FROM login_failures WHERE address=?',(key,)).fetchone()[0]
            row=c.execute('SELECT password FROM users WHERE id=?',(user['id'],)).fetchone()
        if tries>=8:return False
        ok=bool(row and check_password_hash(row['password'],request.form.get('password','')))
        with db() as c:
            if ok:c.execute('DELETE FROM login_failures WHERE address=?',(key,))
            else:c.execute('INSERT INTO login_failures(address,happened) VALUES(?,?)',(key,stamp))
        return ok

    def credential():
        value=request.form.get('credential','')
        if len(value)>20000:raise ValueError('credential too large')
        data=json.loads(value)
        if not isinstance(data,dict) or not isinstance(data.get('id'),str) or len(data['id'])>2048:raise ValueError('invalid credential')
        return data

    @app.post('/passkey/register/options')
    @login_required
    def passkey_register_options():
        user=current()
        if not password_ok(user):return jsonify(error='密码不正确或尝试次数过多，请稍后再试。'),400
        try:rp_id,_=relying_party()
        except ValueError:return jsonify(error='通行密钥暂不可用，请联系管理员。'),503
        with db() as c:
            existing=c.execute('SELECT credential_id FROM passkeys WHERE user_id=?',(user['id'],)).fetchall()
        handle=hmac.new(app.config['SECRET_KEY'].encode(),('passkey-user:'+str(user['id'])).encode(),hashlib.sha256).digest()
        options=generate_registration_options(rp_id=rp_id,rp_name='LINGNAN UNITED',user_id=handle,user_name=user['name'],user_display_name=user['name'],timeout=180000,
            authenticator_selection=AuthenticatorSelectionCriteria(resident_key=ResidentKeyRequirement.REQUIRED,user_verification=UserVerificationRequirement.REQUIRED),
            exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(r['credential_id'])) for r in existing])
        save_challenge('register',options.challenge,user)
        return app.response_class(options_to_json(options),mimetype='application/json')

    @app.post('/passkey/register/finish')
    @login_required
    def passkey_register_finish():
        user=current(); challenge=take_challenge('register')
        if not challenge or challenge['user_id']!=user['id'] or challenge['session_version']!=user['session_version']:
            return jsonify(error='验证已过期，请重新开始。'),400
        try:
            rp_id,origin=relying_party(); data=credential()
            result=verify_registration_response(credential=data,expected_challenge=challenge['challenge'],expected_rp_id=rp_id,expected_origin=origin,require_user_verification=True)
            label=request.form.get('label','').strip()[:40] or '通行密钥'
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                account=c.execute('SELECT active,deleted,session_version FROM users WHERE id=?',(user['id'],)).fetchone()
                if not account or not account['active'] or account['deleted'] or account['session_version']!=challenge['session_version']:
                    raise ValueError('session changed during registration')
                c.execute('INSERT INTO passkeys(user_id,credential_id,public_key,sign_count,label,created) VALUES(?,?,?,?,?,?)',
                          (user['id'],bytes_to_base64url(result.credential_id),result.credential_public_key,result.sign_count,label,now()))
        except (ValueError,TypeError,KeyError,sqlite3.IntegrityError):return jsonify(error='无法添加通行密钥，请重试。'),400
        except Exception:
            app.logger.info('Passkey registration verification failed',exc_info=False)
            return jsonify(error='无法添加通行密钥，请重试。'),400
        return jsonify(ok=True)

    @app.post('/passkey/login/options')
    def passkey_login_options():
        try:rp_id,_=relying_party()
        except ValueError:return jsonify(error='通行密钥暂不可用，请联系管理员。'),503
        options=generate_authentication_options(rp_id=rp_id,timeout=180000,user_verification=UserVerificationRequirement.REQUIRED)
        save_challenge('login',options.challenge)
        return app.response_class(options_to_json(options),mimetype='application/json')

    @app.post('/passkey/login/finish')
    def passkey_login_finish():
        challenge=take_challenge('login')
        if not challenge:return jsonify(error='验证已过期，请重新登录。'),400
        try:
            rp_id,origin=relying_party();data=credential()
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                row=c.execute('SELECT p.*,u.active,u.deleted,u.session_version FROM passkeys p JOIN users u ON u.id=p.user_id WHERE p.credential_id=?',(data['id'],)).fetchone()
                if not row or not row['active'] or row['deleted']:raise ValueError('unknown credential')
                verified=verify_authentication_response(credential=data,expected_challenge=challenge['challenge'],expected_rp_id=rp_id,expected_origin=origin,credential_public_key=row['public_key'],credential_current_sign_count=row['sign_count'],require_user_verification=True)
                c.execute('UPDATE passkeys SET sign_count=?,last_used=? WHERE id=?',(verified.new_sign_count,now(),row['id']))
                uid,version=row['user_id'],row['session_version']
        except Exception:
            return jsonify(error='通行密钥验证失败，请重试或使用密码登录。'),400
        session.clear();session['uid']=uid;session['version']=version;session.permanent=True
        return jsonify(ok=True)

    @app.post('/passkey/<int:passkey_id>/delete')
    @login_required
    def passkey_delete(passkey_id):
        user=current()
        if not password_ok(user):return jsonify(error='密码不正确或尝试次数过多，请稍后再试。'),400
        with db() as c:
            deleted=c.execute('DELETE FROM passkeys WHERE id=? AND user_id=?',(passkey_id,user['id'])).rowcount
        return jsonify(ok=True) if deleted else (jsonify(error='通行密钥不存在。'),404)
