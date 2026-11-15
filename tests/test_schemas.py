import pytest
from pydantic import ValidationError

from parecut_engine.schemas import JobEvent, PipelineConfig


def test_pipeline_defaults_are_full_run():
    config = PipelineConfig()
    assert config.rough_cut is True
    assert config.enhance_mix == 0.8


def test_rough_cut_requires_transcribe():
    with pytest.raises(ValidationError, match="rough_cut requires transcribe"):
        PipelineConfig(transcribe=False, rough_cut=True)


def test_enhance_mix_is_bounded():
    with pytest.raises(ValidationError):
        PipelineConfig(enhance_mix=1.5)


def test_pipeline_audio_format_defaults_to_mp3():
    assert PipelineConfig().audio_format == "mp3"


def test_pipeline_audio_format_rejects_unknown():
    with pytest.raises(ValidationError):
        PipelineConfig(audio_format="flac")


def test_job_event_has_timestamp():
    event = JobEvent(type="stage.progress", job_id="j1", stage="enhance", percent=50)
    assert event.at.tzinfo is not None
