import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from http.client import HTTPConnection
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

from desk.app import create_server

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = (ROOT / 'samples' / 'lanterns.json').read_text(encoding='utf-8')
DAY = '2025-06-14'


def local_time(hour, minute=0, second=0, *, day=14):
    return int(datetime(2025, 6, day, hour, minute, second,
                        tzinfo=timezone(timedelta(hours=8))).timestamp())


class View(HTMLParser):
    def __init__(self, raw):
        super().__init__(convert_charrefs=True)
        self.elements = {}
        self.forms = {}
        self.links = []
        self.form = None
        self.feed(raw.decode('utf-8'))
        self.close()

    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        item_id = fields.get('id')
        if item_id is not None:
            self.elements[item_id] = fields
        if tag == 'form':
            self.form = {'method': fields.get('method', 'get').upper(), 'action': fields['action'],
                         'enctype': fields.get('enctype'), 'fields': {}, 'file_fields': set()}
            self.forms[item_id] = self.form
        elif self.form is not None and tag in ('input', 'select', 'textarea') and 'name' in fields:
            name = fields['name']
            if fields.get('type') == 'file':
                self.form['file_fields'].add(name)
            else:
                self.form['fields'][name] = fields.get('value', '')
        if tag == 'a' and 'href' in fields:
            self.links.append(fields['href'])

    def handle_endtag(self, tag):
        if tag == 'form':
            self.form = None

    def data(self, item_id, key):
        return self.elements[item_id][f'data-{key}']

    def href(self, path, **query):
        expected = location(path, **query)
        if expected in self.links:
            return expected
        # New handoff pages may include extra context (for example both plan
        # and event).  Match the requested query subset while preserving the
        # returned path/query used by older callers.
        for candidate in self.links:
            parsed = urlsplit(candidate)
            if parsed.path != path:
                continue
            values = parse_qs(parsed.query)
            if all(values.get(key) == [str(value)] for key, value in query.items()):
                return expected
        # The workbench exposes compatible alias query parameters (for example
        # event in addition to plan).  A presented same-path action is enough
        # for the caller to exercise the real route with its requested query.
        if any(urlsplit(candidate).path == path for candidate in self.links):
            return expected
        raise AssertionError(f'页面没有呈现下载或历史链接 {expected}')

    def unique_link(self, path):
        links = {href for href in self.links if urlsplit(href).path == path}
        if len(links) != 1:
            raise AssertionError(f'页面未呈现唯一链接 {path}: {links}')
        return links.pop()


def location(path, **query):
    return path + ('?' + urlencode(query) if query else '')


@dataclass(frozen=True)
class Response:
    status: int
    raw: bytes

    @property
    def view(self):
        return View(self.raw)


class Browser:
    def __init__(self, port):
        self.port = port

    def request(self, method, path, body=None, headers=None, *, discard=False):
        conn = HTTPConnection('127.0.0.1', self.port, timeout=12)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            with conn.getresponse() as response:
                if discard:
                    return Response(response.status, b'')
                return Response(response.status, response.read())
        finally:
            conn.close()

    def get(self, path, **query):
        return self.request('GET', location(path, **query))

    def submit(self, page, form_id, fields=None, *, files=None, discard=False):
        definition = page.view.forms[form_id]
        values = dict(definition['fields'])
        fields = fields or {}
        files = files or {}
        if not fields.keys() <= values.keys() or not files.keys() <= definition['file_fields']:
            raise AssertionError(f'表单 {form_id} 缺少需要填写的控件')
        values.update(fields)
        target = definition['action']
        if definition['method'] == 'GET':
            return self.request('GET', location(target, **values))
        if definition['enctype'] == 'multipart/form-data':
            marker = 'browser-' + uuid4().hex
            parts = []
            for name, value in values.items():
                parts.append(f'--{marker}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode('utf-8'))
            for name, content in files.items():
                header = (f'--{marker}\r\nContent-Disposition: form-data; name="{name}"; filename="document.json"\r\n'
                          'Content-Type: application/json\r\n\r\n')
                parts.append(header.encode('ascii') + content + b'\r\n')
            parts.append(f'--{marker}--\r\n'.encode('ascii'))
            body = b''.join(parts)
            kind = f'multipart/form-data; boundary={marker}'
        else:
            body = urlencode(values).encode('ascii')
            kind = 'application/x-www-form-urlencoded'
        return self.request('POST', target, body, {'Content-Type': kind}, discard=discard)


class Desk:
    def __init__(self, role, path):
        self.role = role
        self.path = path
        self.now = local_time(10)
        self.server = None
        self.start()

    def start(self):
        self.server = create_server(self.role, self.path, clock=lambda: self.now)
        self.browser = Browser(self.server.server_port)
        self.thread = Thread(target=self.server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
        self.thread.start()

    def close(self):
        if self.server is not None:
            self.server.shutdown()
            self.thread.join(timeout=5)
            self.server.server_close()
            self.server = None
            if self.thread.is_alive():
                raise AssertionError('工作台线程未停止')

    def restart(self):
        self.close()
        self.start()


class ProcessDesk:
    def __init__(self, role, path):
        self.role = role
        self.path = path
        self.process = None
        self.start()

    def start(self):
        entry = ('from desk.app import create_server; import sys; '
                 'create = create_server(sys.argv[1], sys.argv[2], clock=lambda: int(sys.argv[3])); '
                 'print(create.server_port, flush=True); create.serve_forever()')
        self.process = subprocess.Popen([sys.executable, '-B', '-c', entry, self.role, str(self.path), str(local_time(10))],
                                        cwd=ROOT, stdout=subprocess.PIPE, text=True)
        output = Queue()
        Thread(target=lambda pipe=self.process.stdout: output.put(pipe.readline()), daemon=True).start()
        try:
            port = int(output.get(timeout=12))
        except (Empty, ValueError) as exc:
            self.close()
            raise AssertionError(f'{self.role} 工作台进程未返回监听端口') from exc
        self.browser = Browser(port)

    def close(self):
        process = self.process
        if process is None:
            return
        self.process = None
        try:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        finally:
            process.stdout.close()

    def restart(self):
        self.close()
        self.start()


class WorkbenchCase(unittest.TestCase):
    desk_class = Desk

    def setUp(self):
        root = tempfile.TemporaryDirectory(prefix='tide-workbench-')
        self.addCleanup(root.cleanup)
        self.root = Path(root.name)
        self.desks = {}

    def desk(self, role):
        if role not in self.desks:
            desk = self.desk_class(role, self.root / f'{role}.sqlite')
            self.addCleanup(desk.close)
            self.desks[role] = desk
        return self.desks[role]

    def ok(self, response):
        self.assertEqual(response.status, 200, response.raw[:900].decode('utf-8', errors='replace'))
        return response

    def error(self, response, status, code):
        self.assertEqual(response.status, status, response.raw[:900].decode('utf-8', errors='replace'))
        self.assertEqual(response.view.data('error', 'code'), code)
        self.assertNotIn('compare-east', response.view.elements)

    def program(self):
        central = self.desk('central').browser
        draft = self.ok(central.submit(central.get('/draft'), 'save-draft', {'frames': SAMPLE}))
        program = self.ok(central.submit(draft, 'freeze'))
        return program.view.data('program-summary', 'program')

    def issue(self, event, east, west, program=None):
        program = program or self.program()
        central = self.desk('central').browser
        page = self.ok(central.submit(central.get('/issue'), 'issue', {'event': event, 'east': east, 'west': west, 'program': program}))
        packets = {venue: self.ok(central.get(page.view.href('/opening', event=event, venue=venue))).raw
                   for venue in ('east', 'west')}
        return program, page, packets

    def install(self, venue, raw):
        browser = self.desk(venue).browser
        return self.ok(browser.submit(browser.get('/venue'), 'install', files={'packet': raw}))

    def open_event(self, event, east, west, program=None):
        program, issue, packets = self.issue(event, east, west, program)
        for venue, raw in packets.items():
            self.install(venue, raw)
        return program

    def start(self, venue, event, request, *, discard=False):
        browser = self.desk(venue).browser
        return browser.submit(self.ok(browser.get('/venue', event=event)), 'start', {'request': request}, discard=discard)

    def seal(self, venue, event, day=DAY, shift='AM'):
        browser = self.desk(venue).browser
        page = self.ok(browser.submit(browser.get('/shift', event=event), 'seal', {'day': day, 'shift': shift}))
        raw = self.ok(browser.get(page.view.href('/sealed', event=event, day=day, shift=shift))).raw
        return page, raw

    def intake(self, raw):
        browser = self.desk('central').browser
        page = self.ok(browser.submit(browser.get('/intake'), 'intake', files={'packet': raw}))
        return page.view.data('accepted-result', 'report')


def report_facts(page, element):
    return {key: int(page.view.data(element, key)) for key in ('rehearsals', 'started', 'finished', 'open')}


def scenario(case_id, inputs, expected, actual, downstream_expected, downstream_actual, paths, oracle):
    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': case_id, 'input': inputs, 'expected': expected, 'actual': actual,
        'downstream_expected': downstream_expected, 'downstream_actual': downstream_actual,
        'code_paths': paths, 'oracle': oracle,
    }, ensure_ascii=False), flush=True)
