from dataclasses import dataclass

from core import moment, transaction
from program.timing import FrameSpan, locate_frame
from venue.install import get_installation


@dataclass(frozen=True)
class Rehearsal:
    rehearsal_id: int
    event_id: str
    at_ms: int
    recorded_at: int


def preview(db, event_id, at_ms, *, now=None) -> tuple[Rehearsal, FrameSpan | None]:
    with transaction(db, write=True):
        installed = get_installation(db, event_id)
        frame = locate_frame(installed.program.timeline, at_ms)
        recorded_at = moment(now)
        cursor = db.execute('INSERT INTO rehearsals (event_id, at_ms, recorded_at) VALUES (?, ?, ?)',
                            (event_id, str(at_ms), recorded_at))
        record = Rehearsal(cursor.lastrowid, event_id, at_ms, recorded_at)
    return record, frame


def list_rehearsals(db, event_id):
    rows = db.execute('''SELECT * FROM rehearsals WHERE event_id = ?
        ORDER BY recorded_at, rehearsal_id''', (event_id,))
    return tuple(Rehearsal(row['rehearsal_id'], row['event_id'], int(row['at_ms']), row['recorded_at'])
                 for row in rows)
