# Apollo — Instrument Practice App

A desktop app that helps you practice an instrument: a tuner, play-along charts built from songs you choose, and a practice mode that scores your timing and pitch against the original recording.

## What it does

You give Apollo a song you already own. It removes the instrument you want to practice, turns that instrument's part into a readable chart (guitar tab with string and fret numbers), and plays back the rest of the band while you play along. The app listens through your microphone and scores how close you were, note by note.

Runs on a laptop with no internet connection. Input is a built-in microphone, a USB instrument cable, or any audio interface.


## Setup

You need [uv](https://docs.astral.sh/uv/) **0.12.19 or newer** installed first.

**Windows** — run this in PowerShell, then restart PowerShell:
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**macOS** — run this in Terminal:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then clone the repo and install:
```bash
git clone <repo-url>
cd <repo-folder>
uv sync --locked
```

`--locked` ensures you get the exact same versions as everyone else. If `uv.lock` is out of date it will tell you instead of quietly changing versions.

### Install the ML dependencies (required for Prep)

Separation and transcription use Demucs and Basic Pitch, which live in a separate optional group so the app still loads on machines that don't need them. Install them with:

```bash
uv sync --locked --extra ml
```

> **This step is required** if you want to prep songs (separate stems, generate charts). Without it, clicking "Prep selected" will fail with a "No module named 'torch'" error.


## Running the app

### Option 1 — Double-click exe (Windows)

Build it once:
```bash
uv sync
uv run pyinstaller apollo.spec
```

That produces `dist/Apollo.exe` (~138 MB, single file, no console window). Double-click it to launch. You can move or copy it anywhere — it is self-contained.

> **Prep still needs the ML extras.** The exe bundles everything except torch and Demucs (too large). If you click "Prep selected" and it fails, see the ML step below under [Install the ML dependencies](#install-the-ml-dependencies-required-for-prep).

### Option 2 — Run from source

```bash
uv run python -m apollo.dev_gui
```

Opens the same window directly from the source tree. Use this during development.

---

Opens the preview window with three tabs: Tuner, Songs, and Chart.

### Quick walkthrough

1. **Tuner tab** — Click Start, play a note, see the note name and how many cents sharp or flat you are.
2. **Songs tab** — Click "Import song…" to load a WAV, MP3, or MP4 file. Select it in the list and click "Prep selected" to separate the stems and build the chart. The four stage indicators (Ingest / Separate / Transcribe / Chart) update as it runs. Prep takes a few minutes.
3. **Chart tab** — Once prep finishes, click "Open in Chart tab" on the Songs tab. Click "Play backing" to start the backing track and watch the play line move through the chart.


## Troubleshooting

### The app won't start at all

**Missing Python or packages** — make sure you ran `uv sync --locked` from the project root. If you see an import error, run it again.

**TensorFlow error at install time** — your uv is too old. Upgrade it and re-run `uv sync --locked`:
```bash
uv self update
uv sync --locked
```

### "No module named 'torch'" when clicking Prep

The ML extras are not installed. Run:
```bash
uv sync --locked --extra ml
```

### Prep fails partway through

Check the terminal window where you launched the app — the error from the failed step is printed there. The most common causes:

- **Separation fails** — `torch` or `demucs` not installed (see above).
- **Very short file** — files under about 10 seconds may not have enough audio for the model to work with.
- **Corrupted file** — try a different copy of the song.

### Audio device errors in the Tuner tab

- **Windows** — make sure your microphone is not disabled in Settings → System → Sound → Input.
- **macOS** — Terminal (or your IDE) needs microphone permission: System Settings → Privacy & Security → Microphone.

### The chart looks very short compared to the song length

The chart was most likely built from a stub or a very quiet recording. Re-import the song and run Prep again. The status bar on the Chart tab will warn you if the chart covers less than 30% of the backing track's length.


## Libraries

Only Python and uv are installed by hand. Everything else comes from `uv.lock`.

| Library | What it does |
| --- | --- |
| Python 3.12 | The language, pinned in `.python-version` |
| [uv](https://docs.astral.sh/uv/) | Installs everything from the lockfile |
| [Demucs](https://github.com/adefossez/demucs) | Splits a song into separate instrument stems |
| [Basic Pitch](https://github.com/spotify/basic-pitch) | Turns a stem into individual notes |
| [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) | Decodes MP3, MP4, and other formats to WAV — includes its own ffmpeg binary |
| [sounddevice](https://python-sounddevice.readthedocs.io/) | Plays the backing track and records the mic |
| [soundfile](https://python-soundfile.readthedocs.io/) | Reads and writes WAV files |
| [numpy](https://numpy.org/) | Math for the pitch detector |
| [librosa](https://librosa.org/) | Audio helpers used in tests |
| [mir_eval](https://github.com/mir-evaluation/mir_eval) | Measures transcription accuracy in tests |

UI framework: not chosen yet.

### Built from scratch

These parts are small enough that we built them ourselves rather than pulling in a library:

- **Pitch detector (YIN):** detects which note is being played. Existing library options don't install reliably on Windows.
- **Note-start detection:** tells one held note apart from two repeated notes.
- **String and fret assignment:** picks the most playable position on the neck for each note.
- **Scoring:** matches what you played to the chart and grades each note.


## Features

Core features are targeted for the February state competition.

| Feature | What you get | Priority |
| --- | --- | --- |
| Tuner | Live note name and cents sharp/flat per string | Core |
| Song import | Load an MP3, WAV, or MP4 you already own | Core |
| Backing track | The song with your instrument removed | Core |
| Auto chart | Your instrument's notes as a chart (guitar: tab with string + fret) | Core |
| Play-along | Backing track plays while the chart scrolls | Core |
| Scoring | Percentage of notes hit, plus timing for each note | Core |
| Calibration | Short tap test so timing is fair on any laptop and mic | Core |
| Section looping | Repeat one hard section and score each pass | Core |
| Chord scoring | Checks every note in a chord, not just one | Stretch |
| Chart editor | Fix notes the auto chart got wrong | Stretch |
| Piano mode | Note-lane view for piano | Stretch |
| MIDI keyboard input | Score a plugged-in keyboard directly | Stretch |
| Slow-down practice | Play along at a reduced speed | Stretch |
| Alternate tunings | Drop D, open G, and others | Stretch |

**Out of scope:** streaming services. Their developer policies forbid analyzing their audio. Import files you already own.


## Contributing

1. Pick an issue from the project board, or open one, or just mention what you're working on so we stay coordinated.
2. Branch off `main` — one branch per change.
3. Don't commit directly to `main`.

Run the tests before pushing:
```bash
uv run pytest
```


## Constraints

- Works with no internet connection after setup.
- Works the same on Windows (x86-64) and Apple Silicon Macs.
