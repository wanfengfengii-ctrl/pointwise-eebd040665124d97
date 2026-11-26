import argparse
import sqlite3
from contextlib import closing
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from core import BusinessError, connect, moment, transaction
from desk.html import Reply, VENUE_LABELS, esc, link, page
from desk import program_pages, report_pages, switch_pages, tour_pages, venue_pages, venue_switch_pages
from program.draft import initialize_drafts
from program.edition import initialize_program_editions
from report.intake import initialize_report_intake
from report.shift import initialize_shift_reports
from tour.events import initialize_issues
from tour.switch_plan import initialize_switch_plans
from venue.local_store import initialize_venue_store
from venue.program_store import initialize_program_registry
from venue.switch_state import initialize_venue_switch

_MAX_BODY = 16 * 1024 * 1024
_STYLE = Path(__file__).with_name('style.css')


_CENTRAL = {
    ('GET', '/draft'): program_pages.draft_page,
    ('POST', '/draft'): program_pages.submit_draft,
    ('GET', '/proof'): program_pages.proof_page,
    ('POST', '/freeze'): program_pages.submit_freeze,
    ('GET', '/program'): program_pages.edition_page,
    ('GET', '/issue'): tour_pages.issue_page,
    ('POST', '/issue'): tour_pages.submit_issue,
    ('GET', '/opening'): tour_pages.download_opening_packet,
    ('GET', '/switch'): switch_pages.switch_page,
    ('GET', '/switch-plan'): switch_pages.switch_page,
    ('GET', '/switch-plans'): switch_pages.switch_page,
    ('POST', '/switch'): switch_pages.submit_switch,
    ('POST', '/switch-plan'): switch_pages.submit_plan,
    ('POST', '/plans/switch'): switch_pages.submit_plan,
    ('POST', '/switch/plan'): switch_pages.submit_plan,
    ('POST', '/switch/credential'): switch_pages.submit_credential,
    ('POST', '/credential'): switch_pages.submit_credential,
    ('POST', '/receipt'): switch_pages.submit_credential,
    ('POST', '/proof'): switch_pages.submit_credential,
    ('POST', '/retirement-receipt'): switch_pages.submit_credential,
    ('GET', '/authorization'): switch_pages.download_authorization,
    ('GET', '/permit'): switch_pages.download_authorization,
    ('GET', '/switch-authorization'): switch_pages.download_authorization,
    ('GET', '/authorize'): switch_pages.download_authorization,
    ('GET', '/switch-program'): switch_pages.download_program_material,
    ('GET', '/program-material'): switch_pages.download_program_material,
    ('GET', '/new-program'): switch_pages.download_program_material,
    ('GET', '/corrected-program'): switch_pages.download_program_material,
    ('GET', '/intake'): report_pages.intake_page,
    ('POST', '/intake'): report_pages.submit_intake,
    ('GET', '/accepted'): report_pages.download_accepted,
    ('POST', '/compare'): report_pages.submit_compare,
}
_VENUE = {
    ('GET', '/venue'): venue_pages.venue_page,
    ('GET', '/switch'): venue_pages.venue_page,
    ('POST', '/install'): venue_pages.submit_install,
    ('GET', '/screening'): venue_pages.screening_page,
    ('GET', '/shift'): report_pages.shift_page,
    ('POST', '/seal'): report_pages.submit_seal,
    ('GET', '/sealed'): report_pages.download_report,
    ('GET', '/retirement'): venue_switch_pages.download_retirement,
    ('GET', '/retirement-receipt'): venue_switch_pages.download_retirement,
    ('GET', '/retirement-packet'): venue_switch_pages.download_retirement,
    ('GET', '/stop-proof'): venue_switch_pages.download_retirement,
}
_CLOCKED = {
    ('POST', '/preview'): venue_pages.submit_preview,
    ('POST', '/start'): venue_pages.submit_start,
    ('POST', '/finish'): venue_pages.submit_finish,
    ('POST', '/retire'): venue_switch_pages.submit_retire,
    ('POST', '/retirement'): venue_switch_pages.submit_retire,
    ('POST', '/retire-old'): venue_switch_pages.submit_retire,
    ('POST', '/stop-old'): venue_switch_pages.submit_retire,
    ('POST', '/stop'): venue_switch_pages.submit_retire,
    ('POST', '/stop-edition'): venue_switch_pages.submit_retire,
    ('POST', '/retire-edition'): venue_switch_pages.submit_retire,
    ('POST', '/authorization'): venue_switch_pages.submit_authorization,
    ('POST', '/permit'): venue_switch_pages.submit_authorization,
    ('POST', '/auth'): venue_switch_pages.submit_authorization,
    ('POST', '/grant'): venue_switch_pages.submit_authorization,
    ('POST', '/license'): venue_switch_pages.submit_authorization,
    ('POST', '/upload-authorization'): venue_switch_pages.submit_authorization,
    ('POST', '/switch-material'): venue_switch_pages.submit_material,
    ('POST', '/material'): venue_switch_pages.submit_material,
    ('POST', '/program-material'): venue_switch_pages.submit_material,
    ('POST', '/upload-material'): venue_switch_pages.submit_material,
    ('POST', '/new-program-material'): venue_switch_pages.submit_material,
    ('POST', '/program-packet'): venue_switch_pages.submit_material,
    ('POST', '/switch-program'): venue_switch_pages.submit_material,
    ('POST', '/enable-switch'): venue_switch_pages.submit_enable,
    ('POST', '/enable'): venue_switch_pages.submit_enable,
    ('POST', '/activate'): venue_switch_pages.submit_enable,
}


def _unique_fields(pairs):
    fields = {}
    for key, value in pairs:
        if not key or key in fields:
            raise BusinessError('invalid_form', '表单字段重复或缺少名称。', 400)
        fields[key] = value
    return fields


def _url_fields(encoded):
    try:
        pairs = parse_qsl(encoded, keep_blank_values=True, strict_parsing=True, errors='strict', max_num_fields=64)
    except (ValueError, UnicodeError) as exc:
        raise BusinessError('invalid_form', '表单编码无法读取。', 400) from exc
    return _unique_fields(pairs)


def _multipart_fields(content_type, raw):
    try:
        header = f'Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n'.encode('ascii')
        message = BytesParser(policy=policy.default).parsebytes(header + raw)
        if not message.is_multipart() or message.defects:
            raise ValueError('invalid multipart')
        pairs = []
        for part in message.iter_parts():
            name = part.get_param('name', header='content-disposition')
            if part.get_content_disposition() != 'form-data' or part.is_multipart() or part.defects:
                raise ValueError('invalid field')
            payload = part.get_payload(decode=True)
            if not isinstance(payload, bytes) or part.defects:
                raise ValueError('invalid payload')
            if part.get_filename() is None:
                payload = payload.decode('utf-8')
            pairs.append((name, payload))
        return _unique_fields(pairs)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise BusinessError('invalid_form', '无法读取上传的表单。', 400) from exc


def _home(role):
    if role == 'central':
        entries = [('/draft', '编排节目', '保存分镜、校样和冻结节目'),
                   ('/issue', '展次发行', '设置两馆分额、领取开馆件'),
                   ('/switch', '校正换版', '登记计划、收凭据并发授权'),
                   ('/intake', '交班核对', '接纳班报并核对两馆开映记录')]
    else:
        entries = [('/venue', '本馆放映', '安装展次、试映、开映、停旧和启用新版'),
                   ('/shift', '本馆班报', '按营业日期和班别封报')]
    cards = [f'<section><h2>{link(path, title)}</h2><p>{esc(description)}</p></section>'
             for path, title, description in entries]
    return page(VENUE_LABELS[role], '<nav class="columns" aria-label="工作入口">' + ''.join(cards) + '</nav>')


class WorkbenchHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._serve('GET')

    def do_POST(self):
        self._serve('POST')

    def log_message(self, format, *args):
        return

    def _post_fields(self):
        try:
            length = int(self.headers.get('Content-Length', ''))
        except ValueError as exc:
            raise BusinessError('invalid_form', '请求须提供明确的表单长度。', 400) from exc
        if not 0 <= length <= _MAX_BODY:
            raise BusinessError('body_size', '表单超过可接纳大小。', 413)
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise BusinessError('invalid_form', '表单在传输中断开。', 400)
        kind = self.headers.get_content_type()
        if kind == 'application/x-www-form-urlencoded':
            try:
                return _url_fields(raw.decode('utf-8'))
            except UnicodeError as exc:
                raise BusinessError('invalid_form', '表单编码无法读取。', 400) from exc
        if kind == 'multipart/form-data':
            return _multipart_fields(self.headers['Content-Type'], raw)
        raise BusinessError('invalid_form', '请使用工作台表单提交。', 415)

    def _dispatch(self, method):
        try:
            request = urlsplit(self.path)
        except ValueError as exc:
            raise BusinessError('invalid_url', '请求路径无效。', 400) from exc
        route = (method, request.path)
        if route == ('GET', '/'):
            return _home(self.server.role)
        if route == ('GET', '/style.css'):
            return Reply(_STYLE.read_bytes(), content_type='text/css; charset=utf-8')
        routes = _CENTRAL if self.server.role == 'central' else _VENUE | _CLOCKED
        handler = routes.get(route)
        if handler is None:
            raise BusinessError('unknown_page', '找不到此工作台入口。', 404)
        fields = self._post_fields() if method == 'POST' else _url_fields(request.query)
        with closing(connect(self.server.db_path)) as db:
            if route in _CLOCKED:
                return handler(db, fields, now=self.server.clock())
            return handler(db, fields)

    def _serve(self, method):
        try:
            reply = self._dispatch(method)
        except BusinessError as exc:
            reply = page('办理未完成', f'<p class="notice" id="error" data-code="{esc(exc.code)}">{esc(exc)}</p>'
                         + link('/', '返回工作台'), status=exc.status)
        except sqlite3.Error:
            reply = page('办理未完成', '<p class="notice" id="error" data-code="storage_error">'
                         '数据库未能完成本次操作，请按原业务编号查验或重办。</p>' + link('/', '返回工作台'), status=503)
        try:
            self.send_response(reply.status)
            self.send_header('Content-Type', reply.content_type)
            self.send_header('Content-Length', str(len(reply.body)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Cache-Control', 'no-store')
            if reply.filename:
                self.send_header('Content-Disposition', f'attachment; filename="{reply.filename}"')
            self.end_headers()
            self.wfile.write(reply.body)
        except (BrokenPipeError, ConnectionResetError):
            return


class _WorkbenchServer(ThreadingHTTPServer):
    def __init__(self, role, db_path, port, clock):
        self.role = role
        self.db_path = db_path
        self.clock = clock
        super().__init__(('127.0.0.1', port), WorkbenchHandler)


def create_server(role, db_path, port=0, *, clock=None):
    if role not in VENUE_LABELS:
        raise BusinessError('invalid_role', '未知工作台角色。')
    with closing(connect(db_path)) as db:
        with transaction(db, write=True):
            db.execute('''CREATE TABLE IF NOT EXISTS workbench_role (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1), role TEXT NOT NULL
            )''')
            db.execute('INSERT OR IGNORE INTO workbench_role VALUES (1, ?)', (role,))
            stored = db.execute('SELECT role FROM workbench_role WHERE singleton = 1').fetchone()['role']
            has_venue_table = db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'venue_identity'").fetchone()
            if stored != role or (role == 'central' and has_venue_table is not None):
                raise BusinessError('role_conflict', '该数据库已绑定另一工作台。', 409)
            if has_venue_table is not None:
                identity = db.execute('SELECT venue_id FROM venue_identity WHERE singleton = 1').fetchone()
                if identity is not None and identity['venue_id'] != role:
                    raise BusinessError('role_conflict', '该数据库已绑定另一工作台。', 409)
            if role == 'central':
                initialize_drafts(db)
                initialize_program_editions(db)
                initialize_issues(db)
                initialize_switch_plans(db)
                initialize_report_intake(db)
        if role != 'central':
            initialize_venue_store(db, role)
            initialize_program_registry(db)
            initialize_venue_switch(db)
            initialize_shift_reports(db)
    return _WorkbenchServer(role, db_path, port, clock if clock is not None else moment)


def main(argv=None):
    parser = argparse.ArgumentParser(description='潮影巡回动画展本地工作台')
    parser.add_argument('--role', required=True, choices=tuple(VENUE_LABELS))
    parser.add_argument('--db', required=True, type=Path)
    parser.add_argument('--port', default=8000, type=int)
    args = parser.parse_args(argv)
    try:
        with create_server(args.role, args.db, args.port) as server:
            print(f'{VENUE_LABELS[args.role]} http://127.0.0.1:{server.server_port}', flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
    except (BusinessError, OSError, sqlite3.Error, OverflowError) as exc:
        parser.exit(1, f'无法启动工作台：{exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
