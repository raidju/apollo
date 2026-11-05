# Temporary preview GUI — to be replaced by the ui module once the team picks a framework.
from __future__ import annotations

import json
import pathlib
import sys
import threading
import time
import tkinter as tk
from collections import deque
from tkinter import filedialog, ttk

import numpy as np

from apollo import jobs
from apollo.ingest import ingest
from apollo.pitch import detect
from apollo.store import SongStore
from apollo.tuner import Tuner, TunerDisplay

# ---------------------------------------------------------------------------
# Constants — change colours here and nowhere else
# ---------------------------------------------------------------------------

COLORS: dict[str, str] = {
    "bg": "#1e1e1e",
    "fg": "#e0e0e0",
    "fg_dim": "#888888",
    "surface": "#2d2d2d",
    "surface2": "#3c3c3c",
    "accent": "#0078d4",
    "green": "#4caf50",
    "orange": "#ff9800",
    "red": "#f44336",
    "blue": "#2196f3",
    "stage_pending": "#888888",
    "stage_running": "#2196f3",
    "stage_done": "#4caf50",
    "stage_failed": "#f44336",
}

FONT_FAMILY = "Segoe UI"
PIXELS_PER_SECOND = 120  # chart x-axis scale
LEFT_MARGIN = 60         # chart: pixels for string labels on left
STRING_SPACING = 30      # chart: vertical pixels between strings
CHART_TOP_MARGIN = 50    # chart: y coordinate of the topmost string line
NOTE_BAR_HEIGHT = 5      # chart: half-height of note rectangles

MIN_CONFIDENCE = 0.8  # tuner: readings below this are skipped — tuned by testing

SAMPLE_RATE = 44100
FRAME_SIZE = 4096    # samples fed to pitch.detect() each poll
BLOCK_SIZE = 2048    # sounddevice callback blocksize
POLL_MS = 50         # tuner timer interval ms
PREP_POLL_MS = 500   # songs-tab prep polling interval ms
PLAY_POLL_MS = 30    # chart playback timer interval ms

STRING_NAMES = ["low E", "A", "D", "G", "B", "high e"]

STRING_COLORS = [
    "#ef5350",  # 0 low E — red
    "#ffa726",  # 1 A     — orange
    "#ffee58",  # 2 D     — yellow
    "#66bb6a",  # 3 G     — green
    "#42a5f5",  # 4 B     — blue
    "#ab47bc",  # 5 high e — purple
]

STRING_COLORS_BRIGHT = [
    "#ff8a80",
    "#ffd180",
    "#ffff8d",
    "#b9f6ca",
    "#82b1ff",
    "#ea80fc",
]

_STAGE_SYMBOLS = {
    "done": "✓",
    "running": "…",
    "failed": "✗",
    "pending": "·",
}

_TAB_DESCRIPTIONS = {
    0: "Listen to a string and see which note it is",
    1: "Import songs and prepare them for practice",
    2: "View a guitar tab and play the backing track",
}

# ---------------------------------------------------------------------------
# Pure helpers — no Tk inside any of these
# ---------------------------------------------------------------------------


def string_name(string_index: int) -> str:
    return STRING_NAMES[string_index]


def cents_to_needle_x(cents: float, bar_width: int) -> int:
    """Map cents to a pixel offset. -50 → 0, 0 → center, +50 → bar_width."""
    clamped = max(-50.0, min(50.0, cents))
    return round((clamped + 50.0) / 100.0 * bar_width)


def time_to_x(seconds: float) -> int:
    return LEFT_MARGIN + round(seconds * PIXELS_PER_SECOND)


def string_to_y(string_index: int) -> int:
    """Return canvas y. String 5 (high e) is at the top (smallest y)."""
    return CHART_TOP_MARGIN + (5 - string_index) * STRING_SPACING


def play_line_seconds(elapsed_s: float, duration_s: float) -> float | None:
    """Return position for the play line, or None once playback has ended."""
    if elapsed_s >= duration_s:
        return None
    return elapsed_s


def active_note_ids(chart: dict, t: float) -> set[int]:
    """Return ids of notes whose interval contains time t."""
    return {
        note["id"]
        for note in chart["notes"]
        if note["start_s"] <= t < note["end_s"]
    }


def list_songs(store: SongStore) -> list[dict]:
    """Return one dict per valid song.json found under store.root."""
    songs: list[dict] = []
    if not store.root.exists():
        return songs
    for folder in store.root.iterdir():
        if not folder.is_dir():
            continue
        try:
            songs.append(store.read_song(folder.name))
        except Exception:  # noqa: BLE001, S110
            pass
    return songs


def stage_row(song: dict, target: str) -> tuple[str, ...]:
    """Return the display values for one Treeview row."""
    def sym(val: str) -> str:
        return _STAGE_SYMBOLS.get(val, "·")

    s = song.get("stages", {})
    return (
        song.get("title", ""),
        song.get("song_id", ""),
        sym(s.get("ingest", "pending")),
        sym(s.get("separate", "pending")),
        sym(s.get("transcribe", {}).get(target, "pending")),
        sym(s.get("chart", {}).get(target, "pending")),
    )


# ---------------------------------------------------------------------------
# Tab 1: Tuner
# ---------------------------------------------------------------------------


class TunerTab:
    def __init__(
        self,
        parent: ttk.Frame,
        root: tk.Tk,
        set_status: object,
    ) -> None:
        self._root = root
        self._set_status = set_status
        self._stream: object = None
        self._running = False
        self._buf: deque[float] = deque(maxlen=FRAME_SIZE)
        self._lock = threading.Lock()
        self._tuner = Tuner()
        self._needle_width = 400
        self._setup_widgets(parent)

    def _setup_widgets(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)

        self._btn = ttk.Button(parent, text="Start", command=self._toggle)
        self._btn.grid(row=0, column=0, pady=(24, 8))

        self._err_label = tk.Label(
            parent, text="",
            font=(FONT_FAMILY, 10),
            bg=COLORS["bg"], fg=COLORS["red"],
            wraplength=500,
        )
        self._err_label.grid(row=1, column=0, padx=20)

        self._note_label = tk.Label(
            parent, text="—",
            font=(FONT_FAMILY, 72, "bold"),
            bg=COLORS["bg"], fg=COLORS["fg"],
        )
        self._note_label.grid(row=2, column=0, pady=(10, 0))

        self._cents_label = tk.Label(
            parent, text="",
            font=(FONT_FAMILY, 18),
            bg=COLORS["bg"], fg=COLORS["fg_dim"],
        )
        self._cents_label.grid(row=3, column=0)

        self._string_label = tk.Label(
            parent, text="",
            font=(FONT_FAMILY, 14),
            bg=COLORS["bg"], fg=COLORS["fg_dim"],
        )
        self._string_label.grid(row=4, column=0, pady=(0, 12))

        self._needle_canvas = tk.Canvas(
            parent,
            width=self._needle_width,
            height=44,
            bg=COLORS["surface"],
            highlightthickness=0,
        )
        self._needle_canvas.grid(row=5, column=0, pady=10)
        self._draw_needle(None)

        chip_frame = tk.Frame(parent, bg=COLORS["bg"])
        chip_frame.grid(row=6, column=0, pady=12)
        self._chips: list[tk.Label] = []
        for i, label in enumerate(["E", "A", "D", "G", "B", "e"]):
            chip = tk.Label(
                chip_frame, text=label, width=4,
                font=(FONT_FAMILY, 11, "bold"),
                bg=COLORS["surface"], fg=COLORS["fg_dim"],
                padx=6, pady=4,
            )
            chip.grid(row=0, column=i, padx=3)
            self._chips.append(chip)

    def _toggle(self) -> None:
        if self._running:
            self._stop()
        else:
            self._start()

    def _start(self) -> None:
        try:
            import sounddevice as sd  # lazy: machines without PortAudio can still import this module
        except Exception as exc:  # noqa: BLE001
            self._err_label.config(text=f"Could not load audio library: {exc}")
            return
        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                blocksize=BLOCK_SIZE,
                dtype="float32",
                callback=self._audio_callback,
            )
            self._stream.start()
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if sys.platform == "darwin":
                msg += (
                    " — on macOS, Terminal may need microphone permission"
                    " in System Settings → Privacy & Security → Microphone"
                )
            self._err_label.config(text=msg)
            return
        self._running = True
        self._btn.config(text="Stop")
        self._err_label.config(text="")
        self._set_status("Tuner listening…")  # type: ignore[operator]
        self._root.after(POLL_MS, self._poll_pitch)

    def _stop(self) -> None:
        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop()  # type: ignore[union-attr]
                self._stream.close()  # type: ignore[union-attr]
            except Exception:  # noqa: BLE001, S110
                pass
            self._stream = None
        self._tuner.reset()
        self._btn.config(text="Start")
        self._update_display(None)
        self._set_status("Tuner stopped.")  # type: ignore[operator]

    def _audio_callback(
        self, indata: np.ndarray, frames: int, time_info: object, status: object
    ) -> None:
        # Runs on sounddevice's thread — no Tk calls here.
        with self._lock:
            self._buf.extend(indata[:, 0])

    def _poll_pitch(self) -> None:
        if not self._running:
            return
        with self._lock:
            buf_copy = list(self._buf)
        if len(buf_copy) >= FRAME_SIZE:
            frame = np.array(buf_copy[-FRAME_SIZE:], dtype=np.float32)
            reading = detect(frame)
            if reading.confidence >= MIN_CONFIDENCE:
                display = self._tuner.update(reading)
            else:
                display = None
            self._update_display(display)
        self._root.after(POLL_MS, self._poll_pitch)

    def _update_display(self, display: TunerDisplay | None) -> None:
        if display is None:
            self._note_label.config(text="—")
            self._cents_label.config(text="")
            self._string_label.config(text="")
            self._draw_needle(None)
            for chip in self._chips:
                chip.config(bg=COLORS["surface"], fg=COLORS["fg_dim"])
            return

        self._note_label.config(text=display.note_name)
        sign = "+" if display.cents >= 0 else ""
        needle_color = COLORS["green"] if display.in_tune else COLORS["orange"]
        self._cents_label.config(
            text=f"{sign}{display.cents:.1f} ¢",
            fg=needle_color,
        )
        self._string_label.config(text=string_name(display.likely_string))
        self._draw_needle(display.cents, needle_color)

        for i, chip in enumerate(self._chips):
            if i == display.likely_string:
                chip.config(
                    bg=COLORS["green"] if display.in_tune else COLORS["accent"],
                    fg="#000000" if display.in_tune else COLORS["fg"],
                )
            else:
                chip.config(bg=COLORS["surface"], fg=COLORS["fg_dim"])

    def _draw_needle(self, cents: float | None, color: str = "#888888") -> None:
        c = self._needle_canvas
        c.delete("all")
        w = self._needle_width
        h = 44
        pad = 12
        track_w = w - 2 * pad
        mid_y = h // 2

        # Track bar
        c.create_rectangle(
            pad, mid_y - 2, w - pad, mid_y + 2,
            fill=COLORS["surface2"], outline="",
        )

        # Tick marks at -50, -25, 0, +25, +50
        for mark in (-50, -25, 0, 25, 50):
            mx = pad + cents_to_needle_x(float(mark), track_w)
            tick_h = 10 if mark == 0 else 5
            tick_w = 2 if mark == 0 else 1
            c.create_line(
                mx, mid_y - tick_h, mx, mid_y + tick_h,
                fill=COLORS["fg_dim"], width=tick_w,
            )

        # Needle triangle
        nx = pad + (cents_to_needle_x(cents, track_w) if cents is not None else track_w // 2)
        c.create_polygon(
            nx, pad,
            nx - 7, h - pad,
            nx + 7, h - pad,
            fill=color, outline="",
        )

    def close(self) -> None:
        if self._running:
            self._stop()


# ---------------------------------------------------------------------------
# Tab 2: Songs
# ---------------------------------------------------------------------------


class SongsTab:
    def __init__(
        self,
        parent: ttk.Frame,
        root: tk.Tk,
        store: SongStore,
        chart_tab: ChartTab,
        notebook: ttk.Notebook,
        chart_frame: ttk.Frame,
        set_status: object,
    ) -> None:
        self._root = root
        self._store = store
        self._chart_tab = chart_tab
        self._notebook = notebook
        self._chart_frame = chart_frame
        self._set_status = set_status
        self._proc: object | None = None
        self._songs: list[dict] = []
        self._setup_widgets(parent)
        self._refresh()

    def _setup_widgets(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        btn_frame = ttk.Frame(parent)
        btn_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=8)

        self._import_btn = ttk.Button(
            btn_frame, text="Import song…", command=self._import
        )
        self._import_btn.grid(row=0, column=0, padx=(0, 8))

        ttk.Label(
            btn_frame,
            text="Accepts WAV, MP3, MP4",
            foreground=COLORS["fg_dim"],
            font=(FONT_FAMILY, 10),
        ).grid(row=0, column=1, padx=4)

        self._prep_btn = ttk.Button(
            btn_frame, text="Prep selected",
            command=self._start_prep, state="disabled",
        )
        self._prep_btn.grid(row=0, column=2, padx=8)

        self._chart_btn = ttk.Button(
            btn_frame, text="Open in Chart tab",
            command=self._open_in_chart, state="disabled",
        )
        self._chart_btn.grid(row=0, column=3, padx=8)

        cols = ("title", "song_id", "ingest", "separate", "transcribe", "chart")
        self._tree = ttk.Treeview(
            parent, columns=cols, show="headings", selectmode="browse"
        )
        headings = ["Title", "Song ID", "Ingest", "Separate", "Transcribe", "Chart"]
        widths = [220, 160, 60, 70, 80, 60]
        for col, heading, width in zip(cols, headings, widths):
            self._tree.heading(col, text=heading)
            anchor = "w" if heading in ("Title", "Song ID") else "center"
            self._tree.column(col, width=width, anchor=anchor)

        self._tree.tag_configure("running", foreground=COLORS["stage_running"])
        self._tree.tag_configure("failed", foreground=COLORS["stage_failed"])
        self._tree.tag_configure("pending", foreground=COLORS["stage_pending"])

        vsb = ttk.Scrollbar(parent, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)

        self._tree.grid(row=1, column=0, sticky="nsew", padx=(10, 0), pady=4)
        vsb.grid(row=1, column=1, sticky="ns", pady=4)

        self._tree.bind("<<TreeviewSelect>>", self._on_select)

    def _row_tag(self, song: dict) -> str:
        s = song.get("stages", {})
        vals = [
            s.get("ingest", "pending"),
            s.get("separate", "pending"),
            s.get("transcribe", {}).get("guitar", "pending"),
            s.get("chart", {}).get("guitar", "pending"),
        ]
        if "failed" in vals:
            return "failed"
        if "running" in vals:
            return "running"
        if all(v == "done" for v in vals):
            return "done"
        return "pending"

    def _refresh(self) -> None:
        self._songs = list_songs(self._store)
        sel = self._tree.selection()
        self._tree.delete(*self._tree.get_children())
        for song in self._songs:
            row = stage_row(song, "guitar")
            self._tree.insert(
                "", "end",
                iid=song["song_id"],
                values=row,
                tags=(self._row_tag(song),),
            )
        if sel and self._tree.exists(sel[0]):
            self._tree.selection_set(sel[0])

    def _on_select(self, _event: object) -> None:
        sel = self._tree.selection()
        if not sel:
            self._prep_btn.config(state="disabled")
            self._chart_btn.config(state="disabled")
            return
        song_id = sel[0]
        song = self._find_song(song_id)
        if song is None:
            return
        prep_ok = self._proc is None or getattr(self._proc, "exitcode", None) is not None
        self._prep_btn.config(state="normal" if prep_ok else "disabled")
        chart_done = (
            song.get("stages", {}).get("chart", {}).get("guitar") == "done"
        )
        self._chart_btn.config(state="normal" if chart_done else "disabled")

    def _find_song(self, song_id: str) -> dict | None:
        return next((s for s in self._songs if s["song_id"] == song_id), None)

    def _import(self) -> None:
        path = filedialog.askopenfilename(
            title="Import song",
            filetypes=[
                ("Audio files", "*.wav *.mp3 *.mp4 *.m4a"),
                ("WAV", "*.wav"),
                ("MP3", "*.mp3"),
                ("MP4 / M4A", "*.mp4 *.m4a"),
            ],
        )
        if not path:
            return
        try:
            song_id = ingest(pathlib.Path(path), self._store)
            self._refresh()
            self._tree.selection_set(song_id)
            self._tree.see(song_id)
            self._set_status(f"Imported: {pathlib.Path(path).name}")  # type: ignore[operator]
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"Import failed: {exc}")  # type: ignore[operator]

    def _start_prep(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        song_id = sel[0]
        self._proc = jobs.start_prep(song_id, "guitar", self._store.root)
        self._prep_btn.config(state="disabled")
        self._chart_btn.config(state="disabled")
        self._set_status("Prep started…")  # type: ignore[operator]
        self._root.after(PREP_POLL_MS, lambda: self._poll_prep(song_id))

    def _poll_prep(self, song_id: str) -> None:
        if self._proc is None:
            return
        try:
            song = self._store.read_song(song_id)
            row = stage_row(song, "guitar")
            self._tree.item(song_id, values=row, tags=(self._row_tag(song),))
            for i, s in enumerate(self._songs):
                if s["song_id"] == song_id:
                    self._songs[i] = song
                    break
            stages = song.get("stages", {})
            running_stage = next(
                (
                    k for k in ("separate", "transcribe", "chart")
                    if stages.get(k) == "running"
                    or (
                        isinstance(stages.get(k), dict)
                        and "running" in stages.get(k, {}).values()
                    )
                ),
                None,
            )
            if running_stage:
                self._set_status(f"Prep running: {running_stage}")  # type: ignore[operator]
        except Exception:  # noqa: BLE001, S110
            pass

        exitcode = getattr(self._proc, "exitcode", None)
        if exitcode is None:
            self._root.after(PREP_POLL_MS, lambda: self._poll_prep(song_id))
            return

        if exitcode != 0:
            self._set_status(  # type: ignore[operator]
                "Prep failed — check the terminal for the error."
                " ML steps need: uv sync --extra ml"
            )
        else:
            self._set_status("Prep complete.")  # type: ignore[operator]
            self._refresh()

        self._proc = None
        if self._tree.selection():
            self._prep_btn.config(state="normal")
        self._on_select(None)

    def _open_in_chart(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        song_id = sel[0]
        song = self._find_song(song_id)
        if song is None:
            return
        try:
            chart = self._store.read_chart(song_id, "guitar")
            self._chart_tab.load_chart(
                chart,
                song.get("title", song_id),
                song_id,
                self._store,
            )
            self._notebook.select(self._chart_frame)
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"Could not open chart: {exc}")  # type: ignore[operator]


# ---------------------------------------------------------------------------
# Tab 3: Chart
# ---------------------------------------------------------------------------


class ChartTab:
    def __init__(
        self,
        parent: ttk.Frame,
        root: tk.Tk,
        set_status: object,
    ) -> None:
        self._root = root
        self._set_status = set_status
        self._chart: dict | None = None
        self._song_id: str | None = None
        self._store: SongStore | None = None
        self._play_start: float | None = None
        self._play_duration = 0.0
        self._play_line_id: int | None = None
        self._active_ids: set[int] = set()
        self._canvas_w = 0
        self._setup_widgets(parent)

    def _setup_widgets(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        self._info_label = tk.Label(
            parent, text="No chart loaded.",
            font=(FONT_FAMILY, 11),
            bg=COLORS["bg"], fg=COLORS["fg_dim"],
            anchor="w",
        )
        self._info_label.grid(row=0, column=0, columnspan=2, sticky="ew",
                               padx=10, pady=(8, 2))

        canvas_h = CHART_TOP_MARGIN + 5 * STRING_SPACING + 40
        self._canvas = tk.Canvas(
            parent,
            height=canvas_h,
            bg=COLORS["surface"],
            highlightthickness=0,
        )
        self._canvas.grid(row=1, column=0, sticky="nsew", padx=(10, 0), pady=4)

        hscroll = ttk.Scrollbar(
            parent, orient="horizontal", command=self._canvas.xview
        )
        hscroll.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10)
        self._canvas.configure(xscrollcommand=hscroll.set)

        btn_frame = ttk.Frame(parent)
        btn_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=8)

        ttk.Button(
            btn_frame, text="Load sample chart", command=self._load_sample
        ).grid(row=0, column=0, padx=(0, 8))

        self._play_btn = ttk.Button(
            btn_frame, text="Play backing",
            command=self._toggle_play, state="disabled",
        )
        self._play_btn.grid(row=0, column=1, padx=8)

        ttk.Button(
            btn_frame,
            text="Score my playing (coming next)",
            state="disabled",
        ).grid(row=0, column=2, padx=8)

        self._short_label = tk.Label(
            parent, text="",
            font=(FONT_FAMILY, 10),
            bg=COLORS["bg"], fg=COLORS["fg_dim"],
        )
        self._short_label.grid(row=4, column=0, columnspan=2, sticky="w", padx=10)

    def load_chart(
        self,
        chart: dict,
        title: str,
        song_id: str | None,
        store: SongStore | None = None,
    ) -> None:
        self._chart = chart
        self._song_id = song_id
        self._store = store
        self._stop_play_silent()
        self._draw_chart(title)

        notes = chart.get("notes", [])
        max_end = max((n["end_s"] for n in notes), default=0.0)
        self._info_label.config(
            text=f"{title}  ·  {len(notes)} notes  ·  {max_end:.1f} s",
            fg=COLORS["fg"],
        )

        self._short_label.config(text="")
        self._play_btn.config(state="disabled")

        if store is None or song_id is None:
            return

        backing_path = store.backing_path(song_id, "guitar")
        if not backing_path.exists():
            return

        self._play_btn.config(state="normal")

        try:
            import soundfile as sf  # lazy: check length for short-chart warning
            info = sf.info(str(backing_path))
            if max_end > 0 and max_end < info.duration * 0.3:
                self._short_label.config(
                    text=(
                        "Chart is much shorter than the backing track."
                        " The song may have been prepped with stub data."
                    )
                )
        except Exception:  # noqa: BLE001, S110
            pass

    def _draw_chart(self, title: str = "") -> None:
        c = self._canvas
        c.delete("all")
        if self._chart is None:
            return

        notes = self._chart.get("notes", [])
        max_end = max((n["end_s"] for n in notes), default=10.0)
        self._canvas_w = time_to_x(max_end) + 80
        canvas_h = CHART_TOP_MARGIN + 5 * STRING_SPACING + 40
        c.configure(scrollregion=(0, 0, self._canvas_w, canvas_h))

        # String lines and labels
        for i in range(6):
            y = string_to_y(i)
            c.create_line(
                LEFT_MARGIN - 5, y, self._canvas_w, y,
                fill=COLORS["fg_dim"], width=1,
            )
            c.create_text(
                LEFT_MARGIN - 8, y,
                text=string_name(i), anchor="e",
                fill=STRING_COLORS[i], font=(FONT_FAMILY, 9),
            )

        # Time marks every second
        max_s = int(max_end) + 2
        for s in range(max_s + 1):
            x = time_to_x(float(s))
            top_y = CHART_TOP_MARGIN - 15
            c.create_line(
                x, top_y, x, CHART_TOP_MARGIN + 5 * STRING_SPACING + 10,
                fill=COLORS["surface2"], width=1, dash=(2, 4),
            )
            c.create_text(
                x, top_y - 2, text=str(s), anchor="s",
                fill=COLORS["fg_dim"], font=(FONT_FAMILY, 8),
            )

        # Notes
        for note in notes:
            x1 = time_to_x(note["start_s"])
            x2 = max(time_to_x(note["end_s"]), x1 + 10)
            y = string_to_y(note["string"])
            color = STRING_COLORS[note["string"]]
            tag = f"note_{note['id']}"
            c.create_rectangle(
                x1, y - NOTE_BAR_HEIGHT,
                x2, y + NOTE_BAR_HEIGHT,
                fill=color, outline="", tags=(tag,),
            )
            c.create_text(
                x1 + 3, y,
                text=str(note["fret"]), anchor="w",
                fill=COLORS["bg"], font=(FONT_FAMILY, 8, "bold"),
                tags=(f"{tag}_txt",),
            )

    def _load_sample(self) -> None:
        fixture = (
            pathlib.Path(__file__).resolve().parent.parent.parent
            / "tests" / "fixtures" / "chart" / "guitar.json"
        )
        if not fixture.exists():
            self._set_status(f"Sample chart not found: {fixture}")  # type: ignore[operator]
            return
        with open(fixture, encoding="utf-8") as f:
            chart = json.load(f)
        self.load_chart(chart, "Sample Chart", None, None)
        self._set_status("Sample chart loaded.")  # type: ignore[operator]

    def _toggle_play(self) -> None:
        if self._play_start is not None:
            self._stop_play()
        else:
            self._play()

    def _play(self) -> None:
        if self._store is None or self._song_id is None:
            return
        backing_path = self._store.backing_path(self._song_id, "guitar")
        if not backing_path.exists():
            return
        try:
            import sounddevice as sd  # lazy: machines without PortAudio still import this module
            import soundfile as sf
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"Audio library error: {exc}")  # type: ignore[operator]
            return
        try:
            info = sf.info(str(backing_path))
            self._play_duration = info.duration
            data, samplerate = sf.read(str(backing_path))
            sd.play(data, samplerate)
            self._play_start = time.monotonic()
            self._play_btn.config(text="Stop")
            self._set_status("Playing backing track…")  # type: ignore[operator]
            self._root.after(PLAY_POLL_MS, self._poll_play)
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"Playback failed: {exc}")  # type: ignore[operator]

    def _stop_play(self) -> None:
        try:
            import sounddevice as sd  # lazy
            sd.stop()
        except Exception:  # noqa: BLE001, S110
            pass
        self._stop_play_silent()
        self._set_status("Playback stopped.")  # type: ignore[operator]

    def _stop_play_silent(self) -> None:
        self._play_start = None
        if self._play_line_id is not None:
            self._canvas.delete(self._play_line_id)
            self._play_line_id = None
        self._play_btn.config(text="Play backing")
        self._active_ids = set()
        self._reset_note_colors()

    def _reset_note_colors(self) -> None:
        if self._chart is None:
            return
        for note in self._chart.get("notes", []):
            self._canvas.itemconfig(
                f"note_{note['id']}", fill=STRING_COLORS[note["string"]]
            )

    def _poll_play(self) -> None:
        if self._play_start is None:
            return
        elapsed = time.monotonic() - self._play_start
        pos = play_line_seconds(elapsed, self._play_duration)
        if pos is None:
            self._stop_play_silent()
            return

        x = time_to_x(pos)
        canvas_h = CHART_TOP_MARGIN + 5 * STRING_SPACING + 40

        if self._play_line_id is not None:
            self._canvas.coords(self._play_line_id, x, 0, x, canvas_h)
        else:
            self._play_line_id = self._canvas.create_line(
                x, 0, x, canvas_h,
                fill=COLORS["red"], width=2, tags=("play_line",),
            )
        self._canvas.tag_raise("play_line")

        # Highlight notes the play line is crossing
        new_active = active_note_ids(self._chart, pos) if self._chart else set()
        for note in (self._chart.get("notes", []) if self._chart else []):
            nid = note["id"]
            tag = f"note_{nid}"
            if nid in new_active and nid not in self._active_ids:
                self._canvas.itemconfig(
                    tag, fill=STRING_COLORS_BRIGHT[note["string"]]
                )
            elif nid not in new_active and nid in self._active_ids:
                self._canvas.itemconfig(tag, fill=STRING_COLORS[note["string"]])
        self._active_ids = new_active

        self._auto_scroll_to(x)
        self._root.after(PLAY_POLL_MS, self._poll_play)

    def _auto_scroll_to(self, x: int) -> None:
        if self._canvas_w <= 0:
            return
        visible_w = self._canvas.winfo_width()
        if visible_w <= 1:
            return
        view = self._canvas.xview()
        left_px = view[0] * self._canvas_w
        right_px = view[1] * self._canvas_w
        if x > right_px - 20 or x < left_px + 20:
            new_left = max(0.0, x - visible_w * 0.3)
            self._canvas.xview_moveto(new_left / self._canvas_w)


# ---------------------------------------------------------------------------
# App — assembles the window
# ---------------------------------------------------------------------------


class App:
    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        root.title("Apollo (preview)")
        root.configure(bg=COLORS["bg"])
        root.geometry("960x640")
        self._apply_style(root)
        self._build_layout(root)

    def _apply_style(self, root: tk.Tk) -> None:
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(
            ".",
            background=COLORS["bg"],
            foreground=COLORS["fg"],
            font=(FONT_FAMILY, 11),
            fieldbackground=COLORS["surface"],
            troughcolor=COLORS["surface"],
            borderwidth=0,
        )
        style.configure("TFrame", background=COLORS["bg"])
        style.configure(
            "TButton",
            background=COLORS["surface2"],
            foreground=COLORS["fg"],
            padding=[8, 4],
            relief="flat",
        )
        style.map(
            "TButton",
            background=[
                ("disabled", COLORS["surface"]),
                ("active", COLORS["accent"]),
            ],
            foreground=[("disabled", COLORS["fg_dim"])],
        )
        style.configure(
            "TLabel",
            background=COLORS["bg"],
            foreground=COLORS["fg"],
        )
        style.configure("TNotebook", background=COLORS["bg"], borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=COLORS["surface"],
            foreground=COLORS["fg_dim"],
            padding=[14, 6],
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", COLORS["surface2"])],
            foreground=[("selected", COLORS["fg"])],
        )
        style.configure(
            "Treeview",
            background=COLORS["surface"],
            foreground=COLORS["fg"],
            fieldbackground=COLORS["surface"],
            rowheight=28,
        )
        style.configure(
            "Treeview.Heading",
            background=COLORS["surface2"],
            foreground=COLORS["fg_dim"],
            relief="flat",
        )
        style.map(
            "Treeview",
            background=[("selected", COLORS["accent"])],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            "TScrollbar",
            background=COLORS["surface2"],
            troughcolor=COLORS["surface"],
        )

    def _build_layout(self, root: tk.Tk) -> None:
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        # Header strip
        header = tk.Frame(root, bg=COLORS["accent"])
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        tk.Label(
            header, text="Apollo (preview)",
            font=(FONT_FAMILY, 13, "bold"),
            bg=COLORS["accent"], fg="#ffffff",
            padx=14, pady=10,
        ).grid(row=0, column=0, sticky="w")

        self._header_desc = tk.Label(
            header, text="",
            font=(FONT_FAMILY, 10),
            bg=COLORS["accent"], fg="#cce4ff",
            padx=14, pady=10,
        )
        self._header_desc.grid(row=0, column=1, sticky="e")

        # Notebook
        self._notebook = ttk.Notebook(root)
        self._notebook.grid(row=1, column=0, sticky="nsew")

        tuner_frame = ttk.Frame(self._notebook)
        songs_frame = ttk.Frame(self._notebook)
        chart_frame = ttk.Frame(self._notebook)

        self._notebook.add(tuner_frame, text="Tuner")
        self._notebook.add(songs_frame, text="Songs")
        self._notebook.add(chart_frame, text="Chart")

        # Status bar
        self._status_var = tk.StringVar(value="Ready.")
        tk.Label(
            root,
            textvariable=self._status_var,
            bg=COLORS["surface"],
            fg=COLORS["fg_dim"],
            font=(FONT_FAMILY, 9),
            anchor="w",
            padx=10,
            pady=4,
        ).grid(row=2, column=0, sticky="ew")

        def set_status(msg: str) -> None:
            self._status_var.set(msg)

        store = SongStore(pathlib.Path("songs"))

        self._chart_tab = ChartTab(chart_frame, root, set_status)
        self._tuner_tab = TunerTab(tuner_frame, root, set_status)
        self._songs_tab = SongsTab(
            songs_frame, root, store,
            self._chart_tab, self._notebook, chart_frame,
            set_status,
        )

        self._notebook.bind("<<NotebookTabChanged>>", self._on_tab_change)
        self._update_header()

        root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_tab_change(self, _event: object) -> None:
        self._update_header()

    def _update_header(self) -> None:
        idx = self._notebook.index("current")
        self._header_desc.config(text=_TAB_DESCRIPTIONS.get(idx, ""))

    def _on_close(self) -> None:
        self._tuner_tab.close()
        self._root.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
