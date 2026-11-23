import io
import os
import tempfile
import unittest

os.environ['TEAM_DATA_DIR']=tempfile.mkdtemp(prefix='matches-test-')
os.environ['TEAM_SECRET']='test-only'
import app as m
from PIL import Image


class MatchCenterTest(unittest.TestCase):
    def setUp(self):
        with m.db() as c:
            c.executescript('DELETE FROM match_reflection_comments; DELETE FROM match_reflection_likes; DELETE FROM match_reflections; DELETE FROM match_ratings; DELETE FROM match_players; DELETE FROM match_managers; DELETE FROM matches WHERE seed_key IS NULL; DELETE FROM users;')
            self.admin=c.execute("INSERT INTO users(name,password,role) VALUES('admin','x','admin')").lastrowid
            self.member=c.execute("INSERT INTO users(name,password,role) VALUES('member','x','member')").lastrowid
            self.other=c.execute("INSERT INTO users(name,password,role) VALUES('other','x','member')").lastrowid
            self.game=c.execute("SELECT id FROM matches WHERE date='2026-11-22' AND home='岭南学院' AND away='数学学院'").fetchone()['id']
        self.a=self.client(self.admin); self.u=self.client(self.member); self.v=self.client(self.other)

    def client(self,uid):
        client=m.app.test_client()
        with client.session_transaction() as s: s.update(uid=uid,version=0,csrf='csrf')
        return client

    def post(self,client,path,**data): return client.post(path,data={'csrf':'csrf',**data})

    def test_schedule_seed_is_idempotent_and_home_uses_schedule(self):
        m.init(); m.init()
        with m.db() as c:
            row=c.execute('SELECT * FROM matches WHERE id=?',(self.game,)).fetchone()
            self.assertEqual((row['status'],row['home_score'],row['away_score']),('finished',0,0))
            first=c.execute("SELECT status,home_score,away_score,report FROM matches WHERE date='2026-11-14'").fetchone()
            self.assertEqual((first['status'],first['home_score'],first['away_score']),('finished',3,0))
            self.assertIn('弃赛',first['report'])
            self.assertEqual(c.execute('SELECT count(*) FROM matches').fetchone()[0],10)
        self.assertEqual(self.u.get('/matches').status_code,200)
        self.assertEqual(self.u.get('/').status_code,200)

    def test_latest_result_is_featured_and_future_fixtures_are_grouped(self):
        with m.db() as c:
            c.execute("INSERT INTO matches(date,time,competition,home,away,status,home_score,away_score) VALUES('2026-11-23','12:00','测试赛','岭南学院','新对手','finished',2,1)")
        html=self.u.get('/matches').get_data(as_text=True)
        self.assertLess(html.index('最近完赛'),html.index('接下来'))
        self.assertIn('新对手',html)
        self.assertIn('历史比赛',html)
        self.assertIn('查看全部赛程',html)

    def test_create_edit_and_scheduled_matches_do_not_allow_reflections(self):
        data=dict(date='2027-06-01',time='15:00',competition='友谊赛',round='',home='岭南学院',away='对手',venue='球场',status='scheduled',home_score='',away_score='',report='',goals='',assists='')
        self.assertEqual(self.post(self.u,'/matches/new',**data).status_code,403)
        self.assertEqual(self.post(self.a,'/matches/new',**data).status_code,302)
        with m.db() as c: game=c.execute("SELECT id FROM matches WHERE competition='友谊赛'").fetchone()['id']
        self.assertEqual(self.post(self.a,f'/matches/{game}/players',name='测试球员',lineup='starter').status_code,302)
        self.assertEqual(self.u.get(f'/matches/{game}/reflections/new').status_code,404)
        data.update(status='finished',home_score='2',away_score='1',report='一场好球')
        self.assertEqual(self.post(self.a,f'/matches/{game}/edit',**data).status_code,302)
        self.assertEqual(self.u.get(f'/matches/{game}/reflections/new').status_code,200)
        m.init()
        self.assertIn('一场好球',self.u.get(f'/matches/{game}').get_data(as_text=True))

    def test_manage_permissions_and_existing_ratings_are_preserved(self):
        path=f'/matches/{self.game}/players'
        self.assertEqual(self.post(self.u,path,name='新球员',lineup='starter').status_code,403)
        self.assertEqual(self.post(self.a,path,name='新球员',lineup='starter').status_code,302)
        with m.db() as c: player=c.execute('SELECT id FROM match_players WHERE match_id=?',(self.game,)).fetchone()['id']
        with m.db() as c:c.execute('INSERT INTO match_ratings(player_id,user_id,score,comment,updated) VALUES(?,?,?,?,?)',(player,self.member,90,'旧评分评论','2026'))
        rating=f'/matches/{self.game}/players/{player}/rate'
        self.assertEqual(self.post(self.u,rating,score='8.5',comment='新评论').status_code,404)
        with m.db() as c:self.assertEqual(c.execute('SELECT comment FROM match_ratings WHERE player_id=?',(player,)).fetchone()['comment'],'旧评分评论')
        page=self.u.get(f'/matches/{self.game}')
        self.assertEqual(page.status_code,200)
        self.assertNotIn('球员评分',page.get_data(as_text=True))
        self.assertNotIn('旧评分评论',page.get_data(as_text=True))
        self.assertIn('发布赛后反思',page.get_data(as_text=True))
        self.assertEqual(self.post(self.a,'/matches/managers',user_id=str(self.member),action='add').status_code,302)
        self.assertEqual(self.post(self.u,path,name='另一位',lineup='substitute').status_code,302)
        self.assertEqual(self.post(self.u,'/matches/managers',user_id=str(self.other),action='add').status_code,403)

    def test_players_show_account_avatar_or_default(self):
        url=f'/matches/{self.game}'
        self.assertEqual(self.post(self.a,url+'/players',user_id=str(self.member),lineup='starter').status_code,302)
        self.assertEqual(self.post(self.a,url+'/players',name='未注册球员',lineup='substitute').status_code,302)
        page=self.u.get(url).get_data(as_text=True)
        self.assertIn(f'src="/avatar/{self.member}"',page)
        self.assertIn('src="/static/avatars/default-1.jpg?',page)
        self.assertEqual(self.u.get(f'/avatar/{self.member}').status_code,302)

    def test_reflection_interactions_accept_async_json_and_image_size(self):
        image=io.BytesIO(); Image.new('RGB',(40,30),'red').save(image,'PNG'); image.seek(0)
        self.assertEqual(self.u.post(f'/matches/{self.game}/reflections',data={'csrf':'csrf','content':'异步反思','image':(image,'x.png')}).status_code,302)
        with m.db() as c: row=c.execute('SELECT id,image_w,image_h FROM match_reflections').fetchone()
        self.assertEqual((row['image_w'],row['image_h']),(40,30))
        rid=row['id']
        self.assertEqual(self.v.get(f'/matches/reflections/{rid}/image?thumb=1').status_code,200)
        like=self.v.post(f'/matches/{self.game}/reflections/{rid}/like',data={'csrf':'csrf'},headers={'X-Requested-With':'fetch'})
        self.assertEqual(like.status_code,200)
        self.assertEqual((like.get_json()['liked'],like.get_json()['likes']),(True,1))
        self.assertEqual(like.get_json()['label'],'取消赞 · 1')
        comment=self.v.post(f'/matches/{self.game}/reflections/{rid}/comment',data={'csrf':'csrf','content':'异步评论'},headers={'X-Requested-With':'fetch'})
        self.assertEqual(comment.status_code,200)
        self.assertIn('异步评论',comment.get_json()['html'])
        page=self.v.get(f'/matches/{self.game}').get_data(as_text=True)
        self.assertIn('异步评论',page)
        self.assertIn('data-remote="like"',page)
        self.assertIn('width="40" height="30"',page)

    def test_reflection_image_like_comments_and_ownership(self):
        image=io.BytesIO(); Image.new('RGB',(5,5),'red').save(image,'PNG'); image.seek(0)
        response=self.u.post(f'/matches/{self.game}/reflections',data={'csrf':'csrf','content':'比赛反思','image':(image,'x.png')})
        self.assertEqual(response.status_code,302)
        self.assertTrue(response.headers['Location'].endswith('#reflections'))
        with m.db() as c: rid=c.execute('SELECT id FROM match_reflections').fetchone()['id']
        self.assertEqual(self.v.get(f'/matches/reflections/{rid}/image').status_code,200)
        base=f'/matches/{self.game}/reflections/{rid}'
        self.assertEqual(self.post(self.v,base+'/like').status_code,302)
        self.assertEqual(self.post(self.v,base+'/comment',content='加油').status_code,302)
        self.assertEqual(self.post(self.v,base+'/edit',content='越权').status_code,403)
        self.assertEqual(self.post(self.u,base+'/edit',content='更新反思').status_code,302)
        self.assertEqual(self.v.get(f'/matches/{self.game}').status_code,200)
        self.assertEqual(self.post(self.a,base+'/delete').status_code,302)
        with m.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM match_reflection_comments').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM match_reflection_likes').fetchone()[0],0)


if __name__=='__main__': unittest.main()
