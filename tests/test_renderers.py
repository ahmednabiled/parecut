from app.demo_data import demo_transcript
from app.renderers import (
    FPS_VALUES,
    build_cut_plan,
    format_clock,
    format_smpte,
    frame_number,
    render_transcript,
)
from parecut_engine.schemas import Transcript, TranscriptSegment


def test_timecode_conversions():
    assert frame_number(1.0, "25") == 25
    assert format_smpte(1.04, "25") == "00:00:01:01"
    assert format_clock(8.48) == "00:00:08.480"
    assert FPS_VALUES["29.97"] > 29.9
    assert frame_number(1.0, "50") == 50
    assert format_smpte(1.02, "50") == "00:00:01:01"


def test_before_renderer_keeps_feeder_and_source_time():
    transcript = demo_transcript(24.72)
    roles = {"SPEAKER_01": "presenter", "SPEAKER_02": "feeder"}
    plan = build_cut_plan(transcript, roles)
    srt = render_transcript(
        transcript, plan, roles, "25", variant="before", fmt="srt"
    )
    assert "Today we're going to talk about three-point lighting." in srt
    assert "[SPEAKER_02]" in srt
    assert "00:00:02,500 --> 00:00:05,000" in srt


def test_after_renderer_omits_feeder_and_starts_at_zero():
    transcript = demo_transcript(24.72)
    roles = {"SPEAKER_01": "presenter", "SPEAKER_02": "feeder"}
    plan = build_cut_plan(transcript, roles)
    srt = render_transcript(transcript, plan, roles, "25", variant="after", fmt="srt")
    assert "SPEAKER_02" not in srt
    assert "00:00:00,000 --> " in srt


def test_cut_plan_marks_silence_and_feeder():
    transcript = demo_transcript(24.72)
    plan = build_cut_plan(transcript, {"SPEAKER_01": "presenter", "SPEAKER_02": "feeder"})
    assert any(range_.reason == "SILENCE" for range_ in plan)
    assert any(range_.reason == "FEEDER_PROMPT" for range_ in plan)
    assert any(range_.action == "keep" for range_ in plan)


def test_cut_plan_removes_restart_false_start():
    transcript = demo_transcript(24.72)
    roles = {"SPEAKER_01": "presenter", "SPEAKER_02": "presenter"}

    plan = build_cut_plan(transcript, roles)
    false_starts = [
        range_
        for range_ in plan
        if range_.action == "remove" and range_.reason == "FALSE_START"
    ]

    assert any("let me go again" in (range_.text or "") for range_ in false_starts)


def test_cut_plan_removes_prefix_false_start():
    transcript = Transcript(
        speakers=["S"],
        segments=[
            TranscriptSegment(
                speaker="S",
                start=0.0,
                end=2.0,
                text="Today we're going to talk",
            ),
            TranscriptSegment(
                speaker="S",
                start=3.0,
                end=6.0,
                text="Today we're going to talk about three-point lighting.",
            ),
        ],
    )

    plan = build_cut_plan(transcript, {"S": "presenter"})

    assert [(r.start, r.end) for r in plan if r.reason == "FALSE_START"] == [
        (0.0, 2.0)
    ]
    assert any(r.action == "keep" and r.start == 3.0 for r in plan)


def test_cut_plan_keeps_later_same_speaker_retake():
    transcript = Transcript(
        speakers=["S"],
        segments=[
            TranscriptSegment(
                speaker="S",
                start=0.0,
                end=2.0,
                text="The key light is the main light source.",
            ),
            TranscriptSegment(
                speaker="S",
                start=3.0,
                end=6.0,
                text="The key light is the main light source on set.",
            ),
        ],
    )

    plan = build_cut_plan(transcript, {"S": "presenter"})

    assert [(r.start, r.end) for r in plan if r.reason == "RETAKE"] == [(0.0, 2.0)]
    assert any(r.action == "keep" and r.start == 3.0 for r in plan)


def test_cut_plan_does_not_treat_apology_as_false_start():
    transcript = Transcript(
        speakers=["S"],
        segments=[
            TranscriptSegment(
                speaker="S",
                start=0.0,
                end=3.0,
                text="Sorry for the delay, the key light is the main source.",
            )
        ],
    )

    plan = build_cut_plan(transcript, {"S": "presenter"})

    assert not [r for r in plan if r.reason == "FALSE_START"]


def test_demo_transcript_scales_to_duration():
    transcript = demo_transcript(12.0)
    assert transcript.segments[-1].end <= 12.0
    assert {segment.speaker for segment in transcript.segments} == {"SPEAKER_01", "SPEAKER_02"}


def test_cut_plan_keeps_distinct_arabic_segments_and_catches_arabic_retake():
    transcript = Transcript(
        speakers=["SPEAKER_01"],
        segments=[
            TranscriptSegment(
                speaker="SPEAKER_01",
                start=0.0,
                end=2.5,
                text="أهلا بكم في هذا الفيديو الجديد",
            ),
            TranscriptSegment(
                speaker="SPEAKER_01",
                start=3.0,
                end=6.0,
                text="اليوم سنتحدث عن الإضاءة في التصوير.",
            ),
            TranscriptSegment(
                speaker="SPEAKER_01",
                start=7.0,
                end=10.0,
                text="اليوم سنتحدث عن الإضاءة في التصوير الاحترافي.",
            ),
        ],
    )

    plan = build_cut_plan(transcript, {"SPEAKER_01": "presenter"})
    kept = [r for r in plan if r.action == "keep"]
    retakes = [r for r in plan if r.reason == "RETAKE"]

    assert [r.start for r in kept] == [0.0, 7.0]
    assert [r.start for r in retakes] == [3.0]
