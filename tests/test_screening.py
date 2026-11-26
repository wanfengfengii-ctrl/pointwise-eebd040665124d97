from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Barrier

from core import connect
from tests.support import WorkbenchCase, local_time


class TestScreening(WorkbenchCase):
    def test_finish_and_reopen(self):
        program = self.open_event('play', 2, 0)
        desk = self.desk('east')
        opened = self.ok(self.start('east', 'play', 'original'))
        screening_id = opened.view.data('screening-result', 'id')
        self.assertEqual(opened.view.data('screening-result', 'state'), 'open')
        self.assertEqual(opened.view.data('screening-result', 'remaining'), '1')
        frame = self.ok(desk.browser.submit(opened, 'screening-picker', {'ms': 1000}))
        self.assertEqual(frame.view.data('frame', 'index'), '2')
        desk.now = local_time(10, 30)
        ended = self.ok(desk.browser.submit(opened, 'finish'))
        self.assertEqual(ended.view.data('screening-result', 'state'), 'finished')
        self.assertEqual(ended.view.data('screening-result', 'ended'), str(local_time(10, 30)))
        desk.now = local_time(11)
        with self.subTest(case='S1.finish_retry'):
            again = self.ok(desk.browser.submit(opened, 'finish'))
            self.assertEqual(again.view.data('screening-result', 'ended'), str(local_time(10, 30)))
        with self.subTest(case='S1.unknown_finish'):
            self.error(desk.browser.submit(opened, 'finish', {'id': 'missing'}), 404, 'unknown_screening')
        with self.subTest(case='S1.reinitialize'):
            desk.restart()
            history = self.ok(desk.browser.get('/venue', event='play'))
            self.assertEqual(history.view.data('venue-result', 'open'), '0')
            self.assertEqual(history.view.data('venue-result', 'started'), '1')
            self.assertEqual(history.view.data('venue-result', 'remaining'), '1')
            retrieved = self.ok(desk.browser.get(history.view.href('/screening', id=screening_id)))
            again = self.ok(self.start('east', 'play', 'original'))
            for result in (retrieved, again):
                self.assertEqual(result.view.data('screening-result', 'id'), screening_id)
                self.assertEqual(result.view.data('screening-result', 'program'), program)
                self.assertEqual(result.view.data('screening-result', 'state'), 'finished')
                self.assertEqual(result.view.data('screening-result', 'remaining'), '1')

    def test_exhaustion_and_retry(self):
        program = self.open_event('exhaust', 1, 0)
        desk = self.desk('east')
        original = self.ok(self.start('east', 'exhaust', 'A'))
        self.error(self.start('east', 'exhaust', 'B'), 409, 'no_quota')
        replay = self.ok(self.start('east', 'exhaust', 'A'))
        self.assertEqual(replay.view.data('screening-result', 'id'), original.view.data('screening-result', 'id'))
        self.assertEqual(replay.view.data('screening-result', 'remaining'), '0')
        with self.subTest(case='S2.lost_response'):
            self.open_event('lost', 1, 0, program)
            response = self.start('east', 'lost', 'A', discard=True)
            self.assertEqual((response.status, response.raw), (200, b''))
            desk.restart()
            self.error(self.start('east', 'lost', 'B'), 409, 'no_quota')
            history = self.ok(desk.browser.get('/venue', event='lost'))
            saved = self.ok(desk.browser.get(history.view.unique_link('/screening')))
            replay = self.ok(self.start('east', 'lost', 'A'))
            self.assertEqual(history.view.data('venue-result', 'started'), '1')
            self.assertEqual(replay.view.data('screening-result', 'id'), saved.view.data('screening-result', 'id'))
            self.assertEqual(replay.view.data('screening-result', 'program'), program)
        with self.subTest(case='S2.last_slot_race'):
            self.open_event('race', 1, 0, program)
            barrier = Barrier(2)

            def race(request):
                barrier.wait(timeout=5)
                return request, self.start('east', 'race', request)

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(race, ('left', 'right')))
            self.assertEqual(sorted(result.status for _, result in results), [200, 409])
            winner, winning_response = next(pair for pair in results if pair[1].status == 200)
            self.error(next(result for _, result in results if result.status == 409), 409, 'no_quota')
            desk.restart()
            state = self.ok(desk.browser.get('/venue', event='race')).view
            self.assertEqual(state.data('venue-result', 'started'), '1')
            self.assertEqual(state.data('venue-result', 'remaining'), '0')
            replay = self.ok(self.start('east', 'race', winner))
            self.assertEqual(replay.view.data('screening-result', 'id'), winning_response.view.data('screening-result', 'id'))
        with self.subTest(case='S2.rollback'):
            self.open_event('write-failure', 1, 0, program)
            with closing(connect(desk.path)) as db:
                db.executescript('''
                    CREATE TABLE test_parent (id TEXT PRIMARY KEY);
                    CREATE TABLE test_commit_guard (id TEXT REFERENCES test_parent(id) DEFERRABLE INITIALLY DEFERRED);
                    CREATE TRIGGER fail_screening_commit AFTER INSERT ON screenings
                    WHEN NEW.event_id = 'write-failure'
                    BEGIN INSERT INTO test_commit_guard VALUES (NEW.screening_id); END;
                ''')
            self.error(self.start('east', 'write-failure', 'retry'), 503, 'storage_error')
            after = self.ok(desk.browser.get('/venue', event='write-failure')).view
            self.assertEqual(after.data('venue-result', 'started'), '0')
            self.assertEqual(after.data('venue-result', 'remaining'), '1')
            with closing(connect(desk.path)) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM test_commit_guard').fetchone()[0], 0)
                db.execute('DROP TRIGGER fail_screening_commit')
            retried = self.ok(self.start('east', 'write-failure', 'retry'))
            self.assertEqual(retried.view.data('screening-result', 'remaining'), '0')
            self.assertEqual(self.ok(desk.browser.get('/venue', event='write-failure')).view.data('venue-result', 'started'), '1')
