from __future__ import annotations

import subprocess
import tempfile
import time
import wave
from pathlib import Path

import numpy as np
import onnx_asr


REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = REPO_ROOT / "models" / "parakeet-tdt-0.6b-v2-onnx-int8"


def main() -> None:
    sample_rate = 16000
    expected = "This is the final local dictation test."
    with tempfile.TemporaryDirectory(prefix="macos-local-asr-smoke-") as tmpdir:
        tmp = Path(tmpdir)
        aiff = tmp / "speech.aiff"
        wav = tmp / "speech.wav"
        subprocess.run(["say", "-v", "Samantha", "-o", str(aiff), expected], check=True)
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(aiff), "-ac", "1", "-ar", str(sample_rate), str(wav)],
            check=True,
        )
        with wave.open(str(wav), "rb") as handle:
            duration = handle.getnframes() / float(handle.getframerate())
        started = time.perf_counter()
        model = onnx_asr.load_model(
            "nemo-parakeet-tdt-0.6b-v2",
            path=MODEL_DIR,
            quantization="int8",
            providers=["CPUExecutionProvider"],
        )
        load_sec = time.perf_counter() - started
        started = time.perf_counter()
        text = str(model.recognize(wav, sample_rate=sample_rate)).strip()
        latency = time.perf_counter() - started
    print(f"duration_sec={duration:.2f}")
    print(f"load_sec={load_sec:.2f}")
    print(f"latency_sec={latency:.2f}")
    print(f"transcript={text}")
    if "final local dictation test" not in text.lower():
        raise SystemExit("Smoke test failed: transcript did not contain expected phrase.")


if __name__ == "__main__":
    main()
