import datetime
import os
import tempfile
import unittest
from zoneinfo import ZoneInfo

from training_leave import leave_deadline, submitted_on_time

os.environ['TEAM_DATA_DIR']=tempfile.mkdtemp(prefix='training-leave-test-')
os.environ['TEAM_SECRET']='test-only'
import app as m


class TrainingLeaveDeadlineTests(unittest.TestCase):
    def test_deadline_is_inclusive_at_exactly_72_hours(self):
        start=datetime.datetime(2026,11,29,15,tzinfo=ZoneInfo('Asia/Shanghai'))
        deadline=datetime.datetime(2026,11,26,15,tzinfo=ZoneInfo('Asia/Shanghai'))
        self.assertEqual(leave_deadline(start),deadline)
        self.assertTrue(submitted_on_time(start,deadline))
        self.assertFalse(submitted_on_time(start,deadline+datetime.timedelta(seconds=1)))
        self.assertTrue(submitted_on_time(start,deadline-datetime.timedelta(seconds=1)))

    def test_naive_datetimes_are_rejected(self):
        start=datetime.datetime(2026,11,29,15)
        with self.assertRaises(ValueError): leave_deadline(start)
        with self.assertRaises(ValueError): submitted_on_time(start.replace(tzinfo=datetime.timezone.utc),start)


class TrainingLeaveFlowTests(unittest.TestCase):
    def setUp(self):
        with m.db() as c:
            c.executescript('DELETE FROM training_attendance; DELETE FROM training_leave_requests; DELETE FROM training_sessions; DELETE FROM users;')
            self.admin=c.execute("INSERT INTO users(name,password,role) VALUES('admin','x','admin')").lastrowid
            self.captain=c.execute("INSERT INTO users(name,password,role,is_captain) VALUES('captain','x','member',1)").lastrowid
            self.player=c.execute("INSERT INTO users(name,password,role) VALUES('player','x','member')").lastrowid
            self.other=c.execute("INSERT INTO users(name,password,role) VALUES('other','x','member')").lastrowid
        self.a=self.client(self.admin);self.cap=self.client(self.captain);self.p=self.client(self.player);self.o=self.client(self.other)

    def client(self,uid):
        client=m.app.test_client()
        with client.session_transaction() as s:s.update(uid=uid,version=0,csrf='csrf')
        return client

    def post(self,client,path,**data):return client.post(path,data={'csrf':'csrf',**data})

    def create(self,hours):
        start=(datetime.datetime.now(ZoneInfo('Asia/Shanghai'))+datetime.timedelta(hours=hours)).replace(second=0,microsecond=0)
        end=start+datetime.timedelta(hours=2)
        data=dict(title='周末合练',starts_at=start.strftime('%Y-%m-%dT%H:%M'),ends_at=end.strftime('%Y-%m-%dT%H:%M'),location='球场')
        self.assertEqual(self.post(self.p,'/training-sessions/new',**data).status_code,403)
        result=self.post(self.cap,'/training-sessions/new',**data)
        self.assertEqual(result.status_code,302)
        with m.db() as c:ident=c.execute('SELECT id FROM training_sessions ORDER BY id DESC').fetchone()['id']
        return ident,data

    def test_leave_privacy_and_captain_views(self):
        ident,_=self.create(100);url=f'/training-sessions/{ident}'
        self.assertEqual(self.post(self.p,url+'/leave',reason='私人原因').status_code,302)
        self.assertIn('href="/leave"',self.p.get('/account').get_data(as_text=True))
        self.assertIn('按时请假',self.p.get('/leave').get_data(as_text=True))
        self.assertIn('私人原因',self.cap.get(url).get_data(as_text=True))
        other=self.o.get(url).get_data(as_text=True)
        self.assertNotIn('私人原因',other);self.assertNotIn('player',other)
        self.assertEqual(self.post(self.o,url+f'/attendance/{self.player}',attendance='absent').status_code,403)
        self.assertEqual(self.post(self.cap,url+f'/attendance/{self.player}',attendance='absent').status_code,400)
        self.assertEqual(self.p.get('/training-sessions').status_code,200)

    def test_late_leave_is_absence_only_after_captain_confirmation(self):
        ident,_=self.create(2);url=f'/training-sessions/{ident}'
        self.assertEqual(self.post(self.p,url+'/leave',reason='身体不适').status_code,302)
        before=self.p.get('/leave').get_data(as_text=True)
        self.assertIn('逾期请假',before);self.assertNotIn('队长确认：',before)
        past=(datetime.datetime.now(ZoneInfo('Asia/Shanghai'))-datetime.timedelta(hours=1)).isoformat(timespec='seconds')
        with m.db() as c:c.execute('UPDATE training_sessions SET ends_at=? WHERE id=?',(past,ident))
        self.assertEqual(self.post(self.cap,url+f'/attendance/{self.player}',attendance='absent').status_code,302)
        self.assertIn('旷训',self.p.get('/leave').get_data(as_text=True))
        self.assertEqual(self.post(self.cap,url+f'/attendance/{self.player}',attendance='attended').status_code,302)
        self.assertIn('已出勤',self.p.get('/leave').get_data(as_text=True))

    def test_timely_leave_and_unannounced_absence_are_distinct(self):
        ident,_=self.create(100);url=f'/training-sessions/{ident}'
        self.post(self.p,url+'/leave',reason='个人安排')
        past=(datetime.datetime.now(ZoneInfo('Asia/Shanghai'))-datetime.timedelta(hours=1)).isoformat(timespec='seconds')
        with m.db() as c:c.execute('UPDATE training_sessions SET ends_at=? WHERE id=?',(past,ident))
        self.post(self.cap,url+f'/attendance/{self.player}',attendance='absent')
        self.post(self.cap,url+f'/attendance/{self.other}',attendance='absent')
        self.assertIn('请假缺席',self.p.get('/leave').get_data(as_text=True))
        self.assertIn('旷训',self.cap.get(url).get_data(as_text=True))
        m.init()
        with m.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM training_attendance').fetchone()[0],2)

    def test_change_reason_preserves_submission_and_resubmission_recalculates(self):
        ident,data=self.create(100);url=f'/training-sessions/{ident}'
        self.post(self.p,url+'/leave',reason='原因一')
        with m.db() as c:original=dict(c.execute('SELECT * FROM training_leave_requests').fetchone())
        self.post(self.p,url+'/leave',reason='原因二')
        with m.db() as c:updated=dict(c.execute('SELECT * FROM training_leave_requests').fetchone())
        self.assertEqual(original['submitted_at'],updated['submitted_at']);self.assertEqual(updated['timely'],1)
        later=(datetime.datetime.now(ZoneInfo('Asia/Shanghai'))+datetime.timedelta(hours=1)).replace(second=0,microsecond=0)
        data['starts_at']=later.strftime('%Y-%m-%dT%H:%M');data['ends_at']=(later+datetime.timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M')
        self.assertEqual(self.post(self.cap,url+'/edit',**data).status_code,302)
        with m.db() as c:self.assertNotEqual(c.execute('SELECT starts_at FROM training_sessions').fetchone()['starts_at'][:16],data['starts_at'])
        self.post(self.p,url+'/leave/cancel')
        self.assertEqual(self.post(self.cap,url+'/edit',**data).status_code,302)
        self.post(self.p,url+'/leave',reason='重新请假')
        with m.db() as c:self.assertEqual(c.execute('SELECT timely FROM training_leave_requests').fetchone()['timely'],0)


if __name__=='__main__': unittest.main()
