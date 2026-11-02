"""
conftest.py — generates tests/fixtures/sample.wav if it does not exist.

Uses only the standard library (wave, math, struct). No external packages.
"""
import math
import pathlib
import struct
import wave

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _make_sample_wav() -> None:
    path = FIXTURES / "sample.wav"
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)

    sample_rate = 44100
    duration_s = 3
    freq_hz = 440  # A4
    n_frames = sample_rate * duration_s

    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # 16-bit PCM
        w.setframerate(sample_rate)
        for i in range(n_frames):
            value = int(32767 * math.sin(2 * math.pi * freq_hz * i / sample_rate))
            w.writeframes(struct.pack("<h", value))


_make_sample_wav()
