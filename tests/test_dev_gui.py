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
    format_elapsed,
    list_songs,
    play_line_seconds,
    prep_caption,
    prep_display_states,
    prep_step_states,
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


def _song_with_stages(separate: str, transcribe: str, chart: str) -> dict:
    return {
        "stages": {
            "ingest": "done",
            "separate": separate,
            "transcribe": {"guitar": transcribe},
            "chart": {"guitar": chart},
        }
    }


def test_prep_step_states_reads_plain_and_per_target_stages() -> None:
    song = _song_with_stages("done", "running", "pending")
    assert prep_step_states(song, "guitar") == ["done", "running", "pending"]


def test_prep_step_states_missing_stages_are_pending() -> None:
    assert prep_step_states({}, "guitar") == ["pending", "pending", "pending"]


def test_display_states_hide_leftovers_from_an_earlier_run() -> None:
    # Re-running prep: step 1 is running again, steps 2 and 3 still say done from last time.
    leftover = ["running", "done", "done"]
    assert prep_display_states(leftover, finished=False) == ["running", "pending", "pending"]


def test_display_states_before_first_step_starts_are_all_pending() -> None:
    assert prep_display_states(["done", "done", "failed"], finished=False) == [
        "pending", "pending", "pending",
    ]


def test_display_states_when_finished_are_unchanged() -> None:
    assert prep_display_states(["done", "failed", "pending"], finished=True) == [
        "done", "failed", "pending",
    ]


def test_format_elapsed() -> None:
    assert format_elapsed(0.0) == "0:00"
    assert format_elapsed(9.9) == "0:09"
    assert format_elapsed(83.4) == "1:23"
    assert format_elapsed(-5.0) == "0:00"


def test_caption_while_running_names_step_and_elapsed_time() -> None:
    caption = prep_caption(["done", "running", "pending"], 75.0, finished=False)
    assert "Step 2 of 3" in caption
    assert "1:15 elapsed" in caption


def test_caption_before_any_step_runs() -> None:
    caption = prep_caption(["pending", "pending", "pending"], 2.0, finished=False)
    assert caption.startswith("Starting prep")


def test_caption_when_complete() -> None:
    caption = prep_caption(["done", "done", "done"], 192.0, finished=True)
    assert caption == "Prep complete in 3:12."


def test_caption_when_a_step_failed_names_that_step() -> None:
    caption = prep_caption(["done", "failed", "pending"], 50.0, finished=True)
    assert "Step 2 of 3 failed" in caption
    assert "prep.log" in caption


def test_caption_when_process_stopped_without_marking_a_step() -> None:
    caption = prep_caption(["done", "running", "pending"], 50.0, finished=True)
    assert caption.startswith("Prep stopped before finishing")


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
