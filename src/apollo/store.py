"""
store.py — the only module that knows where every file lives.

All other modules call these functions to read and write. Nothing else
touches the songs/ folder directly.
"""
from __future__ import annotations

import json
import os
import pathlib
import tempfile
from typing import Any


SCHEMA_VERSION = 1


class SchemaError(ValueError):
    """Raised when a JSON file has the wrong schema_version."""


class SongStore:
    """Reads and writes every file in the song folder layout.

    Pass the songs root as a parameter so tests can use a temp folder
    instead of the real songs/ directory.
    """

    def __init__(self, root: pathlib.Path | str) -> None:
        self.root = pathlib.Path(root)

    # ── directory helpers ──────────────────────────────────────────────

    def song_dir(self, song_id: str) -> pathlib.Path:
        return self.root / song_id

    # ── path helpers ───────────────────────────────────────────────────

    def song_path(self, song_id: str) -> pathlib.Path:
        return self.song_dir(song_id) / "song.json"

    def mix_path(self, song_id: str) -> pathlib.Path:
        return self.song_dir(song_id) / "mix.wav"

    def stem_path(self, song_id: str, stem: str) -> pathlib.Path:
        return self.song_dir(song_id) / "stems" / f"{stem}.wav"

    def backing_path(self, song_id: str, target: str) -> pathlib.Path:
        return self.song_dir(song_id) / "backing" / f"{target}.wav"

    def notes_path(self, song_id: str, target: str) -> pathlib.Path:
        return self.song_dir(song_id) / "notes" / f"{target}.json"

    def chart_path(self, song_id: str, target: str) -> pathlib.Path:
        return self.song_dir(song_id) / "chart" / f"{target}.json"

    # ── JSON read/write ────────────────────────────────────────────────

    def read_song(self, song_id: str) -> dict[str, Any]:
        return self._read_json(self.song_path(song_id))

    def write_song(self, song_id: str, data: dict[str, Any]) -> None:
        self._atomic_write(self.song_path(song_id), data)

    def read_notes(self, song_id: str, target: str) -> dict[str, Any]:
        return self._read_json(self.notes_path(song_id, target))

    def write_notes(self, song_id: str, target: str, data: dict[str, Any]) -> None:
        self._atomic_write(self.notes_path(song_id, target), data)

    def read_chart(self, song_id: str, target: str) -> dict[str, Any]:
        return self._read_json(self.chart_path(song_id, target))

    def write_chart(self, song_id: str, target: str, data: dict[str, Any]) -> None:
        self._atomic_write(self.chart_path(song_id, target), data)

    # ── internals ─────────────────────────────────────────────────────

    def _read_json(self, path: pathlib.Path) -> dict[str, Any]:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self._check_schema(data)
        return data

    def _atomic_write(self, path: pathlib.Path, data: dict[str, Any]) -> None:
        """Write data to path atomically: temp file then rename.

        A crash during the write never leaves a half-written file.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(data, indent=2)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _check_schema(self, data: dict[str, Any]) -> None:
        if data.get("schema_version") != SCHEMA_VERSION:
            raise SchemaError(
                f"Expected schema_version {SCHEMA_VERSION}, "
                f"got {data.get('schema_version')!r}"
            )
