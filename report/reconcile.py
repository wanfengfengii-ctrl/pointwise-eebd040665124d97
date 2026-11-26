from dataclasses import dataclass

from core import BusinessError
from report.report_packet import ShiftReport, decode_shift_report
from tour.quotas import VENUE_IDS


@dataclass(frozen=True)
class Reconciliation:
    event_id: str
    east: ShiftReport
    west: ShiftReport


def compare_reports(left, right):
    reports = (decode_shift_report(left), decode_shift_report(right))
    if reports[0].event_id != reports[1].event_id:
        raise BusinessError('different_events', '两份班报必须属于同一展次。')
    if reports[0].venue_id == reports[1].venue_id:
        raise BusinessError('same_venue', '须各选一份东馆和西馆的班报。')
    by_venue = {report.venue_id: report for report in reports}
    east, west = (by_venue[venue] for venue in VENUE_IDS)
    return Reconciliation(east.event_id, east, west)
