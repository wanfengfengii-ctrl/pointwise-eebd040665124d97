from dataclasses import dataclass

from core import BusinessError, identifier, transaction
from program.edition import ProgramEdition
from tour.venue_packet import decode_opening_packet
from venue.local_store import get_venue_identity


@dataclass(frozen=True)
class Installation:
    event_id: str
    issue_id: str
    venue_id: str
    program: ProgramEdition
    quota: int


def _installed(packet):
    return Installation(packet.event_id, packet.issue_id, packet.venue_id, packet.program, packet.quota)


def install_packet(db, raw):
    packet = decode_opening_packet(raw)
    with transaction(db, write=True):
        if packet.venue_id != get_venue_identity(db):
            raise BusinessError('wrong_venue', '开馆件的收件馆与本馆不符。')
        row = db.execute('SELECT packet FROM installations WHERE event_id = ?', (packet.event_id,)).fetchone()
        if row is not None:
            if row['packet'] != raw:
                raise BusinessError('installation_conflict', '该展次已使用另一份开馆件安装。', 409)
        else:
            db.execute('INSERT INTO installations VALUES (?, ?)', (packet.event_id, raw))
    return _installed(packet)


def get_installation(db, event_id):
    identifier(event_id, '展次号')
    row = db.execute('SELECT packet FROM installations WHERE event_id = ?', (event_id,)).fetchone()
    if row is None:
        raise BusinessError('unknown_installation', '本馆未安装此展次。', 404)
    return _installed(decode_opening_packet(row['packet']))


def list_installed_events(db):
    return tuple(row['event_id'] for row in db.execute('SELECT event_id FROM installations ORDER BY event_id'))
