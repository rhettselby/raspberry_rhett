"""Push-to-talk recording from the default microphone.

Enter starts and stops a recording. It stands in for the Pico button the Pi
will use: press to talk, press again (or release) to stop.
"""

import queue
import sys

import numpy as np
import sounddevice as sd

from stt import SAMPLE_RATE

MAX_SECONDS = 15  # a command takes a few seconds; anything longer is a stuck button
MIN_SECONDS = 0.3  # shorter than this is an accidental double press
SILENCE_PEAK = 1e-3  # macOS records pure silence when the mic permission is off


def record_until_enter(max_seconds: float = MAX_SECONDS) -> np.ndarray:
    """Record mono float32 audio at SAMPLE_RATE until Enter is pressed."""
    blocks: queue.Queue[np.ndarray] = queue.Queue()

    def on_audio(indata, frames, time, status):
        # PortAudio calls this on its own audio thread every few milliseconds.
        # Do as little as possible here: copy the block (PortAudio reuses the
        # buffer) and hand it to the main thread through the queue.
        if status:
            print(f"audio: {status}", file=sys.stderr)
        blocks.put(indata[:, 0].copy())

    # Ask for 16 kHz mono directly. macOS converts from the mic's native rate.
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=on_audio):
        input()

    chunks = []
    while not blocks.empty():
        chunks.append(blocks.get_nowait())
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks)[: int(max_seconds * SAMPLE_RATE)]


def problem_with(audio: np.ndarray) -> str | None:
    """Why a recording can't be used, or None if it can."""
    if len(audio) < MIN_SECONDS * SAMPLE_RATE:
        return "Too short, try again."
    if np.abs(audio).max() < SILENCE_PEAK:
        return (
            "Recorded only silence. Check System Settings > Privacy & Security > "
            "Microphone for your terminal app."
        )
    return None
