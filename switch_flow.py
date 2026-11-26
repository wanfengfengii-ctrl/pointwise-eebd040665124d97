"""End-to-end browser/form flow for the corrected-program switch.

This module is intentionally usable both as a demo script and by unittest.
It drives real localhost HTTP workbench processes, transfers packet bytes as
files, closes the central workbench, and reopens venue processes.
"""
from __future__ import annotations

import json
from pathlib import Path

from tests.support import ROOT, SAMPLE, ProcessDesk, scenario

CORRECTED = (ROOT / 'samples' / 'corrected-lanterns.json').read_text(encoding='utf-8')

EVENT = 'tide-switch'
DAY = '2025-06-14'


class SwitchFlow:
    def __init__(self, root: Path, desk_class=ProcessDesk):
        self.root = Path(root)
        self.desk_class = desk_class
        self.desks = {}

    def desk(self, role):
        if role not in self.desks:
            desk = self.desk_class(role, self.root / f'{role}.sqlite')
            self.desks[role] = desk
        return self.desks[role]

    def close(self):
        for desk in self.desks.values():
            desk.close()

    def ok(self, response):
        if response.status != 200:
            body = response.raw[:1600].decode('utf-8', errors='replace')
            raise AssertionError(f'expected HTTP 200, got {response.status}: {body}')
        return response

    def error(self, response, status, code=None):
        if response.status != status:
            body = response.raw[:1200].decode('utf-8', errors='replace')
            raise AssertionError(f'expected HTTP {status}, got {response.status}: {body}')
        view = response.view
        actual_code = view.data('error', 'code')
        if code is not None and actual_code != code:
            raise AssertionError(f'expected error code {code}, got {actual_code}: '
                                 + response.raw[:1200].decode('utf-8', errors='replace'))
        return response

    def freeze(self, frames):
        central = self.desk('central').browser
        saved = self.ok(central.submit(self.ok(central.get('/draft')), 'save-draft',
                                       {'frames': frames}))
        frozen = self.ok(central.submit(saved, 'freeze'))
        return frozen.view.data('program-summary', 'program')

    def issue_and_install(self):
        original = self.freeze(SAMPLE)
        corrected = self.freeze(CORRECTED)
        central = self.desk('central').browser
        issued = self.ok(central.submit(central.get('/issue'), 'issue', {
            'event': EVENT, 'east': '3', 'west': '2', 'program': original,
        }))
        packets = {}
        for venue in ('east', 'west'):
            href = issued.view.href('/opening', event=EVENT, venue=venue)
            packets[venue] = self.ok(central.get(href)).raw
            browser = self.desk(venue).browser
            installed = self.ok(browser.submit(self.ok(browser.get('/venue')), 'install',
                                               files={'packet': packets[venue]}))
            if installed.view.data('venue-result', 'program') != original:
                raise AssertionError('installation did not expose original program')
        return original, corrected, packets

    def register_plan(self, corrected):
        central = self.desk('central').browser
        page = self.ok(central.get('/switch'))
        registered = self.ok(central.submit(page, 'switch', {
            'event': EVENT, 'program': corrected,
        }))
        view = registered.view
        plan = view.data('switch-result', 'plan')
        if view.data('switch-result', 'east') != '0' or view.data('switch-result', 'west') != '0':
            raise AssertionError('new switch plan should have no receipts')
        # Re-registering the same plan is an idempotent retry.
        again = self.ok(central.submit(page, 'switch-plan', {
            'event': EVENT, 'program': corrected,
        }))
        if again.view.data('switch-result', 'plan') != plan:
            raise AssertionError('same switch registration did not return same plan')
        return plan, registered

    def start(self, venue, request):
        browser = self.desk(venue).browser
        page = self.ok(browser.get('/venue', event=EVENT))
        return self.ok(browser.submit(page, 'start', {'request': request}))

    def retire(self, venue, plan):
        browser = self.desk(venue).browser
        page = self.ok(browser.get('/venue', event=EVENT))
        done = self.ok(browser.submit(page, 'retire', {'plan': plan}))
        if done.view.data('switch-status', 'retired') != '1':
            raise AssertionError(f'{venue} was not durably retired')
        href = done.view.href('/retirement', event=EVENT)
        raw = self.ok(browser.get(href)).raw
        return done, raw

    def upload_credential(self, raw, form='credential'):
        central = self.desk('central').browser
        page = self.ok(central.get('/switch'))
        return self.ok(central.submit(page, form, files={'packet': raw}))

    def venue_upload(self, venue, form_id, raw):
        browser = self.desk(venue).browser
        page = self.ok(browser.get('/venue', event=EVENT))
        return self.ok(browser.submit(page, form_id, files={'packet': raw}))

    def run(self):
        original, corrected, opening_packets = self.issue_and_install()
        plan, central_plan_page = self.register_plan(corrected)
        central = self.desk('central').browser

        # East opens A and keeps the exact old form response for a late replay.
        east_browser = self.desk('east').browser
        old_east_form = self.ok(east_browser.get('/venue', event=EVENT))
        a = self.ok(east_browser.submit(old_east_form, 'start', {'request': 'A'}))
        a_id = a.view.data('screening-result', 'id')
        if a.view.data('screening-result', 'remaining') != '2':
            raise AssertionError('east quota after A should leave 2')

        east_retired, east_credential = self.retire('east', plan)
        if east_retired.view.data('venue-result', 'remaining') != '2':
            raise AssertionError('retirement must not consume quota')

        # Before west's receipt exists, authorization is not available.
        self.error(central.get('/authorization', plan=plan), 409, 'switch_incomplete')

        # West keeps an old form too, but first legally opens one old edition.
        west_browser = self.desk('west').browser
        old_west_form = self.ok(west_browser.get('/venue', event=EVENT))
        w = self.ok(west_browser.submit(old_west_form, 'start', {'request': 'W'}))
        w_id = w.view.data('screening-result', 'id')
        if w.view.data('screening-result', 'remaining') != '1':
            raise AssertionError('west quota after W should leave 1')
        _, west_credential = self.retire('west', plan)

        # A stale old form cannot create an unseen request while waiting.
        self.error(west_browser.submit(old_west_form, 'start', {'request': 'UNSEEN'}),
                   409, 'old_edition_retired')

        # Wrong/corrupt receipts do not move central state.
        damaged = east_credential.replace(b'tide-switch', b'tide-damaged')
        self.error(central.submit(self.ok(central.get('/switch')), 'credential',
                                  files={'packet': damaged}), 422, 'invalid_packet')
        from tour.switch_packets import RetirementReceipt, encode_retirement_receipt
        other = encode_retirement_receipt(RetirementReceipt(
            'switch-other-plan', 'other-event', 'issue-other', 'east', original, 1))
        self.error(central.submit(self.ok(central.get('/switch')), 'credential',
                                  files={'packet': other}), 404, 'unknown_switch_plan')
        self.error(central.submit(self.ok(central.get('/switch')), 'credential-east',
                                  fields={'venue': 'east'}, files={'packet': west_credential}),
                   422, 'wrong_venue')

        east_upload = self.upload_credential(east_credential)
        self.upload_credential(west_credential)
        duplicate = self.upload_credential(east_credential)
        if duplicate.view.data('switch-result', 'east') != '1':
            raise AssertionError('duplicate east receipt changed status')
        if '重送' not in duplicate.raw.decode('utf-8'):
            raise AssertionError('duplicate receipt page should identify idempotent replay')

        auth_href = duplicate.view.href('/authorization', plan=plan)
        auth = self.ok(central.get(auth_href)).raw
        east_only_auth = self.ok(central.get('/authorization', plan=plan, venue='east')).raw
        material_href = duplicate.view.href('/switch-program', plan=plan)
        material = self.ok(central.get(material_href)).raw
        auth_again = self.ok(central.get(auth_href)).raw
        if auth != auth_again:
            raise AssertionError('authorization is not re-collectible as the same packet')

        # Central may stop now; venues enable independently from files.
        central_desk = self.desks['central']
        central_desk.close()

        # Invalid venue materials do not advance local state.
        broken_auth_page = self.ok(east_browser.get('/venue', event=EVENT))
        self.error(east_browser.submit(broken_auth_page, 'authorization',
                                       files={'packet': auth.replace(b'tide-switch', b'tide-bad')}),
                   422, 'invalid_packet')
        from tour.switch_packets import SwitchAuthorization, encode_authorization
        other_auth = encode_authorization(SwitchAuthorization(
            'switch-other-plan', EVENT, 'issue-other', original, corrected))
        other_auth_page = self.ok(east_browser.get('/venue', event=EVENT))
        self.error(east_browser.submit(other_auth_page, 'authorization',
                                       files={'packet': other_auth}),
                   409, 'switch_material_conflict')
        self.venue_upload('east', 'authorization', auth)
        bad_material = material[:-3] + (b'000' if not material.endswith(b'000\n') else b'111')
        self.error(east_browser.submit(self.ok(east_browser.get('/venue', event=EVENT)),
                                       'switch-program', files={'packet': bad_material}),
                   422, 'invalid_packet')
        enabled_east = self.venue_upload('east', 'switch-program', material)
        if enabled_east.view.data('switch-status', 'enabled') != '1':
            raise AssertionError('east should auto-enable when matching materials are complete')
        # Explicit enable and valid redelivery remain idempotent.
        self.ok(east_browser.submit(self.ok(east_browser.get('/venue', event=EVENT)),
                                    'enable-switch', {'plan': plan}))
        self.venue_upload('east', 'authorization', auth)
        self.venue_upload('east', 'switch-program', material)

        # Handled request replays on the stale old form; unseen requests never
        # become new-edition screenings.
        replay_a = self.ok(east_browser.submit(old_east_form, 'start', {'request': 'A'}))
        if replay_a.view.data('screening-result', 'id') != a_id:
            raise AssertionError('old request A did not reclaim its original screening')
        if replay_a.view.data('screening-result', 'program') != original:
            raise AssertionError('A replay changed opening program')
        self.error(east_browser.submit(old_east_form, 'start', {'request': 'LATE'}),
                   409, 'stale_start_form')

        b = self.start('east', 'B')
        b_id = b.view.data('screening-result', 'id')
        if b.view.data('screening-result', 'remaining') != '1':
            raise AssertionError('east should have one cumulative use after A and B')
        if b.view.data('screening-result', 'program') != corrected:
            raise AssertionError('B did not open the enabled corrected program')

        # Reapplying the premiere opening packet keeps local history/quota.
        reinstall_page = self.ok(east_browser.get('/venue', event=EVENT))
        reinstalled = self.ok(east_browser.submit(
            reinstall_page, 'install', files={'packet': opening_packets['east']}))
        if reinstalled.view.data('venue-result', 'started') != '2' \
                or reinstalled.view.data('venue-result', 'remaining') != '1':
            raise AssertionError('premiere packet reinstall changed cumulative history or quota')

        # Reopen the east process; credentials, enablement and screenings persist.
        self.desks['east'].restart()
        east_browser = self.desk('east').browser
        credential_after_restart = self.ok(
            east_browser.get(east_retired.view.href('/retirement', event=EVENT))).raw
        if credential_after_restart != east_credential:
            raise AssertionError('retirement credential was not re-collectible after restart')
        a_at = self.ok(east_browser.get('/screening', id=a_id, ms=1000))
        b_at = self.ok(east_browser.get('/screening', id=b_id, ms=1000))
        facts_at_1000 = {
            'A': {'index': int(a_at.view.data('frame', 'index')),
                  'title': a_at.view.data('frame', 'title'),
                  'program': a_at.view.data('screening-result', 'program'),
                  'state': a_at.view.data('screening-result', 'state')},
            'B': {'index': int(b_at.view.data('frame', 'index')),
                  'title': b_at.view.data('frame', 'title'),
                  'program': b_at.view.data('screening-result', 'program'),
                  'title_present': '潮门（校正）'.encode() in b_at.raw},
        }
        if facts_at_1000['A']['index'] != 2 or facts_at_1000['A']['program'] != original \
                or facts_at_1000['A']['title'] != '鲸影过桥':
            raise AssertionError(f'A at 1000ms must show original frame 2: {facts_at_1000}')
        if facts_at_1000['B']['index'] != 1 or not facts_at_1000['B']['title_present'] \
                or facts_at_1000['B']['title'] != '潮门（校正）' \
                or facts_at_1000['B']['program'] != corrected:
            raise AssertionError(f'B at 1000ms must show corrected frame 1: {facts_at_1000}')

        finished_a = self.ok(east_browser.submit(a_at, 'finish'))
        if finished_a.view.data('screening-result', 'state') != 'finished':
            raise AssertionError('old screening A could not be finished')

        # Same-shift report counts both openings but keeps the premiere program.
        seal_page, report_raw = self.seal('east')
        report = seal_page.view.data('sealed-result', 'report')
        report_facts = {key: int(seal_page.view.data('sealed-result', key))
                        for key in ('started', 'finished', 'open')}
        if report_facts != {'started': 2, 'finished': 1, 'open': 1}:
            raise AssertionError(f'unexpected east shift facts: {report_facts}')
        if seal_page.view.data('sealed-result', 'program') != original:
            raise AssertionError('shift report header must retain premiere program')
        seal_again, report_raw_again = self.seal('east')
        if seal_again.view.data('sealed-result', 'report') != report or report_raw_again != report_raw:
            raise AssertionError('sealed report was not reissued as the same original')

        # A venue-scoped authorization for East is a wrong-venue file at West.
        west_browser = self.desk('west').browser
        wrong_venue_page = self.ok(west_browser.get('/venue', event=EVENT))
        self.error(west_browser.submit(wrong_venue_page, 'authorization',
                                       files={'packet': east_only_auth}),
                   422, 'wrong_venue')
        # West receives both qualified materials while central is still stopped.
        self.venue_upload('west', 'authorization', auth)
        west_enabled = self.venue_upload('west', 'switch-program', material)
        if west_enabled.view.data('switch-status', 'enabled') != '1':
            raise AssertionError('west could not enable its matching new program')
        c = self.start('west', 'C')
        c_id = c.view.data('screening-result', 'id')
        if c.view.data('screening-result', 'remaining') != '0':
            raise AssertionError('west should consume its final cumulative quota')
        self.desks['west'].restart()
        c_at = self.ok(self.desk('west').browser.get('/screening', id=c_id, ms=1000))
        c_frame = int(c_at.view.data('frame', 'index'))
        c_title = c_at.view.data('frame', 'title')
        c_debug = {
            'index': c_at.view.data('frame', 'index'),
            'title': c_title,
            'program': c_at.view.data('screening-result', 'program'),
            'has_title': '潮门（校正）'.encode() in c_at.raw,
            'snippet': c_at.raw[:1200].decode('utf-8', errors='replace'),
        }
        if c_at.view.data('frame', 'index') != '1' or '潮门（校正）'.encode() not in c_at.raw:
            raise AssertionError(f'west C did not play corrected first frame after restart: {c_debug}')

        # Central can reopen and reissue the same authorization.
        self.desks['central'].start()
        auth_after = self.ok(self.desk('central').browser.get(auth_href)).raw
        if auth_after != auth:
            raise AssertionError('central did not retain the same authorization')
        reopened_central = self.desk('central').browser
        intake_page = self.ok(reopened_central.submit(
            self.ok(reopened_central.get('/intake')), 'intake', files={'packet': report_raw}))
        if intake_page.view.data('accepted-result', 'report') != report:
            raise AssertionError('central could not accept the switch-event shift report after reopen')

        scenario(
            'SWITCH1',
            {'event': EVENT, 'east_quota': 3, 'west_quota': 2, 'at_ms': 1000},
            {'A_frame': 2, 'B_frame': 1, 'C_frame': 1, 'east_started': 2},
            {'A_frame': facts_at_1000['A']['index'],
             'B_frame': facts_at_1000['B']['index'],
             'C_frame': c_frame,
             'east_started': report_facts['started']},
            {'report_program': original, 'quota_after_east_B': 1, 'quota_after_west_C': 0},
            {'report_program': original, 'quota_after_east_B': 1, 'quota_after_west_C': 0},
            ['tour/switch_plan.py', 'tour/switch_packets.py', 'venue/switch_state.py',
             'venue/screening.py', 'desk/switch_pages.py', 'desk/venue_switch_pages.py'],
            '旧申请复领旧场次并查开场节目；停旧凭据双到后发授权；新版材料与授权相符才启用，次数按展次累计，班报保留首发节目。')

        return {
            'event': EVENT,
            'plan': plan,
            'programs': {'original': original, 'corrected': corrected},
            'screenings': {'A': a_id, 'B': b_id, 'W': w_id, 'C': c_id},
            'frame_at_1000ms': facts_at_1000,
            'east_report': {'report': report, **report_facts},
            'west_new_screening': c_id,
            'west_frame_at_1000ms': {'index': c_frame, 'title': c_title},
        }

    def seal(self, venue):
        browser = self.desk(venue).browser
        page = self.ok(browser.submit(browser.get('/shift', event=EVENT), 'seal',
                                      {'day': DAY, 'shift': 'AM'}))
        raw = self.ok(browser.get(page.view.href('/sealed', event=EVENT, day=DAY, shift='AM'))).raw
        return page, raw


def main():
    import tempfile
    with tempfile.TemporaryDirectory(prefix='tide-switch-demo-') as tmp:
        flow = SwitchFlow(Path(tmp))
        try:
            result = flow.run()
        finally:
            flow.close()
    print('POINTWISE_SWITCH_DEMO ' + json.dumps(result, ensure_ascii=False, sort_keys=True))
    print('换版浏览器流程核验通过：A 复领原版第 2 段，B/C 播放校正版第 1 段，班报保留首发节目号。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
