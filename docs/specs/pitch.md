# Pitch Detection Handoff: PitchReading

**Module**: `apollo.pitch`  
**Algorithm**: YIN (de Cheveigné & Kawahara, 2002)  
**Consumers**: `apollo.onsets` (L4), `apollo.tuner` (T2–T3)

---

## PitchReading

In-memory dataclass produced by `detect()` once per audio frame.

| Field | Type | Range | Description |
|---|---|---|---|
| `freq_hz` | `float \| None` | > 0 or `None` | Fundamental frequency in Hz. `None` when the frame is silent or unvoiced. |
| `midi` | `float` | fractional | Fractional MIDI note number (A4 = 69.0). E.g. 40.05 = E2 + 5 cents. `0.0` when `freq_hz` is `None`. |
| `confidence` | `float` | 0.0 – 1.0 | Derived from `1 − CMNDF_value` at the detected period. Higher = more periodic. |
| `rms` | `float` | ≥ 0 | Root-mean-square amplitude of the frame. Used by consumers to distinguish silence from soft notes. |

`midi` is always consistent with `freq_hz`: `midi = 69 + 12 * log2(freq_hz / 440)`.

---

## detect() signature

```python
def detect(frame: np.ndarray, sample_rate: int = 44100) -> PitchReading
```

- `frame`: 1-D float32 array, any length ≥ 2 × `tau_max`. Typical length: 4096 samples.
- `sample_rate`: samples per second. Must match the source stream.
- Returns one `PitchReading`. Never raises on valid input.

### Default YIN parameters

| Parameter | Value | Rationale |
|---|---|---|
| `tau_min` | `sample_rate // 400` | f_max ≈ 400 Hz (above high E open string) |
| `tau_max` | `sample_rate // 65` | f_min ≈ 65 Hz (below low E open string E2 = 82.41 Hz) |
| `threshold` | 0.10 | CMNDF threshold from the YIN paper; lower = fewer false positives |
| `silence_rms` | 1e-4 | Frames quieter than this return `freq_hz = None` immediately |

---

## Frame size guidance

For reliable low-E detection (82.41 Hz, period ≈ 535 samples at 44100 Hz):

- **Minimum**: 2 × 535 = 1070 samples
- **Recommended**: 4096 samples (≈ 7.6 periods → robust autocorrelation)
- **Hop** (for streaming): 2048 samples → new reading every ≈ 46 ms

First reading is available after one full frame accumulates: 4096 / 44100 ≈ 93 ms.

---

## Usage example

```python
import numpy as np
from apollo.pitch import detect

frame = np.sin(2 * np.pi * 82.41 * np.arange(4096) / 44100).astype(np.float32)
reading = detect(frame)
# reading.freq_hz ≈ 82.41, reading.midi ≈ 40.0, reading.confidence > 0.9
```
