import json

from core import pack
from tests.support import DAY, WorkbenchCase, local_time, report_facts


class TestReports(WorkbenchCase):
    def test_dual_venue_reconcile(self):
        program = self.open_event('review', 3, 2)
        east = self.desk('east')
        west = self.desk('west')
        central = self.desk('central')
        venue = self.ok(east.browser.get('/venue', event='review'))
        self.ok(east.browser.submit(venue, 'preview', {'ms': 1000}))
        east_play = self.ok(self.start('east', 'review', 'e1'))
        self.ok(east.browser.submit(east_play, 'finish'))
        west_play = self.ok(self.start('west', 'review', 'w1'))
        east_page, east_packet = self.seal('east', 'review')
        west_page, west_packet = self.seal('west', 'review')
        east_id, west_id = self.intake(east_packet), self.intake(west_packet)
        result = self.ok(central.browser.submit(central.browser.get('/intake'), 'compare', {'left': west_id, 'right': east_id}))
        east_counts = {'rehearsals': 1, 'started': 1, 'finished': 1, 'open': 0}
        west_counts = {'rehearsals': 0, 'started': 1, 'finished': 0, 'open': 1}
        self.assertEqual(report_facts(result, 'compare-east'), east_counts)
        self.assertEqual(report_facts(result, 'compare-west'), west_counts)
        self.assertEqual(report_facts(east_page, 'sealed-result'), east_counts)
        self.assertEqual(report_facts(west_page, 'sealed-result'), west_counts)
        for side in ('east', 'west'):
            self.assertEqual(result.view.data(f'compare-{side}', 'program'), program)
        with self.subTest(case='R1.intake_retry'):
            self.assertEqual(self.intake(east_packet), east_id)
            path = self.ok(central.browser.get('/intake')).view.href('/accepted', report=east_id)
            self.assertEqual(self.ok(central.browser.get(path)).raw, east_packet)
            links = central.browser.get('/intake').view.links
            self.assertEqual(sum(link.startswith('/accepted?') for link in links), 2)
        with self.subTest(case='R1.seal_snapshot'):
            west.now = local_time(10, 5)
            finished = self.ok(west.browser.submit(west_play, 'finish'))
            self.assertEqual(finished.view.data('screening-result', 'state'), 'finished')
            west.restart()
            refrozen, raw = self.seal('west', 'review')
            self.assertEqual(refrozen.view.data('sealed-result', 'report'), west_id)
            self.assertEqual(report_facts(refrozen, 'sealed-result'), west_counts)
            self.assertEqual(raw, west_packet)
            self.assertEqual(west.browser.get('/venue', event='review').view.data('venue-result', 'open'), '0')
        with self.subTest(case='R1.reinitialize'):
            central.restart()
            central_home = self.ok(central.browser.get('/intake'))
            self.assertEqual(self.ok(central.browser.get(central_home.view.href('/accepted', report=west_id))).raw, west_packet)
            compared = self.ok(central.browser.submit(central_home, 'compare', {'left': east_id, 'right': west_id}))
            self.assertEqual(report_facts(compared, 'compare-west'), west_counts)
        with self.subTest(case='R1.shift_boundary'):
            self.open_event('boundary', 3, 0, program)
            east.now = local_time(11, 59, 59)
            before = self.ok(self.start('east', 'boundary', 'before'))
            east.now = local_time(12)
            current = self.ok(east.browser.get('/venue', event='boundary'))
            self.assertEqual(current.view.data('venue-result', 'open'), '1')
            self.ok(east.browser.submit(current, 'preview', {'ms': 0}))
            self.ok(east.browser.submit(before, 'finish'))
            self.ok(self.start('east', 'boundary', 'at-noon'))
            east.now = local_time(0, day=15)
            self.ok(self.start('east', 'boundary', 'midnight'))
            am, _ = self.seal('east', 'boundary')
            pm, _ = self.seal('east', 'boundary', shift='PM')
            next_am, _ = self.seal('east', 'boundary', day='2025-06-15')
            self.assertEqual(report_facts(am, 'sealed-result'), {'rehearsals': 0, 'started': 1, 'finished': 1, 'open': 0})
            self.assertEqual(report_facts(pm, 'sealed-result'), {'rehearsals': 1, 'started': 1, 'finished': 0, 'open': 1})
            self.assertEqual(report_facts(next_am, 'sealed-result'), {'rehearsals': 0, 'started': 1, 'finished': 0, 'open': 1})
            self.assertIn(b'at-noon', pm.raw)
            self.assertNotIn(b'before', pm.raw)
            self.assertNotIn(b'midnight', pm.raw)
        with self.subTest(case='R1.empty_shift'):
            empty, _ = self.seal('west', 'boundary', shift='PM')
            self.assertEqual(report_facts(empty, 'sealed-result'), {'rehearsals': 0, 'started': 0, 'finished': 0, 'open': 0})
        with self.subTest(case='R1.invalid_seal'):
            form = self.ok(west.browser.get('/shift', event='boundary'))
            self.error(west.browser.submit(form, 'seal', {'day': '2025-02-30', 'shift': 'AM'}), 422, 'invalid_shift')
            self.error(west.browser.submit(form, 'seal', {'day': DAY, 'shift': 'night'}), 422, 'invalid_shift')
            self.error(west.browser.submit(form, 'seal', {'event': 'absent', 'day': DAY, 'shift': 'AM'}), 404, 'unknown_installation')
            self.error(west.browser.get('/sealed', event='boundary', day=DAY, shift='AM'), 404, 'unknown_report')

    def test_wrong_event(self):
        program = self.open_event('event-a', 1, 1)
        self.open_event('event-b', 1, 1, program)
        self.ok(self.start('east', 'event-a', 'first'))
        _, a_east = self.seal('east', 'event-a')
        _, a_west = self.seal('west', 'event-a')
        _, b_east = self.seal('east', 'event-b')
        _, b_west = self.seal('west', 'event-b')
        ids = [self.intake(raw) for raw in (a_east, a_west, b_east, b_west)]
        browser = self.desk('central').browser
        intake = self.ok(browser.get('/intake'))
        with self.subTest(case='R2.same_program_cross_event'):
            self.error(browser.submit(intake, 'compare', {'left': ids[0], 'right': ids[3]}), 422, 'different_events')
        with self.subTest(case='R2.same_venue'):
            _, same_venue = self.seal('east', 'event-a', shift='PM')
            same_id = self.intake(same_venue)
            self.error(browser.submit(intake, 'compare', {'left': ids[0], 'right': same_id}), 422, 'same_venue')
        with self.subTest(case='R2.damaged_report'):
            bad = a_east.replace(b'event-a', b'event-z')
            self.assertNotEqual(bad, a_east)
            payload = json.loads(a_east)['payload']
            payload['counts']['started'] = 2
            inconsistent = pack('shift-report', payload)
            before = self.ok(browser.get('/intake')).view.links
            for raw in (bad, inconsistent):
                self.error(browser.submit(intake, 'intake', files={'packet': raw}), 422, 'invalid_packet')
            self.assertEqual(self.ok(browser.get('/intake')).view.links, before)
        valid = self.ok(browser.submit(intake, 'compare', {'left': ids[1], 'right': ids[0]}))
        self.assertEqual(report_facts(valid, 'compare-east'), {'rehearsals': 0, 'started': 1, 'finished': 0, 'open': 1})
        self.assertEqual(valid.view.data('compare-west', 'program'), program)
