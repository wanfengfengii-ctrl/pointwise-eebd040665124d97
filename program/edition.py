import json
from dataclasses import dataclass

from core import BusinessError, exact_fields, identifier, json_bytes, new_id, transaction
from program.draft import load_draft
from program.timing import Timeline, decode_timeline, timeline_data


@dataclass(frozen=True)
class ProgramEdition:
    program_id: str
    timeline: Timeline


def initialize_program_editions(db):
    db.execute('''CREATE TABLE IF NOT EXISTS program_editions (
        program_id TEXT PRIMARY KEY,
        draft_id TEXT NOT NULL REFERENCES drafts(draft_id),
        snapshot BLOB NOT NULL
    )''')


def program_data(program):
    return {'program_id': program.program_id, 'timeline': timeline_data(program.timeline)}


def decode_program(value):
    exact_fields(value, 'program_id', 'timeline')
    return ProgramEdition(identifier(value['program_id'], '节目号'), decode_timeline(value['timeline']))


def freeze_program(db, draft_id):
    with transaction(db, write=True):
        draft = load_draft(db, draft_id)
        program = ProgramEdition(new_id('program'), draft.timeline)
        db.execute('INSERT INTO program_editions VALUES (?, ?, ?)',
                   (program.program_id, draft_id, json_bytes(program_data(program))))
    return program


def get_program(db, program_id):
    identifier(program_id, '节目号')
    row = db.execute('SELECT snapshot FROM program_editions WHERE program_id = ?', (program_id,)).fetchone()
    if row is None:
        raise BusinessError('unknown_program', '找不到该固定节目。', 404)
    return decode_program(json.loads(row['snapshot']))


def list_programs(db):
    rows = db.execute('SELECT snapshot FROM program_editions ORDER BY rowid DESC')
    return tuple(decode_program(json.loads(row['snapshot'])) for row in rows)
