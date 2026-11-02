from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class PitchReading:
    freq_hz: Optional[float]
    midi: float
    confidence: float
    rms: float


_SILENCE_RMS = 1e-4
_THRESHOLD = 0.10


def detect(
    frame: np.ndarray,
    sample_rate: int = 44100,
    tau_min: Optional[int] = None,
    tau_max: Optional[int] = None,
) -> PitchReading:
    """Return a PitchReading for one mono float32 audio frame using the YIN algorithm."""
    if tau_min is None:
        tau_min = sample_rate // 400
    if tau_max is None:
        tau_max = sample_rate // 65

    frame = np.asarray(frame, dtype=np.float64)

    rms = float(np.sqrt(np.mean(frame ** 2)))
    if rms < _SILENCE_RMS:
        return PitchReading(freq_hz=None, midi=0.0, confidence=0.0, rms=rms)

    half = len(frame) // 2
    tau_max = min(tau_max, half - 1)

    # --- Step 1: Difference function ---
    # d(tau) = sum_j ( x[j] - x[j+tau] )^2
    diff = np.zeros(tau_max + 1)
    for tau in range(tau_min, tau_max + 1):
        delta = frame[:half] - frame[tau: tau + half]
        diff[tau] = float(np.dot(delta, delta))

    # --- Step 2: Cumulative mean normalised difference function (CMNDF) ---
    # d'(0) = 1; d'(tau) = d(tau) * tau / sum_{j=1}^{tau} d(j)
    cmndf = np.ones(tau_max + 1)
    running_sum = 0.0
    for tau in range(1, tau_max + 1):
        running_sum += diff[tau]
        if running_sum > 0.0:
            cmndf[tau] = diff[tau] * tau / running_sum
        else:
            cmndf[tau] = 1.0

    # --- Step 3: Absolute threshold ---
    # Find the first tau in search range where cmndf < threshold.
    # Fall back to the global minimum if none qualifies.
    tau_est = tau_min
    found = False
    for tau in range(tau_min, tau_max + 1):
        if cmndf[tau] < _THRESHOLD:
            # Accept the next local minimum rather than the first crossing.
            while tau + 1 <= tau_max and cmndf[tau + 1] < cmndf[tau]:
                tau += 1
            tau_est = tau
            found = True
            break

    if not found:
        tau_est = int(np.argmin(cmndf[tau_min: tau_max + 1])) + tau_min

    # --- Step 4: Parabolic interpolation ---
    # Refine tau_est to sub-sample accuracy.
    tau_star = float(tau_est)
    if tau_min < tau_est < tau_max:
        a = cmndf[tau_est - 1]
        b = cmndf[tau_est]
        c = cmndf[tau_est + 1]
        denom = 2.0 * (a - 2.0 * b + c)
        if abs(denom) > 1e-10:
            tau_star = tau_est + (a - c) / denom

    freq_hz = sample_rate / tau_star
    midi = 69.0 + 12.0 * math.log2(freq_hz / 440.0)
    confidence = max(0.0, min(1.0, 1.0 - float(cmndf[tau_est])))

    return PitchReading(freq_hz=freq_hz, midi=midi, confidence=confidence, rms=rms)
