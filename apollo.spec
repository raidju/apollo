# -*- mode: python ; coding: utf-8 -*-
# Build: uv run pyinstaller apollo.spec
# Output: dist/Apollo.exe  (single file, no console window)

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# imageio-ffmpeg bundles its own ffmpeg binary — it must travel with the exe.
datas = collect_data_files("imageio_ffmpeg")

# librosa ships a small set of audio example files; include them so it
# initialises cleanly even though the app does not use them directly.
datas += collect_data_files("librosa")

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=collect_dynamic_libs("soundfile") + collect_dynamic_libs("sounddevice"),
    datas=datas,
    hiddenimports=[
        "sounddevice",
        "soundfile",
        "scipy.signal",
        "scipy.fft",
        "numpy",
        "librosa",
        "librosa.util.decorators",
        "librosa.filters",
        "resampy",
        "audioread",
        "pooch",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # ML extras — not bundled; the app still runs without them,
        # Prep just fails until the user installs --extra ml separately.
        "torch",
        "torchaudio",
        "demucs",
        "basic_pitch",
        "onnxruntime",
        "tensorflow",
        "tensorflow_macos",
        "coremltools",
        # Test and dev tools
        "pytest",
        "ruff",
        "pyinstaller",
        # Heavy unused stdlib
        "tkinter.test",
        "unittest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Apollo",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,   # no black terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=None,       # replace with "assets/apollo.ico" if you add an icon
    target_arch=None,
)
