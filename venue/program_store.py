import json

from core import BusinessError, json_bytes
from program.edition import ProgramEdition, decode_program, program_data


def initialize_program_registry(db):
    db.execute('''CREATE TABLE IF NOT EXISTS venue_programs (
        program_id TEXT PRIMARY KEY,
        snapshot BLOB NOT NULL
    )''')


def store_venue_program(db, program: ProgramEdition):
    """Persist a complete program snapshot readable by this venue."""
    snapshot = json_bytes(program_data(program))
    db.execute('''INSERT INTO venue_programs (program_id, snapshot)
                  VALUES (?, ?)
                  ON CONFLICT(program_id) DO UPDATE SET snapshot = excluded.snapshot''',
               (program.program_id, snapshot))


def get_venue_program(db, program_id: str) -> ProgramEdition:
    row = db.execute('SELECT snapshot FROM venue_programs WHERE program_id = ?',
                    (program_id,)).fetchone()
    if row is not None:
        return decode_program(json.loads(row['snapshot']))

    # Older databases only carry the opening program inside their opening
    # packet.  Decode those packets as a compatible fallback.
    from tour.venue_packet import decode_opening_packet
    for packet_row in db.execute('SELECT packet FROM installations'):
        program = decode_opening_packet(packet_row['packet']).program
        if program.program_id == program_id:
            return program
    raise BusinessError('program_material_missing', '本馆缺少该固定节目的完整材料。', 404)
