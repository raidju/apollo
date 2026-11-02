# Stub: fakes P1 (song import and ID assignment) and P2 (audio extraction).
# Real P1: validate file type, check audio stream, reject files > 10 min.
# Real P2: decode any format to 44.1 kHz stereo WAV via imageio-ffmpeg.

from __future__ import annotations

import hashlib
import pathlib
import shutil

from lodestone.store import SongStore


def ingest(source_path: str | pathlib.Path, store: SongStore) -> str:
    """Import a song file and return its song_id.

    Computes the song_id from the file's SHA-256 hash, copies the file
    to mix.wav in the song folder, and writes an initial song.json with
    all prep stages set to pending.

    The stub copies the file as-is instead of decoding through ffmpeg.
    Real code will convert any format (MP3, MP4, WAV) to a standard WAV.
    """
    source_path = pathlib.Path(source_path)

    # song_id is the first 16 hex characters of the file's SHA-256 hash.
    # The same file always gets the same ID, so importing twice is free.
    song_id = _sha256_prefix(source_path)

    # Create the song directory (safe to call again if already exists).
    store.song_dir(song_id).mkdir(parents=True, exist_ok=True)

    # Copy the file to mix.wav. Real code will decode to 44.1 kHz stereo WAV.
    shutil.copy2(source_path, store.mix_path(song_id))

    # Write the initial song.json with ingest marked done and the rest pending.
    song_data = {
        "schema_version": 1,
        "song_id": song_id,
        "title": source_path.stem,
        "duration_s": 0.0,  # stub: real code reads this from the WAV header
        "low_note_mode": "drop",
        "stages": {
            "ingest": "done",
            "separate": "pending",
            "transcribe": {"guitar": "pending"},
            "chart": {"guitar": "pending"},
        },
        "error": None,
    }
    store.write_song(song_id, song_data)

    return song_id


def _sha256_prefix(path: pathlib.Path) -> str:
    """Return the first 16 hex chars of the SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]
