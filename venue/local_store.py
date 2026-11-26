from core import BusinessError, connect, transaction
from tour.quotas import require_venue


def initialize_venue_store(db, venue_id):
    require_venue(venue_id)
    with transaction(db, write=True):
        db.execute('''CREATE TABLE IF NOT EXISTS venue_identity (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            venue_id TEXT NOT NULL CHECK (venue_id IN ('east', 'west'))
        )''')
        db.execute('INSERT OR IGNORE INTO venue_identity VALUES (1, ?)', (venue_id,))
        if get_venue_identity(db) != venue_id:
            raise BusinessError('venue_identity_conflict', '该数据库已绑定另一馆。', 409)
        db.execute('''CREATE TABLE IF NOT EXISTS installations (
            event_id TEXT PRIMARY KEY,
            packet BLOB NOT NULL
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS rehearsals (
            rehearsal_id INTEGER PRIMARY KEY,
            event_id TEXT NOT NULL REFERENCES installations(event_id),
            at_ms TEXT NOT NULL,
            recorded_at INTEGER NOT NULL
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS screenings (
            screening_id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL REFERENCES installations(event_id),
            request_id TEXT NOT NULL,
            program_id TEXT NOT NULL,
            started_at INTEGER NOT NULL,
            ended_at INTEGER CHECK (ended_at >= started_at),
            UNIQUE (event_id, request_id)
        )''')
        db.execute('CREATE INDEX IF NOT EXISTS rehearsals_by_event ON rehearsals(event_id, recorded_at)')
        db.execute('CREATE INDEX IF NOT EXISTS screenings_by_event ON screenings(event_id, started_at)')


def open_venue_store(path, venue_id):
    db = connect(path)
    try:
        initialize_venue_store(db, venue_id)
    except BaseException:
        db.close()
        raise
    return db


def get_venue_identity(db):
    row = db.execute('SELECT venue_id FROM venue_identity WHERE singleton = 1').fetchone()
    if row is None:
        raise BusinessError('unbound_venue', '馆库尚未配置馆身份。', 409)
    return row['venue_id']
