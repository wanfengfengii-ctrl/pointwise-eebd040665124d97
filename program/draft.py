import json
from dataclasses import dataclass

from core import BusinessError, identifier, json_bytes, new_id, transaction
from program.frames import Frame, frames_data, validate_frames
from program.timing import Timeline, build_timeline


@dataclass(frozen=True)
class Draft:
    draft_id: str
    frames: tuple[Frame, ...]
    timeline: Timeline


def initialize_drafts(db):
    db.execute('''CREATE TABLE IF NOT EXISTS drafts (
        draft_id TEXT PRIMARY KEY,
        frames BLOB NOT NULL
    )''')


def save_draft(db, frames, draft_id=None):
    frames = validate_frames(frames)
    timeline = build_timeline(frames)
    encoded = json_bytes(frames_data(frames))
    with transaction(db, write=True):
        if draft_id is None:
            draft_id = new_id('draft')
            db.execute('INSERT INTO drafts VALUES (?, ?)', (draft_id, encoded))
        else:
            identifier(draft_id, '草稿号')
            changed = db.execute('UPDATE drafts SET frames = ? WHERE draft_id = ?', (encoded, draft_id))
            if changed.rowcount != 1:
                raise BusinessError('unknown_draft', '找不到该草稿。', 404)
    return Draft(draft_id, frames, timeline)


def load_draft(db, draft_id):
    identifier(draft_id, '草稿号')
    row = db.execute('SELECT frames FROM drafts WHERE draft_id = ?', (draft_id,)).fetchone()
    if row is None:
        raise BusinessError('unknown_draft', '找不到该草稿。', 404)
    frames = validate_frames(json.loads(row['frames']))
    return Draft(draft_id, frames, build_timeline(frames))
