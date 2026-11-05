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

### Download the separation model (once, while online)

The model that splits out the guitar (about 55 MB) isn't part of the install. Download it once on each machine:

```bash
uv run python -m apollo.separate --download
```

After that, song prep never goes online, so it works with no internet. If you skip this step, the "Split instruments" step fails and `prep.log` shows `Separation model not downloaded`, along with the command above.


## Running the app

### Option 1 — Double-click exe (Windows)

Build it once:
```powershell
uv sync --locked
Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
Remove-Item -Recurse -Force build -ErrorAction SilentlyContinue
uv run pyinstaller apollo.spec --distpath launch
```

That produces `launch/Apollo.exe` (~138 MB, single file, no console window). Double-click it to launch. You can move or copy it anywhere — it is self-contained.

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
2. **Songs tab** — Click "Import song…" to load a WAV, MP3, or MP4 file. Select it in the list and click "Prep selected" to separate the stems and build the chart. Prep takes a few minutes; see [While prep runs](#while-prep-runs) below.
3. **Chart tab** — Once prep finishes, click "Open in Chart tab" on the Songs tab. Click "Play backing" to start the backing track and watch the play line move through the chart.

### Demo song

Our demo song is **"Blackbird" by The Beatles**. Use your own copy of the recording. Audio files are never committed, and the `songs/` folder is gitignored. Import it on the Songs tab and prep it like any other song.

### While prep runs

A progress bar appears at the top of the Songs tab with one block per step:

| Step | What it does | How long |
| --- | --- | --- |
| Split instruments | Separates the guitar from the rest of the band | The longest step, usually a few minutes |
| Find notes | Lists every note in the guitar track | Much quicker than splitting |
| Build chart | Cleans up the notes and picks a string and fret for each | A few seconds |

- The step that's running is blue, with a light stripe sliding across it so you can see the app is still working.
- Finished steps turn green with a ✓. A failed step turns red with a ✗.
- The line under the bar says which step is running (for example "Step 1 of 3") and how long prep has been going.
- When prep ends, it shows the total time or which step failed.

The bar shows which step is running, not a percentage. The prep steps don't report how far along they are, so the bar doesn't guess. You can keep using the Tuner tab while prep runs.


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

The progress bar on the Songs tab turns the failed step red, and the list's stage columns show it too. For details, open `prep.log` inside that song's folder in the app's store directory — it records each step and any error. The most common causes:

- **Separation fails** — `torch` or `demucs` not installed, or the separation model was never downloaded (see [Download the separation model](#download-the-separation-model-once-while-online)).
- **Crashes with "OpenBLAS error: Memory allocation" or "access violation"** — the computer ran out of memory. Close other apps, especially browsers, and try again.
- **Very short file** — files under about 10 seconds may not have enough audio for the model to work with.
- **Corrupted file** — try a different copy of the song.

### Audio device errors in the Tuner tab

- **Windows** — make sure your microphone is not disabled in Settings → System → Sound → Input.
- **macOS** — Terminal (or your IDE) needs microphone permission: System Settings → Privacy & Security → Microphone.

### The chart has a stray very high note (fret 12 and up)

Basic Pitch sometimes hears the ring of an open string two or three octaves up and reports it as a separate note. The chart step now removes these. A song prepped before that fix still has its old chart, so select it and click "Prep selected" again to rebuild it.

### The chart uses a different string than the real song

The chart picks the lowest fret that fits near your hand, so a note may land on a different string than the original recording uses. For example, in "Blackbird" some melody notes show on the high e string, while the real song plays them higher up the B string. The notes are the same pitch and still score correctly; only the fingering differs.

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
