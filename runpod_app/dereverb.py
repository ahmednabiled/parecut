import os
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path


def _is_empty_wav(path: Path) -> bool:
    try:
        with wave.open(str(path), "rb") as reader:
            return reader.getnframes() == 0
    except wave.Error:
        return False


def _select_dry_stem(output_files: list[str], output_dir: Path) -> Path:
    resolved = [
        Path(item) if Path(item).is_absolute() else output_dir / item
        for item in output_files
    ]
    if not resolved:
        raise RuntimeError("audio-separator produced no output files")

    for candidate in resolved:
        norm = candidate.stem.lower().replace("_", " ").replace("-", " ")
        if "no reverb" in norm or "no echo" in norm:
            return candidate

    for candidate in resolved:
        norm = candidate.stem.lower().replace("_", " ").replace("-", " ")
        if "reverb" not in norm and "echo" not in norm:
            return candidate

    return resolved[0]


def _run_separate(
    input_path: Path,
    tmp_dir: Path,
    model_dir: str,
    model_name: str,
    *,
    force_cpu: bool,
) -> Path:
    import torch

    if force_cpu:
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        torch.cuda.is_available = lambda: False

    from audio_separator.separator import Separator

    separator = Separator(
        model_file_dir=model_dir,
        output_dir=str(tmp_dir),
        output_format="WAV",
    )
    separator.load_model(model_name)
    outputs = separator.separate(str(input_path))
    return _select_dry_stem(list(outputs), tmp_dir)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(f"Usage: {sys.argv[0]} <input.wav> <output.wav>")

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if _is_empty_wav(input_path):
        shutil.copyfile(input_path, output_path)
        return

    import torch

    model_dir = os.getenv("PARECUT_DEREVERB_MODEL_DIR", "/opt/dereverb/models")
    model_name = os.getenv("PARECUT_DEREVERB_MODEL", "UVR-DeEcho-DeReverb.pth")
    requested = os.getenv(
        "PARECUT_DEREVERB_DEVICE",
        "cuda" if torch.cuda.is_available() else "cpu",
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        try:
            dry_path = _run_separate(
                input_path,
                tmp_dir,
                model_dir,
                model_name,
                force_cpu=(requested == "cpu"),
            )
        except Exception as exc:
            if requested == "cpu":
                raise
            print(
                f"De-reverb failed on {requested} ({exc}); retrying on cpu",
                file=sys.stderr,
            )
            if torch.cuda.is_available():
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass
            dry_path = _run_separate(
                input_path,
                tmp_dir,
                model_dir,
                model_name,
                force_cpu=True,
            )

        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(dry_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "48000",
                "-c:a",
                "pcm_s16le",
                str(output_path),
            ],
            check=True,
            capture_output=True,
        )


if __name__ == "__main__":
    main()
