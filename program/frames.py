from dataclasses import asdict, dataclass

from core import BusinessError, exact_fields


@dataclass(frozen=True)
class Frame:
    title: str
    body: str
    duration_ms: int


def validate_frames(values):
    if not isinstance(values, (list, tuple)) or not values:
        raise BusinessError('invalid_frames', '节目至少需要一段分镜。')
    frames = []
    for index, value in enumerate(values, start=1):
        if isinstance(value, Frame):
            value = asdict(value)
        try:
            exact_fields(value, 'title', 'body', 'duration_ms')
        except BusinessError as exc:
            raise BusinessError('invalid_frames', f'第 {index} 段须提供标题、正文和时长。') from exc
        title, body, duration = value['title'], value['body'], value['duration_ms']
        for text in (title, body):
            if not isinstance(text, str) or not text.strip():
                raise BusinessError('invalid_frames', f'第 {index} 段的标题和正文均须有内容。')
            try:
                text.encode('utf-8')
            except UnicodeError as exc:
                raise BusinessError('invalid_frames', f'第 {index} 段包含非法 Unicode 字符。') from exc
        if type(duration) is not int or duration <= 0:
            raise BusinessError('invalid_duration', f'第 {index} 段时长须为正整数毫秒。')
        frames.append(Frame(title, body, duration))
    return tuple(frames)


def frames_data(frames):
    return [asdict(frame) for frame in frames]
