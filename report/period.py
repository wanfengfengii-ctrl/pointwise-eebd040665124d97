from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from core import BusinessError

SHIFT_UTC_OFFSET = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class ShiftPeriod:
    day: str
    shift: str
    first_second: int
    end_second: int

    def contains(self, instant):
        return self.first_second <= instant < self.end_second


def parse_shift(day, shift):
    if shift not in ('AM', 'PM'):
        raise BusinessError('invalid_shift', '班别须为 AM 或 PM。')
    try:
        local_date = date.fromisoformat(day)
        if local_date.isoformat() != day:
            raise ValueError('noncanonical date')
        hour = 0 if shift == 'AM' else 12
        start = datetime.combine(local_date, time(hour), SHIFT_UTC_OFFSET)
        first_second = int(start.timestamp())
    except (ValueError, TypeError, OverflowError, OSError) as exc:
        raise BusinessError('invalid_shift', '营业日期须为有效的 YYYY-MM-DD。') from exc
    return ShiftPeriod(day, shift, first_second, first_second + 12 * 3600)
