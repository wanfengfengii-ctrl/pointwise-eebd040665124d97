from dataclasses import asdict, dataclass

from core import BusinessError, exact_fields, identifier, pack, unpack
from report.counts import ShiftCounts, ShiftScreening, validate_shift_counts
from report.period import ShiftPeriod, parse_shift
from tour.quotas import require_venue


@dataclass(frozen=True)
class ShiftReport:
    report_id: str
    event_id: str
    venue_id: str
    program_id: str
    period: ShiftPeriod
    counts: ShiftCounts
    screenings: tuple[ShiftScreening, ...]


def encode_shift_report(report):
    return pack('shift-report', {
        'report_id': report.report_id, 'event_id': report.event_id, 'venue_id': report.venue_id,
        'program_id': report.program_id, 'day': report.period.day, 'shift': report.period.shift,
        'counts': asdict(report.counts), 'screenings': [asdict(row) for row in report.screenings],
    })


def decode_shift_report(raw):
    try:
        item = exact_fields(unpack('shift-report', raw), 'report_id', 'event_id', 'venue_id', 'program_id',
                            'day', 'shift', 'counts', 'screenings')
        period = parse_shift(item['day'], item['shift'])
        counts = ShiftCounts(**exact_fields(item['counts'], 'rehearsals', 'started', 'finished', 'open'))
        if not isinstance(item['screenings'], list):
            raise BusinessError('invalid_report_counts', '班报须提供正式场次明细。')
        rows = tuple(ShiftScreening(**exact_fields(row, 'screening_id', 'request_id', 'started_at', 'ended_at'))
                     for row in item['screenings'])
        validate_shift_counts(counts, rows, period)
        return ShiftReport(identifier(item['report_id'], '班报号'), identifier(item['event_id'], '展次号'),
                           require_venue(item['venue_id']), identifier(item['program_id'], '节目号'),
                           period, counts, rows)
    except BusinessError as exc:
        if exc.code == 'invalid_packet':
            raise
        raise BusinessError('invalid_packet', f'班报无效。{exc}') from exc
