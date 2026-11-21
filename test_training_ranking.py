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

    def test_redemption_and_refund_change_balance_but_not_standings(self):
        member=m.app.test_client();self.join_member(member);self.login('coach')
        with m.db() as c:
            uid=c.execute("SELECT id FROM users WHERE name='player'").fetchone()[0]
            c.execute("INSERT INTO ledger(user_id,amount,note,created) VALUES(?,30,'训练得分',?)",(uid,m.now()))
            reward=c.execute("INSERT INTO rewards(name,cost,stock) VALUES('球袜',20,1)").lastrowid
        self.post('/redeem/'+str(reward),{},member)
        rows,_,_=m.team_standings();self.assertEqual(next(r['points'] for r in rows if r['id']==uid),30)
        with m.db() as c:
            self.assertEqual(c.execute('SELECT sum(amount) FROM ledger WHERE user_id=?',(uid,)).fetchone()[0],10)
            oid=c.execute('SELECT id FROM redemptions').fetchone()[0]
        self.post('/cancel/'+str(oid),{},member)
        rows,_,_=m.team_standings();self.assertEqual(next(r['points'] for r in rows if r['id']==uid),30)
        with m.db() as c:self.assertEqual(c.execute('SELECT sum(amount) FROM ledger WHERE user_id=?',(uid,)).fetchone()[0],30)

    def test_exemption_counts_in_display_without_changing_ranking(self):
        with m.db() as c:
            uid=c.execute("SELECT id FROM users WHERE name='coach'").fetchone()[0]
            task=c.execute("INSERT INTO tasks(title,detail,week,kind) VALUES('跑步','',?,'required')",(m.week(),)).lastrowid
            c.execute('INSERT INTO exemptions(user_id,task_id) VALUES(?,?)',(uid,task))
        rows,total,_=m.team_standings(); row=next(r for r in rows if r['id']==uid)
        self.assertEqual((row['done'],row['required_met'],total),(0,1,1))
        with m.db() as c:
            c.execute("INSERT INTO records(user_id,task_id,sport,minutes,effort,note,image,created,status) VALUES(?,?,'跑步',10,1,'','',?,'approved')",(uid,task,m.now()))
        rows,total,_=m.team_standings(); row=next(r for r in rows if r['id']==uid)
        self.assertEqual((row['done'],row['required_met'],total),(1,1,1))
        with m.db() as c: c.execute('UPDATE tasks SET deleted=1 WHERE id=?',(task,))
        rows,total,_=m.team_standings(); row=next(r for r in rows if r['id']==uid)
        self.assertEqual((row['required_met'],total),(0,0))

    def test_existing_redemption_entries_are_classified_on_upgrade(self):
        with m.db() as c:
            uid=c.execute("SELECT id FROM users WHERE name='coach'").fetchone()[0]
            if 'category' in {r['name'] for r in c.execute('PRAGMA table_info(ledger)')}:
                c.execute('ALTER TABLE ledger DROP COLUMN category')
            for amount,note in [(30,'训练得分'),(-20,'兑换 球袜'),(20,'兑换退回'),(-10,'兑换 护腿板')]:
                c.execute('INSERT INTO ledger(user_id,amount,note,created) VALUES(?,?,?,?)',(uid,amount,note,m.now()))
        m.init();m.init()
        rows,_,_=m.team_standings();self.assertEqual(rows[0]['points'],30)
        with m.db() as c:self.assertEqual(c.execute('SELECT sum(amount) FROM ledger WHERE user_id=?',(uid,)).fetchone()[0],20)
