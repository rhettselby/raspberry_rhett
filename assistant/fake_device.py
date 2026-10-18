"""A stand-in for the C++ device, so commands do something on the Mac.

The real device is a separate program the assistant will talk to over a Unix
socket. Until that exists, this class takes the same command dicts and fakes
them with device/build/noise_gen and macOS `afplay`. Later, a socket client
with the same handle() method replaces it, and nothing else has to change.
"""

import subprocess
import tempfile
import threading
from pathlib import Path

NOISE_GEN = Path(__file__).resolve().parent.parent / "device" / "build" / "noise_gen"
DEFAULT_COLOR = "white"  # for "play some noise"; defaults belong to the device
CLIP_SECONDS = 60  # afplay can't loop, so each play is one clip
VOLUME = "0.2"  # afplay volume, 0 to 1. Full-scale noise is loud.
WAV_HEADER_BYTES = 44


class FakeDevice:
    def __init__(self, noise_gen: Path = NOISE_GEN):
        self._noise_gen = Path(noise_gen)
        self._tmp = tempfile.TemporaryDirectory(prefix="fake_device_")
        self._player: subprocess.Popen | None = None
        self._timer: threading.Timer | None = None
        # The sleep timer calls stop() from its own thread.
        self._lock = threading.Lock()

    def handle(self, command: dict) -> str:
        name, args = command["command"], command["args"]
        if name == "play":
            return self.play(args.get("color", DEFAULT_COLOR))
        if name == "stop":
            return self.stop()
        if name == "sleep_timer":
            return self.sleep_timer(args["minutes"])
        if name == "set_alarm":
            return f"alarm noted for {args['time']} (the stand-in doesn't ring)"
        return f"unknown command {name!r}"

    def play(self, color: str) -> str:
        if not self._noise_gen.exists():
            return f"can't play: build {self._noise_gen} first"
        wav = Path(self._tmp.name) / f"{color}.wav"
        subprocess.run(
            [str(self._noise_gen), color, str(CLIP_SECONDS), str(wav)],
            check=True,
            capture_output=True,
        )
        if wav.stat().st_size <= WAV_HEADER_BYTES:
            return "noise_gen wrote no samples: finish WavWriter::write() and rebuild"
        with self._lock:
            self._stop_player()
            self._player = subprocess.Popen(["afplay", "-v", VOLUME, str(wav)])
        return f"playing {color} noise ({CLIP_SECONDS} s clip)"

    def stop(self) -> str:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._stop_player()
        return "stopped"

    def sleep_timer(self, minutes: int) -> str:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(minutes * 60, self.stop)
            self._timer.daemon = True
            self._timer.start()
        return f"stopping in {minutes} min"

    def close(self) -> None:
        self.stop()
        self._tmp.cleanup()

    def _stop_player(self) -> None:
        # Callers hold self._lock.
        if self._player is not None:
            self._player.terminate()
            self._player = None
