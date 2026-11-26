from dataclasses import dataclass

from core import BusinessError, identifier, moment, new_id, transaction
from venue.install import get_installation
from venue.program_store import get_venue_program
from venue.switch_state import current_startable_program, read_switch_state


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


def start(db, event_id, request_id, *, now=None, form_program_id=None):
    identifier(request_id, '开映申请号')
    if form_program_id is not None:
        identifier(form_program_id, '表单节目号')
    with transaction(db, write=True):
        installed = get_installation(db, event_id)
        existing = db.execute('SELECT * FROM screenings WHERE event_id = ? AND request_id = ?',
                              (event_id, request_id)).fetchone()
        balance = remaining_starts(db, event_id)
        if existing is not None:
            return StartReceipt(_screening(existing), balance)

        state = read_switch_state(db, event_id)
        if form_program_id is not None:
            if form_program_id == installed.program.program_id:
                if state.enabled_program_id is not None:
                    raise BusinessError(
                        'stale_start_form',
                        '这是旧版开映表单，不能开出新版场次；请刷新后使用当前节目表单。', 409)
                if state.retired:
                    raise BusinessError(
                        'old_edition_retired',
                        '旧版已停旧，未办申请不能用旧表单首次开映。', 409)
                program = installed.program
            elif state.enabled_program_id is not None \
                    and form_program_id == state.enabled_program_id:
                program = get_venue_program(db, form_program_id)
            elif state.retired:
                raise BusinessError(
                    'stale_start_form',
                    '开映表单不是当前已启用节目，请刷新后重新提交。', 409)
            else:
                raise BusinessError('unknown_program', '开映表单指向找不到的固定节目。', 404)
        else:
            program, state = current_startable_program(db, event_id)

        if balance <= 0:
            raise BusinessError('no_quota', '本馆已用完此展次的放映分额。', 409)
        screening = Screening(new_id('screening'), event_id, request_id,
                              program.program_id, moment(now), None)
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
