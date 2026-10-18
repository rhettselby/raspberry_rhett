"""Record your own voice reading the eval phrases, for run_eval.py --audio-dir.

Run from the repo root:

    .venv/bin/python assistant/record_eval.py rhett                   # record what's missing
    .venv/bin/python assistant/record_eval.py rhett --redo alarm-03   # re-record a phrase
    .venv/bin/python assistant/run_eval.py --audio-dir assistant/recordings/rhett

It shows each phrase in evals/commands.jsonl in turn. Press Enter, say it, and
press Enter again, the same as in ptt.py. Each take you keep is saved as a
16-bit 16 kHz mono WAV in assistant/recordings/<name>/<id>.wav. That folder is
gitignored and nothing here uses the network, so recordings stay on this machine.
"""

import argparse
import datetime
import json
import os
import re
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

from recorder import problem_with, record_until_enter
from run_eval import RECORDINGS, TAKES, load_cases, load_takes, recording_status
from stt import SAMPLE_RATE

CLIP_PEAK = 0.99  # at full scale the mic clips: the loudest parts of the waveform get cut off


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("name", help="folder under assistant/recordings/, e.g. rhett or rhett-bed-usbmic")
    parser.add_argument("--redo", nargs="+", default=[], metavar="ID", help="re-record these phrases, e.g. alarm-03")
    args = parser.parse_args()
    # The name becomes one folder inside recordings/, which is what keeps it gitignored.
    if not re.fullmatch(r"[\w-]+", args.name):
        parser.error("the name can only use letters, digits, - and _")

    cases = load_cases()
    unknown = sorted(set(args.redo) - {case["id"] for case in cases})
    if unknown:
        parser.error(f"no such phrase: {' '.join(unknown)} (the ids are in evals/commands.jsonl)")

    folder = RECORDINGS / args.name
    takes = load_takes(folder)
    status = {case["id"]: recording_status(case, folder, takes) for case in cases}
    todo = [case for case in cases if case["id"] in args.redo or status[case["id"]] != "ok"]
    score_command = f".venv/bin/python assistant/run_eval.py --audio-dir {os.path.relpath(folder)}"
    if not todo:
        print(f"All {len(cases)} phrases are recorded (--redo ID re-records one). To score them:\n  {score_command}")
        return

    mic = sd.query_devices(kind="input")["name"]
    print(f'{len(todo)} of {len(cases)} phrases to record with "{mic}" into {os.path.relpath(folder)}/')
    print("For each one: [Enter], say it the way you'd say it to the device, [Enter]. Ctrl+C stops.")
    folder.mkdir(parents=True, exist_ok=True)
    saved = 0
    try:
        for n, case in enumerate(todo, 1):
            note = "  (the phrase changed since it was recorded)" if status[case["id"]] == "stale" else ""
            print(f'\n[{n}/{len(todo)}] {case["id"]}{note}\n    "{case["text"]}"')
            audio = take()
            if audio is None:
                break
            save_wav(folder / f"{case['id']}.wav", audio)
            # Saved after every take, so stopping halfway loses nothing.
            takes[case["id"]] = {
                "text": case["text"],
                "mic": mic,
                "date": datetime.datetime.now().isoformat(timespec="seconds"),
            }
            (folder / TAKES).write_text(json.dumps(takes, indent=2) + "\n")
            saved += 1
    except (KeyboardInterrupt, EOFError):
        print()

    left = sum(recording_status(case, folder, takes) != "ok" for case in cases)
    print(f"\nSaved {saved} take(s) in {os.path.relpath(folder)}/.", end=" ")
    print(f"{left} phrase(s) left: run this again to continue." if left else "Every phrase is recorded.")
    print(f"To score them:\n  {score_command}")


def take() -> np.ndarray | None:
    """Record until the user keeps a take. Returns None if they quit."""
    while True:
        input("  [Enter] to talk ")
        print("  Listening... [Enter] to stop")
        audio = record_until_enter()
        problem = problem_with(audio)
        if problem:
            print(f"  {problem}")
            continue
        peak = float(np.abs(audio).max())
        warning = " Clipped: move back or turn the input volume down." if peak >= CLIP_PEAK else ""
        prompt = f"  {len(audio) / SAMPLE_RATE:.1f} s, peak {peak:.0%}.{warning} [Enter] keep, r redo, p play, q quit: "
        choice = None
        while choice not in ("", "r", "q"):
            choice = input(prompt).strip().lower()
            if choice == "p":
                sd.play(audio, SAMPLE_RATE)
                sd.wait()
        if choice == "":
            return audio
        if choice == "q":
            return None


def save_wav(path: Path, audio: np.ndarray) -> None:
    """Save float32 audio in [-1, 1] as a 16-bit mono WAV at SAMPLE_RATE."""
    # 16-bit has far more range than speech needs, it's what `say` writes for
    # --audio (so both sets reach Whisper through the same decoding), it's
    # half the size of float32, and any audio player opens it.
    pcm = np.round(np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes(pcm.tobytes())


if __name__ == "__main__":
    main()
