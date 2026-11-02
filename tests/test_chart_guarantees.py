"""
test_chart_guarantees.py — verifies all 5 chart guarantees defined in
ARCHITECTURE.md against the fixture, and unit-tests each clean_notes step.
"""
import json
import pathlib
from collections import defaultdict

from lodestone.chart import (
    _drop_out_of_range,
    _drop_short_or_quiet,
    _drop_octave_doubles,
    _merge_same_pitch,
    _merge_shifted_duplicates,
    _shift_to_playable,
)


FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "chart" / "guitar.json"


def _load() -> dict:
    with open(FIXTURE) as f:
        return json.load(f)


def test_guarantee_1_sorted_by_start():
    """Notes are sorted by start_s (non-decreasing)."""
    chart = _load()
    starts = [n["start_s"] for n in chart["notes"]]
    assert starts == sorted(starts)


def test_guarantee_2_end_after_start():
    """Every note has end_s strictly after start_s."""
    chart = _load()
    for note in chart["notes"]:
        assert note["end_s"] > note["start_s"], (
            f"Note {note['id']}: end_s={note['end_s']} <= start_s={note['start_s']}"
        )


def test_guarantee_3_string_fret_midi():
    """tuning[string] + capo + fret == midi for every note."""
    chart = _load()
    tuning = chart["tuning"]
    capo = chart["capo"]
    for note in chart["notes"]:
        expected = tuning[note["string"]] + capo + note["fret"]
        assert expected == note["midi"], (
            f"Note {note['id']}: tuning[{note['string']}]={tuning[note['string']]} "
            f"+ capo={capo} + fret={note['fret']} = {expected} != midi={note['midi']}"
        )


def test_guarantee_4_no_string_overlap():
    """No two notes overlap in time on the same string."""
    chart = _load()
    by_string: dict[int, list] = defaultdict(list)
    for note in chart["notes"]:
        by_string[note["string"]].append(note)
    for string_id, notes in by_string.items():
        notes_sorted = sorted(notes, key=lambda n: n["start_s"])
        for i in range(len(notes_sorted) - 1):
            a, b = notes_sorted[i], notes_sorted[i + 1]
            assert a["end_s"] <= b["start_s"], (
                f"String {string_id}: note {a['id']} ({a['start_s']}-{a['end_s']}) "
                f"overlaps note {b['id']} ({b['start_s']}-{b['end_s']})"
            )


def test_guarantee_5_playable_fret():
    """Every note has fret in [0, 24] — within the instrument's playable range."""
    chart = _load()
    for note in chart["notes"]:
        assert note["fret"] >= 0, f"Note {note['id']} has negative fret {note['fret']}"
        assert note["fret"] <= 24, f"Note {note['id']} has fret {note['fret']} > 24"


# ── clean_notes step tests ─────────────────────────────────────────────────


def _ev(midi=60, start=0.0, end=0.5, amplitude=0.5) -> dict:
    return {"midi": midi, "start_s": start, "end_s": end, "amplitude": amplitude}


def test_clean_drop_out_of_range():
    events = [_ev(midi=32), _ev(midi=33), _ev(midi=88), _ev(midi=89)]
    result = _drop_out_of_range(events)
    midis = [e["midi"] for e in result]
    assert 32 not in midis
    assert 89 not in midis
    assert 33 in midis
    assert 88 in midis


def test_clean_drop_short_or_quiet():
    events = [
        _ev(end=0.05),                    # too short → dropped
        _ev(end=0.08),                    # exactly at limit → kept
        _ev(amplitude=0.29),              # too quiet → dropped
        _ev(amplitude=0.30),              # exactly at limit → kept
        _ev(end=0.05, amplitude=0.29),    # both bad → dropped
    ]
    result = _drop_short_or_quiet(events)
    assert len(result) == 2


def test_clean_drop_octave_doubles():
    louder = _ev(midi=40, start=0.0, amplitude=0.8)
    quieter = _ev(midi=52, start=0.02, amplitude=0.4)   # 12 semitones up, same onset
    unrelated = _ev(midi=55, start=0.0, amplitude=0.5)  # not 12 or 19 apart → kept
    result = _drop_octave_doubles([louder, quieter, unrelated])
    midis = [e["midi"] for e in result]
    assert 40 in midis
    assert 52 not in midis
    assert 55 in midis


def test_clean_merge_same_pitch():
    # Two notes of the same pitch that overlap → merged into one
    a = _ev(midi=60, start=0.0, end=0.5, amplitude=0.6)
    b = _ev(midi=60, start=0.4, end=0.9, amplitude=0.8)
    # A different pitch in between — should not be affected
    c = _ev(midi=62, start=0.2, end=0.4, amplitude=0.5)
    result = _merge_same_pitch([a, b, c])
    pitch_60 = [e for e in result if e["midi"] == 60]
    assert len(pitch_60) == 1
    assert pitch_60[0]["start_s"] == 0.0
    assert pitch_60[0]["end_s"] == 0.9
    assert pitch_60[0]["amplitude"] == 0.8  # louder of the two
    assert len([e for e in result if e["midi"] == 62]) == 1


def test_shift_to_playable():
    # Seven Nation Army riff: D=38, C#/Db=36, B=35 all shift up one octave
    assert _shift_to_playable(38) == 50   # D2 → D3
    assert _shift_to_playable(36) == 48   # C2 → C3
    assert _shift_to_playable(35) == 47   # B1 → B2
    # Notes already at or above the floor are unchanged
    assert _shift_to_playable(40) == 40
    assert _shift_to_playable(64) == 64


def test_merge_shifted_duplicates():
    # A native 48 and a shifted-from-36 note that overlap → one note at 48
    native = _ev(midi=48, start=0.10, end=0.35, amplitude=0.6)
    native["octave_shift_applied"] = False
    native["source_midi"] = None
    shifted = _ev(midi=48, start=0.24, end=0.44, amplitude=0.7)
    shifted["octave_shift_applied"] = True
    shifted["source_midi"] = 36

    result = _merge_shifted_duplicates([native, shifted])

    assert len(result) == 1
    assert result[0]["midi"] == 48
    assert result[0]["start_s"] == 0.10
    assert result[0]["end_s"] == 0.44
    assert result[0]["octave_shift_applied"] is True
    assert result[0]["source_midi"] == 36
