from app.demo_data import demo_transcript
from app.renderers import render_rough_cut_md
from parecut_engine.schemas import RoughCutMeta, Transcript


def _meta(duration: float = 24.72) -> RoughCutMeta:
    return RoughCutMeta(
        source_filename="A001_C014_interview.mov",
        duration_seconds=duration,
        fps="25",
        sample_rate=48000,
        estimated_duration_seconds=duration,
    )


def _render():
    transcript = demo_transcript(24.72)
    return render_rough_cut_md(_meta(), transcript)


def test_rough_cut_is_detailed_transcription_only():
    output = _render()
    assert "# PARECUT DETAILED TRANSCRIPTION" in output
    assert "## Source Media" in output
    assert "## Detailed Transcription" in output
    assert "A001_C014_interview.mov" in output

    for removed_marker in [
        "KEEP",
        "REMOVE",
        "FEEDER_PROMPT",
        "FALSE_START",
        "SILENCE",
        "mediaPool.AppendToTimeline",
    ]:
        assert removed_marker not in output


def test_rough_cut_has_accurate_timestamps_and_segments():
    transcript = demo_transcript(24.72)
    output = render_rough_cut_md(_meta(), transcript)

    assert "00:00:02:13" in output  # 2.5 s @ 25 fps, half-up frame rounding
    assert "00:00:02.500" in output
    assert "`2.500`" in output
    assert "`63`" in output

    for segment in transcript.segments:
        assert segment.speaker in output
        assert segment.text in output


def test_rough_cut_handles_empty_transcript():
    output = render_rough_cut_md(_meta(0.0), Transcript(speakers=[], segments=[]))
    assert "# PARECUT DETAILED TRANSCRIPTION" in output
    assert "_No speech segments detected._" in output
