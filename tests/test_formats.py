"""
test_formats.py — checks that every fixture file matches the handoff
format defined in ARCHITECTURE.md.
"""
import json
import pathlib


FIXTURES = pathlib.Path(__file__).parent / "fixtures"

VALID_STAGES = {"pending", "running", "done", "failed"}
VALID_GRADES = {"perfect", "good", "early", "late", "wrong_pitch", "miss"}


def _stage_values(stages: dict):
    """Yield every leaf stage value from a possibly-nested stages dict."""
    for v in stages.values():
        if isinstance(v, dict):
            yield from v.values()
        else:
            yield v


def test_song_json():
    with open(FIXTURES / "song.json") as f:
        song = json.load(f)

    assert song["schema_version"] == 1
    assert isinstance(song["song_id"], str) and len(song["song_id"]) == 16
    int(song["song_id"], 16)  # must be valid hex
    assert song["duration_s"] > 0
    for v in _stage_values(song["stages"]):
        assert v in VALID_STAGES, f"Unknown stage value: {v!r}"
    assert song["error"] is None or isinstance(song["error"], str)


def test_notes_guitar_json():
    with open(FIXTURES / "notes" / "guitar.json") as f:
        notes = json.load(f)

    assert notes["schema_version"] == 1
    assert isinstance(notes["target"], str)
    assert isinstance(notes["events"], list)
    for ev in notes["events"]:
        assert "start_s" in ev and "end_s" in ev
        assert 0 <= ev["midi"] <= 127
        assert 0.0 <= ev["amplitude"] <= 1.0


def test_chart_guitar_json():
    with open(FIXTURES / "chart" / "guitar.json") as f:
        chart = json.load(f)

    assert chart["schema_version"] == 1
    assert isinstance(chart["instrument"], str)
    assert isinstance(chart["tuning"], list) and len(chart["tuning"]) == 6
    assert chart["capo"] >= 0
    assert isinstance(chart["notes"], list)
    for note in chart["notes"]:
        assert "id" in note
        assert "start_s" in note and "end_s" in note
        assert 0 <= note["midi"] <= 127
        assert 0 <= note["string"] <= 5
        assert note["fret"] >= 0


def test_played_event_json():
    with open(FIXTURES / "played_event.json") as f:
        ev = json.load(f)

    assert ev["song_time_s"] >= 0
    assert 0 <= ev["midi"] <= 127
    assert 0.0 <= ev["confidence"] <= 1.0


def test_session_score_json():
    with open(FIXTURES / "session_score.json") as f:
        score = json.load(f)

    assert 0 <= score["hit_pct"] <= 100
    assert 0 <= score["perfect_pct"] <= 100
    assert score["mean_abs_timing_ms"] >= 0
    assert score["extra_notes"] >= 0
    assert isinstance(score["results"], list)
    for r in score["results"]:
        assert "note_id" in r
        assert r["grade"] in VALID_GRADES, f"Unknown grade: {r['grade']!r}"
        assert isinstance(r["timing_error_ms"], (int, float))
        assert 0 <= r["played_midi"] <= 127
