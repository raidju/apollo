# Walking Skeleton — Three PRs

## Goal

Every module exists as a stub that returns fake data in the exact shapes
from ARCHITECTURE.md, and the stubs are wired together so one command
runs the whole app end to end.

Observable outcome:

```
uv run python -m lodestone demo tests/fixtures/sample.wav
```

1. Imports the file (song_id = first 16 hex chars of SHA-256).
2. Runs prep in a separate background process via `jobs`, which updates
   `song.json` stages `pending → running → done` and prints progress.
3. Writes every file in the song folder layout through `store`.
4. Runs a fake play-along: fake audio chunks → fake pitch readings →
   fake PlayedEvents → scoring → prints a SessionScore.
5. Runs the tuner path once and prints a fake reading.
6. Exits with code 0.

## Rules

- Real code in only two places: `store` (folder layout, JSON read/write,
  atomic write, schema_version check) and the wiring (`jobs` process
  launch + `demo` command). Everything else is a stub.
- `store` takes the songs root folder as a parameter so tests can use
  a temp folder. `songs/` stays gitignored.
- Stub output must pass the same checks real code will face. The chart
  stub must satisfy all 5 chart guarantees in ARCHITECTURE.md.
- No stub imports torch, demucs, basic_pitch, or sounddevice. The ui
  path must never import torch.
- No new dependencies. Standard library only: dataclasses, json,
  hashlib, multiprocessing, wave.
- Top of every stub file: a short comment saying what it fakes and
  which real step replaces it (P1-P5, L1-L6, T1-T3).
- Units: time as float seconds, pitch as MIDI ints, guitar strings
  numbered 0 = lowest.

---

## PR 1 — Package layout, store, fixtures, format checks, tests

### pyproject.toml

Move `demucs`, `basic-pitch`, and `onnxruntime` to an optional
`[project.optional-dependencies] ml = [...]` extra.

- `uv sync --locked` (no extras) installs only the skeleton.
- `uv sync --locked --extra ml` installs the full ML stack.

This is required because `demucs → torch → triton` has no Windows wheel,
so the base install would fail on Windows AMD64.

### New files

| Path | What it is |
|------|------------|
| `docs/ARCHITECTURE.md` | Copy from source; defines fixed handoff shapes |
| `src/lodestone/store.py` | Real implementation — atomic writes, schema checks |
| `tests/conftest.py` | Generates `tests/fixtures/sample.wav` on first run |
| `tests/fixtures/song.json` | Example song.json from ARCHITECTURE.md |
| `tests/fixtures/notes/guitar.json` | Example raw notes from ARCHITECTURE.md |
| `tests/fixtures/chart/guitar.json` | Example chart from ARCHITECTURE.md |
| `tests/fixtures/played_event.json` | Example PlayedEvent shape |
| `tests/fixtures/session_score.json` | Example SessionScore shape |
| `tests/test_formats.py` | Format validation for every fixture file |
| `tests/test_chart_guarantees.py` | All 5 chart guarantees against the fixture |
| `tests/test_store.py` | SongStore unit tests using tmp_path |

### Delete

- `tests/test_smoke.py` — tests ML imports not available without `--extra ml`.

---

## PR 2 — Prep stubs + jobs process

### New modules

| Module | Fakes | Real replacement |
|--------|-------|-----------------|
| `src/lodestone/ingest.py` | P1 + P2 | SHA-256 ID, validity check, ffmpeg decode |
| `src/lodestone/separate.py` | P3 | `demucs.api.Separator` |
| `src/lodestone/transcribe.py` | P4 | `basic_pitch.inference.predict` |
| `src/lodestone/chart.py` | P5 | ghost-note filter, string/fret assignment, chord grouping |
| `src/lodestone/jobs.py` | **real** | multiprocessing — already real in this PR |

`jobs.py` is real code: it launches prep in a background process and
updates `song.json` stages (`pending → running → done/failed`) via
`store`.

### New tests

`tests/test_prep.py` — each stub writes correct files; `jobs` updates
all stages to `"done"` after `.join()`.

---

## PR 3 — Live stubs, tuner stub, demo command, CI

### New modules

| Module | Fakes | Real replacement |
|--------|-------|-----------------|
| `src/lodestone/audio_io.py` | L2 + T1 | sounddevice duplex stream |
| `src/lodestone/pitch.py` | L3 + T2 | YIN algorithm |
| `src/lodestone/onsets.py` | L4 | amplitude/pitch transition detector |
| `src/lodestone/scoring.py` | L5 | note-matching within timing windows |
| `src/lodestone/tuner.py` | T3 | cents deviation + string guess |
| `src/lodestone/settings.py` | L1 | tap-test latency measurement |
| `src/lodestone/ui.py` | L6 | full GUI (framework TBD); **no torch import** |

### Updated files

- `src/lodestone/__init__.py` — add `demo()` command wiring all stubs.
- `src/lodestone/__main__.py` — entry point for `python -m lodestone`.

### New tests

- `tests/test_live.py` — stub unit tests for pitch, onsets, scoring, tuner.
- `tests/test_ui_no_torch.py` — importing `lodestone.ui` must not load torch.
- `tests/test_e2e.py` — full demo in a temp folder; assert all files exist
  and exit code is 0.

### CI

`.github/workflows/ci.yml` — matrix on `windows-latest` and `macos-latest`;
steps: checkout, install uv, `uv sync --locked`, `uv run pytest`.

---

## Verification

| PR | Command | Expected |
|----|---------|----------|
| 1 | `uv sync --locked` | succeeds without ML packages |
| 1 | `uv run pytest tests/test_formats.py tests/test_chart_guarantees.py tests/test_store.py` | all pass |
| 2 | `uv run pytest tests/test_prep.py` | all pass |
| 3 | `uv run pytest` | all pass |
| 3 | `uv run python -m lodestone demo tests/fixtures/sample.wav` | prints song_id, progress, score, tuner; exits 0 |
