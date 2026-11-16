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

    def test_actual_award_and_cap_are_visible_per_record(self):
        member=m.app.test_client();self.join_member(member);self.login('coach')
        with m.db() as c:
            uid=c.execute("SELECT id FROM users WHERE name='player'").fetchone()[0]
            tid=c.execute("INSERT INTO tasks(title,detail,week,kind,points,cap) VALUES('核心','',?,'bonus',5,1)",(m.week(),)).lastrowid
            ids=[c.execute("INSERT INTO records(user_id,task_id,sport,minutes,effort,note,image,created) VALUES(?,?,'核心',15,5,'','x.jpg',?)",(uid,tid,m.now())).lastrowid for _ in range(2)]
        for rid in ids:self.post('/admin/review/'+str(rid),{'action':'approved'})
        with m.db() as c:c.execute('UPDATE tasks SET points=99 WHERE id=?',(tid,))
        for path in ('/','/history'):
            page=member.get(path).get_data(as_text=True)
            self.assertIn('本次 +5 分',page)
            self.assertIn('本次 +0 分 · 本周计分次数已满',page)
            self.assertNotIn('本次 +99 分',page)
