from parecut_engine.schemas import Transcript, TranscriptSegment

TEMPLATE_DURATION = 24.72

_TEMPLATE = [
    (2.5, 5.0, "SPEAKER_02", "Today we're going to talk about three-point lighting."),
    (5.0, 8.0, "SPEAKER_01", "Today we're gonna— sorry, let me go again."),
    (
        8.48,
        11.16,
        "SPEAKER_01",
        "Today we're going to talk about three-point lighting.",
    ),
    (
        11.16,
        15.4,
        "SPEAKER_02",
        "The key light is your primary light source on set.",
    ),
    (15.4, 19.08, "SPEAKER_01", "The key light is the main light source."),
    (
        19.08,
        24.72,
        "SPEAKER_01",
        "The key light is your primary light source on set.",
    ),
]


def demo_transcript(duration_seconds: float | None) -> Transcript:
    duration = duration_seconds if duration_seconds else TEMPLATE_DURATION
    factor = duration / TEMPLATE_DURATION
    segments = [
        TranscriptSegment(
            speaker=speaker,
            start=min(start * factor, duration),
            end=min(end * factor, duration),
            text=text,
        )
        for start, end, speaker, text in _TEMPLATE
    ]
    return Transcript(speakers=["SPEAKER_01", "SPEAKER_02"], segments=segments)
