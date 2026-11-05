# Real code: launches the full prep pipeline in a background process and
# tracks progress by updating song.json stages via store.
#
# ingest is called by the caller before start_prep, so _run_prep only
# handles separate, transcribe, and chart.

from __future__ import annotations

import multiprocessing
import os
import pathlib
import subprocess
import sys

from apollo.store import SongStore


def start_prep(
    song_id: str,
    target: str,
    store_root: pathlib.Path | str,
) -> multiprocessing.Process | _SubprocWrapper:
    """Start the prep pipeline in a background process and return it.

    The caller is responsible for calling .join() or polling .exitcode.
    store_root is passed as a plain Path (not a SongStore) so it
    serialises cleanly across the process boundary.

    When running as a frozen exe, spawns the venv Python directly via
    subprocess so it can import torch/demucs from the venv site-packages.
    """
    store_root = pathlib.Path(store_root)

    # Write a diagnostic line from the parent process so we can confirm
    # which path is taken even if the child crashes silently.
    log_path = store_root / song_id / "prep.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    ml_python = _find_ml_python()
    log_path.write_text(
        f"start_prep: frozen={getattr(sys, 'frozen', False)!r}"
        f"  ml_python={ml_python!r}\n",
        encoding="utf-8",
    )

    if ml_python:
        # Frozen exe: spawn the venv Python directly so it can import torch.
        # Use a bootstrap -c script that adds src/ to sys.path explicitly,
        # avoiding reliance on the editable-install -m apollo.jobs mechanism.
        src_dir = str(pathlib.Path(sys.executable).parent.parent / "src")
        bootstrap = (
            "import sys, pathlib; "
            f"sys.path.insert(0, {src_dir!r}); "
            "from apollo.jobs import _run_prep; "
            f"_run_prep({song_id!r}, {target!r}, pathlib.Path({str(store_root)!r}))"
        )
        # Strip PyInstaller's temp dir from PATH before spawning. The frozen
        # exe adds _MEIPASS to PATH, and the subprocess inheriting that PATH
        # loads PyInstaller-bundled DLLs instead of system ones, which causes
        # torch's c10.dll initialization to fail with WinError 1114.
        env = os.environ.copy()
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            env["PATH"] = os.pathsep.join(
                p for p in env.get("PATH", "").split(os.pathsep)
                if p != meipass
            )
        log_file = open(log_path, "a", encoding="utf-8", buffering=1)
        proc = subprocess.Popen(
            [ml_python, "-c", bootstrap],
            stdout=log_file,
            stderr=log_file,
            env=env,
        )
        log_file.close()  # child has its own inherited handle
        return _SubprocWrapper(proc)

    proc = multiprocessing.Process(
        target=_run_prep,
        args=(song_id, target, store_root),
        daemon=False,  # must not be a daemon so it can spawn child workers later
    )
    proc.start()
    return proc


class _SubprocWrapper:
    """Exposes the same .exitcode property as multiprocessing.Process."""

    def __init__(self, proc: subprocess.Popen) -> None:
        self._proc = proc

    @property
    def exitcode(self) -> int | None:
        self._proc.poll()
        return self._proc.returncode


def _find_ml_python() -> str | None:
    """Return a Python executable that has the ML extras installed.

    When running frozen the child process re-enters the frozen exe, which
    never has torch. Use the project venv Python so the child gets a full
    site-packages with torch and demucs.
    Returns None when not frozen; ordinary multiprocessing behaviour is fine.
    """
    if not getattr(sys, "frozen", False):
        return None
    import shutil
    exe_path = pathlib.Path(sys.executable)
    # Search both the exe's own directory and its parent — the exe lives in
    # launch/ so the venv is one level up at lodestone/.venv/.
    for root in [exe_path.parent, exe_path.parent.parent]:
        for rel in [
            pathlib.Path(".venv") / "Scripts" / "python.exe",  # Windows
            pathlib.Path(".venv") / "bin" / "python",           # macOS/Linux
        ]:
            candidate = root / rel
            if candidate.exists():
                return str(candidate)
    return shutil.which("python") or shutil.which("python3")


def _run_prep(song_id: str, target: str, store_root: pathlib.Path) -> None:
    """Run separate → transcribe → chart inside the child process.

    Updates song.json before and after each step so the UI can show
    live progress. On any error, marks the failing stage as 'failed'
    and exits with a non-zero code.
    """
    # Import here so the imports only happen inside the child process.
    from apollo.chart import build_chart
    from apollo.separate import separate
    from apollo.transcribe import transcribe

    store = SongStore(store_root)

    steps = [
        ("separate",   lambda: separate(song_id, target, store),   None),
        ("transcribe", lambda: transcribe(song_id, target, store),  target),
        ("chart",      lambda: build_chart(song_id, target, store), target),
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
            return


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


if __name__ == "__main__":
    _run_prep(sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3]))
