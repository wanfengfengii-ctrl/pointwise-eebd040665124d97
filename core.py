import hashlib
import hmac
import json
import re
import sqlite3
import time
from contextlib import contextmanager
from uuid import uuid4


class BusinessError(ValueError):
    def __init__(self, code, message, status=422):
        super().__init__(message)
        self.code = code
        self.status = status


def identifier(value, label='编号'):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', value):
        raise BusinessError('invalid_id', f'{label}须为有效业务编号。')
    return value


def new_id(prefix):
    return f'{prefix}-{uuid4().hex}'


def moment(value=None):
    if value is None:
        return int(time.time())
    if type(value) is not int or not -(2**63) <= value < 2**63:
        raise BusinessError('invalid_clock', '馆钟须提供有效的 Unix 整数秒。')
    return value


def connect(path):
    db = sqlite3.connect(path, timeout=8, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    return db


@contextmanager
def transaction(db, *, write=False):
    db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
    try:
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise


def json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def exact_fields(value, *fields):
    if not isinstance(value, dict) or value.keys() != set(fields):
        raise BusinessError('invalid_fields', '数据字段不完整或包含未识别字段。')
    return value


def pack(kind, payload):
    content = {'kind': kind, 'version': 1, 'payload': payload}
    checksum = hashlib.sha256(json_bytes(content)).hexdigest()
    return json_bytes({**content, 'sha256': checksum}) + b'\n'


def unpack(kind, raw):
    try:
        if not isinstance(raw, bytes):
            raise ValueError('expected bytes')
        doc = exact_fields(json.loads(raw.decode('utf-8')), 'kind', 'version', 'payload', 'sha256')
        if doc['kind'] != kind or type(doc['version']) is not int or doc['version'] != 1:
            raise ValueError('wrong kind or version')
        if not isinstance(doc['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', doc['sha256']):
            raise ValueError('invalid digest')
        expected = pack(kind, doc['payload'])
        if not hmac.compare_digest(expected, raw):
            raise ValueError('noncanonical or damaged document')
        return doc['payload']
    except (ValueError, RecursionError) as exc:
        raise BusinessError('invalid_packet', '文件用途、版本或完整性校验失败。') from exc
