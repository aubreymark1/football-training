import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from werkzeug.middleware.proxy_fix import ProxyFix

os.environ['TEAM_DATA_DIR']=tempfile.mkdtemp(prefix='moments-initial-')
os.environ['TEAM_SECRET']='test-only'
os.environ.pop('TEAM_HTTPS',None)
import app as m


class MomentsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='moments-test-')
        self.old_db,self.old_data=m.DB,m.DATA
        m.DATA=Path(self.temp.name);(m.DATA/'uploads').mkdir();m.DB=m.DATA/'test.sqlite3';m.init()
        with m.db() as c:
            for name,role in [('alice','member'),('bob','member'),('admin','admin')]:
                c.execute('INSERT INTO users(name,password,role) VALUES(?,?,?)',(name,'unused',role))
            self.ids={r['name']:r['id'] for r in c.execute('SELECT id,name FROM users')}
            c.execute("INSERT INTO tasks(title,detail,week,kind) VALUES('跑步任务','',?,'required')",(m.week(),))
            self.tid=c.execute('SELECT id FROM tasks').fetchone()[0]
            c.execute("INSERT INTO records(user_id,task_id,sport,minutes,effort,note,image,created) VALUES(?,?,?,?,?,?,?,?)",
                      (self.ids['alice'],self.tid,'历史跑步',30,5,'历史私有','old.jpg',m.now()))
            self.old_id=c.execute('SELECT last_insert_rowid()').fetchone()[0]
        self.alice=self.client('alice');self.bob=self.client('bob');self.admin=self.client('admin')
    def tearDown(self):
        m.DB,m.DATA=self.old_db,self.old_data;self.temp.cleanup()
    def client(self,name):
        c=m.app.test_client()
        with c.session_transaction() as s:s['uid']=self.ids[name];s['version']=0;s['csrf']='token'
        return c
    def image(self):
        out=io.BytesIO();Image.new('RGB',(12,12),'green').save(out,'PNG');out.seek(0);return out
    def submit(self,client,free=False,note='今天跑得不错'):
        path='/free' if free else '/submit/'+str(self.tid)
        with patch('image_forensics.inspect_upload',return_value=(0,'')):
            return client.post(path,data={'csrf':'token','moments_notice':'1','sport':'跑步','minutes':'42','effort':'6','note':note,'image':(self.image(),'run.png')})
    def post(self,client,path,**data):return client.post(path,data={'csrf':'token',**data})
    def latest(self):
        with m.db() as c:return c.execute('SELECT max(id) FROM records').fetchone()[0]

    def test_new_submissions_shared_old_records_private_and_image_rules(self):
        self.assertEqual(m.app.test_client().get('/moments').status_code,302)
        self.assertEqual(self.bob.get('/moments/%s/image'%self.old_id).status_code,404)
        self.assertNotIn('历史私有',self.bob.get('/moments').get_data(as_text=True))
        self.assertIn('所有登录队员可见',self.alice.get('/submit/'+str(self.tid)).get_data(as_text=True))
        self.assertEqual(self.submit(self.alice,note='<script>坏内容</script>').status_code,302)
        rid=self.latest();body=self.bob.get('/moments').get_data(as_text=True)
        self.assertIn('跑步任务',body);self.assertIn('&lt;script&gt;',body);self.assertNotIn('<script>坏内容</script>',body)
        self.assertEqual(self.bob.get('/moments/%s/image?thumb=1'%rid).status_code,200)
        self.assertIn('no-store',self.bob.get('/moments/%s/image?thumb=1'%rid).headers['Cache-Control'])
        self.assertEqual(self.bob.get('/image/%s'%rid).status_code,403)
        self.assertEqual(m.app.test_client().get('/moments/%s/image'%rid).status_code,302)
        self.assertEqual(self.submit(self.alice,free=True).status_code,302)
        self.assertIn('自主训练',self.bob.get('/moments').get_data(as_text=True))
        with m.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM moment_posts').fetchone()[0],2)
            self.assertEqual(c.execute('SELECT status FROM records WHERE id=?',(rid,)).fetchone()[0],'pending')

    def test_likes_comments_hide_and_authorization(self):
        self.submit(self.alice);rid=self.latest()
        self.assertEqual(self.bob.post(f'/moments/{rid}/like').status_code,400)
        self.assertEqual(self.post(self.bob,f'/moments/{rid}/like').status_code,302)
        self.assertIn('bob',self.alice.get('/moments').get_data(as_text=True))
        with m.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM moment_likes').fetchone()[0],1)
        self.post(self.bob,f'/moments/{rid}/like')
        with m.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM moment_likes').fetchone()[0],0)
        self.post(self.bob,f'/moments/{rid}/comment',content='加油 <b>队友</b>')
        self.assertIn('&lt;b&gt;队友&lt;/b&gt;',self.alice.get('/moments').get_data(as_text=True))
        with m.db() as c:cid=c.execute('SELECT id FROM moment_comments').fetchone()[0]
        self.assertEqual(self.post(self.alice,f'/moments/{rid}/comment/{cid}/delete').status_code,403)
        self.assertEqual(self.post(self.bob,f'/moments/{rid}/comment/{cid}/delete').status_code,302)
        self.assertEqual(self.post(self.bob,f'/moments/{rid}/hide').status_code,403)
        self.assertEqual(self.post(self.alice,f'/moments/{rid}/hide').status_code,302)
        self.assertEqual(self.bob.get(f'/moments/{rid}/image').status_code,404)
        self.assertEqual(self.alice.get(f'/image/{rid}').status_code,200)
        self.assertEqual(self.post(self.bob,f'/moments/{rid}/comment',content='隐藏后').status_code,404)
        with m.db() as c:self.assertIsNotNone(c.execute('SELECT id FROM records WHERE id=?',(rid,)).fetchone())

    def test_feed_pagination_and_invalid_cursor(self):
        with m.db() as c:
            for i in range(22):
                r=c.execute("INSERT INTO records(user_id,task_id,sport,minutes,effort,note,image,created) VALUES(?,?,?,?,?,?,?,?)",(self.ids['alice'],self.tid,'跑步',10,5,'条目'+str(i),'none.jpg',m.now()))
                c.execute('INSERT INTO moment_posts(record_id) VALUES(?)',(r.lastrowid,))
        first=self.bob.get('/moments').get_data(as_text=True)
        self.assertIn('查看更早的动态',first);self.assertNotIn('条目0',first)
        with m.db() as c:cursor=c.execute('SELECT record_id FROM moment_posts ORDER BY record_id DESC LIMIT 1 OFFSET 19').fetchone()[0]
        older=self.bob.get('/moments?before='+str(cursor)).get_data(as_text=True)
        self.assertIn('条目0',older);self.assertNotIn('条目21',older)
        self.assertEqual(self.bob.get('/moments?before='+'9'*5000).status_code,400)

    def test_record_and_post_are_committed_together(self):
        with m.db() as c: before=c.execute('SELECT count(*) FROM records').fetchone()[0]
        previous=m.app.testing
        m.app.testing=True
        try:
            with patch('moments.record_post',side_effect=RuntimeError('test failure')):
                with self.assertRaises(RuntimeError):self.submit(self.alice)
        finally:
            m.app.testing=previous
        with m.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM records').fetchone()[0],before)
            self.assertEqual(c.execute('SELECT count(*) FROM moment_posts').fetchone()[0],0)

    def test_old_submission_page_cannot_accidentally_share(self):
        with m.db() as c: before=c.execute('SELECT count(*) FROM records').fetchone()[0]
        for path in ('/submit/'+str(self.tid),'/free'):
            response=self.alice.post(path,data={'csrf':'token','sport':'跑步','minutes':'10','effort':'5','image':(self.image(),'run.png')},follow_redirects=True)
            self.assertIn('提交页面已更新',response.get_data(as_text=True))
        with m.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM records').fetchone()[0],before)
            self.assertEqual(c.execute('SELECT count(*) FROM moment_posts').fetchone()[0],0)

    def test_admin_moderation_and_invalid_comments(self):
        self.submit(self.alice);rid=self.latest()
        self.post(self.bob,f'/moments/{rid}/comment',content=' ')
        self.post(self.bob,f'/moments/{rid}/comment',content='字'*301)
        with m.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM moment_comments').fetchone()[0],0)
        self.post(self.bob,f'/moments/{rid}/comment',content='加油')
        with m.db() as c:cid=c.execute('SELECT id FROM moment_comments').fetchone()[0]
        self.assertEqual(self.post(self.admin,f'/moments/{rid}/comment/{cid}/delete').status_code,302)
        self.assertEqual(self.post(self.admin,f'/moments/{rid}/hide').status_code,302)
        self.assertEqual(self.bob.get(f'/moments/{rid}/image').status_code,404)

    def test_reverse_proxy_prefix_in_feed_urls(self):
        self.submit(self.alice);rid=self.latest()
        original=m.app.wsgi_app
        try:
            m.app.wsgi_app=ProxyFix(original,x_for=1,x_proto=1,x_host=1,x_prefix=1)
            body=self.bob.get('/moments',headers={'X-Forwarded-Prefix':'/football','X-Forwarded-Proto':'https','X-Forwarded-Host':'example.test'}).get_data(as_text=True)
            self.assertIn('/football/moments/%s/image' % rid,body)
            self.assertIn('/football/moments/%s/like' % rid,body)
        finally:
            m.app.wsgi_app=original

    def test_feed_likes_and_comments_use_nicknames(self):
        with m.db() as c:
            c.execute('UPDATE users SET real_name=? WHERE id=?',('真实姓名甲',self.ids['alice']))
            c.execute('UPDATE users SET real_name=? WHERE id=?',('真实姓名乙',self.ids['bob']))
        self.submit(self.alice);rid=self.latest()
        self.post(self.bob,f'/moments/{rid}/like')
        self.post(self.bob,f'/moments/{rid}/comment',content='训练加油')
        body=self.alice.get('/moments').get_data(as_text=True)
        self.assertIn('alice',body);self.assertIn('bob',body)
        self.assertNotIn('真实姓名甲',body);self.assertNotIn('真实姓名乙',body)
        self.assertNotIn('一起训练，一起留下记录',body)


if __name__=='__main__':unittest.main()
