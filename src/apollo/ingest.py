from __future__ import annotations

import hashlib
import pathlib
import shutil
import subprocess

from apollo.store import SongStore

_WAV_FORMATS = {".wav"}
_CONVERTIBLE_FORMATS = {".mp3", ".mp4", ".m4a", ".flac", ".ogg", ".aac"}


def ingest(source_path: str | pathlib.Path, store: SongStore) -> str:
    """Import a song file and return its song_id.

    Accepts WAV, MP3, MP4, and other common formats. Non-WAV files are
    decoded to 44.1 kHz stereo 16-bit WAV via the ffmpeg binary bundled
    with imageio-ffmpeg. WAV files are copied as-is.
    """
    source_path = pathlib.Path(source_path)
    suffix = source_path.suffix.lower()

    if suffix not in _WAV_FORMATS | _CONVERTIBLE_FORMATS:
        raise ValueError(f"Unsupported file format: {suffix!r}")

    # song_id is the first 16 hex characters of the file's SHA-256 hash.
    # The same file always gets the same ID, so importing twice is free.
    song_id = _sha256_prefix(source_path)

    # Create the song directory (safe to call again if already exists).
    store.song_dir(song_id).mkdir(parents=True, exist_ok=True)

    mix_path = store.mix_path(song_id)
    if suffix in _WAV_FORMATS:
        shutil.copy2(source_path, mix_path)
    else:
        _convert_to_wav(source_path, mix_path)

    # Write the initial song.json with ingest marked done and the rest pending.
    # duration_s is 0.0 here; the transcribe step fills it in from the WAV header.
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


def _convert_to_wav(source_path: pathlib.Path, dest_path: pathlib.Path) -> None:
    """Decode source_path to 44.1 kHz stereo 16-bit WAV at dest_path."""
    import imageio_ffmpeg  # bundled ffmpeg binary — no system install needed

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run(
        [
            ffmpeg, "-y",
            "-i", str(source_path),
            "-vn",             # strip video track (for MP4)
            "-ar", "44100",
            "-ac", "2",
            "-sample_fmt", "s16",
            str(dest_path),
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="replace"))


def _sha256_prefix(path: pathlib.Path) -> str:
    """Return the first 16 hex chars of the SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]
