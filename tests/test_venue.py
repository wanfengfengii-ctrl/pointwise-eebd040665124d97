from tests.support import WorkbenchCase


class TestVenue(WorkbenchCase):
    def test_install_and_preview(self):
        program, issued, packets = self.issue('opening', 3, 0)
        central = self.desk('central').browser
        for venue, balance in (('east', '3'), ('west', '0')):
            page = self.install(venue, packets[venue])
            view = page.view
            self.assertEqual(view.data('venue-result', 'program'), program)
            self.assertEqual(view.data('venue-result', 'remaining'), balance)
            browser = self.desk(venue).browser
            trial = self.ok(browser.submit(page, 'preview', {'ms': 1000}))
            self.assertEqual(trial.view.data('frame', 'index'), '2')
            self.assertEqual(trial.view.data('venue-result', 'remaining'), balance)
            with self.subTest(case='O1.preview_boundary', venue=venue):
                ending = self.ok(browser.submit(page, 'preview', {'ms': 1500}))
                self.assertEqual(ending.view.data('frame', 'state'), 'end')
                self.assertEqual(ending.view.data('venue-result', 'rehearsals'), '2')
                self.assertEqual(ending.view.data('venue-result', 'remaining'), balance)
            with self.subTest(case='O1.preview_invalid', venue=venue):
                self.error(browser.submit(page, 'preview', {'ms': 1501}), 422, 'invalid_time')
                self.error(browser.submit(page, 'preview', {'event': 'missing', 'ms': 0}), 404, 'unknown_installation')
                self.assertEqual(self.ok(browser.get('/venue', event='opening')).view.data('venue-result', 'rehearsals'), '2')
        with self.subTest(case='O1.issue_conflict'):
            distinct_program = self.program()
            for changed in ({'west': 1}, {'program': distinct_program}):
                params = {'event': 'opening', 'east': 3, 'west': 0, 'program': program} | changed
                self.error(central.submit(issued, 'issue', params), 409, 'issue_conflict')
        with self.subTest(case='O1.issue_retry'):
            params = {'event': 'opening', 'east': 3, 'west': 0, 'program': program}
            again = self.ok(central.submit(issued, 'issue', params))
            self.assertEqual(again.view.data('issue-result', 'issue'), issued.view.data('issue-result', 'issue'))
            for venue in ('east', 'west'):
                original = self.ok(central.get(again.view.href('/opening', event='opening', venue=venue)))
                self.assertEqual(original.raw, packets[venue])
        with self.subTest(case='O1.invalid_issue'):
            for event, use_program, west, status, code in (
                ('bad-quota', program, -1, 422, 'invalid_quota'),
                ('bad-integer', program, '1.5', 422, 'invalid_integer'),
                ('bad-program', 'unknown', 0, 404, 'unknown_program'),
            ):
                response = central.submit(issued, 'issue', {'event': event, 'east': 3, 'west': west, 'program': use_program})
                self.error(response, status, code)
                self.error(central.get('/opening', event=event, venue='east'), 404, 'unknown_issue')
        with self.subTest(case='O1.reinstall'):
            screening = self.ok(self.start('east', 'opening', 'first'))
            restored = self.install('east', packets['east'])
            self.assertEqual(restored.view.data('venue-result', 'remaining'), '2')
            self.assertEqual(restored.view.data('venue-result', 'rehearsals'), '2')
            self.assertEqual(restored.view.data('venue-result', 'started'), '1')
            restored.view.href('/screening', id=screening.view.data('screening-result', 'id'))

    def test_wrong_venue(self):
        program, issued, packets = self.issue('for-east', 3, 0)
        west = self.desk('west').browser
        home = self.ok(west.get('/venue'))
        self.error(west.submit(home, 'install', files={'packet': packets['east']}), 422, 'wrong_venue')
        self.error(west.get('/venue', event='for-east'), 404, 'unknown_installation')
        with self.subTest(case='O2.damaged_packet'):
            damaged = packets['west'].replace(b'for-east', b'for-west')
            self.assertNotEqual(damaged, packets['west'])
            self.error(west.submit(home, 'install', files={'packet': damaged}), 422, 'invalid_packet')
            self.error(west.get('/venue', event='for-east'), 404, 'unknown_installation')
            self.error(west.get('/venue', event='for-west'), 404, 'unknown_installation')
            self.assertEqual(self.install('west', packets['west']).view.data('venue-result', 'program'), program)
