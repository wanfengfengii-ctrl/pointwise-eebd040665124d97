from dataclasses import dataclass

from core import identifier
from tour.quotas import VenueQuotas


@dataclass(frozen=True)
class TourIssue:
    event_id: str
    issue_id: str
    program_id: str
    quotas: VenueQuotas
    east_packet: bytes
    west_packet: bytes


def initialize_issues(db):
    db.execute('''CREATE TABLE IF NOT EXISTS tour_issues (
        event_id TEXT PRIMARY KEY,
        issue_id TEXT UNIQUE NOT NULL,
        program_id TEXT NOT NULL REFERENCES program_editions(program_id),
        east_quota TEXT NOT NULL,
        west_quota TEXT NOT NULL,
        east_packet BLOB NOT NULL,
        west_packet BLOB NOT NULL
    )''')


def find_issue(db, event_id):
    identifier(event_id, '展次号')
    row = db.execute('SELECT * FROM tour_issues WHERE event_id = ?', (event_id,)).fetchone()
    if row is None:
        return None
    quotas = VenueQuotas(int(row['east_quota']), int(row['west_quota']))
    return TourIssue(row['event_id'], row['issue_id'], row['program_id'], quotas,
                     row['east_packet'], row['west_packet'])


def store_issue(db, issue):
    db.execute('''INSERT INTO tour_issues
        (event_id, issue_id, program_id, east_quota, west_quota, east_packet, west_packet)
        VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (issue.event_id, issue.issue_id, issue.program_id, str(issue.quotas.east),
         str(issue.quotas.west), issue.east_packet, issue.west_packet))
