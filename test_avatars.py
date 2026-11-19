from contextlib import closing
import io
import os
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from PIL import Image
from werkzeug.middleware.proxy_fix import ProxyFix

os.environ['TEAM_DATA_DIR']=tempfile.mkdtemp(prefix='avatars-initial-')
os.environ['TEAM_SECRET']='test-only'
os.environ.pop('TEAM_HTTPS',None)
import app as m
import avatars
import backup


class AvatarTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='avatars-test-')
        self.old_db,self.old_data=m.DB,m.DATA
        m.DATA=Path(self.temp.name)/'data';m.DATA.mkdir();(m.DATA/'uploads').mkdir();m.DB=m.DATA/'team.sqlite3';m.init()
        with m.db() as c:
            for name in ('alice','bob'):
                c.execute('INSERT INTO users(name,password,role) VALUES(?,?,?)',(name,'unused','member'))
            self.ids={r['name']:r['id'] for r in c.execute('SELECT id,name FROM users')}
        self.alice=self.client('alice');self.bob=self.client('bob')
    def tearDown(self):
        m.DB,m.DATA=self.old_db,self.old_data;self.temp.cleanup()
    def client(self,name):
        c=m.app.test_client()
        with c.session_transaction() as s:s['uid']=self.ids[name];s['version']=0;s['csrf']='token'
        return c
    def png(self):
        out=io.BytesIO();Image.new('RGBA',(300,200),(25,130,70,120)).save(out,'PNG');out.seek(0);return out
    def upload(self,client=None,data=None,**values):
        return (client or self.alice).post('/account/avatar',data={'csrf':'token','avatar':(data or self.png(),'avatar.png'),**values},follow_redirects=True)

    def test_stable_default_and_access(self):
        self.assertEqual({avatars.default_number(i) for i in range(1,100)}, {1,2,3,4})
        uid=self.ids['alice'];first=self.bob.get('/avatar/%s'%uid);second=self.bob.get('/avatar/%s'%uid)
        self.assertEqual(first.status_code,302);self.assertEqual(first.location,second.location)
        self.assertIn('/static/avatars/default-%s.jpg'%avatars.default_number(uid),first.location)
        self.assertIn('no-store',first.headers['Cache-Control'])
        self.assertEqual(m.app.test_client().get('/avatar/%s'%uid).status_code,302)
        self.assertEqual(self.bob.get('/avatar/99999').status_code,404)
        self.assertIn('/avatar/%s'%uid,self.alice.get('/account').get_data(as_text=True))
        self.assertIn('/avatar/%s'%uid,self.bob.get('/team').get_data(as_text=True))

    def test_upload_visible_only_to_members_and_backed_up(self):
        result=self.upload(user_id=str(self.ids['bob']))
        self.assertIn('头像已更新',result.get_data(as_text=True))
        with m.db() as c:
            rows=c.execute('SELECT user_id,image FROM user_avatars').fetchall()
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['user_id'],self.ids['alice'])
        image=self.bob.get('/avatar/%s'%self.ids['alice'])
        self.assertEqual(image.status_code,200);self.assertEqual(image.mimetype,'image/jpeg')
        self.assertIn('no-store',image.headers['Cache-Control'])
        with Image.open(io.BytesIO(image.data)) as im:
            self.assertEqual(im.size,(256,256));self.assertFalse(im.getexif())
        destination=Path(self.temp.name)/'backup.zip'
        backup.backup(m.DATA,destination)
        with zipfile.ZipFile(destination) as z:
            snapshot=Path(self.temp.name)/'snapshot.sqlite3';snapshot.write_bytes(z.read('team.sqlite3'))
        with closing(sqlite3.connect(snapshot)) as c:
            self.assertEqual(c.execute('SELECT image FROM user_avatars WHERE user_id=?',(self.ids['alice'],)).fetchone()[0],rows[0]['image'])

    def test_invalid_upload_reset_and_csrf(self):
        self.upload()
        before=self.alice.get('/avatar/%s'%self.ids['alice']).data
        response=self.upload(data=io.BytesIO(b'not an image'))
        self.assertIn('图片无法读取',response.get_data(as_text=True))
        self.assertEqual(self.alice.get('/avatar/%s'%self.ids['alice']).data,before)
        response=self.upload(data=io.BytesIO(b'x'*(avatars.MAX_BYTES+1)))
        self.assertIn('不超过 7MB',response.get_data(as_text=True))
        self.assertEqual(self.alice.get('/avatar/%s'%self.ids['alice']).data,before)
        self.assertEqual(self.alice.post('/account/avatar/reset').status_code,400)
        self.assertEqual(self.alice.post('/account/avatar/reset',data={'csrf':'token'}).status_code,302)
        self.assertEqual(self.alice.get('/avatar/%s'%self.ids['alice']).status_code,302)
        self.assertEqual(self.bob.get('/avatar/%s'%self.ids['bob']).status_code,302)

    def test_moments_avatar_and_proxy_url(self):
        with m.db() as c:
            r=c.execute("INSERT INTO records(user_id,task_id,sport,minutes,effort,note,image,created) VALUES(?,?,?,?,?,?,?,?)",(self.ids['alice'],None,'跑步',10,4,'测试','x.jpg',m.now()))
            c.execute('INSERT INTO moment_posts(record_id) VALUES(?)',(r.lastrowid,))
        body=self.bob.get('/moments').get_data(as_text=True)
        self.assertIn('/avatar/%s'%self.ids['alice'],body)
        old=m.app.wsgi_app
        try:
            m.app.wsgi_app=ProxyFix(old,x_for=1,x_proto=1,x_host=1,x_prefix=1)
            response=self.bob.get('/avatar/%s'%self.ids['alice'],headers={'X-Forwarded-Prefix':'/football','X-Forwarded-Proto':'https','X-Forwarded-Host':'example.test'})
            self.assertIn('/football/static/avatars/default-',response.location)
        finally:m.app.wsgi_app=old


if __name__=='__main__':unittest.main()
