from __future__ import annotations

import argparse
import os

import soundfile as sf

from apollo.store import SongStore

MODEL_NAME = "htdemucs_6s"  # the only Demucs model with a guitar stem
DOWNLOAD_COMMAND = "uv run python -m apollo.separate --download"


class ModelNotDownloadedError(RuntimeError):
    """The separation model has not been saved to this machine yet."""


def separate(song_id: str, target: str, store: SongStore) -> None:
    """Split mix.wav into per-stem WAVs and write a backing track.

    Uses htdemucs_6s on CPU, loaded only from the copy saved on this machine;
    prep never goes online. All six stems (vocals, drums, bass, other,
    guitar, piano) are written to stems/. The backing track is every stem
    except <target> summed and clamped, written to backing/<target>.wav.
    """
    use_offline_mode()
    check_model_downloaded()

    import torch
    from demucs.api import Separator

    sep = Separator(MODEL_NAME, device="cpu")
    _origin, separated = sep.separate_audio_file(store.mix_path(song_id))
    sample_rate = sep.samplerate

    for stem_name, tensor in separated.items():
        out = store.stem_path(song_id, stem_name)
        out.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(out), tensor.numpy().T, samplerate=sample_rate, subtype="PCM_16")

    other = [t for name, t in separated.items() if name != target]
    backing = torch.stack(other).sum(dim=0).clamp(-1.0, 1.0)
    out = store.backing_path(song_id, target)
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), backing.numpy().T, samplerate=sample_rate, subtype="PCM_16")


def use_offline_mode() -> None:
    """Tell the Hugging Face library never to go online in this process.

    Demucs fetches its model through that library. The setting is read when
    the library is first imported, so this must run before Demucs is imported.
    """
    os.environ["HF_HUB_OFFLINE"] = "1"


def check_model_downloaded() -> None:
    """Raise ModelNotDownloadedError if any model file is missing from this machine."""
    for filename in _model_filenames():
        if _cached_model_file(filename) is None:
            raise ModelNotDownloadedError(
                f"Separation model not downloaded. While online, run once: {DOWNLOAD_COMMAND}"
            )


def _model_filenames() -> list[str]:
    """Return the model's description file plus every weights file it lists."""
    import yaml

    description_file = f"{MODEL_NAME}.yaml"
    description_path = _cached_model_file(description_file)
    if description_path is None:
        return [description_file]
    with open(description_path, encoding="utf-8") as f:
        description = yaml.safe_load(f)
    weight_files = [f"{signature}.safetensors" for signature in description["models"]]
    return [description_file, *weight_files]


def _cached_model_file(filename: str) -> str | None:
    """Return the saved path of one model file, or None if it isn't on this machine."""
    from demucs.hf import DEFAULT_NAMESPACE, hf_repo_name
    from huggingface_hub import try_to_load_from_cache

    repo_id = f"{DEFAULT_NAMESPACE}/{hf_repo_name(MODEL_NAME)}"
    path = try_to_load_from_cache(repo_id, filename)
    if isinstance(path, str):
        return path
    return None


def download_model() -> None:
    """Download the separation model once, while online, so prep can run offline."""
    from demucs.pretrained import get_model

    print(f"Downloading separation model {MODEL_NAME} (about 55 MB)...")
    get_model(MODEL_NAME)
    check_model_downloaded()
    print("Model saved. Song prep now works offline.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Separation model tools.")
    parser.add_argument(
        "--download", action="store_true",
        help="download the separation model so prep can run offline",
    )
    args = parser.parse_args()
    if args.download:
        download_model()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
