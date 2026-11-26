from dataclasses import dataclass

from core import BusinessError, identifier, moment, transaction
from tour.switch_packets import (
    RetirementReceipt,
    decode_authorization,
    decode_program_material,
    decode_retirement_receipt,
    encode_retirement_receipt,
)
from venue.install import get_installation
from venue.local_store import get_venue_identity
from venue.program_store import get_venue_program, store_venue_program


@dataclass(frozen=True)
class VenueSwitchState:
    event_id: str
    plan_id: str | None
    retired: bool
    stopped_at: int | None
    has_authorization: bool
    has_program_material: bool
    enabled_program_id: str | None
    enabled_at: int | None

    @property
    def active(self):
        return self.enabled_program_id is not None


def initialize_venue_switch(db):
    db.execute('''CREATE TABLE IF NOT EXISTS venue_switch_state (
        event_id TEXT PRIMARY KEY REFERENCES installations(event_id),
        plan_id TEXT NOT NULL,
        retirement BLOB NOT NULL,
        stopped_at INTEGER NOT NULL,
        authorization BLOB,
        program_material BLOB,
        enabled_program_id TEXT,
        enabled_at INTEGER
    )''')


def _state(row):
    if row is None:
        return VenueSwitchState('', None, False, None, False, False, None, None)
    return VenueSwitchState(
        row['event_id'], row['plan_id'], True, row['stopped_at'],
        row['authorization'] is not None,
        row['program_material'] is not None,
        row['enabled_program_id'], row['enabled_at'],
    )


def read_switch_state(db, event_id):
    identifier(event_id, '展次号')
    row = db.execute('SELECT * FROM venue_switch_state WHERE event_id = ?',
                     (event_id,)).fetchone()
    return _state(row)


def stop_old_edition(db, event_id, plan_id, *, now=None):
    identifier(event_id, '展次号')
    identifier(plan_id, '换版计划号')
    with transaction(db, write=True):
        installation = get_installation(db, event_id)
        venue_id = get_venue_identity(db)
        existing = db.execute('SELECT retirement FROM venue_switch_state WHERE event_id = ?',
                              (event_id,)).fetchone()
        if existing is not None:
            receipt = decode_retirement_receipt(existing['retirement'])
            if receipt.plan_id != plan_id:
                raise BusinessError('retirement_conflict', '本馆已为另一换版计划停旧。', 409)
            return receipt, existing['retirement']

        stopped_at = moment(now)
        receipt = RetirementReceipt(plan_id, event_id, installation.issue_id,
                                    venue_id, installation.program.program_id, stopped_at)
        raw = encode_retirement_receipt(receipt)
        db.execute('''INSERT INTO venue_switch_state
            (event_id, plan_id, retirement, stopped_at, authorization,
             program_material, enabled_program_id, enabled_at)
            VALUES (?, ?, ?, ?, NULL, NULL, NULL, NULL)''',
                   (event_id, plan_id, raw, stopped_at))
        store_venue_program(db, installation.program)
        return receipt, raw


def get_retirement_packet(db, event_id):
    identifier(event_id, '展次号')
    row = db.execute('SELECT retirement FROM venue_switch_state WHERE event_id = ?',
                     (event_id,)).fetchone()
    if row is None:
        raise BusinessError('not_retired', '本馆尚未持久停旧，没有可复领的凭据。', 404)
    return row['retirement']


def _require_row(db, event_id):
    row = db.execute('SELECT * FROM venue_switch_state WHERE event_id = ?',
                     (event_id,)).fetchone()
    if row is None:
        raise BusinessError('not_retired', '请先办理本馆停旧，再接收换版材料。', 409)
    return row


def _matches_retirement(row, packet):
    retirement = decode_retirement_receipt(row['retirement'])
    if packet.plan_id != retirement.plan_id or packet.event_id != retirement.event_id:
        raise BusinessError('switch_material_conflict', '材料属于其他换版计划或展次。', 409)
    return retirement


def _activate_if_complete(db, row, *, now=None):
    if row['authorization'] is None or row['program_material'] is None:
        return _state(row)
    auth = decode_authorization(row['authorization'])
    material = decode_program_material(row['program_material'])
    retirement = decode_retirement_receipt(row['retirement'])
    if auth.plan_id != retirement.plan_id or auth.event_id != retirement.event_id:
        raise BusinessError('switch_material_conflict', '授权与停旧凭据不属于同一计划或展次。', 409)
    if material.plan_id != auth.plan_id or material.event_id != auth.event_id:
        raise BusinessError('switch_material_conflict', '新版材料与授权不属于同一计划或展次。', 409)
    if material.program.program_id != auth.new_program_id:
        raise BusinessError('program_material_mismatch', '新版材料的节目号与授权不符。', 409)
    if auth.old_program_id != retirement.old_program_id:
        raise BusinessError('switch_material_conflict', '授权指向的原版节目与本馆停旧记录不符。', 409)

    store_venue_program(db, material.program)
    if row['enabled_program_id'] is None:
        enabled_at = moment(now)
        db.execute('''UPDATE venue_switch_state
                      SET enabled_program_id = ?, enabled_at = ?
                      WHERE event_id = ? AND enabled_program_id IS NULL''',
                   (auth.new_program_id, enabled_at, row['event_id']))
    updated = db.execute('SELECT * FROM venue_switch_state WHERE event_id = ?',
                         (row['event_id'],)).fetchone()
    return _state(updated)


def receive_authorization(db, raw, *, event_id=None, now=None):
    auth = decode_authorization(raw)
    target_event = event_id or auth.event_id
    identifier(target_event, '展次号')
    if event_id is not None and event_id != auth.event_id:
        raise BusinessError('switch_material_conflict', '授权展次与当前办理展次不符。', 409)
    with transaction(db, write=True):
        venue_id = get_venue_identity(db)
        if auth.venue_id != 'both' and auth.venue_id != venue_id:
            raise BusinessError('wrong_venue', '换版授权的收件馆与本馆不符。', 422)
        row = _require_row(db, target_event)
        _matches_retirement(row, auth)
        previous = row['authorization']
        if previous is not None and previous != raw:
            raise BusinessError('authorization_conflict', '本馆已收到另一份换版授权。', 409)
        if previous is None:
            db.execute('UPDATE venue_switch_state SET authorization = ? WHERE event_id = ?',
                       (raw, target_event))
            row = db.execute('SELECT * FROM venue_switch_state WHERE event_id = ?',
                             (target_event,)).fetchone()
        return _activate_if_complete(db, row, now=now)


def receive_program_material(db, raw, *, event_id=None, now=None):
    material = decode_program_material(raw)
    target_event = event_id or material.event_id
    identifier(target_event, '展次号')
    if event_id is not None and event_id != material.event_id:
        raise BusinessError('switch_material_conflict', '新版材料展次与当前办理展次不符。', 409)
    with transaction(db, write=True):
        row = _require_row(db, target_event)
        _matches_retirement(row, material)
        store_venue_program(db, material.program)
        previous = row['program_material']
        if previous is not None and previous != raw:
            raise BusinessError('program_material_conflict', '本馆已收到另一份新版材料。', 409)
        if previous is None:
            db.execute('UPDATE venue_switch_state SET program_material = ? WHERE event_id = ?',
                       (raw, target_event))
            row = db.execute('SELECT * FROM venue_switch_state WHERE event_id = ?',
                             (target_event,)).fetchone()
        return _activate_if_complete(db, row, now=now)


def enable_new_edition(db, event_id, plan_id=None, *, now=None):
    identifier(event_id, '展次号')
    with transaction(db, write=True):
        row = _require_row(db, event_id)
        if plan_id is not None:
            identifier(plan_id, '换版计划号')
            if plan_id != row['plan_id']:
                raise BusinessError('switch_material_conflict', '启用确认属于其他换版计划。', 409)
        if row['authorization'] is None or row['program_material'] is None:
            raise BusinessError('switch_incomplete', '授权或完整新版材料尚未齐备。', 409)
        return _activate_if_complete(db, row, now=now)


def current_startable_program(db, event_id):
    """Return (program, state); raise when retirement bars an old first start."""
    installation = get_installation(db, event_id)
    state = read_switch_state(db, event_id)
    if state.enabled_program_id is not None:
        return get_venue_program(db, state.enabled_program_id), state
    if state.retired:
        raise BusinessError('old_edition_retired', '旧版已持久停旧，须等待相符授权和完整新版。', 409)
    return installation.program, state
