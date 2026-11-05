import json
from typing import Literal

from parecut_engine.schemas import CutRange, RoughCutMeta, SpeakerRole, Transcript

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


def _cell(value: str | None) -> str:
    return (value or "").replace("|", "\\|").replace("\n", " ")


_ROLE_DISPLAY = {
    "presenter": ("Presenter", "KEEP (Best Takes)", "On-camera talent"),
    "feeder": ("Feeder / Director", "REMOVE ALL", "Off-camera line prompts"),
    "cohost": ("Co-host", "KEEP", "Additional on-camera host"),
}


def render_rough_cut_md(
    meta: RoughCutMeta, plan: list[CutRange], roles: dict[str, SpeakerRole]
) -> str:
    keeps = [range_ for range_ in plan if range_.action == "keep"]
    removes = [range_ for range_ in plan if range_.action == "remove"]
    kept_duration = sum(range_.end - range_.start for range_ in keeps)
    removed = max(0.0, meta.duration_seconds - kept_duration)
    percent_removed = (removed / meta.duration_seconds * 100) if meta.duration_seconds else 0.0
    total_frames = frame_number(meta.duration_seconds, meta.fps)
    sample_rate = f"{meta.sample_rate} Hz" if meta.sample_rate else "unknown"

    lines: list[str] = [
        "# PARECUT ROUGH-CUT SPECIFICATION",
        "",
        "## 1. Source Media & Timeline Metadata",
        "",
        f"- **Source Filename:** `{meta.source_filename}`",
        f"- **Duration:** `{format_clock(meta.duration_seconds)}` (`{meta.duration_seconds:.3f}s` / `{total_frames} frames @ {meta.fps} fps`)",
        f"- **Frame Rate:** `{meta.fps} fps`",
        f"- **Sample Rate:** `{sample_rate}`",
        f"- **Estimated Duration After Cut:** `{format_clock(kept_duration)}` (`{kept_duration:.3f}s`)",
        f"- **Estimated Removal:** `{percent_removed:.1f}%` (`{removed:.3f}s`)",
        "- **Recommended Audio Track:** `speaker_01_presenter_enhanced.wav`",
        "",
        "## 2. Speaker Map",
        "",
        "| Speaker ID | Assigned Role | Action | Notes |",
        "|---|---|---|---|",
    ]

    for speaker in sorted(roles):
        role = roles[speaker]
        display, action, notes = _ROLE_DISPLAY.get(role, _ROLE_DISPLAY["presenter"])
        lines.append(f"| `{speaker}` | **{display}** | `{action}` | {notes} |")

    lines += [
        "",
        "## 3. Machine-Readable Cut List",
        "",
        "> **Note for Coding Agents:** Build the rough cut by appending the `KEEP` ranges in order onto a new timeline (ripple assembly), rather than making destructive in-place razor deletes from back to front. Both tables are provided so the host NLE API can use whichever approach it prefers.",
        "",
        "### 3.1 `KEEP` Ranges (Assemble in Order)",
        "",
        "| # | Source In (TC) | Source Out (TC) | Source In (Sec) | Source Out (Sec) | In Frame | Out Frame | New Timeline TC | Speaker | Text |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]

    timeline_cursor = 0.0
    for index, range_ in enumerate(keeps, start=1):
        lines.append(
            "| {i} | `{si}` | `{so}` | `{ss:.3f}` | `{es:.3f}` | `{inf}` | `{outf}` | `{ntc}` | `{spk}` | {text} |".format(
                i=index,
                si=format_smpte(range_.start, meta.fps),
                so=format_smpte(range_.end, meta.fps),
                ss=range_.start,
                es=range_.end,
                inf=frame_number(range_.start, meta.fps),
                outf=frame_number(range_.end, meta.fps),
                ntc=format_smpte(timeline_cursor, meta.fps),
                spk=range_.speaker or "—",
                text=_cell(range_.text),
            )
        )
        timeline_cursor += range_.end - range_.start

    lines += [
        "",
        "### 3.2 `REMOVE` Ranges (Trimmed / Cut Out from Original)",
        "",
        "| # | Source In (TC) | Source Out (TC) | Source In (Sec) | Source Out (Sec) | In Frame | Out Frame | Reason | Speaker | Transcript / Detail |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for index, range_ in enumerate(removes, start=1):
        lines.append(
            "| {i} | `{si}` | `{so}` | `{ss:.3f}` | `{es:.3f}` | `{inf}` | `{outf}` | `{reason}` | `{spk}` | {text} |".format(
                i=index,
                si=format_smpte(range_.start, meta.fps),
                so=format_smpte(range_.end, meta.fps),
                ss=range_.start,
                es=range_.end,
                inf=frame_number(range_.start, meta.fps),
                outf=frame_number(range_.end, meta.fps),
                reason=range_.reason,
                spk=range_.speaker or "—",
                text=_cell(range_.text) or ("Pre/post-roll dead air" if range_.reason == "SILENCE" else ""),
            )
        )

    lines += ["", "## 4. Full Chronological Audit Log", ""]
    for range_ in plan:
        if range_.action == "keep":
            marker = f"✅ **KEEP ({range_.reason} — {range_.speaker}):**"
        else:
            speaker = f" — {range_.speaker}" if range_.speaker else ""
            marker = f"❌ **REMOVE ({range_.reason}{speaker}):**"
        lines.append(
            f"- `[{format_clock(range_.start)} - {format_clock(range_.end)}]` {marker} {range_.text or ''}".rstrip()
        )

    lines += [
        "",
        "## 5. Ready-to-Use Coding Agent Instructions",
        "",
        "> Copy this file into your coding agent (Claude Code, Cursor, Codex, ChatGPT) and ask:",
        ">",
        '> - *"Write a DaVinci Resolve Python script (`DaVinciResolveScript`) that creates a new timeline named `Rough Cut` and appends the `KEEP` frame ranges from Section 3.1 using `mediaPool.AppendToTimeline`."*',
        '> - *"Write an Adobe Premiere Pro ExtendScript (`.jsx`) or UXP script that builds a new sequence from the `KEEP` ranges in Section 3.1."*',
        '> - *"Generate an FCPXML 1.10 or OpenTimelineIO (`.otio`) file from Section 3.1 that I can import directly into Resolve, Premiere, or Final Cut Pro."*',
        "",
    ]

    return "\n".join(lines)
