"""Check the spectrum of noise WAV files made by noise_gen.

Prints each file's slope in dB per octave (white is about 0, pink -3, brown -6)
and, if matplotlib is installed, saves a plot of all the spectra.

    python3 device/tools/plot_spectrum.py white.wav pink.wav brown.wav
"""

import argparse
import os
import sys
import wave

import numpy as np

SEGMENT = 8192  # FFT size: about 5.9 Hz per bin at 48 kHz
EXPECTED_SLOPES = {"white": 0.0, "pink": -3.0, "brown": -6.0}


def read_wav(path):
    """Return (sample_rate, samples in [-1, 1]) for the first channel of a 16-bit WAV."""
    with wave.open(path, "rb") as f:
        if f.getsampwidth() != 2:
            sys.exit(f"{path}: expected 16-bit samples")
        rate = f.getframerate()
        channels = f.getnchannels()
        frames = f.readframes(f.getnframes())
    data = np.frombuffer(frames, dtype="<i2").reshape(-1, channels)[:, 0]
    return rate, data / 32768.0


def power_spectrum(samples):
    """Average the power spectrum of 50%-overlapping, Hann-windowed segments (Welch's method)."""
    if len(samples) < SEGMENT:
        sys.exit(f"need at least {SEGMENT} samples; generate a longer file")
    window = np.hanning(SEGMENT)
    starts = range(0, len(samples) - SEGMENT + 1, SEGMENT // 2)
    power = np.zeros(SEGMENT // 2 + 1)
    for start in starts:
        power += np.abs(np.fft.rfft(samples[start:start + SEGMENT] * window)) ** 2
    return power / len(starts)


def expected_slope(path):
    name = os.path.basename(path).lower()
    return next((slope for color, slope in EXPECTED_SLOPES.items() if color in name), None)


def main():
    parser = argparse.ArgumentParser(description="Check the spectrum of noise WAV files.")
    parser.add_argument("files", nargs="+", help="WAV files written by noise_gen")
    parser.add_argument("--fmin", type=float, default=500, help="start of the slope fit, Hz")
    parser.add_argument("--fmax", type=float, default=10000, help="end of the slope fit, Hz")
    parser.add_argument("--out", default="spectrum.png", help="where to save the plot")
    args = parser.parse_args()

    curves = []
    for path in args.files:
        rate, samples = read_wav(path)
        freqs = np.fft.rfftfreq(SEGMENT, 1 / rate)
        power_db = 10 * np.log10(power_spectrum(samples) + 1e-20)

        # Fit a straight line to dB against log2(frequency): its slope is dB per octave.
        band = (freqs >= args.fmin) & (freqs <= args.fmax)
        slope = np.polyfit(np.log2(freqs[band]), power_db[band], 1)[0]
        expected = expected_slope(path)
        note = f" (expected about {expected:+.0f})" if expected is not None else ""
        print(f"{path}: {slope:+.1f} dB/octave{note}")

        # Shift each curve so it reads 0 dB at 1 kHz, which makes the slopes easy to compare.
        reference = power_db[np.argmin(np.abs(freqs - 1000))]
        curves.append((path, freqs[1:], power_db[1:] - reference))

    try:
        import matplotlib

        matplotlib.use("Agg")  # draw to a file; no window needed
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib isn't installed, so there's no plot (see device/README.md)")
        return

    fig, ax = plt.subplots(figsize=(9, 5))
    for path, freqs, power_db in curves:
        ax.semilogx(freqs, power_db, linewidth=1, label=os.path.basename(path))
    guide = np.geomspace(20, 20000, 50)
    for slope in EXPECTED_SLOPES.values():
        ax.semilogx(guide, slope * np.log2(guide / 1000), "--", color="gray", linewidth=0.8)
    ax.set_xlim(20, 24000)
    ax.set_ylim(-60, 40)
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Power relative to 1 kHz (dB)")
    ax.set_title("Noise spectra (dashed: 0, -3 and -6 dB per octave)")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    fig.savefig(args.out, dpi=120)
    print(f"saved {args.out}")


if __name__ == "__main__":
    main()
