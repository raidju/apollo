"""
test_store.py — unit tests for SongStore using a pytest tmp_path folder.
"""
import json

import pytest

from lodestone.store import SchemaError, SongStore


SONG_ID = "abc123test"

VALID_SONG = {
    "schema_version": 1,
    "song_id": SONG_ID,
    "title": "Test Song",
    "duration_s": 10.0,
    "stages": {"ingest": "done"},
    "error": None,
}

VALID_NOTES = {
    "schema_version": 1,
    "target": "guitar",
    "events": [{"start_s": 0.0, "end_s": 0.5, "midi": 64, "amplitude": 0.8}],
}

VALID_CHART = {
    "schema_version": 1,
    "instrument": "guitar",
    "tuning": [40, 45, 50, 55, 59, 64],
    "capo": 0,
    "notes": [
        {"id": 0, "start_s": 0.0, "end_s": 0.5, "midi": 40, "string": 0, "fret": 0, "chord": None}
    ],
}


def test_song_round_trip(tmp_path):
    store = SongStore(tmp_path)
    store.write_song(SONG_ID, VALID_SONG)
    assert store.read_song(SONG_ID) == VALID_SONG


def test_notes_round_trip(tmp_path):
    store = SongStore(tmp_path)
    store.write_notes(SONG_ID, "guitar", VALID_NOTES)
    assert store.read_notes(SONG_ID, "guitar") == VALID_NOTES


def test_chart_round_trip(tmp_path):
    store = SongStore(tmp_path)
    store.write_chart(SONG_ID, "guitar", VALID_CHART)
    assert store.read_chart(SONG_ID, "guitar") == VALID_CHART


def test_atomic_write_no_tmp_left(tmp_path):
    """After a successful write, no .tmp file should remain in the directory."""
    store = SongStore(tmp_path)
    store.write_song(SONG_ID, VALID_SONG)
    tmp_files = list(store.song_dir(SONG_ID).glob("*.tmp"))
    assert tmp_files == []


def test_schema_error_on_wrong_version(tmp_path):
    store = SongStore(tmp_path)
    bad = {**VALID_SONG, "schema_version": 99}
    store.write_song(SONG_ID, bad)  # _atomic_write does not validate on write
    with pytest.raises(SchemaError):
        store.read_song(SONG_ID)


def test_schema_error_on_missing_version(tmp_path):
    store = SongStore(tmp_path)
    path = store.song_path(SONG_ID)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"no_version": True}), encoding="utf-8")
    with pytest.raises(SchemaError):
        store.read_song(SONG_ID)


def test_path_structure(tmp_path):
    store = SongStore(tmp_path)
    sid = "testid"
    assert store.song_path(sid) == tmp_path / sid / "song.json"
    assert store.mix_path(sid) == tmp_path / sid / "mix.wav"
    assert store.stem_path(sid, "guitar") == tmp_path / sid / "stems" / "guitar.wav"
    assert store.backing_path(sid, "guitar") == tmp_path / sid / "backing" / "guitar.wav"
    assert store.notes_path(sid, "guitar") == tmp_path / sid / "notes" / "guitar.json"
    assert store.chart_path(sid, "guitar") == tmp_path / sid / "chart" / "guitar.json"
