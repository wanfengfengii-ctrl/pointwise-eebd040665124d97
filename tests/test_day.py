import unittest

from tests.support import ProcessDesk, SAMPLE, WorkbenchCase, report_facts, scenario


class TestDay(WorkbenchCase):
    desk_class = ProcessDesk

    def test_browser_day(self):
        central = self.desk('central')
        saved = self.ok(central.browser.submit(central.browser.get('/draft'), 'save-draft', {'frames': SAMPLE}))
        proof = []
        for at in (999, 1000, 1500):
            fact = self.ok(central.browser.submit(saved, 'proof-picker', {'ms': at})).view
            state = fact.data('frame', 'state')
            proof.append('end' if state == 'end' else int(fact.data('frame', 'index')))
        frozen = self.ok(central.browser.submit(saved, 'freeze'))
        program = frozen.view.data('program-summary', 'program')
        self.assertEqual(frozen.view.data('program-summary', 'total'), '1500')
        _, issued, packets = self.issue('tide-day', 3, 1, program)
        self.assertEqual(issued.view.data('issue-result', 'program'), program)
        central.close()

        trials = {}
        for venue, balance in (('east', 3), ('west', 1)):
            installed = self.install(venue, packets[venue])
            desk = self.desk(venue)
            self.assertEqual(installed.view.data('venue-result', 'program'), program)
            trial = self.ok(desk.browser.submit(installed, 'preview', {'ms': 1000})).view
            trials[venue] = {'frame': int(trial.data('frame', 'index')),
                             'remaining': int(trial.data('venue-result', 'remaining'))}
            self.assertEqual(trials[venue], {'frame': 2, 'remaining': balance})
        self.assertEqual(proof, [1, 2, 'end'])
        scenario('P1', {'duration_ms': [1000, 500], 'at_ms': [999, 1000, 1500]}, [1, 2, 'end'], proof,
                 {'east': {'frame': 2, 'remaining': 3}, 'west': {'frame': 2, 'remaining': 1}}, trials,
                 ['program/timing.py', 'program/edition.py', 'tour/venue_packet.py', 'venue/rehearsal.py'],
                 '手算区间 [0,1000) 和 [1000,1500)，总终点结束，试映不占初额。')

        east = self.desk('east')
        east_open = self.ok(self.start('east', 'tide-day', 'east-first'))
        west_open = self.ok(self.start('west', 'tide-day', 'west-first'))
        east_id = east_open.view.data('screening-result', 'id')
        west_id = west_open.view.data('screening-result', 'id')
        self.ok(east.browser.submit(east_open, 'finish'))
        east.restart()
        west = self.desk('west')
        west.restart()
        west_history = self.ok(west.browser.get('/venue', event='tide-day'))
        west_again = self.ok(self.start('west', 'tide-day', 'west-first'))
        self.assertEqual(west_again.view.data('screening-result', 'remaining'), '0')
        self.assertEqual(west_again.view.data('screening-result', 'id'), west_id)
        self.assertEqual(self.ok(west.browser.get(west_history.view.href('/screening', id=west_id))).view.data('screening-result', 'state'), 'open')
        self.assertEqual(self.ok(east.browser.get('/screening', id=east_id)).view.data('screening-result', 'state'), 'finished')

        east_report, east_raw = self.seal('east', 'tide-day')
        west_report, west_raw = self.seal('west', 'tide-day')
        expected = {'east': {'rehearsals': 1, 'started': 1, 'finished': 1, 'open': 0},
                    'west': {'rehearsals': 1, 'started': 1, 'finished': 0, 'open': 1}}
        actual = {'east': report_facts(east_report, 'sealed-result'), 'west': report_facts(west_report, 'sealed-result')}
        self.assertEqual(actual, expected)
        central.start()
        east_report_id = self.intake(east_raw)
        west_report_id = self.intake(west_raw)
        central.restart()
        inbox = self.ok(central.browser.get('/intake'))
        result = self.ok(central.browser.submit(inbox, 'compare', {'left': west_report_id, 'right': east_report_id}))
        comparison = {venue: report_facts(result, f'compare-{venue}') for venue in ('east', 'west')}
        self.assertEqual(comparison, expected)
        programs = {venue: result.view.data(f'compare-{venue}', 'program') for venue in ('east', 'west')}
        self.assertEqual(programs, {'east': program, 'west': program})
        self.assertIn(east_id.encode(), result.raw)
        self.assertIn(west_id.encode(), result.raw)
        scenario('R1', {'event': 'tide-day', 'east': ['试映', '开映', '结束'], 'west': ['试映', '开映', '复领']},
                 expected, actual, {'counts': expected, 'programs': {'east': program, 'west': program}},
                 {'counts': comparison, 'programs': programs},
                 ['venue/activity.py', 'report/counts.py', 'report/shift.py', 'report/intake.py', 'report/reconcile.py'],
                 '逐项点数。两馆各试映一次和正式开映一次，东场已结束，西场复领保持原号且仍待结束。')


if __name__ == '__main__':
    unittest.main(verbosity=2)
