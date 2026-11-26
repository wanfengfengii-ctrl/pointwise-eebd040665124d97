from dataclasses import dataclass

from core import BusinessError, identifier, moment, new_id, transaction
from venue.install import get_installation


@dataclass(frozen=True)
class Screening:
    screening_id: str
    event_id: str
    request_id: str
    program_id: str
    started_at: int
    ended_at: int | None


@dataclass(frozen=True)
class StartReceipt:
    screening: Screening
    remaining: int


def _screening(row):
    return Screening(row['screening_id'], row['event_id'], row['request_id'], row['program_id'],
                     row['started_at'], row['ended_at'])


def remaining_starts(db, event_id):
    installed = get_installation(db, event_id)
    count = db.execute('SELECT COUNT(*) FROM screenings WHERE event_id = ?', (event_id,)).fetchone()[0]
    return installed.quota - count


def start(db, event_id, request_id, *, now=None):
    identifier(request_id, '开映申请号')
    with transaction(db, write=True):
        installed = get_installation(db, event_id)
        existing = db.execute('SELECT * FROM screenings WHERE event_id = ? AND request_id = ?',
                              (event_id, request_id)).fetchone()
        balance = remaining_starts(db, event_id)
        if existing is not None:
            return StartReceipt(_screening(existing), balance)
        if balance <= 0:
            raise BusinessError('no_quota', '本馆已用完此展次的放映分额。', 409)
        screening = Screening(new_id('screening'), event_id, request_id,
                              installed.program.program_id, moment(now), None)
        db.execute('''INSERT INTO screenings
            (screening_id, event_id, request_id, program_id, started_at, ended_at)
            VALUES (?, ?, ?, ?, ?, NULL)''',
            (screening.screening_id, event_id, request_id, screening.program_id, screening.started_at))
        return StartReceipt(screening, balance - 1)


def get_screening(db, screening_id):
    identifier(screening_id, '开映号')
    row = db.execute('SELECT * FROM screenings WHERE screening_id = ?', (screening_id,)).fetchone()
    if row is None:
        raise BusinessError('unknown_screening', '找不到本馆的该场放映。', 404)
    return _screening(row)


def list_screenings(db, event_id):
    rows = db.execute('SELECT * FROM screenings WHERE event_id = ? ORDER BY started_at, screening_id', (event_id,))
    return tuple(_screening(row) for row in rows)
