"""Score the command parser, and optionally Whisper, on evals/commands.jsonl.

Run from the repo root:

    .venv/bin/python assistant/run_eval.py                  # text in: parser only
    .venv/bin/python assistant/run_eval.py --audio          # say -> Whisper -> parser
    .venv/bin/python assistant/run_eval.py --audio --model small.en --out small.json
    .venv/bin/python assistant/run_eval.py --audio-dir assistant/recordings/rhett

--audio speaks each phrase with macOS `say` (cached in evals/audio/), then
reports word error rate, transcription time and end-to-end accuracy.
--audio-dir does the same with your own voice, recorded by record_eval.py.
"""

import argparse
import datetime
import hashlib
import json
import math
import platform
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from commands import normalize, parse

HERE = Path(__file__).resolve().parent
CASES = HERE / "evals" / "commands.jsonl"
AUDIO_DIR = HERE / "evals" / "audio"  # generated speech; *.wav is gitignored
RECORDINGS = HERE / "recordings"  # your voice, one folder per speaker/setup; gitignored
TAKES = "takes.json"  # in each recordings folder: the words and mic behind each <id>.wav


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--audio", action="store_true", help="speak each phrase and run it through Whisper")
    parser.add_argument(
        "--audio-dir", type=Path, help="run your recordings from record_eval.py through Whisper instead of `say`"
    )
    parser.add_argument("--model", default=None, help="Whisper model (default: stt.DEFAULT_MODEL)")
    parser.add_argument("--beam-size", type=int, default=None, help="Whisper beam size (default: stt.BEAM_SIZE)")
    parser.add_argument("--no-prompt", action="store_true", help="transcribe without stt.PROMPT")
    parser.add_argument("--voice", default=None, help="macOS `say` voice, e.g. Samantha (`say -v '?'` lists them)")
    parser.add_argument("--out", help="also write the summary and every result to this JSON file")
    args = parser.parse_args()
    if args.voice and args.audio_dir:
        parser.error("--voice picks a `say` voice, so it doesn't apply to --audio-dir")

    cases = load_cases()
    run_info = {"date": datetime.datetime.now().isoformat(timespec="seconds"), "platform": platform.platform()}
    audio = args.audio or args.audio_dir is not None
    if audio:
        if args.audio_dir:
            clips, source = recorded(cases, args.audio_dir)
        else:
            clips = [(case, speak(case, args.voice)) for case in cases]
            source = {"audio": "say", "voice": args.voice}
        print(describe(source, len(clips)))
        results, stt_info = run_audio(clips, args.model, args.beam_size, not args.no_prompt)
        run_info.update(source, **stt_info)
    else:
        results = [score(case, heard=case["text"]) for case in cases]

    summary = summarize(results)
    print_report(summary, results, audio=audio)
    if len(results) < len(cases):
        print(f"\nOnly {len(results)} of {len(cases)} phrases were scored, so don't compare this with a full run.")
    if args.out:
        Path(args.out).write_text(json.dumps({**run_info, "summary": summary, "results": results}, indent=2))
        print(f"\nWrote {args.out}")


def load_cases() -> list[dict]:
    return [json.loads(line) for line in CASES.read_text().splitlines() if line.strip()]


def score(case: dict, heard: str, **extra) -> dict:
    got = parse(heard)
    return {**case, "heard": heard, "got": got, "ok": got == case["expected"], **extra}


def run_audio(clips: list[tuple[dict, Path]], model: str | None, beam_size: int | None, use_prompt: bool):
    """Transcribe each (case, audio file) pair and score the transcript."""
    # Imported here so the text-only eval doesn't need the audio libraries.
    from faster_whisper import decode_audio

    import stt

    transcriber = stt.Transcriber(
        model or stt.DEFAULT_MODEL, beam_size or stt.BEAM_SIZE, stt.PROMPT if use_prompt else None
    )
    print(
        f"Whisper {transcriber.model_name} ({stt.COMPUTE_TYPE}, {stt.CPU_THREADS} threads, "
        f"beam {transcriber.beam_size}, prompt {'on' if use_prompt else 'off'}): "
        f"loaded in {transcriber.load_seconds:.1f} s"
    )
    results = []
    for case, path in clips:
        audio = decode_audio(str(path), sampling_rate=stt.SAMPLE_RATE)
        transcript = transcriber.transcribe(audio)
        results.append(
            score(
                case,
                heard=transcript.text,
                parser_ok=parse(case["text"]) == case["expected"],
                word_errors=word_errors(words(case["text"]), words(transcript.text)),
                stt_seconds=round(transcript.seconds, 4),
                audio_seconds=round(transcript.audio_seconds, 3),
            )
        )
    info = {
        "model": transcriber.model_name,
        "beam_size": transcriber.beam_size,
        "prompt": transcriber.prompt,
        "compute_type": stt.COMPUTE_TYPE,
        "cpu_threads": stt.CPU_THREADS,
        "load_seconds": round(transcriber.load_seconds, 2),
    }
    return results, info


def describe(source: dict, count: int) -> str:
    if source["audio"] == "say":
        return f"Audio: {count} phrases spoken by macOS `say` ({source['voice'] or 'default'} voice)"
    mics = ", ".join(source["mics"]) or "unknown"
    return f"Audio: {count} recordings from {source['audio']} (mic: {mics})"


def speak(case: dict, voice: str | None) -> Path:
    """Synthesize a phrase with macOS `say`, cached as a 16 kHz mono WAV."""
    key = hashlib.sha1(f"{voice}|{case['text']}".encode()).hexdigest()[:8]
    path = AUDIO_DIR / f"{case['id']}-{key}.wav"
    if not path.exists():
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        command = ["say", "-o", str(path), "--file-format=WAVE", "--data-format=LEI16@16000"]
        if voice:
            command += ["-v", voice]
        subprocess.run([*command, case["text"]], check=True)
    return path


# --- Recordings of your voice (made by record_eval.py) -----------------------


def load_takes(folder: Path) -> dict:
    """{id: {"text", "mic", "date"}} for a recordings folder; empty if it has no takes.json."""
    path = folder / TAKES
    return json.loads(path.read_text()) if path.exists() else {}


def recording_status(case: dict, folder: Path, takes: dict) -> str:
    """"ok", "missing", or "stale" (recorded when the phrase had different words)."""
    if not (folder / f"{case['id']}.wav").exists():
        return "missing"
    take = takes.get(case["id"])
    # The phrase's text is the reference for word error rate, so a recording
    # of old words would count as transcription errors that aren't there.
    if take is not None and take["text"] != case["text"]:
        return "stale"
    return "ok"


def recorded(cases: list[dict], folder: Path) -> tuple[list[tuple[dict, Path]], dict]:
    """Pair each case with its recording in folder, leaving out missing and stale ones."""
    if not folder.is_dir():
        sys.exit(f"No folder {folder}. Record one with: .venv/bin/python assistant/record_eval.py NAME")
    takes = load_takes(folder)
    status = {case["id"]: recording_status(case, folder, takes) for case in cases}
    for kind, why in [("missing", "not recorded yet"), ("stale", "the phrase changed after it was recorded")]:
        ids = [case_id for case_id, s in status.items() if s == kind]
        if ids:
            print(f"Skipping {len(ids)} ({why}): {' '.join(ids[:10])}{' ...' if len(ids) > 10 else ''}")
    clips = [(case, folder / f"{case['id']}.wav") for case in cases if status[case["id"]] == "ok"]
    if not clips:
        sys.exit(f"No usable recordings in {folder}")
    mics = sorted({takes[case["id"]]["mic"] for case, _ in clips if case["id"] in takes})
    return clips, {"audio": str(folder), "mics": mics}


# --- Metrics ------------------------------------------------------------------


def words(text: str) -> list[str]:
    """Words for WER, normalized so "7:30 a.m." and "seven thirty am" match."""
    return normalize(text).replace(":", " ").split()


def word_errors(reference: list[str], hypothesis: list[str]) -> int:
    """Edit distance in words: substitutions + deletions + insertions."""
    previous = list(range(len(hypothesis) + 1))
    for i, ref_word in enumerate(reference, 1):
        current = [i]
        for j, hyp_word in enumerate(hypothesis, 1):
            current.append(
                min(
                    previous[j] + 1,  # deletion
                    current[j - 1] + 1,  # insertion
                    previous[j - 1] + (ref_word != hyp_word),  # substitution or match
                )
            )
        previous = current
    return previous[-1]


def summarize(results: list[dict]) -> dict:
    def tally(key) -> dict:
        counts = defaultdict(lambda: [0, 0])
        for r in results:
            for k in key(r):
                counts[k][0] += r["ok"]
                counts[k][1] += 1
        return {k: f"{ok}/{n}" for k, (ok, n) in counts.items()}

    failures = [r for r in results if not r["ok"]]
    negatives = [r for r in results if r["expected"] is None]
    summary = {
        "correct": sum(r["ok"] for r in results),
        "total": len(results),
        "by_command": tally(lambda r: [r["expected"]["command"] if r["expected"] else "none"]),
        "by_tag": tally(lambda r: r["tags"]),
        # A missed command means "say it again". A wrong one does something
        # you didn't ask for, which is worse at 3 a.m.
        "missed": sum(r["got"] is None for r in failures),
        "wrong": sum(r["got"] is not None for r in failures),
        "false_triggers": f"{sum(r['got'] is not None for r in negatives)}/{len(negatives)}",
    }
    if "stt_seconds" in results[0]:
        times = sorted(r["stt_seconds"] for r in results)
        reference_words = sum(len(words(r["text"])) for r in results)
        summary.update(
            wer=sum(r["word_errors"] for r in results) / reference_words,
            exact_transcripts=sum(r["word_errors"] == 0 for r in results),
            parser_correct_on_text=sum(r["parser_ok"] for r in results),
            lost_to_transcription=sum(r["parser_ok"] and not r["ok"] for r in results),
            stt_mean=statistics.mean(times),
            stt_median=statistics.median(times),
            stt_p95=times[math.ceil(0.95 * len(times)) - 1],
            stt_max=times[-1],
            audio_mean=statistics.mean(r["audio_seconds"] for r in results),
            real_time_factor=sum(times) / sum(r["audio_seconds"] for r in results),
        )
    return summary


def print_report(s: dict, results: list[dict], audio: bool) -> None:
    title = "End-to-end accuracy (speech in)" if audio else "Parser accuracy (text in)"
    print(f"\n{title}: {s['correct']}/{s['total']} = {s['correct'] / s['total']:.1%}")
    print("  by command:  " + "  ".join(f"{k} {v}" for k, v in s["by_command"].items()))
    print("  by tag:      " + "  ".join(f"{k} {v}" for k, v in s["by_tag"].items()))
    print(f"  failures:    {s['missed']} missed (no command), {s['wrong']} wrong (a different command)")
    print(f"  false triggers on non-commands: {s['false_triggers']}")
    if audio:
        print(f"\nTranscription ({s['total']} phrases)")
        print(f"  word error rate: {s['wer']:.1%}   exact transcripts: {s['exact_transcripts']}/{s['total']}")
        print(
            f"  time: mean {s['stt_mean']:.2f} s, median {s['stt_median']:.2f} s, "
            f"p95 {s['stt_p95']:.2f} s, max {s['stt_max']:.2f} s"
        )
        print(f"  audio: mean {s['audio_mean']:.1f} s, real-time factor {s['real_time_factor']:.2f}")
        print(
            f"  parser alone (text in): {s['parser_correct_on_text']}/{s['total']}, "
            f"so {s['lost_to_transcription']} lost to transcription errors"
        )

    failures = [r for r in results if not r["ok"]]
    if failures:
        print("\nFailures")
        for r in failures:
            print(f"  {r['id']:<9} \"{r['text']}\"")
            if audio:
                print(f"            heard    \"{r['heard']}\"")
            print(f"            expected {json.dumps(r['expected'])}")
            print(f"            got      {json.dumps(r['got'])}")


if __name__ == "__main__":
    main()
