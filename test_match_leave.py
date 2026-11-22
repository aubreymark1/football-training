import datetime
import os
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

os.environ['TEAM_DATA_DIR']=tempfile.mkdtemp(prefix='match-leave-initial-')
os.environ['TEAM_SECRET']='test-only'
import app as m


class MatchLeaveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='match-leave-db-');self.old_db=m.DB
        m.DB=Path(self.temp.name)/'team.sqlite3';m.init()
        with m.db() as c:
            self.admin=c.execute("INSERT INTO users(name,password,role) VALUES('admin','x','admin')").lastrowid
            self.captain=c.execute("INSERT INTO users(name,password,role,is_captain) VALUES('captain','x','member',1)").lastrowid
            self.member=c.execute("INSERT INTO users(name,password,role) VALUES('member','x','member')").lastrowid
            self.other=c.execute("INSERT INTO users(name,password,role) VALUES('other','x','member')").lastrowid
            start=(datetime.datetime.now(ZoneInfo('Asia/Shanghai'))+datetime.timedelta(days=5)).replace(second=0,microsecond=0)
            self.game=c.execute("INSERT INTO matches(date,time,competition,home,away,status) VALUES(?,?,?,?,?,'scheduled')",(start.date().isoformat(),start.strftime('%H:%M'),'测试赛','岭南学院','对手')).lastrowid
            self.training=c.execute("INSERT INTO training_sessions(title,starts_at,ends_at,location,created_by,created_at) VALUES(?,?,?,?,?,?)",('训练',start.isoformat(),(start+datetime.timedelta(hours=2)).isoformat(),'球场',self.admin,m.now())).lastrowid
        self.a=self.client(self.admin);self.cap=self.client(self.captain);self.u=self.client(self.member);self.v=self.client(self.other)

    def tearDown(self):m.DB=self.old_db;self.temp.cleanup()

    def client(self,uid):
        client=m.app.test_client()
        with client.session_transaction() as s:s.update(uid=uid,version=0,csrf='csrf')
        return client

    def post(self,client,url,**data):return client.post(url,data={'csrf':'csrf',**data})

    def test_separate_counts_and_cancelled_events(self):
        self.assertEqual(self.post(self.u,f'/training-sessions/{self.training}/leave',reason='训练原因').status_code,302)
        self.assertEqual(self.post(self.u,f'/account/match-leave/{self.game}',reason='比赛原因').status_code,302)
        with m.db() as c:
            import match_leave
            state=match_leave.account_data(c,self.member,m.now());self.assertEqual((state['training_count'],state['match_count']),(1,1))
        self.assertIn('训练原因',self.u.get('/account').get_data(as_text=True))
        self.assertNotIn('训练原因',self.v.get('/account').get_data(as_text=True))
        self.assertNotIn('比赛原因',self.v.get(f'/matches/{self.game}').get_data(as_text=True))
        self.assertEqual(self.post(self.u,f'/account/match-leave/{self.game}/cancel').status_code,302)
        with m.db() as c:
            state=match_leave.account_data(c,self.member,m.now());self.assertEqual((state['training_count'],state['match_count']),(1,0))
        self.post(self.u,f'/account/match-leave/{self.game}',reason='重新申请')
        with m.db() as c:
            c.execute("UPDATE matches SET status='cancelled' WHERE id=?",(self.game,))
            c.execute("UPDATE training_sessions SET status='cancelled' WHERE id=?",(self.training,))
            state=match_leave.account_data(c,self.member,m.now());self.assertEqual((state['training_count'],state['match_count']),(0,0))

    def test_upgrade_preserves_existing_training_leave(self):
        self.assertEqual(self.post(self.u,f'/training-sessions/{self.training}/leave',reason='已有记录').status_code,302)
        with m.db() as c:
            c.execute('DROP TABLE match_attendance')
            c.execute('DROP TABLE match_leave_requests')
            c.execute("DELETE FROM app_settings WHERE key='match_leave_enabled_at'")
        m.init()
        with m.db() as c:
            self.assertEqual(c.execute('SELECT reason FROM training_leave_requests WHERE user_id=?',(self.member,)).fetchone()['reason'],'已有记录')
            self.assertEqual(c.execute('SELECT count(*) FROM match_leave_requests').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM match_attendance').fetchone()[0],0)
            self.assertIsNotNone(c.execute("SELECT value FROM app_settings WHERE key='match_leave_enabled_at'").fetchone())

    def test_match_attendance_permissions_and_no_retroactive_punishment(self):
        url=f'/matches/{self.game}/attendance'
        self.assertEqual(self.v.get(url).status_code,403)
        self.assertEqual(self.cap.get(url).status_code,200)
        self.assertEqual(self.post(self.cap,url+f'/{self.member}',attendance='absent').status_code,400)
        past=datetime.datetime.now(ZoneInfo('Asia/Shanghai'))-datetime.timedelta(hours=1)
        with m.db() as c:
            c.execute("UPDATE matches SET date=?,time=?,status='finished',home_score=0,away_score=0 WHERE id=?",(past.date().isoformat(),past.strftime('%H:%M'),self.game))
        self.assertEqual(self.post(self.cap,url+f'/{self.member}',attendance='absent').status_code,400)
        self.assertIn('不追溯',self.cap.get(url).get_data(as_text=True))

    def test_late_leave_after_confirmed_absence_and_reschedule_guard(self):
        start=(datetime.datetime.now(ZoneInfo('Asia/Shanghai'))+datetime.timedelta(hours=1)).replace(second=0,microsecond=0)
        with m.db() as c:c.execute('UPDATE matches SET date=?,time=? WHERE id=?',(start.date().isoformat(),start.strftime('%H:%M'),self.game))
        self.assertEqual(self.post(self.u,f'/account/match-leave/{self.game}',reason='比赛原因').status_code,302)
        with m.db() as c:self.assertEqual(c.execute('SELECT timely FROM match_leave_requests WHERE user_id=?',(self.member,)).fetchone()['timely'],0)
        next_day=start+datetime.timedelta(days=1)
        form=dict(date=next_day.date().isoformat(),time=next_day.strftime('%H:%M'),competition='测试赛',round='',home='岭南学院',away='对手',venue='',status='scheduled',home_score='',away_score='',report='',goals='',assists='')
        self.assertEqual(self.post(self.a,f'/matches/{self.game}/edit',**form).status_code,302)
        with m.db() as c:self.assertNotEqual(c.execute('SELECT date FROM matches WHERE id=?',(self.game,)).fetchone()['date'],form['date'])
        past=datetime.datetime.now(ZoneInfo('Asia/Shanghai'))-datetime.timedelta(hours=1)
        with m.db() as c:
            c.execute("UPDATE app_settings SET value=? WHERE key='match_leave_enabled_at'",((past-datetime.timedelta(days=1)).isoformat(),))
            c.execute("UPDATE matches SET date=?,time=?,status='finished',home_score=0,away_score=0 WHERE id=?",(past.date().isoformat(),past.strftime('%H:%M'),self.game))
        account=self.u.get('/account').get_data(as_text=True)
        self.assertIn('比赛原因',account)
        self.assertNotIn(f'/account/match-leave/{self.game}/cancel',account)
        self.assertEqual(self.post(self.cap,f'/matches/{self.game}/attendance/{self.member}',attendance='absent').status_code,302)
        self.assertIn('旷赛',self.u.get('/account').get_data(as_text=True))
        self.assertEqual(self.post(self.cap,f'/matches/{self.game}/attendance/{self.member}',attendance='attended').status_code,302)
        self.assertIn('已出勤',self.u.get('/account').get_data(as_text=True))


if __name__=='__main__':unittest.main()
