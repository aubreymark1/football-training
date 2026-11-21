import os,tempfile,unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
os.environ['TEAM_DATA_DIR']=tempfile.mkdtemp(prefix='lottery_test_')
os.environ['TEAM_SECRET']='test'
import app as m
import lottery
class LotteryTest(unittest.TestCase):
 def setUp(self):
  self.client=m.app.test_client()
  with m.db() as c:
   c.execute('DELETE FROM lottery_settings'); c.execute('DELETE FROM lottery_draws'); c.execute('DELETE FROM ledger');c.execute('DELETE FROM redemptions');c.execute('DELETE FROM rewards');c.execute('DELETE FROM users')
   c.execute("INSERT INTO users(name,password,role) VALUES('lottery-member','x','member')");self.uid=c.execute('SELECT id FROM users').fetchone()[0]
   c.execute("INSERT INTO ledger(user_id,amount,note,created) VALUES(?,100,'test','2026')",(self.uid,))
   for name,_,_ in lottery.PRIZES:c.execute('INSERT INTO rewards(name,cost,stock) VALUES(?,?,?)',(name,0,3))
   self.rid=c.execute("SELECT id FROM rewards WHERE name='弹力带'").fetchone()[0]
  with self.client.session_transaction() as s:s['uid']=self.uid;s['version']=0;s['csrf']='testcsrf'
 def draw(self,token):return self.client.post('/lottery/draw',data={'csrf':'testcsrf','wish':str(self.rid),'token':token})
 def test_page_and_insufficient_balance(self):
  page=self.client.get('/lottery'); self.assertEqual(page.status_code,200)
  html=page.get_data(as_text=True)
  for forbidden in ('概率', 'weight', '65.4%', '20%', '10%', '50%'):self.assertNotIn(forbidden,html)
  with m.db() as c:c.execute('DELETE FROM ledger')
  self.assertEqual(self.draw('insufficient').status_code,400)
  with m.db() as c:self.assertEqual(c.execute('select count(*) from lottery_draws').fetchone()[0],0)
 def test_concurrent_draws_share_last_stock(self):
  with m.db() as c:c.execute("update rewards set stock=1 where name='医用绷带'")
  def request_once(token):
   client=m.app.test_client()
   with client.session_transaction() as s:s['uid']=self.uid;s['version']=0;s['csrf']='testcsrf'
   return client.post('/lottery/draw',data={'csrf':'testcsrf','wish':str(self.rid),'token':token}).json
  with patch('lottery.secrets.randbelow',return_value=0), ThreadPoolExecutor(max_workers=2) as pool:
   results=list(pool.map(request_once,['parallel1','parallel2']))
  self.assertEqual(sorted(r['result'] for r in results),sorted(['医用绷带','谢谢参与']))
  with m.db() as c:
   self.assertEqual(c.execute("select stock from rewards where name='医用绷带'").fetchone()[0],0)
   self.assertEqual(c.execute('select count(*) from redemptions').fetchone()[0],1)
 def test_other_guarantee(self):
  with m.db() as c:c.executemany('INSERT INTO lottery_draws(user_id,token,result,created) VALUES(?,?,?,?)',[(self.uid,str(i),'谢谢参与','2026') for i in range(49)])
  with patch('lottery.secrets.randbelow',side_effect=[1,0]):r=self.draw('other')
  self.assertTrue(r.json['guaranteed']);self.assertEqual(r.json['result'],'医用绷带')
 def test_wish_saved_across_sessions(self):
  r=self.client.post('/lottery/wish',data={'csrf':'testcsrf','wish':str(self.rid)})
  self.assertEqual(r.status_code,200)
  self.assertIn('selected',self.client.get('/lottery').get_data(as_text=True))
  with m.db() as c:self.assertEqual(c.execute('select wish_reward_id from lottery_settings where user_id=?',(self.uid,)).fetchone()[0],self.rid)
 def test_normal_bonus_and_idempotence(self):
  with patch('lottery.secrets.randbelow',return_value=46):
   r=self.draw('same');self.assertEqual(r.status_code,200);self.assertEqual(r.json['result'],'0.5积分奖励');self.assertEqual(r.json['points'],99.5)
   self.assertEqual(self.draw('same').json['points'],99.5)
  with m.db() as c:self.assertEqual(c.execute('select count(*) from lottery_draws').fetchone()[0],1)
 def test_fiftieth_guaranteed_and_stock(self):
  with m.db() as c:
   c.executemany('INSERT INTO lottery_draws(user_id,token,result,created) VALUES(?,?,?,?)',[(self.uid,str(i),'谢谢参与','2026') for i in range(49)])
  with patch('lottery.secrets.randbelow',return_value=0):r=self.draw('fiftieth')
  self.assertEqual(r.json['result'],'弹力带');self.assertTrue(r.json['guaranteed']);self.assertEqual(r.json['progress'],0)
  with m.db() as c:
   self.assertEqual(c.execute('select stock from rewards where id=?',(self.rid,)).fetchone()[0],2)
   self.assertEqual(c.execute('select count(*) from redemptions').fetchone()[0],1)
 def test_direct_free_redeem_blocked(self):
  self.client.post('/redeem/'+str(self.rid),data={'csrf':'testcsrf'})
  with m.db() as c:self.assertEqual(c.execute('select count(*) from redemptions').fetchone()[0],0)
if __name__=='__main__':unittest.main()
