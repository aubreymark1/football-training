import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ['TEAM_DATA_DIR']=tempfile.mkdtemp(prefix='plans-offline-test-')
os.environ['TEAM_SECRET']='test-only'
os.environ.pop('TEAM_HTTPS',None)
os.environ.pop('TEAM_PLANS_ENABLED',None)
import app as m


class OfflinePlansTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='plans-offline-db-');self.previous=m.DB;m.DB=Path(self.temp.name)/'team.sqlite3';m.init()
  with m.db() as c:
   c.execute("INSERT INTO users(name,password,role,is_captain,tour_seen) VALUES('captain','x','member',1,1)")
   c.execute("INSERT INTO users(name,password,role,tour_seen) VALUES('admin','x','admin',1)")
   c.execute("INSERT INTO team_training_plans(week,draft,updated_at) VALUES('2026-11-16',?,?)",(json.dumps({'title':'保留草稿','items':[]}),m.now()))
   self.ids={r['name']:r['id'] for r in c.execute('SELECT id,name FROM users')}
 def tearDown(self):m.DB=self.previous;self.temp.cleanup()
 def client(self,name):
  c=m.app.test_client()
  with c.session_transaction() as s:s['uid']=self.ids[name];s['version']=0;s['csrf']='token'
  return c
 def test_offline_hides_entries_and_denies_all_plan_routes_without_deleting_data(self):
  captain=self.client('captain');admin=self.client('admin')
  with patch.dict(os.environ,{'TEAM_PLANS_ENABLED':'0'}):
   for client in (captain,admin):
    for path in ('/plans','/plans/1','/plans/1/edit'):
     self.assertEqual(client.get(path).status_code,404,path)
    for path in ('/plans/new','/plans/1/save','/plans/1/ai','/plans/1/board-agent','/plans/1/videos'):
     self.assertEqual(client.post(path,data={'csrf':'token'}).status_code,404,path)
    self.assertNotIn('球队训练计划',client.get('/').get_data(as_text=True))
    self.assertNotIn('球队训练计划',client.get('/team').get_data(as_text=True))
   self.assertEqual(admin.post('/admin/member/%s/captain'%self.ids['captain'],data={'csrf':'token','captain':'0'}).status_code,404)
   self.assertNotIn('取消队长权限',admin.get('/admin/members').get_data(as_text=True))
   self.assertEqual(captain.get('/history').status_code,200)
   self.assertEqual(captain.get('/rewards').status_code,200)
  with m.db() as c:
   self.assertEqual(json.loads(c.execute('select draft from team_training_plans').fetchone()[0])['title'],'保留草稿')
   self.assertEqual(c.execute('select is_captain from users where name=?',('captain',)).fetchone()[0],1)
 def test_can_enable_only_in_isolated_test_environment(self):
  with patch.dict(os.environ,{'TEAM_PLANS_ENABLED':'1'}):
   self.assertEqual(self.client('captain').get('/plans').status_code,200)


if __name__=='__main__':unittest.main()
