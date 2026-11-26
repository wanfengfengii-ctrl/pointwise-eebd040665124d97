from core import BusinessError, identifier, new_id, transaction
from program.edition import get_program
from tour.events import TourIssue, find_issue, store_issue
from tour.quotas import VENUE_IDS, require_venue, validate_quotas
from tour.venue_packet import VenuePacket, encode_opening_packet


def issue_tour(db, event_id, program_id, east, west):
    identifier(event_id, '展次号')
    identifier(program_id, '节目号')
    quotas = validate_quotas(east, west)
    with transaction(db, write=True):
        existing = find_issue(db, event_id)
        if existing is not None:
            if existing.program_id != program_id or existing.quotas != quotas:
                raise BusinessError('issue_conflict', '展次已用不同的节目或分额发行。', 409)
            return existing
        program = get_program(db, program_id)
        issue_id = new_id('issue')
        packets = [encode_opening_packet(VenuePacket(
            event_id, issue_id, venue, program, quotas.for_venue(venue),
        )) for venue in VENUE_IDS]
        issued = TourIssue(event_id, issue_id, program_id, quotas, *packets)
        store_issue(db, issued)
    return issued


def get_issued_packet(db, event_id, venue_id):
    require_venue(venue_id)
    issue = find_issue(db, event_id)
    if issue is None:
        raise BusinessError('unknown_issue', '找不到该展次发行。', 404)
    return issue.east_packet if venue_id == 'east' else issue.west_packet
