from core import BusinessError
from desk.html import VENUE_LABELS, facts, field, file_reply, form, get_form, integer, link, page, select_field, text
from program.edition import list_programs
from tour.events import find_issue
from tour.issue import get_issued_packet, issue_tour
from tour.quotas import VENUE_IDS


def _issue_result(issued):
    summary = facts('issue-result', [
        ('event', '展次', issued.event_id), ('issue', '发行号', issued.issue_id),
        ('program', '固定节目', issued.program_id), ('east', '东馆分额', issued.quotas.east),
        ('west', '西馆分额', issued.quotas.west),
    ])
    links = ' · '.join(link('/opening', f'下载{VENUE_LABELS[venue]}开馆件', event=issued.event_id, venue=venue)
                       for venue in VENUE_IDS)
    return summary + f'<p class="actions">{links}</p>'


def issue_page(db, fields):
    event_id = fields.get('event', '')
    lookup = get_form('issue-lookup', '/issue', field('event', '已发行展次号', event_id), '领取原开馆件')
    result = ''
    if event_id:
        issued = find_issue(db, event_id)
        if issued is None:
            raise BusinessError('unknown_issue', '找不到该展次发行。', 404)
        result = _issue_result(issued)
    programs = list_programs(db)
    if not programs:
        return page('展次发行', lookup + '<p>请先冻结一份节目。</p>' + link('/draft', '编排节目'))
    choices = [(item.program_id, f'{item.timeline.spans[0].frame.title} · {item.program_id}') for item in programs]
    controls = field('event', '展次号') + select_field('program', '固定节目', choices)
    controls += field('east', '东馆分额', 3, kind='number', minimum=0)
    controls += field('west', '西馆分额', 1, kind='number', minimum=0)
    return page('展次发行', result + form('issue', '/issue', controls, '发行并领取馆件') + lookup)


def submit_issue(db, fields):
    issued = issue_tour(db, text(fields, 'event'), text(fields, 'program'), integer(fields, 'east'), integer(fields, 'west'))
    return issue_page(db, {'event': issued.event_id})


def download_opening_packet(db, fields):
    event_id, venue = text(fields, 'event'), text(fields, 'venue')
    raw = get_issued_packet(db, event_id, venue)
    return file_reply(raw, f'{event_id}-{venue}-opening.json')
