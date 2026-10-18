"""Tests for recording and loading your own eval audio, with a fake microphone.

Run: .venv/bin/python -m pytest assistant
"""

import json
import sys

import numpy as np
import pytest
from faster_whisper import decode_audio

import record_eval
import run_eval
from stt import SAMPLE_RATE


def tone(peak: float = 0.5, seconds: float = 1.0) -> np.ndarray:
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    return (peak * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


def test_save_wav_round_trip(tmp_path):
    audio = tone()
    path = tmp_path / "take.wav"
    record_eval.save_wav(path, audio)
    back = decode_audio(str(path), sampling_rate=SAMPLE_RATE)  # how run_eval reads it
    assert len(back) == len(audio)
    assert np.abs(back - audio).max() < 1e-4  # one 16-bit step is 3e-5


def test_take_rejects_silence_and_redoes(monkeypatch):
    clips = iter([np.zeros(SAMPLE_RATE, np.float32), tone(0.3), tone(0.6)])
    # talk (silence, rejected), talk, redo, talk, keep
    keys = iter(["", "", "r", "", ""])
    monkeypatch.setattr(record_eval, "record_until_enter", lambda: next(clips))
    monkeypatch.setattr("builtins.input", lambda prompt="": next(keys))
    assert np.abs(record_eval.take()).max() == pytest.approx(0.6, abs=1e-3)


@pytest.fixture
def record(tmp_path, monkeypatch):
    """Run record_eval.py into tmp_path/test with a fake mic and scripted key presses."""
    monkeypatch.setattr(record_eval, "RECORDINGS", tmp_path)
    monkeypatch.setattr(record_eval, "record_until_enter", tone)
    monkeypatch.setattr(record_eval.sd, "query_devices", lambda kind: {"name": "Fake Mic"})

    def run(*argv: str, keys: list[str]) -> None:
        presses = iter(keys)
        monkeypatch.setattr("builtins.input", lambda prompt="": next(presses))
        monkeypatch.setattr(sys, "argv", ["record_eval.py", "test", *argv])
        record_eval.main()

    return run


def saved(folder) -> set[str]:
    return {path.stem for path in folder.glob("*.wav")}


def test_resumes_where_it_stopped(record, tmp_path):
    folder = tmp_path / "test"
    record(keys=["", "", "", "q"])  # keep play-01, quit during play-02
    assert saved(folder) == {"play-01"}
    record(keys=["", "", "", "q"])  # starts at play-02 this time
    assert saved(folder) == {"play-01", "play-02"}
    takes = json.loads((folder / "takes.json").read_text())
    assert takes["play-02"]["text"] == "play pink noise"
    assert takes["play-02"]["mic"] == "Fake Mic"


def test_redo_and_changed_phrases_are_recorded_again(record, tmp_path):
    folder = tmp_path / "test"
    record(keys=["", "", "", "", "", "q"])  # keep play-01 and play-02
    first = (folder / "play-01.wav").stat().st_mtime_ns
    # Without --redo this would keep play-03; with it, play-01 comes first.
    record("--redo", "play-01", keys=["", "", "", "q"])
    assert saved(folder) == {"play-01", "play-02"}
    assert (folder / "play-01.wav").stat().st_mtime_ns > first

    # Edit the phrase play-02 was recorded from: its take no longer matches.
    takes_file = folder / "takes.json"
    takes = json.loads(takes_file.read_text())
    takes["play-02"]["text"] = "play pink noise now"
    takes_file.write_text(json.dumps(takes))
    record(keys=["", "", "", "q"])
    assert json.loads(takes_file.read_text())["play-02"]["text"] == "play pink noise"


def test_redo_rejects_unknown_ids(record):
    with pytest.raises(SystemExit):
        record("--redo", "play-99", keys=[])


def test_eval_skips_missing_and_changed_recordings(tmp_path, capsys):
    cases = run_eval.load_cases()[:3]
    for case in cases[:2]:
        record_eval.save_wav(tmp_path / f"{case['id']}.wav", tone())
    takes = {cases[0]["id"]: {"text": cases[0]["text"], "mic": "Fake Mic"}, cases[1]["id"]: {"text": "old words"}}
    (tmp_path / "takes.json").write_text(json.dumps(takes))

    clips, source = run_eval.recorded(cases, tmp_path)
    assert [case["id"] for case, _ in clips] == [cases[0]["id"]]
    assert source["mics"] == ["Fake Mic"]
    out = capsys.readouterr().out
    assert f"not recorded yet): {cases[2]['id']}" in out
    assert f"after it was recorded): {cases[1]['id']}" in out
