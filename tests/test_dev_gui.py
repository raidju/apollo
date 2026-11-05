"""Tests for dev_gui pure helpers. No test opens a window or an audio device."""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

from apollo.dev_gui import (
    active_note_ids,
    cents_to_needle_x,
    list_songs,
    play_line_seconds,
    stage_row,
    string_to_y,
    time_to_x,
)
from apollo.ingest import ingest
from apollo.store import SongStore

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def test_no_heavy_imports() -> None:
    """Importing dev_gui must not pull in torch, demucs, or basic_pitch."""
    code = (
        "import apollo.dev_gui; import sys; "
        "bad = [m for m in ('torch', 'demucs', 'basic_pitch') if m in sys.modules]; "
        "assert not bad, bad"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_cents_to_needle_x() -> None:
    bar = 200
    assert cents_to_needle_x(-50.0, bar) == 0
    assert cents_to_needle_x(0.0, bar) == 100
    assert cents_to_needle_x(50.0, bar) == 200
    # Clamp
    assert cents_to_needle_x(200.0, bar) == 200
    assert cents_to_needle_x(-200.0, bar) == 0


def test_string_to_y() -> None:
    ys = [string_to_y(i) for i in range(6)]
    # High e (string 5) must be above low E (string 0) — smaller y = higher on screen
    assert string_to_y(5) < string_to_y(0)
    # All six y values must be distinct
    assert len(set(ys)) == 6


def test_time_to_x() -> None:
    assert time_to_x(0.0) >= 0
    assert time_to_x(1.0) > time_to_x(0.0)
    assert time_to_x(2.0) > time_to_x(1.0)


def test_list_songs(tmp_path: pathlib.Path) -> None:
    store = SongStore(tmp_path)
    song_id = ingest(FIXTURES / "sample.wav", store)
    # Empty folder should not appear
    (tmp_path / "empty_folder").mkdir()
    songs = list_songs(store)
    assert len(songs) == 1
    assert songs[0]["song_id"] == song_id


def test_stage_row() -> None:
    with open(FIXTURES / "song.json", encoding="utf-8") as f:
        song = json.load(f)
    row = stage_row(song, "guitar")
    assert row == ("Sample Song", "3f9a1c0e7b2d4a61", "✓", "✓", "✓", "✓")


def test_play_line_seconds() -> None:
    assert play_line_seconds(1.0, 5.0) == 1.0
    assert play_line_seconds(4.9, 5.0) == pytest.approx(4.9)
    assert play_line_seconds(5.0, 5.0) is None
    assert play_line_seconds(6.0, 5.0) is None


def test_active_note_ids() -> None:
    with open(FIXTURES / "chart" / "guitar.json", encoding="utf-8") as f:
        chart = json.load(f)
    # note 0: start=1.0, end=1.4  — active at 1.2
    assert active_note_ids(chart, 1.2) == {0}
    # note 1: start=2.0, end=2.5  — active at 2.2
    assert active_note_ids(chart, 2.2) == {1}
    # nothing at 0.5
    assert active_note_ids(chart, 0.5) == set()
