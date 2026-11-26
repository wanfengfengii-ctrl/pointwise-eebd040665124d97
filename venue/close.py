from core import BusinessError, moment, transaction
from venue.screening import get_screening


def finish(db, screening_id, *, now=None):
    with transaction(db, write=True):
        screening = get_screening(db, screening_id)
        if screening.ended_at is not None:
            return screening
        ended_at = moment(now)
        if ended_at < screening.started_at:
            raise BusinessError('invalid_clock', '首次结束时点不得早于开映时点。')
        db.execute('UPDATE screenings SET ended_at = ? WHERE screening_id = ?', (ended_at, screening_id))
        return get_screening(db, screening_id)
