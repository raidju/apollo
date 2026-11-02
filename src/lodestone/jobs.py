# Real code: launches the full prep pipeline in a background process and
# tracks progress by updating song.json stages via store.
#
# ingest is called by the caller before start_prep, so _run_prep only
# handles separate, transcribe, and chart.

from __future__ import annotations

import multiprocessing
import pathlib

from lodestone.store import SongStore


def start_prep(
    song_id: str,
    target: str,
    store_root: pathlib.Path | str,
) -> multiprocessing.Process:
    """Start the prep pipeline in a background process and return it.

    The caller is responsible for calling .join() or polling .exitcode.
    store_root is passed as a plain Path (not a SongStore) so it
    serialises cleanly across the process boundary.
    """
    store_root = pathlib.Path(store_root)
    proc = multiprocessing.Process(
        target=_run_prep,
        args=(song_id, target, store_root),
        daemon=False,  # must not be a daemon so it can spawn child workers later
    )
    proc.start()
    return proc


def _run_prep(song_id: str, target: str, store_root: pathlib.Path) -> None:
    """Run separate → transcribe → chart inside the child process.

    Updates song.json before and after each step so the UI can show
    live progress. On any error, marks the failing stage as 'failed'
    and exits with a non-zero code.
    """
    # Import here so the imports only happen inside the child process.
    from lodestone.chart import build_chart
    from lodestone.separate import separate
    from lodestone.transcribe import transcribe

    store = SongStore(store_root)

    steps = [
        ("separate",   lambda: separate(song_id, target, store),          None),
        ("transcribe", lambda: transcribe(song_id, target, store),         target),
        ("chart",      lambda: build_chart(song_id, target, store),        target),
    ]

    for stage_key, fn, sub in steps:
        try:
            _set_stage(song_id, stage_key, "running", store, sub=sub)
            print(f"[prep] {stage_key}: running", flush=True)
            fn()
            _set_stage(song_id, stage_key, "done", store, sub=sub)
            print(f"[prep] {stage_key}: done", flush=True)
        except Exception as exc:
            _set_stage(song_id, stage_key, "failed", store, sub=sub)
            print(f"[prep] {stage_key}: failed — {exc}", flush=True)
            raise


def _set_stage(
    song_id: str,
    stage: str,
    value: str,
    store: SongStore,
    sub: str | None = None,
) -> None:
    """Read song.json, update one stage value, write it back atomically."""
    data = store.read_song(song_id)
    if sub is None:
        data["stages"][stage] = value
    else:
        # stages like transcribe and chart are dicts keyed by target name.
        data["stages"][stage][sub] = value
    store.write_song(song_id, data)
