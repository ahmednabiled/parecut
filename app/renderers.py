import json
from typing import Literal

from parecut_engine.schemas import CutRange, SpeakerRole, Transcript

FPS_VALUES = {
    "24": 24.0,
    "25": 25.0,
    "29.97": 30000 / 1001,
    "30": 30.0,
    "60": 60.0,
}

Entry = tuple[str | None, str | None, float, float, float, float]


def fps_value(fps: str) -> float:
    return FPS_VALUES[fps]


def frame_number(seconds: float, fps: str) -> int:
    return int(seconds * fps_value(fps) + 0.5)


def _split(seconds: float) -> tuple[int, int, int, int]:
    total_ms = int(round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return hours, minutes, secs, millis


def format_clock(seconds: float) -> str:
    hours, minutes, secs, millis = _split(seconds)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def format_smpte(seconds: float, fps: str) -> str:
    nominal = round(fps_value(fps))
    frames = frame_number(seconds, fps)
    total_seconds, frame = divmod(frames, nominal)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}:{frame:02d}"


def _srt_time(seconds: float) -> str:
    return format_clock(seconds).replace(".", ",")


def _vtt_time(seconds: float) -> str:
    return format_clock(seconds)


def build_cut_plan(
    transcript: Transcript, roles: dict[str, SpeakerRole]
) -> list[CutRange]:
    plan: list[CutRange] = []
    cursor = 0.0
    for segment in sorted(transcript.segments, key=lambda item: item.start):
        if segment.start - cursor > 1e-6:
            plan.append(
                CutRange(
                    start=cursor,
                    end=segment.start,
                    action="remove",
                    reason="SILENCE",
                )
            )
        role = roles.get(segment.speaker, "presenter")
        if role == "feeder":
            plan.append(
                CutRange(
                    start=segment.start,
                    end=segment.end,
                    action="remove",
                    reason="FEEDER_PROMPT",
                    speaker=segment.speaker,
                    text=segment.text,
                )
            )
        else:
            plan.append(
                CutRange(
                    start=segment.start,
                    end=segment.end,
                    action="keep",
                    reason="BEST_TAKE",
                    speaker=segment.speaker,
                    text=segment.text,
                )
            )
        cursor = max(cursor, segment.end)
    return plan


def _kept_ranges(plan: list[CutRange]) -> list[tuple[CutRange, float, float]]:
    kept: list[tuple[CutRange, float, float]] = []
    cursor = 0.0
    for range_ in plan:
        if range_.action != "keep":
            continue
        duration = range_.end - range_.start
        kept.append((range_, cursor, cursor + duration))
        cursor += duration
    return kept


def _entries(
    transcript: Transcript, plan: list[CutRange], *, variant: str
) -> list[Entry]:
    if variant == "before":
        return [
            (segment.speaker, segment.text, segment.start, segment.end, segment.start, segment.end)
            for segment in sorted(transcript.segments, key=lambda item: item.start)
        ]
    return [
        (range_.speaker, range_.text, range_.start, range_.end, assembled_start, assembled_end)
        for range_, assembled_start, assembled_end in _kept_ranges(plan)
    ]


def _json_output(
    transcript: Transcript,
    plan: list[CutRange],
    roles: dict[str, SpeakerRole],
    variant: str,
) -> str:
    if variant == "before":
        payload = transcript.model_dump()
    else:
        kept = _kept_ranges(plan)
        payload = {
            "segments": [
                {
                    "speaker": range_.speaker,
                    "role": roles.get(range_.speaker or "", "presenter"),
                    "text": range_.text,
                    "source_start": round(range_.start, 3),
                    "source_end": round(range_.end, 3),
                    "assembled_start": round(assembled_start, 3),
                    "assembled_end": round(assembled_end, 3),
                }
                for range_, assembled_start, assembled_end in kept
            ],
            "total_duration": round(kept[-1][2], 3) if kept else 0.0,
        }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _markdown_output(entries: list[Entry], roles: dict[str, SpeakerRole], *, variant: str) -> str:
    title = "# Transcript (Before Cut)" if variant == "before" else "# Transcript (After Cut)"
    lines = [title, ""]
    for speaker, text, source_start, source_end, timeline_start, timeline_end in entries:
        speaker_name = speaker or "—"
        role = roles.get(speaker_name, "presenter") if speaker != "—" else "—"
        if variant == "before":
            timing = f"{format_clock(source_start)} – {format_clock(source_end)}"
        else:
            timing = (
                f"{format_clock(source_start)} – {format_clock(source_end)}"
                f" → {format_clock(timeline_start)} – {format_clock(timeline_end)}"
            )
        lines.append(f"**[{timing}] {speaker_name} ({role}):** {text or ''}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _cue_output(entries: list[Entry], *, fmt: Literal["srt", "vtt"]) -> str:
    blocks: list[str] = []
    for index, (speaker, text, _source_start, _source_end, start, end) in enumerate(
        entries, start=1
    ):
        speaker_name = speaker or "—"
        stamp = _srt_time if fmt == "srt" else _vtt_time
        blocks.append(f"{index}\n{stamp(start)} --> {stamp(end)}\n[{speaker_name}] {text or ''}".rstrip())
    body = "\n\n".join(blocks)
    if fmt == "vtt":
        return "WEBVTT\n\n" + body + ("\n" if body else "")
    return body + ("\n" if body else "")


def render_transcript(
    transcript: Transcript,
    cut_plan: list[CutRange],
    roles: dict[str, SpeakerRole],
    fps: str,
    *,
    variant: Literal["before", "after"],
    fmt: Literal["md", "srt", "vtt", "json"],
) -> str:
    if fmt == "json":
        return _json_output(transcript, cut_plan, roles, variant)
    entries = _entries(transcript, cut_plan, variant=variant)
    if fmt == "md":
        return _markdown_output(entries, roles, variant=variant)
    return _cue_output(entries, fmt=fmt)
