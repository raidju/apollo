# Status

## What works

- **Tuner** — live pitch detection (YIN algorithm), note name, cents sharp/flat, suggested guitar string. All open-string, silence, noise, and display tests pass (`tests/test_pitch_tuner.py`).
- **Song import** — WAV, MP3, MP4 accepted. Content-addressed by SHA-256 so importing the same file twice does nothing. Tested in `tests/test_prep.py`.
- **Instrument separation** — Demucs `htdemucs_6s` on CPU, offline after one model download. Real code in `src/apollo/separate.py`. Requires `uv sync --extra ml` and `uv run python -m apollo.separate --download` once per machine.
- **Transcription** — Basic Pitch turns the isolated stem into a note list. Real code in `src/apollo/transcribe.py`. Requires ML extras.
- **Chart building** — all five architecture guarantees enforced (sorted, valid times, pitch arithmetic, no string overlaps, playable frets) and tested in `tests/test_chart_guarantees.py`. Ghost-note filtering, octave-shift deduplication, and string/fret assignment are real implementations.
- **Prep pipeline** — separate → transcribe → chart runs in a background process (`jobs.start_prep`). Updates `song.json` stages live so the Songs tab can show progress. Tested end-to-end in `tests/test_prep.py`.
- **Chart display** — scrollable guitar tab (Tkinter canvas), color-coded by string, fret numbers shown.
- **Backing track playback** — plays from the Chart tab with an animated play line and per-note highlight.
- **Windows exe** — PyInstaller build via `apollo.spec` produces `launch/Apollo.exe`.

## What's next

- **Live play-along scoring** — the "Score my playing" button exists in the Chart tab but is disabled. `src/apollo/onsets.py` and `src/apollo/scoring.py` do not exist yet; they are specified in `docs/ARCHITECTURE.md`.
- **Calibration** — latency measurement for fair timing. `src/apollo/settings.py` exists; calibration flow is unconfirmed.
- **Section looping** — not started.
- **Final UI framework** — current GUI is `dev_gui.py` (tkinter), marked temporary in the source. README says "UI framework: not chosen yet."

## Known issues

- UI is a temporary tkinter preview; production framework not chosen.
- ML extras (torch, Demucs, Basic Pitch) must be installed separately with `uv sync --extra ml`. The exe bundles everything except torch and Demucs (too large to bundle).
- Separation model (~55 MB) must be downloaded once per machine while online; prep fails offline until this is done.
- unconfirmed: behaviour on Apple Silicon Mac — no CI runs against macOS.
