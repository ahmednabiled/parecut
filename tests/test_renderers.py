from app.demo_data import demo_transcript
from app.renderers import (
    FPS_VALUES,
    build_cut_plan,
    format_clock,
    format_smpte,
    frame_number,
    render_transcript,
)


def test_timecode_conversions():
    assert frame_number(1.0, "25") == 25
    assert format_smpte(1.04, "25") == "00:00:01:01"
    assert format_clock(8.48) == "00:00:08.480"
    assert FPS_VALUES["29.97"] > 29.9


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


def test_demo_transcript_scales_to_duration():
    transcript = demo_transcript(12.0)
    assert transcript.segments[-1].end <= 12.0
    assert {segment.speaker for segment in transcript.segments} == {"SPEAKER_01", "SPEAKER_02"}
