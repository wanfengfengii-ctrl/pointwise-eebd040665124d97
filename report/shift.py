from core import BusinessError, identifier, new_id, transaction
from report.counts import collect_shift_activity
from report.period import parse_shift
from report.report_packet import ShiftReport, decode_shift_report, encode_shift_report
from venue.activity import read_activity


def initialize_shift_reports(db):
    db.execute('''CREATE TABLE IF NOT EXISTS sealed_reports (
        event_id TEXT NOT NULL REFERENCES installations(event_id),
        day TEXT NOT NULL,
        shift TEXT NOT NULL,
        packet BLOB NOT NULL,
        PRIMARY KEY (event_id, day, shift)
    )''')


def _find(db, event_id, period):
    return db.execute('SELECT packet FROM sealed_reports WHERE event_id = ? AND day = ? AND shift = ?',
                      (event_id, period.day, period.shift)).fetchone()


def seal_shift(db, event_id, day, shift):
    identifier(event_id, '展次号')
    period = parse_shift(day, shift)
    with transaction(db, write=True):
        stored = _find(db, event_id, period)
        if stored is not None:
            return decode_shift_report(stored['packet'])
        activity = read_activity(db, event_id)
        counts, rows = collect_shift_activity(activity, period)
        report = ShiftReport(new_id('report'), event_id, activity.installed.venue_id,
                             activity.installed.program.program_id, period, counts, rows)
        db.execute('INSERT INTO sealed_reports VALUES (?, ?, ?, ?)',
                   (event_id, period.day, period.shift, encode_shift_report(report)))
    return report


def get_sealed_report(db, event_id, day, shift):
    identifier(event_id, '展次号')
    stored = _find(db, event_id, parse_shift(day, shift))
    if stored is None:
        raise BusinessError('unknown_report', '该展次和班次尚无本馆班报。', 404)
    return stored['packet']
