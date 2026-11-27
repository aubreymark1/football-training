import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ['TEAM_DATA_DIR'] = tempfile.mkdtemp(prefix='team-plan-tests-')
os.environ['TEAM_SECRET'] = 'test-only'
os.environ.pop('TEAM_HTTPS', None)
import app as m
import team_plans


class TeamPlanTests(unittest.TestCase):
    def setUp(self):
        self.plans_flag = patch.dict(os.environ, {'TEAM_PLANS_ENABLED': '1'})
        self.plans_flag.start()
        self.addCleanup(self.plans_flag.stop)
        self.temp = tempfile.TemporaryDirectory(prefix='team-plan-db-')
        self.old_db = m.DB
        m.DB = Path(self.temp.name) / 'test.sqlite3'
        m.init()
        with m.db() as c:
            c.execute("INSERT INTO users(name,password,role) VALUES('admin','unused','admin')")
            c.execute("INSERT INTO users(name,password,role,is_captain,email,email_verified) VALUES('captain','unused','member',1,'captain@example.org',1)")
            c.execute("INSERT INTO users(name,password,role) VALUES('member','unused','member')")
            c.execute("INSERT INTO users(name,password,role,is_captain) VALUES('captain2','unused','member',1)")
            c.execute("INSERT INTO tasks(title,detail,week,kind) VALUES('现有任务','',?,'required')", (m.week(),))
            ids = {r['name']: r['id'] for r in c.execute('SELECT id,name FROM users')}
        self.admin = self.client(ids['admin'])
        self.captain = self.client(ids['captain'])
        self.captain2 = self.client(ids['captain2'])
        self.member = self.client(ids['member'])
        self.ids = ids

    def tearDown(self):
        m.DB = self.old_db
        self.temp.cleanup()

    def client(self, uid):
        client = m.app.test_client()
        with client.session_transaction() as session:
            session['uid'] = uid
            session['version'] = 0
            session['csrf'] = 'csrf'
        return client

    def post(self, client, url, **values):
        return client.post(url, data={'csrf': 'csrf', **values})

    def create(self):
        response = self.post(self.captain, '/plans/new', week='2026-11-16')
        self.assertEqual(response.status_code, 302)
        with m.db() as c:
            return c.execute('SELECT id FROM team_training_plans').fetchone()[0]

    def sample(self):
        board = {'players': [{'id': 'p1', 'type': 'home', 'label': '1'}, {'id': 'b1', 'type': 'ball', 'label': ''}],
                 'frames': [{'label': '起始', 'duration': 2, 'positions': {'p1': [20, 40], 'b1': [22, 40]}},
                            {'label': '传球', 'duration': 3, 'positions': {'p1': [40, 40], 'b1': [70, 40]}}]}
        return {'title': '传接配合', 'schedule': '周三 19:30', 'location': '球场', 'overview': '练习出球',
                'items': [{'id': 'i1', 'title': '二人传球', 'kind': 'ball', 'goal': '改善接球', 'minutes': 20,
                           'steps': '两人传接\n换位', 'board': board}],
                'videos': [{'title': '训练视频', 'url': 'https://www.youtube.com/watch?v=example', 'source': 'fake'}],
                'chat': [{'role': 'user', 'content': '队长的私人讨论'}]}

    def save(self, client, ident, data, revision=0, action='save'):
        return self.post(client, f'/plans/{ident}/save', plan=json.dumps(data, ensure_ascii=False), revision=str(revision), action=action)

    def test_captain_grant_is_separate_from_admin_and_reminders(self):
        uid = self.ids['member']
        self.assertEqual(self.post(self.member, f'/admin/member/{uid}/captain', captain='1').status_code, 403)
        self.assertEqual(self.post(self.admin, f'/admin/member/{uid}/captain', captain='1').status_code, 302)
        self.assertEqual(self.member.get('/plans').status_code, 200)
        self.assertEqual(self.member.get('/admin').status_code, 403)
        with m.db() as c:
            user = c.execute('SELECT role,is_captain FROM users WHERE id=?', (uid,)).fetchone()
            reminders = m.reminder_candidates(c, m.week())
        self.assertEqual((user['role'], user['is_captain']), ('member', 1))
        self.assertIn(self.ids['captain'], [r['id'] for r in reminders])
        self.assertEqual(self.post(self.admin, f'/admin/member/{uid}/captain', captain='0').status_code, 302)
        self.assertEqual(self.post(self.member, '/plans/new', week='2026-11-16').status_code, 403)

    def test_draft_publication_snapshot_permissions_and_conflict(self):
        ident = self.create()
        self.assertEqual(self.member.get(f'/plans/{ident}').status_code, 404)
        self.assertNotIn('2026-11-16', self.member.get('/plans').get_data(as_text=True))
        self.assertNotIn('2026-11-16', self.member.get('/training-sessions').get_data(as_text=True))
        self.assertEqual(self.member.get(f'/plans/{ident}/edit').status_code, 403)
        self.assertEqual(self.save(self.member, ident, self.sample()).status_code, 403)
        self.assertEqual(self.save(self.captain, ident, self.sample(), action='publish').status_code, 200)
        hub = self.member.get('/training-sessions').get_data(as_text=True)
        self.assertIn('训练安排与出勤', hub)
        self.assertIn(f'href="/plans/{ident}"', hub)
        self.assertNotIn(f'href="/plans/{ident}/edit"', hub)
        published = self.member.get(f'/plans/{ident}').get_data(as_text=True)
        self.assertIn('二人传球', published)
        self.assertNotIn('私人讨论', published)
        self.assertIn('www.youtube.com', published)
        updated = self.sample(); updated['items'][0]['title'] = '新版项目'
        self.assertEqual(self.save(self.captain, ident, updated, revision=1).status_code, 200)
        self.assertIn('二人传球', self.member.get(f'/plans/{ident}').get_data(as_text=True))
        self.assertEqual(self.save(self.captain2, ident, self.sample(), revision=1).status_code, 409)
        self.assertEqual(self.save(self.captain2, ident, updated, revision=2, action='publish').status_code, 200)
        self.assertIn('新版项目', self.member.get(f'/plans/{ident}').get_data(as_text=True))
        with m.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM tasks').fetchone()[0], 1)
            self.assertEqual(c.execute('SELECT count(*) FROM records').fetchone()[0], 0)

    def test_board_and_video_validation(self):
        ident = self.create(); data = self.sample()
        data['items'][0]['board']['frames'].reverse()
        data['items'][0]['board']['frames'][0]['positions']['p1'] = [17, 83]
        response = self.save(self.captain, ident, data)
        self.assertEqual(response.status_code, 200)
        with m.db() as c:
            saved = json.loads(c.execute('SELECT draft FROM team_training_plans WHERE id=?', (ident,)).fetchone()[0])
        self.assertEqual(saved['items'][0]['board']['frames'][0]['positions']['p1'], [17, 83])
        self.assertEqual(saved['items'][0]['board']['frames'][0]['label'], '传球')
        self.assertEqual(saved['videos'][0]['source'], 'www.youtube.com')
        data['items'][0]['board']['frames'][0]['positions']['p1'] = [101, 4]
        self.assertEqual(self.save(self.captain, ident, data, revision=1).status_code, 400)
        data = self.sample(); data['videos'][0]['url'] = 'javascript:alert(1)'
        self.assertEqual(self.save(self.captain, ident, data, revision=1).status_code, 400)
        data = self.sample(); data['items'][0]['goal'] = ''
        self.assertEqual(self.save(self.captain, ident, data, revision=1, action='publish').status_code, 200)

    def test_library_imports_existing_plans_and_preserves_draft(self):
        ident = self.create()
        data = self.sample()
        published = self.sample()
        published['items'][0]['title'] = '历史传球'
        raw = json.dumps(data, ensure_ascii=False)
        with m.db() as c:
            c.execute('UPDATE team_training_plans SET draft=?,published=? WHERE id=?',
                      (raw, json.dumps(published, ensure_ascii=False), ident))
        self.assertEqual(self.member.get('/plans/library').status_code, 403)
        result = self.captain.get('/plans/library').get_json()['items']
        self.assertEqual({x['title'] for x in result}, {'历史传球', '二人传球'})
        self.assertTrue(result[0]['has_board'])
        self.assertNotIn('board', result[0])
        self.assertEqual(self.captain.get('/plans/library/%s' % result[0]['library_id']).get_json()['item']['board']['players'][0]['id'], 'p1')
        self.assertEqual(self.member.get('/plans/library/%s' % result[0]['library_id']).status_code, 403)
        self.assertEqual(len(self.admin.get('/plans/library?q=历史').get_json()['items']), 1)
        self.assertEqual(len(self.captain.get('/plans/library').get_json()['items']), 2)
        with m.db() as c:
            self.assertEqual(c.execute('SELECT draft,revision FROM team_training_plans WHERE id=?', (ident,)).fetchone()[:], (raw, 0))

    def test_library_collects_saves_deduplicates_and_ignores_conflicts(self):
        ident = self.create(); data = self.sample()
        empty = {'id':'empty','title':'','kind':'other','goal':'','minutes':0,'steps':'','board':None}
        data['items'].append(empty)
        self.assertEqual(self.save(self.captain, ident, data).status_code, 200)
        self.assertEqual(self.save(self.captain, ident, data, revision=1).status_code, 200)
        library = self.captain.get('/plans/library').get_json()['items']
        self.assertEqual(len(library), 1)
        self.assertNotIn('id', library[0])
        self.assertEqual(self.captain.get('/plans/library/%s' % library[0]['library_id']).get_json()['item']['board']['frames'][1]['positions']['b1'], [70, 40])
        modified = self.sample(); modified['items'][0]['title'] = '新增但冲突'
        self.assertEqual(self.save(self.captain2, ident, modified, revision=1).status_code, 409)
        self.assertEqual(len(self.captain.get('/plans/library?q=新增但冲突').get_json()['items']), 0)
        self.assertEqual(self.save(self.captain, ident, modified, revision=2, action='publish').status_code, 200)
        self.assertEqual(len(self.captain.get('/plans/library').get_json()['items']), 2)

    def test_publish_optional_fields_without_touching_permissions_or_validation(self):
        ident = self.create()
        data = self.sample()
        data.update(title='', schedule='', location='', overview='', videos=[])
        data['items'][0].update(title='', goal='', minutes=0, steps='')
        self.assertEqual(self.save(self.member, ident, data, action='publish').status_code, 403)
        self.assertEqual(self.save(self.captain, ident, data, action='publish').status_code, 200)
        html = self.member.get(f'/plans/{ident}').get_data(as_text=True)
        self.assertIn('未命名计划', html)
        self.assertIn('未命名项目', html)
        self.assertNotIn('0 分钟', html)
        self.assertNotIn('<strong>目标：</strong>', html)
        self.assertIn('board-data', html)
        self.assertEqual(self.save(self.captain2, ident, data, revision=0, action='publish').status_code, 409)
        data['items'] = []
        self.assertEqual(self.save(self.captain, ident, data, revision=1, action='publish').status_code, 200)
        self.assertIn('暂无训练项目', self.member.get(f'/plans/{ident}').get_data(as_text=True))
        data['items'] = [{'id':'x', 'minutes':-1}]
        self.assertEqual(self.save(self.captain, ident, data, revision=2, action='publish').status_code, 400)

    @unittest.skip('训练计划 AI 助手已下线')
    def test_ai_questions_text_only_and_automatic_search(self):
        ident = self.create()
        with patch('app.ai_call', return_value=json.dumps({'reply': '有多少人参加？', 'draft': None}, ensure_ascii=False)), patch('app.search_web') as search:
            response = self.post(self.captain, f'/plans/{ident}/ai', message='想练传接球', history='[]')
            self.assertEqual(response.get_json()['reply'], '有多少人参加？')
            self.assertEqual(response.get_json()['search'], 'skipped'); search.assert_not_called()
        draft = self.sample(); draft['videos'] = []; draft['chat'] = []
        video = {'title': '足球传球教学', 'url': 'https://www.youtube.com/watch?v=abc', 'source': 'YouTube'}
        with patch('app.ai_call', return_value=json.dumps({'reply': '请核对草稿。', 'draft': draft}, ensure_ascii=False)) as model, patch('app.search_web', return_value=[video]) as search:
            response = self.post(self.captain, f'/plans/{ident}/ai', message='12 人，60 分钟，场地可用', history='[]', draft_context=json.dumps(draft, ensure_ascii=False))
            result = response.get_json(); self.assertEqual(response.status_code, 200)
            self.assertEqual(result['draft']['items'][0]['board']['frames'][1]['positions']['p1'], [40, 40])
            self.assertIn('二人传球', model.call_args.args[0][-1]['content'])
            self.assertNotIn('positions', model.call_args.args[0][-1]['content'])
            self.assertEqual(result['videos'][0]['source'], 'www.youtube.com')
            self.assertEqual(search.call_args.args[1], 'video')
            self.assertNotIn('12 人', search.call_args.args[0])
        with m.db() as c:
            self.assertIsNone(c.execute('SELECT published FROM team_training_plans WHERE id=?', (ident,)).fetchone()[0])
        draft['items'][0]['board'] = None
        with patch('app.ai_call', return_value=json.dumps({'reply': '草稿', 'draft': draft}, ensure_ascii=False)):
            self.assertEqual(self.post(self.captain, f'/plans/{ident}/ai', message='继续', history='[]').status_code, 200)
        draft = self.sample()
        draft['items'][0]['board']['frames'][1]['positions'] = draft['items'][0]['board']['frames'][0]['positions'].copy()
        with patch('app.ai_call', return_value=json.dumps({'reply': '草稿', 'draft': draft}, ensure_ascii=False)):
            self.assertIsNone(self.post(self.captain, f'/plans/{ident}/ai', message='继续', history='[]').get_json()['draft']['items'][0]['board'])
        self.assertEqual(self.post(self.member, f'/plans/{ident}/ai', message='继续', history='[]').status_code, 403)
        self.assertEqual(self.captain.post(f'/plans/{ident}/ai', data={'message': '继续'}).status_code, 400)

    def test_search_failure_is_reported_and_no_leaked_free_text(self):
        ident = self.create()
        items = [{'title': '传球 甲队员膝盖疼', 'goal': '希望恢复'}]
        with patch('app.search_web', side_effect=RuntimeError('unavailable')) as search:
            response = self.post(self.captain, f'/plans/{ident}/videos', items=json.dumps(items, ensure_ascii=False))
        self.assertEqual(response.get_json()['search'], 'error')
        self.assertNotIn('甲队员', search.call_args.args[0])
        self.assertNotIn('膝盖', search.call_args.args[0])

    def test_team_plan_requests_cannot_become_checkin_task_actions(self):
        with patch('app.ai_call') as model:
            result = self.post(self.admin, '/assistant/prepare', message='请发布这周球队训练计划')
        self.assertEqual(result.status_code, 404)
        model.assert_not_called()
        with m.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM tasks').fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
