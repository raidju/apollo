"""Tests that song separation never goes online.

Each test runs in a fresh Python process, because the Hugging Face library
reads its offline setting and model folder only once, when first imported.
The model folder is pointed at an empty temp folder, so nothing is downloaded.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys


def _run_python(code: str, model_folder: pathlib.Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["HF_HUB_CACHE"] = str(model_folder)
    env.pop("HF_HUB_OFFLINE", None)
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=env,
    )


def test_offline_mode_is_on_once_demucs_loads(tmp_path: pathlib.Path) -> None:
    code = (
        "from apollo.separate import use_offline_mode; "
        "use_offline_mode(); "
        "import demucs.api; "
        "import huggingface_hub.constants as hub; "
        "assert hub.HF_HUB_OFFLINE is True, hub.HF_HUB_OFFLINE"
    )
    result = _run_python(code, tmp_path)
    assert result.returncode == 0, result.stderr


def test_missing_model_gives_plain_message(tmp_path: pathlib.Path) -> None:
    code = (
        "from apollo.separate import use_offline_mode, check_model_downloaded, "
        "ModelNotDownloadedError, DOWNLOAD_COMMAND; "
        "use_offline_mode(); "
        "\ntry:\n"
        "    check_model_downloaded()\n"
        "except ModelNotDownloadedError as error:\n"
        "    assert DOWNLOAD_COMMAND in str(error), str(error)\n"
        "    print('raised as expected')\n"
        "else:\n"
        "    raise AssertionError('no error for an empty model folder')\n"
    )
    result = _run_python(code, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "raised as expected" in result.stdout


def test_separate_stops_before_going_online_when_model_missing(tmp_path: pathlib.Path) -> None:
    # A song folder is not needed: the model check runs before any audio is read.
    code = (
        "import pathlib; "
        "from apollo.separate import separate, ModelNotDownloadedError; "
        "from apollo.store import SongStore; "
        "\ntry:\n"
        f"    separate('no_song', 'guitar', SongStore(pathlib.Path({str(tmp_path / 'songs')!r})))\n"
        "except ModelNotDownloadedError:\n"
        "    print('raised as expected')\n"
    )
    result = _run_python(code, tmp_path / "empty_model_folder")
    assert result.returncode == 0, result.stderr
    assert "raised as expected" in result.stdout
