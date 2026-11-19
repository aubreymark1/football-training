"""Small team-visible avatars; uploaded images live in the backed-up database."""
import hashlib
import io

from flask import abort, flash, redirect, request, send_file, url_for
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES=7*1024*1024
MAX_PIXELS=16_000_000
FORMATS={'JPEG','PNG','WEBP','GIF'}


def init_schema(connection):
    connection.execute('''CREATE TABLE IF NOT EXISTS user_avatars (
        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        image BLOB NOT NULL, updated_at TEXT NOT NULL)''')


def default_number(user_id):
    digest=hashlib.sha256(('lingnan-avatar-v1:'+str(user_id)).encode('ascii')).digest()
    return digest[0]%4+1


def prepare_avatar(raw):
    if not raw or len(raw)>MAX_BYTES:
        raise ValueError('请选择不超过 7MB 的图片。')
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in FORMATS or source.width<1 or source.height<1 or source.width*source.height>MAX_PIXELS:
                raise ValueError('请选择尺寸不超过 1600 万像素的 JPG、PNG、WebP 或 GIF 图片。')
            source.verify()
        with Image.open(io.BytesIO(raw)) as source:
            source.draft('RGB',(1024,1024))
            oriented=ImageOps.exif_transpose(source)
            oriented.thumbnail((1024,1024),Image.Resampling.LANCZOS)
            rgba=oriented.convert('RGBA')
            background=Image.new('RGB',rgba.size,'white')
            background.paste(rgba,mask=rgba.getchannel('A'))
            square=ImageOps.fit(background,(256,256),method=Image.Resampling.LANCZOS)
            output=io.BytesIO();square.save(output,format='JPEG',quality=84,optimize=True)
            return output.getvalue()
    except (UnidentifiedImageError,OSError,SyntaxError,Image.DecompressionBombError) as exc:
        raise ValueError('图片无法读取，请选择 JPG、PNG、WebP 或 GIF 图片。') from exc


def register(app, *, db, current, login_required, now):
    @app.get('/avatar/<int:uid>')
    @login_required
    def avatar_image(uid):
        with db() as c:
            row=c.execute('''SELECT a.image FROM users u LEFT JOIN user_avatars a ON a.user_id=u.id
                WHERE u.id=? AND u.active=1 AND u.deleted=0''',(uid,)).fetchone()
        if not row: abort(404)
        if row['image'] is None:
            response=redirect(url_for('static',filename='avatars/default-%s.jpg'%default_number(uid)))
        else:
            response=send_file(io.BytesIO(row['image']),mimetype='image/jpeg',max_age=0)
        response.headers['Cache-Control']='private, no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        return response

    @app.post('/account/avatar')
    @login_required
    def account_avatar():
        upload=request.files.get('avatar')
        if not upload or not upload.filename:
            flash('请选择头像图片。','error');return redirect(url_for('account'))
        try:
            image=prepare_avatar(upload.stream.read(MAX_BYTES+1))
        except ValueError as exc:
            flash(str(exc),'error');return redirect(url_for('account'))
        with db() as c:
            c.execute('''INSERT INTO user_avatars(user_id,image,updated_at) VALUES(?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET image=excluded.image,updated_at=excluded.updated_at''',
                (current()['id'],image,now()))
        flash('头像已更新。');return redirect(url_for('account'))

    @app.post('/account/avatar/reset')
    @login_required
    def account_avatar_reset():
        with db() as c:c.execute('DELETE FROM user_avatars WHERE user_id=?',(current()['id'],))
        flash('已恢复默认头像。');return redirect(url_for('account'))
