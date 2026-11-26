from dataclasses import dataclass

from core import BusinessError, exact_fields, identifier, pack, unpack
from program.edition import ProgramEdition, decode_program, program_data
from tour.quotas import require_venue


RETIREMENT_KIND = 'retirement-receipt'
AUTHORIZATION_KIND = 'switch-authorization'
PROGRAM_MATERIAL_KIND = 'switch-program'


@dataclass(frozen=True)
class RetirementReceipt:
    plan_id: str
    event_id: str
    issue_id: str
    venue_id: str
    old_program_id: str
    stopped_at: int


@dataclass(frozen=True)
class SwitchAuthorization:
    plan_id: str
    event_id: str
    issue_id: str
    old_program_id: str
    new_program_id: str
    venue_id: str = 'both'


@dataclass(frozen=True)
class SwitchProgramMaterial:
    plan_id: str
    event_id: str
    program: ProgramEdition


def encode_retirement_receipt(receipt: RetirementReceipt) -> bytes:
    return pack(RETIREMENT_KIND, {
        'plan_id': receipt.plan_id,
        'event_id': receipt.event_id,
        'issue_id': receipt.issue_id,
        'venue_id': receipt.venue_id,
        'old_program_id': receipt.old_program_id,
        'stopped_at': receipt.stopped_at,
    })


def decode_retirement_receipt(raw: bytes) -> RetirementReceipt:
    try:
        item = exact_fields(unpack(RETIREMENT_KIND, raw),
                            'plan_id', 'event_id', 'issue_id', 'venue_id',
                            'old_program_id', 'stopped_at')
        if type(item['stopped_at']) is not int or item['stopped_at'] < 0:
            raise ValueError('invalid stopped_at')
        return RetirementReceipt(
            identifier(item['plan_id'], '换版计划号'),
            identifier(item['event_id'], '展次号'),
            identifier(item['issue_id'], '发行号'),
            require_venue(item['venue_id']),
            identifier(item['old_program_id'], '原版节目号'),
            item['stopped_at'],
        )
    except BusinessError as exc:
        if exc.code == 'invalid_packet':
            raise
        raise BusinessError('invalid_packet', f'停旧凭据无效。{exc}') from exc


def encode_authorization(auth: SwitchAuthorization) -> bytes:
    return pack(AUTHORIZATION_KIND, {
        'plan_id': auth.plan_id,
        'event_id': auth.event_id,
        'issue_id': auth.issue_id,
        'old_program_id': auth.old_program_id,
        'new_program_id': auth.new_program_id,
        'venue_id': auth.venue_id,
    })


def decode_authorization(raw: bytes) -> SwitchAuthorization:
    try:
        item = unpack(AUTHORIZATION_KIND, raw)
        if not isinstance(item, dict) or set(item) not in (
            {'plan_id', 'event_id', 'issue_id', 'old_program_id', 'new_program_id'},
            {'plan_id', 'event_id', 'issue_id', 'old_program_id', 'new_program_id', 'venue_id'},
        ):
            raise ValueError('invalid authorization fields')
        item = dict(item)
        item.setdefault('venue_id', 'both')
        if item['venue_id'] not in ('both', 'east', 'west'):
            raise ValueError('invalid authorization scope')
        return SwitchAuthorization(
            identifier(item['plan_id'], '换版计划号'),
            identifier(item['event_id'], '展次号'),
            identifier(item['issue_id'], '发行号'),
            identifier(item['old_program_id'], '原版节目号'),
            identifier(item['new_program_id'], '校正版节目号'),
            item['venue_id'],
        )
    except BusinessError as exc:
        if exc.code == 'invalid_packet':
            raise
        raise BusinessError('invalid_packet', f'换版授权无效。{exc}') from exc


def encode_program_material(material: SwitchProgramMaterial) -> bytes:
    return pack(PROGRAM_MATERIAL_KIND, {
        'plan_id': material.plan_id,
        'event_id': material.event_id,
        'program': program_data(material.program),
    })


def decode_program_material(raw: bytes) -> SwitchProgramMaterial:
    try:
        item = exact_fields(unpack(PROGRAM_MATERIAL_KIND, raw),
                            'plan_id', 'event_id', 'program')
        return SwitchProgramMaterial(
            identifier(item['plan_id'], '换版计划号'),
            identifier(item['event_id'], '展次号'),
            decode_program(item['program']),
        )
    except BusinessError as exc:
        if exc.code == 'invalid_packet':
            raise
        raise BusinessError('invalid_packet', f'新版材料无效。{exc}') from exc
