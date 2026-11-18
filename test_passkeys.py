import os,tempfile,unittest,secrets
from unittest.mock import patch
os.environ['TEAM_DATA_DIR']=tempfile.mkdtemp(prefix='football-passkey-tests-')
os.environ['TEAM_SECRET']='tests-only-secret'
os.environ['TEAM_PUBLIC_URL']='http://localhost:5055'
import app as m
from werkzeug.security import generate_password_hash
from webauthn.helpers import bytes_to_base64url

class PasskeyTests(unittest.TestCase):
 def setUp(self):
  self.client=m.app.test_client()
  with m.db() as c:
   self.name='player-'+secrets.token_hex(5);self.email=self.name+'@example.org';self.credential_id=bytes_to_base64url(self.name.encode())
   self.uid=c.execute('INSERT INTO users(name,real_name,password,email,email_verified) VALUES(?,?,?,?,1)',(self.name,'测试队员',generate_password_hash('examplepass123'),self.email)).lastrowid
 def csrf(self,client=None):
  with (client or self.client).session_transaction() as s:
   s.setdefault('csrf','csrf-test');return s['csrf']
 def post(self,path,data=None,client=None):
  client=client or self.client;values={'csrf':self.csrf(client)};values.update(data or {});return client.post(path,data=values)
 def login(self):self.post('/login',{'name':self.name,'password':'examplepass123'})
 def add_key(self):
  with m.db() as c:c.execute('INSERT INTO passkeys(user_id,credential_id,public_key,sign_count,label,created) VALUES(?,?,?,?,?,?)',(self.uid,self.credential_id,b'key',0,'测试密钥',m.now()))
 def test_registration_requires_password_and_consumes_challenge(self):
  self.login()
  self.assertEqual(self.post('/passkey/register/options',{'password':'bad'}).status_code,400)
  self.assertEqual(self.post('/passkey/register/options',{'password':'examplepass123'}).status_code,200)
  self.assertEqual(self.post('/passkey/register/finish',{'credential':'{}'}).status_code,400)
  self.assertEqual(self.post('/passkey/register/finish',{'credential':'{}'}).status_code,400)
  with m.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM passkey_challenges WHERE user_id=?',(self.uid,)).fetchone()[0],0)
 def test_login_challenge_cannot_be_replayed_and_rejects_inactive_user(self):
  self.add_key();self.assertEqual(self.post('/passkey/login/options').status_code,200)
  with m.db() as c:c.execute('UPDATE users SET active=0 WHERE id=?',(self.uid,))
  data={'credential':__import__('json').dumps({'id':self.credential_id,'type':'public-key'})}
  self.assertEqual(self.post('/passkey/login/finish',data).status_code,400)
  self.assertEqual(self.post('/passkey/login/finish',data).status_code,400)
 def test_removal_is_limited_to_owner_and_requires_password(self):
  self.add_key();self.login()
  with m.db() as c:key=c.execute('SELECT id FROM passkeys WHERE user_id=?',(self.uid,)).fetchone()[0]
  self.assertEqual(self.post('/passkey/%s/delete'%key,{'password':'bad'}).status_code,400)
  self.assertEqual(self.post('/passkey/%s/delete'%key,{'password':'examplepass123'}).status_code,200)
  with m.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM passkeys WHERE user_id=?',(self.uid,)).fetchone()[0],0)
 def test_password_reset_revokes_passkeys(self):
  self.add_key()
  with patch('mail_service.configured',return_value=True),patch('mail_service.verification') as sent:
   self.assertEqual(self.post('/reset-password/send-code',{'email':self.email,'real_name':'测试队员'}).status_code,200);code=sent.call_args.args[1]
  self.post('/reset-password',{'email':self.email,'real_name':'测试队员','email_code':code,'password':'replacement123','confirm_password':'replacement123'})
  with m.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM passkeys WHERE user_id=?',(self.uid,)).fetchone()[0],0)
 def test_challenge_is_tied_to_browser_session(self):
  self.assertEqual(self.post('/passkey/login/options').status_code,200)
  with m.db() as c: count=c.execute('SELECT count(*) FROM passkey_challenges').fetchone()[0]
  other=m.app.test_client()
  self.assertEqual(self.post('/passkey/login/finish',{'credential':'{}'},other).status_code,400)
  with m.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM passkey_challenges').fetchone()[0],count)
 def test_password_reset_during_registration_does_not_add_key(self):
  self.login()
  self.assertEqual(self.post('/passkey/register/options',{'password':'examplepass123'}).status_code,200)
  def simulate_reset(**kwargs):
   from types import SimpleNamespace
   with m.db() as c:c.execute('UPDATE users SET session_version=session_version+1 WHERE id=?',(self.uid,))
   return SimpleNamespace(credential_id=b'new-key',credential_public_key=b'pub',sign_count=0)
  with patch('passkeys.verify_registration_response',side_effect=simulate_reset):
   response=self.post('/passkey/register/finish',{'credential':'{"id":"bmV3LWtleQ"}'})
  self.assertEqual(response.status_code,400)
  with m.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM passkeys WHERE user_id=?',(self.uid,)).fetchone()[0],0)
 def test_csrf_required(self):self.assertEqual(self.client.post('/passkey/login/options').status_code,400)

if __name__=='__main__':unittest.main()
