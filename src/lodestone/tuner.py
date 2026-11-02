from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Optional

from lodestone.pitch import PitchReading


STANDARD_TUNING = [40, 45, 50, 55, 59, 64]  # E2 A2 D3 G3 B3 E4

_NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


@dataclass
class TunerDisplay:
    note_name: str
    cents: float
    likely_string: int
    in_tune: bool


def _midi_to_note_name(midi_int: int) -> str:
    octave = (midi_int // 12) - 1
    name = _NOTE_NAMES[midi_int % 12]
    return f"{name}{octave}"


def _nearest_string(midi_int: int) -> int:
    distances = [abs(midi_int - s) for s in STANDARD_TUNING]
    return distances.index(min(distances))


class Tuner:
    def __init__(self, history_size: int = 5) -> None:
        self._history: deque[float] = deque(maxlen=history_size)

    def update(self, reading: PitchReading) -> Optional[TunerDisplay]:
        if reading.freq_hz is None:
            return None

        self._history.append(reading.midi)

        smoothed_midi = float(sorted(self._history)[len(self._history) // 2])
        midi_int = round(smoothed_midi)
        cents = 100.0 * (smoothed_midi - midi_int)

        note_name = _midi_to_note_name(midi_int)
        likely_string = _nearest_string(midi_int)
        in_tune = abs(cents) <= 5.0

        return TunerDisplay(
            note_name=note_name,
            cents=cents,
            likely_string=likely_string,
            in_tune=in_tune,
        )

    def reset(self) -> None:
        self._history.clear()
