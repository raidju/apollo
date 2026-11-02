from lodestone.store import SongStore


def transcribe(song_id: str, target: str, store: SongStore) -> None:
    """Run Basic Pitch on stems/<target>.wav and write notes/<target>.json.

    Basic Pitch returns numpy types; every value is explicitly cast to a
    plain Python type before writing so the JSON serialiser doesn't fail.
    """
    from basic_pitch.inference import predict
    from basic_pitch import ICASSP_2022_MODEL_PATH

    stem = store.stem_path(song_id, target)
    _model_output, _midi_data, note_events = predict(str(stem), ICASSP_2022_MODEL_PATH)

    events = []
    for start_s, end_s, pitch_midi, amplitude, _bends in note_events:
        events.append({
            "start_s": float(start_s),
            "end_s": float(end_s),
            "midi": int(pitch_midi),
            "amplitude": float(amplitude),
        })

    events.sort(key=lambda e: e["start_s"])

    store.write_notes(song_id, target, {
        "schema_version": 1,
        "target": target,
        "events": events,
    })
