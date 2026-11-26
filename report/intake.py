from core import BusinessError, identifier, transaction
from report.report_packet import decode_shift_report


def initialize_report_intake(db):
    db.execute('''CREATE TABLE IF NOT EXISTS accepted_reports (
        report_id TEXT PRIMARY KEY,
        packet BLOB NOT NULL
    )''')


def accept_report(db, raw):
    report = decode_shift_report(raw)
    with transaction(db, write=True):
        previous = db.execute('SELECT packet FROM accepted_reports WHERE report_id = ?',
                              (report.report_id,)).fetchone()
        if previous is None:
            db.execute('INSERT INTO accepted_reports VALUES (?, ?)', (report.report_id, raw))
        elif previous['packet'] != raw:
            raise BusinessError('report_conflict', '该班报号已接纳另一份原件。', 409)
    return report


def list_accepted_reports(db):
    rows = db.execute('SELECT packet FROM accepted_reports ORDER BY rowid DESC')
    return tuple(decode_shift_report(row['packet']) for row in rows)


def get_accepted_report(db, report_id):
    identifier(report_id, '班报号')
    row = db.execute('SELECT packet FROM accepted_reports WHERE report_id = ?', (report_id,)).fetchone()
    if row is None:
        raise BusinessError('unknown_report', '找不到该已接纳班报。', 404)
    return row['packet']
