import math

import numpy as np
import pytest

from lodestone.pitch import PitchReading, detect
from lodestone.tuner import STANDARD_TUNING, Tuner

SAMPLE_RATE = 44100
FRAME_SIZE = 4096


def sine_frame(freq_hz: float) -> np.ndarray:
    t = np.arange(FRAME_SIZE) / SAMPLE_RATE
    return np.sin(2.0 * math.pi * freq_hz * t).astype(np.float32)


def freq_to_cents_error(detected_hz: float, expected_hz: float) -> float:
    return 1200.0 * math.log2(detected_hz / expected_hz)


# --- pitch.py tests ---

@pytest.mark.parametrize(
    "freq_hz, expected_midi",
    [
        (82.41, 40),   # E2 — low E
        (110.00, 45),  # A2
        (146.83, 50),  # D3
        (196.00, 55),  # G3
        (246.94, 59),  # B3
        (329.63, 64),  # E4 — high E
    ],
)
def test_open_strings(freq_hz: float, expected_midi: int) -> None:
    reading = detect(sine_frame(freq_hz), SAMPLE_RATE)
    assert reading.freq_hz is not None, f"detect() returned None for {freq_hz} Hz"
    cents_err = freq_to_cents_error(reading.freq_hz, freq_hz)
    assert abs(cents_err) <= 3.0, (
        f"freq={freq_hz} Hz: detected {reading.freq_hz:.2f} Hz, "
        f"error {cents_err:+.1f} cents (limit ±3)"
    )


def test_sharp_10_cents() -> None:
    target_hz = 82.41
    sharp_hz = target_hz * 2 ** (10.0 / 1200.0)
    reading = detect(sine_frame(sharp_hz), SAMPLE_RATE)
    assert reading.freq_hz is not None
    cents_err = freq_to_cents_error(reading.freq_hz, target_hz)
    assert abs(cents_err - 10.0) <= 3.0, (
        f"Expected +10 cents from {target_hz} Hz, got {cents_err:+.1f} cents"
    )


def test_silence_returns_none() -> None:
    frame = np.zeros(FRAME_SIZE, dtype=np.float32)
    reading = detect(frame, SAMPLE_RATE)
    assert reading.freq_hz is None


def test_noise_low_confidence() -> None:
    rng = np.random.default_rng(42)
    frame = rng.standard_normal(FRAME_SIZE).astype(np.float32)
    reading = detect(frame, SAMPLE_RATE)
    assert reading.confidence < 0.5, (
        f"Expected confidence < 0.5 for white noise, got {reading.confidence:.3f}"
    )


# --- tuner.py tests ---

def test_tuner_note_name_and_string() -> None:
    tuner = Tuner(history_size=3)
    freq_e2 = 82.41
    for _ in range(3):
        reading = detect(sine_frame(freq_e2), SAMPLE_RATE)
        display = tuner.update(reading)
    assert display is not None
    assert display.note_name == "E2", f"Expected E2, got {display.note_name}"
    assert display.likely_string == 0, f"Expected string 0, got {display.likely_string}"
    assert display.in_tune is True, f"Expected in_tune True, got cents={display.cents:.1f}"


def test_tuner_returns_none_on_silence() -> None:
    tuner = Tuner()
    silent = PitchReading(freq_hz=None, midi=0.0, confidence=0.0, rms=0.0)
    result = tuner.update(silent)
    assert result is None
