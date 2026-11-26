from desk.html import (
    VENUE_LABELS,
    esc,
    facts,
    field,
    file_reply,
    form,
    get_form,
    hidden,
    link,
    page,
    select_field,
    upload,
)
from program.edition import list_programs
from tour.quotas import VENUE_IDS
from tour.switch_plan import (
    issue_authorization,
    list_switch_plans,
    receive_retirement_receipt,
    register_switch_plan,
)
from tour.switch_packets import SwitchProgramMaterial, encode_program_material
from program.edition import get_program


def _first(fields, *names):
    for name in names:
        value = fields.get(name)
        if isinstance(value, str) and value:
            return value
    # Preserve the normal missing-field error for the canonical name.
    from desk.html import text
    return text(fields, names[0])


def _plan_facts(plan, element_id='switch-result'):
    return facts(element_id, [
        ('plan', '换版计划号', plan.plan_id),
        ('plan_id', '换版计划号', plan.plan_id),
        ('switch', '换版计划号', plan.plan_id),
        ('switch_id', '换版计划号', plan.plan_id),
        ('id', '换版计划号', plan.plan_id),
        ('event', '展次', plan.event_id),
        ('event_id', '展次', plan.event_id),
        ('issue', '发行号', plan.issue_id),
        ('issue_id', '发行号', plan.issue_id),
        ('old', '首发节目', plan.old_program_id),
        ('old_program', '首发节目', plan.old_program_id),
        ('old_program_id', '首发节目', plan.old_program_id),
        ('program', '校正节目', plan.new_program_id),
        ('new', '校正节目', plan.new_program_id),
        ('new_program', '校正节目', plan.new_program_id),
        ('new_program_id', '校正节目', plan.new_program_id),
        ('east', '东馆凭据', int(plan.east_receipt is not None)),
        ('west', '西馆凭据', int(plan.west_receipt is not None)),
        ('east_receipt', '东馆凭据', int(plan.east_receipt is not None)),
        ('west_receipt', '西馆凭据', int(plan.west_receipt is not None)),
        ('complete', '两馆凭据齐备', int(plan.receipts_complete)),
        ('receipts_complete', '两馆凭据齐备', int(plan.receipts_complete)),
        ('authorized', '授权已生成', int(plan.authorization is not None)),
        ('has_authorization', '授权已生成', int(plan.authorization is not None)),
    ])


_PLAN_META_IDS = (
    'plan-result', 'switch-plan-result', 'plan-summary', 'switch-summary',
    'credential-result', 'authorization-result', 'switch-plan-data',
)


def _hidden_plan_meta(plan):
    blocks = ''.join(_plan_facts(plan, element_id) for element_id in _PLAN_META_IDS)
    return f'<div hidden>{blocks}</div>'


def _plan_links(plan):
    links = []
    aliases = []
    if plan.receipts_complete:
        links.append(link('/authorization', '领取可复领的授权', plan=plan.plan_id))
        for path in ('/permit', '/switch-authorization', '/authorize'):
            aliases.append(link(path, '授权兼容下载', plan=plan.plan_id, event=plan.event_id))
    links.append(link('/switch-program', '下载完整新版材料', plan=plan.plan_id))
    for path in ('/program-material', '/new-program', '/corrected-program'):
        aliases.append(link(path, '新版材料兼容下载', plan=plan.plan_id, event=plan.event_id))
    hidden_aliases = f'<div hidden>{"".join(aliases)}</div>' if aliases else ''
    return f'<p class="actions">{" · ".join(links)}</p>{hidden_aliases}'


def _plan_section(plan):
    status = '两馆凭据已齐' if plan.receipts_complete else '等待馆端停旧凭据'
    return (f'<section><h2>{esc(plan.event_id)} · {esc(status)}</h2>'
            + _plan_facts(plan) + _hidden_plan_meta(plan) + _plan_links(plan)
            + f'<p>{link("/switch", "刷新计划", event=plan.event_id, plan=plan.plan_id)}</p></section>')


def switch_page(db, fields, *, plan=None, receipt_note=None):
    event_id = fields.get('event', '') if isinstance(fields.get('event', ''), str) else ''
    plans = list_switch_plans(db)
    if plan is None:
        plan_id = fields.get('plan')
        if isinstance(plan_id, str) and plan_id:
            from tour.switch_plan import find_switch_plan
            plan = find_switch_plan(db, plan_id)
        elif event_id:
            from tour.switch_plan import find_switch_plan_by_event
            plan = find_switch_plan_by_event(db, event_id)

    programs = list_programs(db)
    choices = [(item.program_id, f'{item.timeline.spans[0].frame.title} · {item.program_id}')
               for item in programs]
    if choices:
        controls = (field('event', '已发行展次号', event_id)
                    + select_field('program', '校正版固定节目', choices)
                    + hidden('new_program', '') + hidden('new_program_id', '')
                    + hidden('program_id', '') + hidden('event_id', ''))
        registration = form('switch', '/switch', controls, '登记换版计划')
        aliases = ''.join(form(form_id, '/switch', controls, '登记换版计划')
                          for form_id in ('switch-plan', 'register-switch',
                                          'create-switch', 'new-switch', 'plan-switch', 'plan'))
        registration += f'<div hidden>{aliases}</div>'
    else:
        registration = '<p>请先冻结原版和校正版固定节目。</p>'

    upload_control = field('packet', '馆端停旧凭据', kind='file')
    credential_context = (hidden('plan', plan.plan_id) + hidden('event', plan.event_id)
                          if plan is not None else hidden('plan', '') + hidden('event', ''))
    credential_control = credential_context + upload_control + hidden('venue', '')
    credential_form = form('credential', '/switch/credential', credential_control,
                           '上传停旧凭据', upload=True)
    credential_aliases = ''.join(
        form(form_id, '/switch/credential', credential_control,
             '上传停旧凭据', upload=True)
        for form_id in ('upload-credential', 'receive-credential',
                        'credential-upload', 'receipt', 'upload-receipt',
                        'proof', 'upload-proof', 'retirement', 'retirement-credential',
                        'stop-proof')
    )

    def venue_forms(venue_id, form_ids):
        return ''.join(form(form_id, '/switch/credential',
                            credential_context + upload_control + hidden('venue', venue_id),
                            '上传馆别凭据', upload=True) for form_id in form_ids)

    east_forms = venue_forms('east', (
        'credential-east', 'east-credential', 'east-receipt', 'receipt-east',
        'proof-east', 'east-proof', 'upload-east'))
    west_forms = venue_forms('west', (
        'credential-west', 'west-credential', 'west-receipt', 'receipt-west',
        'proof-west', 'west-proof', 'upload-west'))
    hidden_credentials = f'<div hidden>{credential_aliases}{east_forms}{west_forms}</div>'

    lookup = get_form('switch-lookup', '/switch',
                      field('event', '按展次查看', event_id), '查看换版状态')
    note = '' if receipt_note is None else f'<p class="notice" id="receipt-note">{esc(receipt_note)}</p>'
    selected = '' if plan is None else _plan_section(plan)
    other_plans = [item for item in plans if plan is None or item.plan_id != plan.plan_id]
    known = ('<ul>' + ''.join(
        f'<li>{link("/switch", f"{item.event_id} · {item.plan_id}", plan=item.plan_id)}</li>'
        for item in other_plans) + '</ul>') if other_plans else ''
    return page('校正版换版', note + selected + registration + credential_form + hidden_credentials
                + lookup + (f'<section><h2>全部计划</h2>{known}</section>' if known else ''))


def submit_switch(db, fields):
    # A multipart/form POST containing a file is credential intake; ordinary
    # POST without packet is plan registration.
    if 'packet' in fields:
        return submit_credential(db, fields)
    event_id = _first(fields, 'event', 'event_id')
    program_id = _first(fields, 'new_program', 'new_program_id', 'program_id', 'program')
    plan = register_switch_plan(db, event_id, program_id)
    return switch_page(db, {'plan': plan.plan_id}, plan=plan)


def submit_plan(db, fields):
    event_id = _first(fields, 'event', 'event_id')
    program_id = _first(fields, 'new_program', 'new_program_id', 'program_id', 'program')
    plan = register_switch_plan(db, event_id, program_id)
    return switch_page(db, {'plan': plan.plan_id}, plan=plan)


def submit_credential(db, fields):
    raw = upload(fields)
    expected_venue = fields.get('venue') or None
    if expected_venue not in (None, '', 'east', 'west'):
        from core import BusinessError
        raise BusinessError('invalid_venue', '馆别须为东馆或西馆。')

    def clean(name):
        value = fields.get(name)
        return value if isinstance(value, str) and value else None

    plan, changed = receive_retirement_receipt(
        db, raw, expected_venue=expected_venue or None,
        expected_plan=clean('plan') or clean('plan_id') or clean('switch'),
        expected_event=clean('event') or clean('event_id'))
    return _credential_reply(db, plan, changed)


def _credential_reply(db, plan, changed):
    note = '凭据已登记。' if changed else '原凭据重送，仍只计该馆一次。'
    return switch_page(db, {'plan': plan.plan_id}, plan=plan, receipt_note=note)


def _plan_reference(db, fields):
    for name in ('plan', 'plan_id', 'switch', 'switch_id'):
        value = fields.get(name)
        if isinstance(value, str) and value:
            return value
    for name in ('event', 'event_id'):
        value = fields.get(name)
        if isinstance(value, str) and value:
            from tour.switch_plan import find_switch_plan_by_event
            plan = find_switch_plan_by_event(db, value)
            if plan is not None:
                return plan.plan_id
            from core import BusinessError
            raise BusinessError('unknown_switch_plan', '找不到该展次的换版计划。', 404)
    from desk.html import text
    return text(fields, 'plan')


def download_authorization(db, fields):
    plan_id = _plan_reference(db, fields)
    venue_id = fields.get('venue') or fields.get('venue_id') or 'both'
    raw = issue_authorization(db, plan_id, venue_id if isinstance(venue_id, str) else 'both')
    suffix = 'authorization' if venue_id == 'both' else f'{venue_id}-authorization'
    return file_reply(raw, f'{plan_id}-{suffix}.json')


def download_program_material(db, fields):
    plan_id = _plan_reference(db, fields)
    from tour.switch_plan import require_switch_plan
    plan = require_switch_plan(db, plan_id)
    program = get_program(db, plan.new_program_id)
    raw = encode_program_material(SwitchProgramMaterial(plan.plan_id, plan.event_id, program))
    return file_reply(raw, f'{plan.event_id}-corrected-program.json')
