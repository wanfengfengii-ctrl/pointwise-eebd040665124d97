from core import transaction
from desk.html import VENUE_LABELS, esc, facts, field, form, frame_panel, get_form, hidden, integer, link, page, select_field, text, time_picker, upload
from program.timing import locate_frame
from venue.activity import read_activity
from venue.close import finish
from venue.install import get_installation, install_packet, list_installed_events
from venue.local_store import get_venue_identity
from venue.rehearsal import preview
from venue.screening import get_screening, remaining_starts, start


def _history(title, screenings):
    if not screenings:
        return f'<section><h2>{title}</h2><p>暂无场次。</p></section>'
    rows = []
    for item in screenings:
        state = '已结束' if item.ended_at is not None else '待结束'
        caption = f'{item.request_id} · {item.screening_id}'
        rows.append(f'<li>{link("/screening", caption, id=item.screening_id)} <span>{esc(state)}</span></li>')
    return f'<section><h2>{title}</h2><ul>{"".join(rows)}</ul></section>'


def venue_page(db, fields, *, trial=None):
    venue = get_venue_identity(db)
    title = f'{VENUE_LABELS[venue]}放映'
    install = form('install', '/install', field('packet', '本馆开馆件', kind='file'), '安装开馆件', upload=True)
    events = list_installed_events(db)
    selection = ''
    if events:
        selection = get_form('event-picker', '/venue', select_field('event', '已安装展次', [(i, i) for i in events]), '打开展次')
    event_id = fields.get('event')
    if not event_id:
        return page(title, install + selection + ('' if events else '<p>请先安装开馆件。</p>'))
    activity = read_activity(db, event_id)
    program = activity.installed.program
    summary = facts('venue-result', [
        ('event', '展次', event_id), ('program', '固定节目', program.program_id), ('venue', '馆别', venue),
        ('remaining', '可用放映次数', activity.remaining), ('rehearsals', '试映记录', len(activity.rehearsals)),
        ('started', '正式开映', len(activity.screenings)), ('open', '待结束', len(activity.pending)),
    ])
    trial_result = '' if trial is None else frame_panel(trial[0].at_ms, trial[1])
    event_input = hidden('event', event_id)
    trial_form = form('preview', '/preview', event_input + field('ms', '试映时点（毫秒）', 0, kind='number', minimum=0), '试映')
    start_form = form('start', '/start', event_input + field('request', '开映申请号'), '办理开映或复领')
    history = _history('待结束场次', activity.pending) + _history('场次历史', activity.screenings)
    return page(title, summary + trial_result + trial_form + start_form + link('/shift', '本馆封报', event=event_id)
                + history + selection + install)


def submit_install(db, fields):
    installed = install_packet(db, upload(fields))
    return venue_page(db, {'event': installed.event_id})


def submit_preview(db, fields, *, now):
    event_id = text(fields, 'event')
    trial = preview(db, event_id, integer(fields, 'ms'), now=now)
    return venue_page(db, {'event': event_id}, trial=trial)


def submit_start(db, fields, *, now):
    receipt = start(db, text(fields, 'event'), text(fields, 'request'), now=now)
    return screening_page(db, {'id': receipt.screening.screening_id}, receipt=receipt)


def screening_page(db, fields, *, receipt=None):
    screening_id = text(fields, 'id')
    with transaction(db):
        item = get_screening(db, screening_id) if receipt is None else receipt.screening
        program = get_installation(db, item.event_id).program
        balance = remaining_starts(db, item.event_id) if receipt is None else receipt.remaining
    at_ms = integer(fields, 'ms') if 'ms' in fields else 0
    frame = locate_frame(program.timeline, at_ms)
    state = 'open' if item.ended_at is None else 'finished'
    summary = facts('screening-result', [
        ('id', '开映号', screening_id), ('event', '展次', item.event_id), ('request', '申请号', item.request_id),
        ('program', '固定节目', item.program_id), ('remaining', '可用放映次数', balance),
        ('state', '场次状态', state), ('ended', '结束时点（Unix 秒）', item.ended_at if item.ended_at is not None else ''),
    ])
    finish_form = '' if item.ended_at is not None else form('finish', '/finish', hidden('id', screening_id), '确认结束')
    return page('正式放映', summary + frame_panel(at_ms, frame) + time_picker('screening-picker', '/screening', 'id', screening_id, at_ms)
                + finish_form + link('/venue', '返回本馆展次', event=item.event_id))


def submit_finish(db, fields, *, now):
    item = finish(db, text(fields, 'id'), now=now)
    return screening_page(db, {'id': item.screening_id})
