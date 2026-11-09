from app.demo_data import demo_transcript
from app.renderers import build_cut_plan, render_rough_cut_md
from parecut_engine.schemas import RoughCutMeta


def _render():
    transcript = demo_transcript(24.72)
    roles = {"SPEAKER_01": "presenter", "SPEAKER_02": "feeder"}
    meta = RoughCutMeta(
        source_filename="A001_C014_interview.mov",
        duration_seconds=24.72,
        fps="25",
        sample_rate=48000,
        estimated_duration_seconds=13.0,
    )
    return render_rough_cut_md(meta, build_cut_plan(transcript, roles), roles)


def test_rough_cut_has_required_sections_and_tables():
    output = _render()
    for heading in [
        "# PARECUT ROUGH-CUT SPECIFICATION",
        "## 1. Source Media & Timeline Metadata",
        "## 2. Speaker Map",
        "### 3.1 `KEEP` Ranges",
        "### 3.2 `REMOVE` Ranges",
        "## 4. Full Chronological Audit Log",
        "## 5. Ready-to-Use Coding Agent Instructions",
    ]:
        assert heading in output


def test_rough_cut_has_timecodes_reasons_and_agent_prompt():
    output = _render()
    assert "00:00:02:13" in output  # 2.5 s @ 25 fps, half-up frame rounding
    assert "FEEDER_PROMPT" in output
    assert "SILENCE" in output
    assert "mediaPool.AppendToTimeline" in output
    assert "A001_C014_interview.mov" in output
    assert "51.5%" in output  # 12.72 s removed of 24.72 s, including the false start
