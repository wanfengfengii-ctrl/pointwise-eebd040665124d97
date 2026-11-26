from dataclasses import dataclass

from core import transaction
from venue.install import Installation, get_installation
from venue.rehearsal import Rehearsal, list_rehearsals
from venue.screening import Screening, list_screenings


@dataclass(frozen=True)
class VenueActivity:
    installed: Installation
    rehearsals: tuple[Rehearsal, ...]
    screenings: tuple[Screening, ...]
    pending: tuple[Screening, ...]
    remaining: int


def _read(db, event_id):
    installed = get_installation(db, event_id)
    rehearsals = list_rehearsals(db, event_id)
    screenings = list_screenings(db, event_id)
    pending = tuple(item for item in screenings if item.ended_at is None)
    return VenueActivity(installed, rehearsals, screenings, pending, installed.quota - len(screenings))


def read_activity(db, event_id):
    if db.in_transaction:
        return _read(db, event_id)
    with transaction(db):
        return _read(db, event_id)
