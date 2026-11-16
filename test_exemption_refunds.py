import unittest, io, datetime as dt, json
from unittest.mock import patch
from PIL import Image
import test_app as base
m=base.m

class Regression(unittest.TestCase):
    setUp=base.Flow.setUp
    csrf=base.Flow.csrf
    post=base.Flow.post
    login=base.Flow.login
    join_member=base.Flow.join_member

    def test_refund_only_when_all_required_tasks_resolved_and_only_once(self):
        member=m.app.test_client();self.join_member(member);self.login('coach')
        prev=(dt.date.fromisoformat(m.week())-dt.timedelta(days=7)).isoformat()
        with m.db() as c:
            uid=c.execute("SELECT id FROM users WHERE name='player'").fetchone()[0]
            if 'joined_week' in {r['name'] for r in c.execute('PRAGMA table_info(users)')}:
                c.execute('UPDATE users SET joined_week=? WHERE id=?',(prev,uid))
            ids=[c.execute("INSERT INTO tasks(title,detail,week,kind) VALUES(?,'',?,'required')",(name,prev)).lastrowid for name in ('跑步','力量')]
        member.get('/')
        with m.db() as c:self.assertEqual(c.execute('SELECT sum(amount) FROM ledger WHERE user_id=?',(uid,)).fetchone()[0],-10)
        self.post('/admin/exempt',{'user_id':str(uid),'task_id':str(ids[0])})
        with m.db() as c:self.assertEqual(c.execute('SELECT sum(amount) FROM ledger WHERE user_id=?',(uid,)).fetchone()[0],-10)
        for _ in range(2):self.post('/admin/exempt',{'user_id':str(uid),'task_id':str(ids[1])})
        member.get('/')
        with m.db() as c:
            amounts=[r[0] for r in c.execute('SELECT amount FROM ledger WHERE user_id=? ORDER BY id',(uid,))]
            self.assertEqual(amounts,[-10,10])

    def test_exemption_without_a_penalty_does_not_award_points(self):
        member=m.app.test_client();self.join_member(member);self.login('coach')
        with m.db() as c:
            uid=c.execute("SELECT id FROM users WHERE name='player'").fetchone()[0]
            tid=c.execute("INSERT INTO tasks(title,detail,week,kind) VALUES('跑步','',?,'required')",(m.week(),)).lastrowid
        self.post('/admin/exempt',{'user_id':str(uid),'task_id':str(tid)})
        with m.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM ledger WHERE user_id=?',(uid,)).fetchone()[0],0)

    def test_later_approval_completes_an_exempt_week_and_refunds_once(self):
        member=m.app.test_client();self.join_member(member);self.login('coach')
        prev=(dt.date.fromisoformat(m.week())-dt.timedelta(days=7)).isoformat()
        with m.db() as c:
            uid=c.execute("SELECT id FROM users WHERE name='player'").fetchone()[0]
            if 'joined_week' in {r['name'] for r in c.execute('PRAGMA table_info(users)')}:
                c.execute('UPDATE users SET joined_week=? WHERE id=?',(prev,uid))
            first=c.execute("INSERT INTO tasks(title,detail,week,kind) VALUES('跑步','',?,'required')",(prev,)).lastrowid
            second=c.execute("INSERT INTO tasks(title,detail,week,kind) VALUES('力量','',?,'required')",(prev,)).lastrowid
            rid=c.execute("INSERT INTO records(user_id,task_id,sport,minutes,effort,note,image,created) VALUES(?,?,'力量',15,5,'','x.jpg',?)",(uid,second,m.now())).lastrowid
        member.get('/')
        self.post('/admin/exempt',{'user_id':str(uid),'task_id':str(first)})
        self.post('/admin/review/'+str(rid),{'action':'approved'})
        member.get('/');member.get('/')
        with m.db() as c:self.assertEqual([r[0] for r in c.execute('SELECT amount FROM ledger WHERE user_id=? ORDER BY id',(uid,))],[-10,10])
