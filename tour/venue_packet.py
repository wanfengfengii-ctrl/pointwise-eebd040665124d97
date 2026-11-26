from dataclasses import dataclass

from core import BusinessError, exact_fields, identifier, pack, unpack
from program.edition import ProgramEdition, decode_program, program_data
from tour.quotas import require_venue, validate_quota


@dataclass(frozen=True)
class VenuePacket:
    event_id: str
    issue_id: str
    venue_id: str
    program: ProgramEdition
    quota: int


def encode_opening_packet(packet):
    return pack('opening', {
        'event_id': packet.event_id, 'issue_id': packet.issue_id,
        'venue_id': packet.venue_id, 'program': program_data(packet.program), 'quota': packet.quota,
    })


def decode_opening_packet(raw):
    try:
        item = exact_fields(unpack('opening', raw), 'event_id', 'issue_id', 'venue_id', 'program', 'quota')
        return VenuePacket(
            identifier(item['event_id'], '展次号'), identifier(item['issue_id'], '发行号'),
            require_venue(item['venue_id']), decode_program(item['program']), validate_quota(item['quota']),
        )
    except BusinessError as exc:
        if exc.code == 'invalid_packet':
            raise
        raise BusinessError('invalid_packet', f'开馆件无效。{exc}') from exc
