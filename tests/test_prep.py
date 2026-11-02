"""
test_prep.py — tests for the prep pipeline stubs (ingest, separate,
transcribe, chart) and the jobs process launcher.
"""
import pathlib
import shutil
from collections import defaultdict

import pytest

from lodestone.chart import build_chart
from lodestone.ingest import ingest
from lodestone.jobs import start_prep
from lodestone.separate import separate
from lodestone.store import SongStore
from lodestone.transcribe import transcribe


SAMPLE_WAV = pathlib.Path(__file__).parent / "fixtures" / "sample.wav"


# ── helpers ────────────────────────────────────────────────────────────


def _make_store(tmp_path: pathlib.Path) -> SongStore:
    return SongStore(tmp_path / "songs")


def _ingest_sample(store: SongStore, tmp_path: pathlib.Path) -> str:
    """Copy sample.wav into tmp_path and ingest it. Returns song_id."""
    src = tmp_path / "sample.wav"
    shutil.copy2(SAMPLE_WAV, src)
    return ingest(src, store)


# ── tests ──────────────────────────────────────────────────────────────


def test_ingest(tmp_path):
    store = _make_store(tmp_path)
    song_id = _ingest_sample(store, tmp_path)

    # song_id is exactly 16 hex characters
    assert len(song_id) == 16
    int(song_id, 16)  # raises ValueError if not valid hex

    # mix.wav was written
    assert store.mix_path(song_id).exists()

    # song.json has the correct shape
    song = store.read_song(song_id)
    assert song["song_id"] == song_id
    assert song["stages"]["ingest"] == "done"
    assert song["stages"]["separate"] == "pending"
    assert song["stages"]["transcribe"]["guitar"] == "pending"
    assert song["stages"]["chart"]["guitar"] == "pending"


def test_separate(tmp_path):
    store = _make_store(tmp_path)
    song_id = _ingest_sample(store, tmp_path)

    separate(song_id, "guitar", store)

    assert store.stem_path(song_id, "guitar").exists()
    assert store.backing_path(song_id, "guitar").exists()


def test_transcribe(tmp_path):
    store = _make_store(tmp_path)
    song_id = _ingest_sample(store, tmp_path)
    separate(song_id, "guitar", store)

    transcribe(song_id, "guitar", store)

    assert store.notes_path(song_id, "guitar").exists()

    notes = store.read_notes(song_id, "guitar")
    assert notes["schema_version"] == 1
    assert notes["target"] == "guitar"
    assert isinstance(notes["events"], list)
    assert len(notes["events"]) > 0

    starts = [e["start_s"] for e in notes["events"]]
    assert starts == sorted(starts), "events must be sorted by start_s"

    for ev in notes["events"]:
        assert 0 <= ev["midi"] <= 127
        assert 0.0 <= ev["amplitude"] <= 1.0
        assert ev["end_s"] > ev["start_s"]


def test_chart_stub(tmp_path):
    store = _make_store(tmp_path)
    song_id = _ingest_sample(store, tmp_path)
    separate(song_id, "guitar", store)
    transcribe(song_id, "guitar", store)

    build_chart(song_id, "guitar", store)

    assert store.chart_path(song_id, "guitar").exists()

    chart = store.read_chart(song_id, "guitar")
    tuning = chart["tuning"]
    capo = chart["capo"]
    notes = chart["notes"]

    # Guarantee 1: sorted by start_s
    starts = [n["start_s"] for n in notes]
    assert starts == sorted(starts)

    # Guarantee 2: end_s > start_s for every note
    for n in notes:
        assert n["end_s"] > n["start_s"], f"note {n['id']}: end not after start"

    # Guarantee 3: tuning[string] + capo + fret == midi
    for n in notes:
        expected = tuning[n["string"]] + capo + n["fret"]
        assert expected == n["midi"], (
            f"note {n['id']}: tuning arithmetic failed "
            f"({tuning[n['string']]} + {capo} + {n['fret']} != {n['midi']})"
        )

    # Guarantee 4: no two notes overlap on the same string
    by_string: dict[int, list] = defaultdict(list)
    for n in notes:
        by_string[n["string"]].append(n)
    for string_id, snotes in by_string.items():
        snotes_sorted = sorted(snotes, key=lambda n: n["start_s"])
        for i in range(len(snotes_sorted) - 1):
            a, b = snotes_sorted[i], snotes_sorted[i + 1]
            assert a["end_s"] <= b["start_s"], (
                f"string {string_id}: notes {a['id']} and {b['id']} overlap"
            )

    # Guarantee 5: all frets in [0, 24]
    for n in notes:
        assert 0 <= n["fret"] <= 24, f"note {n['id']}: fret {n['fret']} out of range"


def test_jobs_stages(tmp_path):
    store = _make_store(tmp_path)
    song_id = _ingest_sample(store, tmp_path)

    proc = start_prep(song_id, "guitar", store.root)
    proc.join(timeout=60)

    assert proc.exitcode == 0, f"prep process exited with code {proc.exitcode}"

    song = store.read_song(song_id)
    assert song["stages"]["separate"] == "done"
    assert song["stages"]["transcribe"]["guitar"] == "done"
    assert song["stages"]["chart"]["guitar"] == "done"
