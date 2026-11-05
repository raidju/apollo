from __future__ import annotations

from collections import defaultdict

from apollo.store import SongStore

_TUNING = [40, 45, 50, 55, 59, 64]  # string 0 (low E) to string 5 (high e)
_CAPO = 0
_MIDI_MIN = 40       # lowest frettable note (open low E)
_MIDI_MAX = 86       # highest note kept after fret assignment
_FRET_MAX = 24

# clean_notes thresholds
_CLEAN_MIDI_MIN = 33
_CLEAN_MIDI_MAX = 88
_MIN_DURATION_S = 0.08
_MIN_AMPLITUDE = 0.30
_ONSET_WINDOW_S = 0.04
_OCTAVE_INTERVALS = (12, 19)
# Overtones two and three octaves up. These are weaker than the ones above,
# so a ghost here only needs to be quieter than its parent, not half as loud.
_WIDE_OCTAVE_INTERVALS = (24, 36)

# octave-shift thresholds
_SHIFT_MIN_AMPLITUDE = 0.40


def build_chart(song_id: str, target: str, store: SongStore) -> None:
    """Build a chart from the raw note list and write chart/<target>.json.

    Steps:
    1. Sort by start_s (guarantee 1).
    2. clean_notes: drop junk, merge duplicates.
    3. Drop ghost notes — harmonics Basic Pitch adds above louder concurrent notes.
    4. Apply octave shifts (low_note_mode="shift"), then merge any same-pitch
       overlaps the shift created.
    5. Assign string and fret, staying within 4 frets of the previous position.
    All 5 chart guarantees from ARCHITECTURE.md are satisfied.
    """
    song_data = store.read_song(song_id)
    low_note_mode = song_data.get("low_note_mode", "drop")

    notes_data = store.read_notes(song_id, target)
    events = sorted(notes_data["events"], key=lambda e: e["start_s"])
    events = clean_notes(events)
    events = [e for e in events if not _is_ghost(e, events)]
    events = _apply_shifts(events, low_note_mode)
    events = _merge_shifted_duplicates(events)

    chart_notes: list[dict] = []
    last_end: dict[int, float] = {}
    prev_fret: int | None = None

    for event in events:
        if event["end_s"] <= event["start_s"]:
            continue

        midi = event["midi"]
        if midi < _MIDI_MIN or midi > _MIDI_MAX:
            continue

        result = _assign_string_fret(midi, prev_fret, last_end, event["start_s"])
        if result is None:
            continue

        assigned_string, assigned_fret = result
        last_end[assigned_string] = event["end_s"]
        prev_fret = assigned_fret

        chart_notes.append({
            "id": len(chart_notes),
            "start_s": float(event["start_s"]),
            "end_s": float(event["end_s"]),
            "midi": midi,
            "string": assigned_string,
            "fret": assigned_fret,
            "chord": None,
            "octave_shift_applied": event["octave_shift_applied"],
            "source_midi": event["source_midi"],
        })

    store.write_chart(song_id, target, {
        "schema_version": 1,
        "instrument": target,
        "tuning": _TUNING,
        "capo": _CAPO,
        "notes": chart_notes,
    })


def clean_notes(events: list[dict]) -> list[dict]:
    """Remove junk from a raw Basic Pitch note list.

    Runs four steps in order — each is small and tested independently.
    """
    events = _drop_out_of_range(events)
    events = _drop_short_or_quiet(events)
    events = _drop_octave_doubles(events)
    events = _merge_same_pitch(events)
    return events


def _apply_shifts(events: list[dict], low_note_mode: str) -> list[dict]:
    """Apply octave shifts to notes below _MIDI_MIN and stamp shift metadata.

    Every event in the returned list has octave_shift_applied (bool) and
    source_midi (int or None) set, so downstream code can read them directly.
    """
    result = []
    for e in events:
        e = dict(e)
        midi = int(e["midi"])
        if (midi < _MIDI_MIN
                and low_note_mode == "shift"
                and e["amplitude"] >= _SHIFT_MIN_AMPLITUDE):
            e["source_midi"] = midi
            e["octave_shift_applied"] = True
            e["midi"] = _shift_to_playable(midi)
        else:
            e["source_midi"] = None
            e["octave_shift_applied"] = False
        result.append(e)
    return result


def _merge_shifted_duplicates(events: list[dict]) -> list[dict]:
    """Merge same-pitch notes that overlap after octave shifting.

    The shift can create two notes at the same pitch at overlapping times —
    one that was always at that pitch and one that was shifted up to it.
    This pass merges them before string/fret assignment so the assigner
    never sees the conflict.

    Merge rules: earliest start, latest end, loudest amplitude. If either
    source note was octave-shifted, the merged note keeps that flag and its
    source_midi.
    """
    by_midi: dict[int, list[dict]] = defaultdict(list)
    for e in events:
        by_midi[e["midi"]].append(e)

    merged: list[dict] = []
    for _midi, group in by_midi.items():
        group = sorted(group, key=lambda e: e["start_s"])
        current = dict(group[0])
        for e in group[1:]:
            if e["start_s"] < current["end_s"]:  # strict overlap
                current["end_s"] = max(current["end_s"], e["end_s"])
                current["amplitude"] = max(current["amplitude"], e["amplitude"])
                if e["octave_shift_applied"]:
                    current["octave_shift_applied"] = True
                    if current["source_midi"] is None:
                        current["source_midi"] = e["source_midi"]
            else:
                merged.append(current)
                current = dict(e)
        merged.append(current)

    return sorted(merged, key=lambda e: e["start_s"])


def _shift_to_playable(midi: int) -> int:
    """Shift midi up by octaves until it reaches _MIDI_MIN."""
    while midi < _MIDI_MIN:
        midi += 12
    return midi


def _drop_out_of_range(events: list[dict]) -> list[dict]:
    """Drop notes whose MIDI pitch is outside [_CLEAN_MIDI_MIN, _CLEAN_MIDI_MAX]."""
    return [e for e in events if _CLEAN_MIDI_MIN <= e["midi"] <= _CLEAN_MIDI_MAX]


def _drop_short_or_quiet(events: list[dict]) -> list[dict]:
    """Drop notes shorter than _MIN_DURATION_S or quieter than _MIN_AMPLITUDE."""
    return [
        e for e in events
        if (e["end_s"] - e["start_s"]) >= _MIN_DURATION_S
        and e["amplitude"] >= _MIN_AMPLITUDE
    ]


def _drop_octave_doubles(events: list[dict]) -> list[dict]:
    """When two notes start within _ONSET_WINDOW_S and are an octave or octave+fifth
    apart, drop the quieter one.

    Scans every pair once. If both have identical amplitude, the second (by index)
    is dropped to give a deterministic result.
    """
    to_drop: set[int] = set()
    for i in range(len(events)):
        for j in range(i + 1, len(events)):
            if abs(events[i]["start_s"] - events[j]["start_s"]) > _ONSET_WINDOW_S:
                continue
            if abs(events[i]["midi"] - events[j]["midi"]) not in _OCTAVE_INTERVALS:
                continue
            if events[i]["amplitude"] >= events[j]["amplitude"]:
                to_drop.add(j)
            else:
                to_drop.add(i)
    return [e for idx, e in enumerate(events) if idx not in to_drop]


def _merge_same_pitch(events: list[dict]) -> list[dict]:
    """Merge same-pitch notes that touch or overlap into one note.

    The merged note spans from the earliest start to the latest end and
    keeps the loudest amplitude. Events must be sorted by start_s on entry;
    output is also sorted by start_s.
    """
    by_midi: dict[int, list[dict]] = defaultdict(list)
    for e in events:
        by_midi[e["midi"]].append(e)

    merged: list[dict] = []
    for _midi, group in by_midi.items():
        group = sorted(group, key=lambda e: e["start_s"])
        current = dict(group[0])
        for e in group[1:]:
            if e["start_s"] <= current["end_s"]:
                current["end_s"] = max(current["end_s"], e["end_s"])
                current["amplitude"] = max(current["amplitude"], e["amplitude"])
            else:
                merged.append(current)
                current = dict(e)
        merged.append(current)

    return sorted(merged, key=lambda e: e["start_s"])


def _is_ghost(note: dict, all_events: list[dict]) -> bool:
    """Return True if note is a harmonic artifact above a louder concurrent note.

    Two kinds count as ghosts:
    - one octave (or octave + fifth) up, when the lower note is at least twice as loud;
    - two or three octaves up, when the lower note is louder at all.
    """
    for other in all_events:
        if other is note:
            continue
        concurrent = note["start_s"] < other["end_s"] and other["start_s"] < note["end_s"]
        if not concurrent:
            continue
        interval = note["midi"] - other["midi"]
        if interval in _OCTAVE_INTERVALS and other["amplitude"] >= 2.0 * note["amplitude"]:
            return True
        if interval in _WIDE_OCTAVE_INTERVALS and other["amplitude"] > note["amplitude"]:
            return True
    return False


def _assign_string_fret(
    midi: int,
    prev_fret: int | None,
    last_end: dict[int, float],
    start_s: float,
) -> tuple[int, int] | None:
    """Return (string, fret) for midi, or None if no string can play it.

    Prefers options within 4 frets of the previous placed note; breaks
    ties by lowest fret. Falls back to globally lowest fret if nothing is nearby.
    """
    valid = []
    for string_idx, open_note in enumerate(_TUNING):
        fret = midi - open_note - _CAPO
        if 0 <= fret <= _FRET_MAX and start_s >= last_end.get(string_idx, 0.0):
            valid.append((string_idx, fret))

    if not valid:
        return None

    if prev_fret is not None:
        nearby = [(s, f) for s, f in valid if abs(f - prev_fret) <= 4]
        if nearby:
            return min(nearby, key=lambda x: x[1])

    return min(valid, key=lambda x: x[1])
