from parecut_engine.schemas import PipelineConfig, StageState

STAGE_ORDER = [
    "noise_reduction",
    "enhance",
    "separate_music",
    "separate_speakers",
    "transcribe",
    "rough_cut",
]


def enabled_stages(config: PipelineConfig) -> list[str]:
    return [stage for stage in STAGE_ORDER if getattr(config, stage)]


def initial_stage_states(config: PipelineConfig) -> dict[str, StageState]:
    enabled = set(enabled_stages(config))
    return {
        stage: StageState(status="pending" if stage in enabled else "skipped")
        for stage in STAGE_ORDER
    }
