from desk.html import VENUE_LABELS, facts, field, file_reply, form, get_form, link, page, select_field, table, text, upload
from report.intake import accept_report, get_accepted_report, list_accepted_reports
from report.reconcile import compare_reports
from report.report_packet import decode_shift_report
from report.shift import get_sealed_report, seal_shift


def _report_facts(element_id, report):
    counts = report.counts
    return facts(element_id, [
        ('report', '班报号', report.report_id), ('event', '展次', report.event_id),
        ('venue', '馆别', VENUE_LABELS[report.venue_id]), ('day', '营业日期', report.period.day),
        ('shift', '班别', report.period.shift), ('program', '固定节目', report.program_id),
        ('rehearsals', '试映', counts.rehearsals), ('started', '正式开映', counts.started),
        ('finished', '已结束', counts.finished), ('open', '待结束', counts.open),
    ])


def _details(report):
    if not report.screenings:
        return '<p>本班没有正式开映场次。</p>'
    return table(('开映号', '申请号', '开映时点（Unix 秒）', '结束时点（Unix 秒）'),
                 ((row.screening_id, row.request_id, row.started_at, row.ended_at if row.ended_at is not None else '待结束')
                  for row in report.screenings))


def _shift_fields(event_id):
    shifts = [('AM', 'AM · 00:00–12:00'), ('PM', 'PM · 12:00–次日 00:00')]
    return field('event', '展次号', event_id) + field('day', '营业日期', kind='date') + select_field('shift', '班别', shifts)


def shift_page(db, fields, *, report=None):
    event_id = report.event_id if report is not None else fields.get('event', '')
    controls = _shift_fields(event_id)
    result = ''
    if report is not None:
        result = _report_facts('sealed-result', report) + _details(report)
        result += link('/sealed', '下载本馆班报', event=report.event_id, day=report.period.day, shift=report.period.shift)
    return page('馆端班报', result + form('seal', '/seal', controls, '封报或复领')
                + get_form('report-lookup', '/sealed', controls, '下载已封班报'))


def submit_seal(db, fields):
    report = seal_shift(db, text(fields, 'event'), text(fields, 'day'), text(fields, 'shift'))
    return shift_page(db, fields, report=report)


def download_report(db, fields):
    event_id = text(fields, 'event')
    raw = get_sealed_report(db, event_id, text(fields, 'day'), text(fields, 'shift'))
    report = decode_shift_report(raw)
    return file_reply(raw, f'{report.report_id}.json')


def download_accepted(db, fields):
    report_id = text(fields, 'report')
    return file_reply(get_accepted_report(db, report_id), f'{report_id}.json')


def intake_page(db, fields, *, accepted=None):
    notes = _report_facts('accepted-result', accepted) if accepted is not None else ''
    reports = list_accepted_reports(db)
    parts = [notes, form('intake', '/intake', field('packet', '馆端班报', kind='file'), '接纳原班报', upload=True)]
    if reports:
        choices = [(report.report_id,
                    f'{VENUE_LABELS[report.venue_id]} · {report.event_id} · {report.period.day} {report.period.shift} · {report.report_id}')
                   for report in reports]
        links = ''.join(f'<li>{link("/accepted", caption, report=key)}</li>' for key, caption in choices)
        parts.append(f'<section><h2>已接纳原件</h2><ul>{links}</ul></section>')
        parts.append(form('compare', '/compare', select_field('left', '第一份班报', choices)
                          + select_field('right', '第二份班报', choices), '核对两馆班报'))
    return page('交班工作台', ''.join(parts))


def submit_intake(db, fields):
    report = accept_report(db, upload(fields))
    return intake_page(db, fields, accepted=report)


def submit_compare(db, fields):
    first = get_accepted_report(db, text(fields, 'left'))
    second = get_accepted_report(db, text(fields, 'right'))
    result = compare_reports(first, second)
    sections = []
    for report in (result.east, result.west):
        name = VENUE_LABELS[report.venue_id]
        sections.append(f'<section><h2>{name}</h2>' + _report_facts(f'compare-{report.venue_id}', report)
                        + _details(report) + '</section>')
    return page('双馆班报核对', '<div class="columns">' + ''.join(sections) + '</div>'
                + link('/intake', '返回已接纳班报'))
