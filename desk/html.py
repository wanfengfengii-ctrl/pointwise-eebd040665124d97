import re
from dataclasses import dataclass
from html import escape
from urllib.parse import urlencode

from core import BusinessError

VENUE_LABELS = {'east': '东馆', 'west': '西馆', 'central': '中央工作台'}


@dataclass(frozen=True)
class Reply:
    body: bytes
    status: int = 200
    content_type: str = 'text/html; charset=utf-8'
    filename: str | None = None


def esc(value):
    return escape(str(value), quote=True)


def url(path, **fields):
    return f'{path}?{urlencode(fields)}' if fields else path


def link(path, title, **fields):
    return f'<a href="{esc(url(path, **fields))}">{esc(title)}</a>'


def page(title, body, *, status=200):
    markup = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · 潮影动画展</title><link rel="stylesheet" href="/style.css"></head>
<body><header><a href="/">潮影动画展</a></header>
<main><h1>{esc(title)}</h1>{body}</main></body></html>'''
    return Reply(markup.encode('utf-8'), status)


def file_reply(raw, filename):
    return Reply(raw, content_type='application/json; charset=utf-8', filename=filename)


def form(form_id, action, controls, label, *, upload=False):
    enctype = ' enctype="multipart/form-data"' if upload else ''
    return (f'<form id="{esc(form_id)}" method="post" action="{esc(action)}"{enctype}>'
            f'{controls}<button type="submit">{esc(label)}</button></form>')


def hidden(name, value):
    return f'<input type="hidden" name="{esc(name)}" value="{esc(value)}">'


def field(name, label, value='', *, kind='text', minimum=None):
    min_attr = '' if minimum is None else f' min="{minimum}" step="1"'
    value_attr = '' if kind == 'file' else f' value="{esc(value)}"'
    return (f'<label>{esc(label)}<input type="{esc(kind)}" name="{esc(name)}"'
            f'{value_attr}{min_attr} required></label>')


def select_field(name, label, choices):
    options = ''.join(f'<option value="{esc(key)}">{esc(text)}</option>' for key, text in choices)
    return f'<label>{esc(label)}<select name="{esc(name)}" required>{options}</select></label>'


def get_form(fields, path, controls, label):
    return f'<form id="{esc(fields)}" method="get" action="{esc(path)}">{controls}<button>{esc(label)}</button></form>'


def text(fields, name):
    value = fields.get(name)
    if not isinstance(value, str) or value == '':
        raise BusinessError('missing_field', f'缺少字段 {name}。')
    return value


def integer(fields, name):
    value = text(fields, name)
    if not re.fullmatch(r'-?[0-9]+', value):
        raise BusinessError('invalid_integer', f'字段 {name} 须为整数。')
    try:
        return int(value)
    except ValueError as exc:
        raise BusinessError('invalid_integer', f'字段 {name} 的整数超出可处理长度。') from exc


def upload(fields, name='packet'):
    value = fields.get(name)
    if not isinstance(value, bytes) or not value:
        raise BusinessError('missing_file', '请选择要上传的原件。')
    return value


def facts(element_id, entries):
    attrs = ''.join(f' data-{key}="{esc(value)}"' for key, label, value in entries)
    rows = ''.join(f'<div><dt>{esc(label)}</dt><dd>{esc(value)}</dd></div>' for key, label, value in entries)
    return f'<dl id="{esc(element_id)}"{attrs}>{rows}</dl>'


def frame_panel(at_ms, span):
    if span is None:
        return (f'<article class="frame" id="frame" data-state="end" data-at="{at_ms}">'
                f'<p>{at_ms} 毫秒</p><h2>节目结束</h2></article>')
    return (f'<article class="frame" id="frame" data-state="frame" data-at="{at_ms}" '
            f'data-index="{span.index}" data-start="{span.start_ms}" data-end="{span.end_ms}">'
            f'<p>{at_ms} 毫秒 · 分镜 {span.index}</p><h2>{esc(span.frame.title)}</h2>'
            f'<div class="story">{esc(span.frame.body)}</div></article>')


def time_picker(form_id, path, key, value, at_ms=0):
    controls = hidden(key, value) + field('ms', '时点（毫秒）', at_ms, kind='number', minimum=0)
    return get_form(form_id, path, controls, '查看时点')


def table(headers, rows):
    top = ''.join(f'<th scope="col">{esc(label)}</th>' for label in headers)
    body = ''.join('<tr>' + ''.join(f'<td>{esc(cell)}</td>' for cell in row) + '</tr>' for row in rows)
    return f'<div class="table-wrap"><table><thead><tr>{top}</tr></thead><tbody>{body}</tbody></table></div>'
