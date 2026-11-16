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

    def test_new_member_has_no_pre_membership_debt(self):
        prev=(dt.date.fromisoformat(m.week())-dt.timedelta(days=7)).isoformat()
        with m.db() as c:
            c.execute("INSERT INTO tasks(title,detail,week,kind) VALUES('旧任务','',?,'required')",(prev,))
        member=m.app.test_client(); self.join_member(member,'newcomer')
        member.get('/')
        with m.db() as c:
            uid=c.execute("SELECT id FROM users WHERE name='newcomer'").fetchone()[0]
            self.assertEqual(c.execute('SELECT coalesce(sum(amount),0) FROM ledger WHERE user_id=?',(uid,)).fetchone()[0],0)
            c.execute("INSERT INTO tasks(title,detail,week,kind) VALUES('入队当周任务','',?,'required')",(m.week(),))
        next_week=(dt.date.fromisoformat(m.week())+dt.timedelta(days=7)).isoformat()
        with patch('app.week',return_value=next_week):member.get('/')
        with m.db() as c:
            self.assertEqual(c.execute('SELECT sum(amount) FROM ledger WHERE user_id=?',(uid,)).fetchone()[0],-10)
            self.assertEqual(c.execute('SELECT count(*) FROM ledger WHERE user_id=?',(uid,)).fetchone()[0],1)

    def test_legacy_member_is_not_charged_for_unknown_old_weeks(self):
        prev=(dt.date.fromisoformat(m.week())-dt.timedelta(days=7)).isoformat()
        with m.db() as c:
            uid=c.execute("SELECT id FROM users WHERE name='coach'").fetchone()[0]
            c.execute("INSERT INTO tasks(title,detail,week,kind) VALUES('旧任务','',?,'required')",(prev,))
        m.settle_required_penalties()
        with m.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM ledger WHERE user_id=?',(uid,)).fetchone()[0],0)

    def test_admin_confirmed_join_date_corrects_old_penalty_without_double_refund(self):
        member=m.app.test_client();self.join_member(member);self.login('coach')
        prev=(dt.date.fromisoformat(m.week())-dt.timedelta(days=7)).isoformat()
        with m.db() as c:
            uid=c.execute("SELECT id FROM users WHERE name='player'").fetchone()[0]
            c.execute('UPDATE users SET joined_week=NULL WHERE id=?',(uid,))
            c.execute('INSERT INTO ledger(user_id,amount,note,created) VALUES(?,?,?,?)',(uid,-10,prev+' 周未完成必做任务',m.now()))
        for _ in range(2): self.post('/admin/member/%d/joined-week'%uid,{'joined_date':m.week()})
        with m.db() as c:self.assertEqual(c.execute('SELECT sum(amount) FROM ledger WHERE user_id=?',(uid,)).fetchone()[0],0)
        self.post('/admin/member/%d/joined-week'%uid,{'joined_date':prev})
        with m.db() as c:self.assertEqual(c.execute('SELECT sum(amount) FROM ledger WHERE user_id=?',(uid,)).fetchone()[0],-10)
