from __future__ import annotations

import torch
import soundfile as sf

from lodestone.store import SongStore


def separate(song_id: str, target: str, store: SongStore) -> None:
    """Split mix.wav into per-stem WAVs and write a backing track.

    Uses htdemucs_6s (the only Demucs model with a guitar stem) on CPU.
    All six stems (vocals, drums, bass, other, guitar, piano) are written
    to stems/. The backing track is every stem except <target> summed and
    clamped, written to backing/<target>.wav.
    """
    from demucs.api import Separator

    sep = Separator("htdemucs_6s", device="cpu")
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
