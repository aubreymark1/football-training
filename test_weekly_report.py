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

    def test_free_training_is_grouped_by_full_week(self):
        member=m.app.test_client();self.join_member(member);self.login('coach')
        monday=dt.date.fromisoformat(m.week())
        with m.db() as c:
            uid=c.execute("SELECT id FROM users WHERE name='player'").fetchone()[0]
            for days,sport in [(-1,'上周日'),(1,'周二'),(6,'周日'),(7,'下周一')]:
                created=(monday+dt.timedelta(days=days)).isoformat()+'T18:00:00+08:00'
                c.execute("INSERT INTO records(user_id,sport,minutes,effort,note,image,created,status) VALUES(?,?,30,5,'','x.jpg',?,'approved')",(uid,sport,created))
        with patch('app.ai_call',return_value='周分析') as ai:
            self.post('/admin/report/'+str(uid),{'week':m.week()})
            self.assertTrue(ai.called)
            payload=json.loads(ai.call_args.args[0][1]['content'])
            self.assertEqual({r['sport'] for r in payload['records']},{'周二','周日'})
