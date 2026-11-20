import json
import re
from difflib import SequenceMatcher
from typing import Literal

from parecut_engine.schemas import CutRange, RoughCutMeta, SpeakerRole, Transcript

FPS_VALUES = {
    "24": 24.0,
    "25": 25.0,
    "29.97": 30000 / 1001,
    "30": 30.0,
    "50": 50.0,
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


RESTART_PHRASES = (
    "let me go again",
    "let me start over",
    "start over",
    "start again",
    "one more time",
    "take two",
)

RETAKE_SIMILARITY = 0.85
RETAKE_WINDOW_SECONDS = 30.0


def _normalized_words(text: str) -> list[str]:
    return [
        word
        for word in re.findall(r"[^\W_]+(?:'[^\W_]+)*", text.lower())
        if word
    ]


def _is_restart(text: str) -> bool:
    normalized = " ".join(_normalized_words(text))
    return any(phrase in normalized for phrase in RESTART_PHRASES)


def _is_prefix(earlier: str, later: str) -> bool:
    first = _normalized_words(earlier)
    second = _normalized_words(later)
    return (
        len(first) >= 3
        and len(second) > len(first)
        and second[: len(first)] == first
    )


def _similarity(first: str, second: str) -> float:
    left = " ".join(_normalized_words(first))
    right = " ".join(_normalized_words(second))
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _false_start_indices(segments) -> set[int]:
    indices: set[int] = set()
    for index, segment in enumerate(segments):
        if _is_restart(segment.text):
            indices.add(index)
            continue
        if index + 1 < len(segments):
            following = segments[index + 1]
            incomplete = not segment.text.rstrip().endswith((".", "!", "?"))
            if (
                incomplete
                and following.speaker == segment.speaker
                and _is_prefix(segment.text, following.text)
            ):
                indices.add(index)
    return indices


def _retake_indices(segments, false_starts: set[int]) -> set[int]:
    indices: set[int] = set()
    for index, segment in enumerate(segments):
        if index in false_starts or index in indices:
            continue
        for later_index in range(index + 1, len(segments)):
            later = segments[later_index]
            if later.start - segment.end > RETAKE_WINDOW_SECONDS:
                break
            if later_index in false_starts or later.speaker != segment.speaker:
                continue
            if _similarity(segment.text, later.text) >= RETAKE_SIMILARITY:
                if len(later.text) >= len(segment.text):
                    indices.add(index)
                else:
                    indices.add(later_index)
                break
    return indices


def build_cut_plan(
    transcript: Transcript, roles: dict[str, SpeakerRole]
) -> list[CutRange]:
    plan: list[CutRange] = []
    cursor = 0.0
    segments = sorted(transcript.segments, key=lambda item: item.start)
    false_starts = _false_start_indices(segments)
    retakes = _retake_indices(segments, false_starts)

    for index, segment in enumerate(segments):
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
            action, reason = "remove", "FEEDER_PROMPT"
        elif index in false_starts:
            action, reason = "remove", "FALSE_START"
        elif index in retakes:
            action, reason = "remove", "RETAKE"
        else:
            action, reason = "keep", "BEST_TAKE"

        plan.append(
            CutRange(
                start=segment.start,
                end=segment.end,
                action=action,
                reason=reason,
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
        role = roles.get(speaker_name, "presenter") if speaker_name != "—" else "—"
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


def _cell(value: str | None) -> str:
    return (value or "").replace("|", "\\|").replace("\n", " ")


def render_rough_cut_md(meta: RoughCutMeta, transcript: Transcript) -> str:
    segments = sorted(transcript.segments, key=lambda item: (item.start, item.end))
    total_frames = frame_number(meta.duration_seconds, meta.fps)
    sample_rate = f"{meta.sample_rate} Hz" if meta.sample_rate else "unknown"

    lines: list[str] = [
        "# PARECUT DETAILED TRANSCRIPTION",
        "",
        "## Source Media",
        "",
        f"- **Source Filename:** `{meta.source_filename}`",
        f"- **Duration:** `{format_clock(meta.duration_seconds)}` (`{meta.duration_seconds:.3f}s` / `{total_frames} frames @ {meta.fps} fps`)",
        f"- **Frame Rate:** `{meta.fps} fps`",
        f"- **Sample Rate:** `{sample_rate}`",
        f"- **Segments:** `{len(segments)}`",
        "",
        "## Detailed Transcription",
        "",
    ]

    if not segments:
        lines.append("_No speech segments detected._")
        lines.append("")
        return "\n".join(lines)

    lines += [
        "| # | Start (Clock) | End (Clock) | Start (TC) | End (TC) | Start (Sec) | End (Sec) | In Frame | Out Frame | Speaker | Transcription |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    for index, segment in enumerate(segments, start=1):
        lines.append(
            "| {i} | `{sc}` | `{ec}` | `{si}` | `{so}` | `{ss:.3f}` | `{es:.3f}` | `{inf}` | `{outf}` | `{spk}` | {text} |".format(
                i=index,
                sc=format_clock(segment.start),
                ec=format_clock(segment.end),
                si=format_smpte(segment.start, meta.fps),
                so=format_smpte(segment.end, meta.fps),
                ss=segment.start,
                es=segment.end,
                inf=frame_number(segment.start, meta.fps),
                outf=frame_number(segment.end, meta.fps),
                spk=segment.speaker or "—",
                text=_cell(segment.text),
            )
        )

    lines.append("")
    return "\n".join(lines)
