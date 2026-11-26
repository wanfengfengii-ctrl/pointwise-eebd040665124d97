from dataclasses import dataclass

from core import BusinessError, identifier, new_id, transaction
from program.edition import get_program
from tour.events import find_issue
from tour.quotas import VENUE_IDS, require_venue
from tour.switch_packets import (
    RetirementReceipt,
    SwitchAuthorization,
    decode_retirement_receipt,
    encode_authorization,
)


@dataclass(frozen=True)
class SwitchPlan:
    plan_id: str
    event_id: str
    issue_id: str
    old_program_id: str
    new_program_id: str
    east_receipt: bytes | None
    west_receipt: bytes | None
    authorization: bytes | None

    def receipt_for(self, venue_id):
        require_venue(venue_id)
        return self.east_receipt if venue_id == 'east' else self.west_receipt

    @property
    def receipts_complete(self):
        return self.east_receipt is not None and self.west_receipt is not None


def initialize_switch_plans(db):
    db.execute('''CREATE TABLE IF NOT EXISTS switch_plans (
        plan_id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL UNIQUE,
        issue_id TEXT NOT NULL,
        old_program_id TEXT NOT NULL,
        new_program_id TEXT NOT NULL,
        east_receipt BLOB,
        west_receipt BLOB,
        authorization BLOB
    )''')


def _row_to_plan(row):
    return SwitchPlan(row['plan_id'], row['event_id'], row['issue_id'],
                      row['old_program_id'], row['new_program_id'],
                      row['east_receipt'], row['west_receipt'], row['authorization'])


def find_switch_plan(db, plan_id):
    identifier(plan_id, '换版计划号')
    row = db.execute('SELECT * FROM switch_plans WHERE plan_id = ?', (plan_id,)).fetchone()
    return None if row is None else _row_to_plan(row)


def find_switch_plan_by_event(db, event_id):
    identifier(event_id, '展次号')
    row = db.execute('SELECT * FROM switch_plans WHERE event_id = ?', (event_id,)).fetchone()
    return None if row is None else _row_to_plan(row)


def require_switch_plan(db, plan_id):
    plan = find_switch_plan(db, plan_id)
    if plan is None:
        raise BusinessError('unknown_switch_plan', '找不到该换版计划。', 404)
    return plan


def list_switch_plans(db):
    rows = db.execute('SELECT * FROM switch_plans ORDER BY rowid DESC').fetchall()
    return tuple(_row_to_plan(row) for row in rows)


def register_switch_plan(db, event_id, new_program_id):
    identifier(event_id, '展次号')
    identifier(new_program_id, '校正版节目号')
    issue = find_issue(db, event_id)
    if issue is None:
        raise BusinessError('unknown_issue', '找不到该展次发行。', 404)
    new_program = get_program(db, new_program_id)
    if new_program.program_id == issue.program_id:
        raise BusinessError('same_switch_program', '校正节目须与首发固定节目不同。', 422)

    with transaction(db, write=True):
        existing = find_switch_plan_by_event(db, event_id)
        if existing is not None:
            if existing.new_program_id != new_program_id:
                raise BusinessError('switch_conflict', '该展次已登记另一次换版计划。', 409)
            return existing
        plan_id = new_id('switch')
        db.execute('''INSERT INTO switch_plans
            (plan_id, event_id, issue_id, old_program_id, new_program_id,
             east_receipt, west_receipt, authorization)
            VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL)''',
                   (plan_id, event_id, issue.issue_id, issue.program_id, new_program_id))
        return require_switch_plan(db, plan_id)


def _authorization_for(plan, venue_id='both'):
    if venue_id != 'both':
        require_venue(venue_id)
    auth = SwitchAuthorization(plan.plan_id, plan.event_id, plan.issue_id,
                              plan.old_program_id, plan.new_program_id, venue_id)
    return encode_authorization(auth)


def receive_retirement_receipt(db, raw, *, expected_venue=None,
                               expected_plan=None, expected_event=None):
    receipt = decode_retirement_receipt(raw)
    if expected_venue is not None:
        require_venue(expected_venue)
        if receipt.venue_id != expected_venue:
            raise BusinessError('wrong_venue', '停旧凭据的出具馆与收件馆别不符。', 422)
    if expected_plan is not None and receipt.plan_id != expected_plan:
        raise BusinessError('receipt_conflict', '停旧凭据属于其他换版计划。', 409)
    if expected_event is not None and receipt.event_id != expected_event:
        raise BusinessError('receipt_conflict', '停旧凭据属于其他展次。', 409)

    column = f'{receipt.venue_id}_receipt'
    with transaction(db, write=True):
        plan = require_switch_plan(db, receipt.plan_id)
        if receipt.event_id != plan.event_id or receipt.issue_id != plan.issue_id \
                or receipt.old_program_id != plan.old_program_id:
            raise BusinessError('receipt_conflict', '停旧凭据与换版计划或首发节目不一致。', 409)
        previous = db.execute(
            f'SELECT {column} AS packet FROM switch_plans WHERE plan_id = ?',
            (plan.plan_id,)).fetchone()['packet']
        changed = previous is None
        if previous is not None and previous != raw:
            raise BusinessError('receipt_conflict', '该馆已收到另一份停旧凭据。', 409)
        if previous is None:
            db.execute(f'UPDATE switch_plans SET {column} = ? WHERE plan_id = ?',
                       (raw, plan.plan_id))
        updated = require_switch_plan(db, plan.plan_id)
        if updated.receipts_complete and updated.authorization is None:
            authorization = _authorization_for(updated)
            db.execute('UPDATE switch_plans SET authorization = ? WHERE plan_id = ?',
                       (authorization, plan.plan_id))
        return require_switch_plan(db, plan.plan_id), changed


def issue_authorization(db, plan_id, venue_id='both'):
    if venue_id != 'both':
        require_venue(venue_id)
    with transaction(db, write=True):
        plan = require_switch_plan(db, plan_id)
        if not plan.receipts_complete:
            missing = '、'.join({'east': '东馆', 'west': '西馆'}[v]
                               for v in VENUE_IDS if plan.receipt_for(v) is None)
            raise BusinessError('switch_incomplete', f'{missing}的停旧凭据尚未到齐，不能发出授权。', 409)
        if plan.authorization is None:
            authorization = _authorization_for(plan)
            db.execute('UPDATE switch_plans SET authorization = ? WHERE plan_id = ?',
                       (authorization, plan.plan_id))
        stored = require_switch_plan(db, plan_id).authorization
        return stored if venue_id == 'both' else _authorization_for(plan, venue_id)
