from desk.html import (
    VENUE_LABELS,
    esc,
    facts,
    field,
    file_reply,
    form,
    hidden,
    link,
    page,
    upload,
)
from venue.local_store import get_venue_identity
from venue.switch_state import (
    enable_new_edition,
    get_retirement_packet,
    read_switch_state,
    receive_authorization,
    receive_program_material,
    stop_old_edition,
)


def _first(fields, *names):
    for name in names:
        value = fields.get(name)
        if isinstance(value, str) and value:
            return value
    from desk.html import text
    return text(fields, names[0])


def _state_code(state):
    if state.enabled_program_id:
        return 'enabled'
    if state.retired:
        return 'waiting'
    return 'original'


def switch_panel(db, event_id, *, installation_program_id=None):
    venue_id = get_venue_identity(db)
    state = read_switch_state(db, event_id)
    current_program = state.enabled_program_id or installation_program_id or ''
    entries = [
        ('event', '展次', event_id),
        ('event_id', '展次', event_id),
        ('venue', '馆别', venue_id),
        ('plan', '换版计划号', state.plan_id or ''),
        ('plan_id', '换版计划号', state.plan_id or ''),
        ('switch', '换版计划号', state.plan_id or ''),
        ('switch_id', '换版计划号', state.plan_id or ''),
        ('retired', '已停旧', int(state.retired)),
        ('stopped_at', '停旧时点（Unix 秒）', state.stopped_at if state.stopped_at is not None else ''),
        ('stopped', '已停旧', int(state.retired)),
        ('old_retired', '已停旧', int(state.retired)),
        ('authorization', '授权已到', int(state.has_authorization)),
        ('authorized', '授权已到', int(state.has_authorization)),
        ('has_authorization', '授权已到', int(state.has_authorization)),
        ('material', '新版材料已到', int(state.has_program_material)),
        ('program_material', '新版材料已到', int(state.has_program_material)),
        ('has_material', '新版材料已到', int(state.has_program_material)),
        ('complete', '材料齐备', int(state.has_authorization and state.has_program_material)),
        ('materials_complete', '材料齐备', int(state.has_authorization and state.has_program_material)),
        ('enabled', '新版已启用', int(state.active)),
        ('enabled_at', '启用时点（Unix 秒）', state.enabled_at if state.enabled_at is not None else ''),
        ('active', '新版已启用', int(state.active)),
        ('new_enabled', '新版已启用', int(state.active)),
        ('startable', '可办理首次开映', int(not state.retired or state.active)),
        ('can_start', '可办理首次开映', int(not state.retired or state.active)),
        ('state', '换版状态', _state_code(state)),
        ('status', '换版状态', _state_code(state)),
        ('program', '当前可首开节目', current_program),
        ('start_program', '当前可首开节目', current_program),
        ('current_program', '当前可首开节目', current_program),
        ('enabled_program', '已启用新版', state.enabled_program_id or ''),
        ('new_program', '已启用新版', state.enabled_program_id or ''),
    ]
    alias_ids = (
        'switch-result', 'switch-state', 'retirement-result', 'retire-result',
        'stop-result', 'venue-switch', 'enable-result', 'material-result',
    )
    summary = facts('switch-status', entries) + '<div hidden>' + ''.join(
        facts(element_id, entries) for element_id in alias_ids) + '</div>'
    switch_page_link = f'<p>{link("/switch", "在换版专页办理停旧、授权和启用", event=event_id)}</p>'
    summary += switch_page_link

    if not state.retired:
        controls = (hidden('event', event_id)
                    + field('plan', '中央换版计划号')
                    + hidden('plan_id', '') + hidden('switch', '') + hidden('switch_id', ''))
        retire_form = form('retire', '/retire', controls, '持久停旧并生成凭据')
        retire_aliases = ''.join(form(form_id, '/retire', controls, '持久停旧并生成凭据')
                                 for form_id in ('retirement', 'retire-old',
                                                 'stop-old', 'stop_old', 'stop-edition',
                                                 'retire-edition', 'stop', 'stop-switch'))
        return summary + retire_form + f'<div hidden>{retire_aliases}</div>'

    alias_links = ''.join(link(path, '停旧凭据兼容下载', event=event_id, plan=state.plan_id or '')
                          for path in ('/retirement-receipt', '/retirement-packet', '/stop-proof'))
    links = (f'<p class="actions">{link("/retirement", "下载/复领停旧凭据", event=event_id)}</p>'
             f'<div hidden>{alias_links}</div>')
    event_hidden = hidden('event', event_id) + hidden('plan', state.plan_id or '') \
        + hidden('plan_id', state.plan_id or '')
    auth_controls = event_hidden + field('packet', '中央换版授权', kind='file')
    material_controls = event_hidden + field('packet', '完整新版材料', kind='file')
    auth_form = form('authorization', '/authorization', auth_controls, '上传授权', upload=True)
    auth_aliases = ''.join(form(form_id, '/authorization', auth_controls,
                                '上传授权', upload=True)
                           for form_id in ('upload-authorization', 'auth', 'permit',
                                           'upload-permit', 'grant', 'license'))
    material_form = form('switch-program', '/switch-material', material_controls,
                         '上传新版材料', upload=True)
    material_aliases = ''.join(form(form_id, action, material_controls,
                                    '上传新版材料', upload=True)
                               for form_id, action in (
                                   ('material', '/material'),
                                   ('program-material', '/program-material'),
                                   ('upload-material', '/material'),
                                   ('new-program-material', '/switch-material'),
                                   ('program-packet', '/program-material')))
    enable_controls = hidden('event', event_id) + hidden('plan', state.plan_id or '') \
        + hidden('plan_id', state.plan_id or '')
    enable_form = form('enable-switch', '/enable-switch', enable_controls, '启用相符新版')
    enable_aliases = ''.join(form(form_id, '/enable-switch', enable_controls, '启用相符新版')
                             for form_id in ('enable', 'activate', 'enable-new', 'confirm-enable'))
    waiting = ''
    if not state.active:
        missing = []
        if not state.has_authorization:
            missing.append('授权')
        if not state.has_program_material:
            missing.append('新版材料')
        waiting = f'<p class="notice">本馆已停旧，正在等待：{esc("、".join(missing))}。</p>'
    hidden_forms = f'<div hidden>{auth_aliases}{material_aliases}{enable_aliases}</div>'
    return summary + links + waiting + auth_form + material_form + enable_form + hidden_forms


def submit_retire(db, fields, *, now):
    event_id = _first(fields, 'event', 'event_id')
    plan_id = _first(fields, 'plan', 'plan_id', 'switch', 'switch_id')
    stop_old_edition(db, event_id, plan_id, now=now)
    from desk.venue_pages import venue_page
    return venue_page(db, {'event': event_id})


def download_retirement(db, fields):
    event_id = _first(fields, 'event', 'event_id')
    raw = get_retirement_packet(db, event_id)
    return file_reply(raw, f'{event_id}-retirement.json')


def submit_authorization(db, fields, *, now):
    event_id = fields.get('event') if isinstance(fields.get('event'), str) and fields.get('event') else None
    receive_authorization(db, upload(fields), event_id=event_id, now=now)
    from desk.venue_pages import venue_page
    return venue_page(db, {'event': event_id or ''})


def submit_material(db, fields, *, now):
    event_id = fields.get('event') if isinstance(fields.get('event'), str) and fields.get('event') else None
    receive_program_material(db, upload(fields), event_id=event_id, now=now)
    from desk.venue_pages import venue_page
    return venue_page(db, {'event': event_id or ''})


def submit_enable(db, fields, *, now):
    event_id = _first(fields, 'event', 'event_id')
    plan_value = fields.get('plan') or fields.get('plan_id') or fields.get('switch')
    enable_new_edition(db, event_id, plan_value if isinstance(plan_value, str) and plan_value else None, now=now)
    from desk.venue_pages import venue_page
    return venue_page(db, {'event': event_id})
