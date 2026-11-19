import json
from unittest.mock import patch
from test_team_plans import TeamPlanTests


class RemovalTests(TeamPlanTests):
    def test_disabled_routes_and_retained_plan_tools(self):
        ident = self.create()
        for client in (self.captain, self.member, self.admin):
            self.assertEqual(client.get('/assistant').status_code, 404)
            self.assertEqual(client.get('/assistant/threads').status_code, 404)
            for path in ('/assistant/message', '/assistant/prepare', '/assistant/execute',
                         '/assistant/threads', '/assistant/threads/test/delete',
                         f'/plans/{ident}/ai', f'/plans/{ident}/board-agent'):
                self.assertEqual(self.post(client, path).status_code, 404, path)
            self.assertNotIn('guide-nav-assistant', client.get('/').get_data(as_text=True))
        edit = self.captain.get(f'/plans/{ident}/edit').get_data(as_text=True)
        self.assertNotIn('ai-panel', edit)
        self.assertNotIn('data-ai=', edit)
        self.assertIn('search-videos', edit)
        self.assertIn('plans-board.js', edit)
        data = self.sample()
        self.assertEqual(self.save(self.captain, ident, data, action='publish').status_code, 200)
        with self.patch_db() as c:
            row = c.execute('SELECT draft FROM team_training_plans WHERE id=?', (ident,)).fetchone()
            saved = json.loads(row[0])
        self.assertEqual(saved['chat'], data['chat'])
        self.assertIsNotNone(saved['items'][0]['board'])
        self.assertEqual(self.save(self.member, ident, data, revision=1).status_code, 403)
        with patch('app.search_web', return_value=[]):
            result = self.post(self.captain, f'/plans/{ident}/videos', items='[]')
        self.assertEqual(result.status_code, 200)

    def patch_db(self):
        import app
        return app.db()
