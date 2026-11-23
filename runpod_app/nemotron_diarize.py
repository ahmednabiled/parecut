import json
import os
import sys

import soundfile as sf
import torch
from transformers import AutoModelForAudioFrameClassification, AutoProcessor

MODEL_ID = "nvidia/Nemotron-3-Diarization"


def _run(model, inputs, device: str):
    model.to(device).eval()
    moved = inputs.to(device, dtype=model.dtype)
    with torch.inference_mode():
        return model(**moved).logits.cpu()


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(f"Usage: {sys.argv[0]} <input.wav> <output.json>")
    input_path, output_path = sys.argv[1], sys.argv[2]

    audio, sample_rate = sf.read(input_path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if audio.size == 0:
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump([], handle)
        return

    processor = AutoProcessor.from_pretrained(MODEL_ID)
    model = AutoModelForAudioFrameClassification.from_pretrained(MODEL_ID)

    inputs = processor(audio, sampling_rate=sample_rate, return_tensors="pt")

    requested = os.getenv(
        "PARECUT_NEMOTRON_DEVICE",
        "cuda" if torch.cuda.is_available() else "cpu",
    )
    try:
        logits = _run(model, inputs, requested)
    except Exception as exc:
        if requested == "cpu":
            raise
        print(
            f"Nemotron diarization failed on {requested} ({exc}); retrying on cpu",
            file=sys.stderr,
        )
        if torch.cuda.is_available():
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass
        logits = _run(model, inputs, "cpu")

    segments = processor.extract_speaker_dict(logits, inputs.attention_mask)[0]
    payload = []
    for segment in segments:
        start = max(0.0, float(segment["Start"]))
        end = max(start, float(segment["End"]))
        payload.append(
            {
                "speaker": f"SPEAKER_{int(segment['Speaker']):02d}",
                "start": start,
                "end": end,
            }
        )

    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)


if __name__ == "__main__":
    main()
