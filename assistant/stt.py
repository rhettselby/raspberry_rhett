"""Local speech-to-text with faster-whisper.

Audio goes in as a numpy array and never touches the disk or the network.
The model is downloaded once from Hugging Face on first use, then loaded from
the local cache (~/.cache/huggingface) with no network calls.
"""

import time
from dataclasses import dataclass

import numpy as np
from faster_whisper import WhisperModel
from huggingface_hub.errors import LocalEntryNotFoundError

SAMPLE_RATE = 16_000  # Whisper is trained on 16 kHz mono; other rates get resampled

DEFAULT_MODEL = "base.en"
COMPUTE_TYPE = "int8"  # 8-bit weights: ~4x smaller and faster on CPU than float32
CPU_THREADS = 4  # the Pi 5 has 4 cores, so Mac timings use the same thread count
BEAM_SIZE = 1  # greedy decoding; see the README for the measured trade-off

# Whisper reads this as text spoken just before the audio, so it leans toward
# these words. Without it, base.en hears the `say` voice's "white" as "wide".
PROMPT = "Play white noise, pink noise or brown noise. Stop. Sleep timer. Set an alarm."


@dataclass
class Transcript:
    text: str
    seconds: float  # wall-clock time spent transcribing
    audio_seconds: float  # length of the audio that went in


class Transcriber:
    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        beam_size: int = BEAM_SIZE,
        prompt: str | None = PROMPT,
    ):
        self.model_name = model_name
        self.beam_size = beam_size
        self.prompt = prompt
        start = time.perf_counter()
        options = dict(device="cpu", compute_type=COMPUTE_TYPE, cpu_threads=CPU_THREADS)
        try:
            self._model = WhisperModel(model_name, local_files_only=True, **options)
        except LocalEntryNotFoundError:
            print(f"Downloading Whisper {model_name} (first run only)...")
            self._model = WhisperModel(model_name, **options)
        self.load_seconds = time.perf_counter() - start

    def transcribe(self, audio: np.ndarray) -> Transcript:
        """Transcribe mono float32 audio at SAMPLE_RATE."""
        start = time.perf_counter()
        segments, info = self._model.transcribe(
            audio,
            language="en",
            beam_size=self.beam_size,
            initial_prompt=self.prompt,
            # Decode once. By default, a low-confidence result is retried at
            # higher temperatures, up to 6 decodes: that made the slowest eval
            # phrase take 3 s instead of 0.6 s, with the same text.
            temperature=0.0,
            # Silero VAD trims silence before and after speech. It speeds up
            # decoding, and Whisper invents text ("Thank you.") on silence.
            vad_filter=True,
            # Each command stands alone; don't feed earlier text back in.
            condition_on_previous_text=False,
        )
        # `segments` is a lazy generator: the decoding happens while we
        # iterate, so the join has to be inside the timed region.
        text = " ".join(segment.text.strip() for segment in segments)
        return Transcript(text.strip(), time.perf_counter() - start, info.duration)
