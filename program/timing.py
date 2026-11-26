from bisect import bisect_right
from dataclasses import dataclass

from core import BusinessError, exact_fields, json_bytes
from program.frames import Frame, frames_data, validate_frames


@dataclass(frozen=True)
class FrameSpan:
    index: int
    frame: Frame
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class Timeline:
    spans: tuple[FrameSpan, ...]
    endpoints: tuple[int, ...]
    total_ms: int


def build_timeline(frames):
    frames = validate_frames(frames)
    cursor = 0
    spans = []
    for index, frame in enumerate(frames, start=1):
        end = cursor + frame.duration_ms
        spans.append(FrameSpan(index, frame, cursor, end))
        cursor = end
    return Timeline(tuple(spans), tuple(span.end_ms for span in spans), cursor)


def locate_frame(timeline, at_ms):
    if type(at_ms) is not int or not 0 <= at_ms <= timeline.total_ms:
        raise BusinessError('invalid_time', f'时点须为 0 至 {timeline.total_ms} 之间的整数毫秒。')
    if at_ms == timeline.total_ms:
        return None
    return timeline.spans[bisect_right(timeline.endpoints, at_ms)]


def timeline_data(timeline):
    return {
        'frames': frames_data(span.frame for span in timeline.spans),
        'spans': [[span.start_ms, span.end_ms] for span in timeline.spans],
        'total_ms': timeline.total_ms,
    }


def decode_timeline(value):
    exact_fields(value, 'frames', 'spans', 'total_ms')
    timeline = build_timeline(value['frames'])
    if json_bytes(timeline_data(timeline)) != json_bytes(value):
        raise BusinessError('invalid_timeline', '分镜时长与节目时间表不一致。')
    return timeline
