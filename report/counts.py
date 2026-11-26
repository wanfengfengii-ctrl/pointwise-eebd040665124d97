from dataclasses import dataclass

from core import BusinessError, identifier


@dataclass(frozen=True)
class ShiftScreening:
    screening_id: str
    request_id: str
    started_at: int
    ended_at: int | None


@dataclass(frozen=True)
class ShiftCounts:
    rehearsals: int
    started: int
    finished: int
    open: int


def _counts(rehearsals, rows):
    finished = sum(row.ended_at is not None for row in rows)
    return ShiftCounts(rehearsals, len(rows), finished, len(rows) - finished)


def collect_shift_activity(activity, period):
    rehearsal_count = sum(period.contains(record.recorded_at) for record in activity.rehearsals)
    rows = tuple(ShiftScreening(item.screening_id, item.request_id, item.started_at, item.ended_at)
                 for item in activity.screenings if period.contains(item.started_at))
    return _counts(rehearsal_count, rows), rows


def validate_shift_counts(counts, rows, period):
    totals = (counts.rehearsals, counts.started, counts.finished, counts.open)
    if any(type(value) is not int or value < 0 for value in totals):
        raise BusinessError('invalid_report_counts', '班报计数须为非负整数。')
    screening_ids = set()
    request_ids = set()
    for row in rows:
        identifier(row.screening_id, '开映号')
        identifier(row.request_id, '开映申请号')
        if row.screening_id in screening_ids or row.request_id in request_ids:
            raise BusinessError('invalid_report_counts', '班报出现重复的场次或申请。')
        screening_ids.add(row.screening_id)
        request_ids.add(row.request_id)
        if type(row.started_at) is not int or not period.contains(row.started_at):
            raise BusinessError('invalid_report_counts', '班报记录的开映时点不在本班。')
        if row.ended_at is not None and (type(row.ended_at) is not int or row.ended_at < row.started_at):
            raise BusinessError('invalid_report_counts', '班报记录的结束时点非法。')
    if counts != _counts(counts.rehearsals, rows):
        raise BusinessError('invalid_report_counts', '正式开映、已结束或待结束计数与明细不符。')
