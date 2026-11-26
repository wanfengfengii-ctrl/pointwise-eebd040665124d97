import json

from core import BusinessError
from desk.html import esc, facts, form, frame_panel, get_form, hidden, integer, link, page, table, text, time_picker, field
from program.draft import load_draft, save_draft
from program.edition import freeze_program, get_program
from program.frames import frames_data
from program.timing import locate_frame


def _timeline_table(timeline):
    return table(('分镜', '标题', '起点（毫秒）', '终点（毫秒）'),
                 ((span.index, span.frame.title, span.start_ms, span.end_ms) for span in timeline.spans))


def draft_page(db, fields):
    draft_id = fields.get('draft')
    lookup = get_form('draft-lookup', '/draft', field('draft', '草稿号', draft_id or ''), '打开原草稿')
    summary = ''
    value = ''
    bound_id = ''
    if draft_id:
        draft = load_draft(db, draft_id)
        value = json.dumps(frames_data(draft.frames), indent=2, ensure_ascii=False)
        bound_id = hidden('draft', draft_id)
        summary = facts('draft-summary', [('draft', '草稿号', draft_id), ('total', '总时长（毫秒）', draft.timeline.total_ms)])
        summary += _timeline_table(draft.timeline)
        summary += time_picker('proof-picker', '/proof', 'draft', draft_id)
        summary += form('freeze', '/freeze', bound_id, '冻结此稿')
    controls = bound_id + ('<label>分镜清单（JSON）<textarea name="frames" rows="12" required>'
                           f'{esc(value)}</textarea></label>')
    return page('编排节目', lookup + summary + form('save-draft', '/draft', controls, '保存完整清单'))


def submit_draft(db, fields):
    try:
        values = json.loads(text(fields, 'frames'))
    except (json.JSONDecodeError, RecursionError) as exc:
        raise BusinessError('invalid_json', '分镜清单须为有效的 JSON。') from exc
    except ValueError as exc:
        if isinstance(exc, BusinessError):
            raise
        raise BusinessError('invalid_json', '分镜清单含超长数值。') from exc
    draft = save_draft(db, values, fields.get('draft') or None)
    return draft_page(db, {'draft': draft.draft_id})


def proof_page(db, fields):
    draft = load_draft(db, text(fields, 'draft'))
    at_ms = integer(fields, 'ms')
    panel = frame_panel(at_ms, locate_frame(draft.timeline, at_ms))
    back = link('/draft', '返回草稿', draft=draft.draft_id)
    return page('时间点校样', panel + time_picker('proof-picker', '/proof', 'draft', draft.draft_id, at_ms) + back)


def submit_freeze(db, fields):
    program = freeze_program(db, text(fields, 'draft'))
    return edition_page(db, {'program': program.program_id})


def edition_page(db, fields):
    program = get_program(db, text(fields, 'program'))
    at_ms = integer(fields, 'ms') if 'ms' in fields else 0
    panel = frame_panel(at_ms, locate_frame(program.timeline, at_ms))
    summary = facts('program-summary', [('program', '节目号', program.program_id),
                                       ('total', '总时长（毫秒）', program.timeline.total_ms)])
    pick = time_picker('edition-picker', '/program', 'program', program.program_id, at_ms)
    return page('固定节目', summary + panel + pick + _timeline_table(program.timeline) + link('/issue', '前往发行'))
