import json
from contextlib import closing

from core import connect
from tests.support import SAMPLE, WorkbenchCase


class TestProgram(WorkbenchCase):
    def _draft_count(self, table='drafts'):
        with closing(connect(self.desk('central').path)) as db:
            if table == 'drafts':
                return db.execute('SELECT COUNT(*) FROM drafts').fetchone()[0]
            return db.execute('SELECT COUNT(*) FROM program_editions').fetchone()[0]

    def test_boundaries_and_freeze(self):
        desk = self.desk('central')
        browser = desk.browser
        saved = self.ok(browser.submit(browser.get('/draft'), 'save-draft', {'frames': SAMPLE}))
        draft_id = saved.view.data('draft-summary', 'draft')
        for millis, expected in ((0, '1'), (999, '1'), (1000, '2'), (1500, 'end')):
            view = self.ok(browser.submit(saved, 'proof-picker', {'ms': millis})).view
            actual = view.data('frame', 'state') if expected == 'end' else view.data('frame', 'index')
            self.assertEqual(actual, expected)
        frozen = self.ok(browser.submit(saved, 'freeze'))
        program = frozen.view.data('program-summary', 'program')
        revised = json.loads(SAMPLE)
        revised[0]['duration_ms'] = 1200
        saved = self.ok(browser.submit(saved, 'save-draft', {'frames': json.dumps(revised)}))
        self.assertEqual(saved.view.data('draft-summary', 'total'), '1700')
        self.assertEqual(self.ok(browser.submit(saved, 'proof-picker', {'ms': 1000})).view.data('frame', 'index'), '1')
        self.assertEqual(self.ok(browser.submit(frozen, 'edition-picker', {'ms': 1000})).view.data('frame', 'index'), '2')
        self.assertEqual(self.ok(browser.get('/program', program=program, ms=1500)).view.data('frame', 'state'), 'end')
        with self.subTest(case='P1.out_of_range'):
            for value, code in ((-1, 'invalid_time'), (1501, 'invalid_time'), ('1.5', 'invalid_integer')):
                self.error(browser.get('/program', program=program, ms=value), 422, code)
        with self.subTest(case='P1.freeze_unknown'):
            self.error(browser.submit(saved, 'freeze', {'draft': 'absent'}), 404, 'unknown_draft')
            self.assertEqual(self._draft_count('program_editions'), 1)
        with self.subTest(case='P1.reinitialize'):
            desk.restart()
            self.assertEqual(self.ok(desk.browser.get('/draft', draft=draft_id)).view.data('draft-summary', 'total'), '1700')
            self.assertEqual(self.ok(desk.browser.get('/program', program=program)).view.data('program-summary', 'total'), '1500')
            self.assertEqual(self._draft_count(), 1)

    def test_zero_duration(self):
        browser = self.desk('central').browser
        blank = self.ok(browser.get('/draft'))
        frames = json.loads(SAMPLE)
        frames[0]['duration_ms'] = 0
        self.error(browser.submit(blank, 'save-draft', {'frames': json.dumps(frames)}), 422, 'invalid_duration')
        self.assertEqual(self._draft_count(), 0)
        with self.subTest(case='P2.late_zero'):
            frames = json.loads(SAMPLE)
            frames[1]['duration_ms'] = 0
            invalid = json.dumps(frames)
            self.error(browser.submit(blank, 'save-draft', {'frames': invalid}), 422, 'invalid_duration')
            self.assertEqual(self._draft_count(), 0)
            existing = self.ok(browser.submit(blank, 'save-draft', {'frames': SAMPLE}))
            self.error(browser.submit(existing, 'save-draft', {'frames': invalid}), 422, 'invalid_duration')
            draft_id = existing.view.data('draft-summary', 'draft')
            saved = self.ok(browser.get('/draft', draft=draft_id))
            self.assertEqual(saved.view.data('draft-summary', 'total'), '1500')
            self.assertIn('鲸影过桥'.encode(), saved.raw)
            self.assertEqual(self._draft_count(), 1)
        with self.subTest(case='P2.empty_and_invalid'):
            for raw in ('[]', '[{}]', '[', *[
                json.dumps([{'title': '分镜', 'body': '正文', 'duration_ms': duration}])
                for duration in (True, 1.5, -2)
            ]):
                response = browser.submit(blank, 'save-draft', {'frames': raw})
                self.assertEqual(response.status, 422)
            self.assertEqual(self._draft_count(), 1)
