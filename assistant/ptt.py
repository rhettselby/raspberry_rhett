"""Push-to-talk voice commands: microphone -> Whisper -> command JSON.

Run from the repo root:

    .venv/bin/python assistant/ptt.py                         # talk into the mic
    .venv/bin/python assistant/ptt.py --play                  # ...and act on commands
    .venv/bin/python assistant/ptt.py --file phrase.aiff      # transcribe a file
    .venv/bin/python assistant/ptt.py --text "play pink noise"   # parser only
"""

import argparse
import json

import numpy as np

from commands import parse


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default=None, help="Whisper model, e.g. tiny.en, base.en, small.en")
    parser.add_argument("--file", help="transcribe this audio file instead of the mic")
    parser.add_argument("--text", help="skip audio and parse this text")
    parser.add_argument("--play", action="store_true", help="act on commands with the stand-in device")
    args = parser.parse_args()

    if args.text:
        print(json.dumps(parse(args.text)))
        return

    # Imported here so --text works without loading the audio and ML libraries.
    from faster_whisper import decode_audio

    from fake_device import FakeDevice
    from stt import DEFAULT_MODEL, SAMPLE_RATE, Transcriber

    stt = Transcriber(args.model or DEFAULT_MODEL)
    print(f"Loaded Whisper {stt.model_name} in {stt.load_seconds:.1f} s")
    device = FakeDevice() if args.play else None

    try:
        if args.file:
            # decode_audio converts any format and rate to 16 kHz mono float32.
            handle(decode_audio(args.file, sampling_rate=SAMPLE_RATE), stt, device)
            return

        from recorder import problem_with, record_until_enter

        print("Press Enter to start talking and Enter again to stop. Ctrl+C quits.")
        while True:
            input("\n[Enter] to talk ")
            print("Listening... [Enter] to stop")
            audio = record_until_enter()
            problem = problem_with(audio)
            if problem:
                print(problem)
                continue
            handle(audio, stt, device)
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        if device is not None:
            device.close()


def handle(audio: np.ndarray, stt, device) -> None:
    result = stt.transcribe(audio)
    print(f'Heard: "{result.text}" ({result.audio_seconds:.1f} s of audio, transcribed in {result.seconds:.2f} s)')
    command = parse(result.text)
    print(json.dumps(command))
    if command is None:
        print("(not a command)")
    elif device is not None:
        print(device.handle(command))


if __name__ == "__main__":
    main()
