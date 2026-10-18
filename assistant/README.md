# assistant (Python)

The speech half of the project. Right now it holds a Mac prototype of milestone 5's voice path: press Enter, speak, and get a structured command back.

```
Enter ─► recorder.py ─► stt.py ─────────► commands.py ─► JSON ─► fake_device.py
         mic, 16 kHz    Whisper base.en    rules          {"command": "play",       noise_gen + afplay
         float32        int8, local                        "args": {"color": "pink"}}   (Unix socket later)
```

The commands are `play` (white, pink or brown), `stop`, `sleep_timer` (minutes) and `set_alarm` (24-hour `HH:MM`). [DESIGN.md](DESIGN.md) explains why each piece works the way it does.

## Setup

Run these from the repo root, using the venv that's already there:

```bash
.venv/bin/pip install -r assistant/requirements.txt
```

On the first run, Whisper downloads its model (`base.en`, about 140 MB) into `~/.cache/huggingface`. After that, everything runs offline. `ptt.py` keeps audio in memory and never saves it. The only script that writes your voice to disk is `record_eval.py`, which does it on purpose for the eval (see [Your own voice](#your-own-voice)).

macOS asks for microphone access the first time you record. If you miss the prompt, enable your terminal app under System Settings > Privacy & Security > Microphone. Without access, macOS silently records zeros, and the program tells you so.

## Run

Talk into the mic. Press Enter, say "play pink noise", then press Enter again:

```bash
.venv/bin/python assistant/ptt.py
```

You'll see:

```
Heard: "Play pink noise." (0.9 s of audio, transcribed in 0.32 s)
{"command": "play", "args": {"color": "pink"}}
```

Add `--play` to act on commands with the stand-in device. It needs a working `device/build/noise_gen`, which writes empty files until `WavWriter::write()` is done. Add `--model tiny.en` to try another Whisper size.

Without a mic, generate speech with macOS `say` and transcribe the file:

```bash
say -o phrase.aiff "set an alarm for 6:30 am"
```

```bash
.venv/bin/python assistant/ptt.py --file phrase.aiff
```

To test only the parser, pass text:

```bash
.venv/bin/python assistant/ptt.py --text "turn it off in twenty minutes"
```

## Evaluate

[evals/commands.jsonl](evals/commands.jsonl) holds 43 phrases, each with the command it should produce. Each one is tagged `basic` (direct phrasing), `hard` (a paraphrase that needs understanding) or `negative` (not a command; it must produce nothing).

To score the parser alone (text in, instant):

```bash
.venv/bin/python assistant/run_eval.py
```

To speak every phrase with `say` and run it through Whisper too, which adds word error rate and transcription time:

```bash
.venv/bin/python assistant/run_eval.py --audio
```

Useful flags: `--model tiny.en|base.en|small.en`, `--beam-size 5`, `--no-prompt`, `--voice Samantha`, and `--out results.json` to save every result. Generated speech is cached in `evals/audio/` (gitignored).

### Your own voice

The `say` voice is clean and synthetic, so its numbers are optimistic. To measure your own voice, record each phrase once. All 43 take about 10 minutes:

```bash
.venv/bin/python assistant/record_eval.py rhett
```

It shows one phrase at a time. Press Enter, say the phrase the way you'd say it to the device, and press Enter again. Then press Enter to keep the take, `r` to redo it, `p` to play it back, or `q` to stop. Read the words as written, since word error rate compares against them, but say numbers however you normally would ("six thirty a.m."). Redo a take only if you misread it, coughed or cut it off. Never redo one because you think Whisper will get it wrong. After each take you see its length and peak level. A peak of a few percent means the mic barely hears you, and 100% means it clipped (it warns you).

Run the same command again to pick up where you stopped. To redo particular phrases later:

```bash
.venv/bin/python assistant/record_eval.py rhett --redo alarm-03 timer-06
```

Then score them. You get the same report as with `--audio`, and `--model`, `--beam-size`, `--no-prompt` and `--out` work the same way:

```bash
.venv/bin/python assistant/run_eval.py --audio-dir assistant/recordings/rhett
```

Each take is saved as `assistant/recordings/<name>/<id>.wav` (16-bit, 16 kHz, mono, about 100 KB). A `takes.json` next to them records which words and which mic each take used. If you later edit a phrase in `commands.jsonl`, scoring skips its old take, and `record_eval.py` asks you for it again. Include the setup in the folder name as well as the speaker, like `rhett-bed-usbmic`, so sets from different mics and rooms stay apart. `recordings/` and `*.wav` are gitignored, and nothing in these scripts uses the network, so the recordings stay on your machine.

Latency changes with whatever else the Mac is doing, so to compare your voice with `say`, run `--audio` right before or after `--audio-dir`.

## Test

```bash
.venv/bin/python -m pytest assistant
```

## Files

| File | What it does |
|---|---|
| `ptt.py` | The push-to-talk loop and CLI |
| `recorder.py` | Records from the default mic until Enter |
| `stt.py` | Loads Whisper and times each transcription |
| `commands.py` | Rule-based parser: text to command dict |
| `fake_device.py` | Stands in for the C++ device: `noise_gen` + `afplay` |
| `run_eval.py` | Scores the parser, and optionally Whisper, on the eval set |
| `record_eval.py` | Records your voice reading the eval set, for `run_eval.py --audio-dir` |
| `evals/commands.jsonl` | The eval set |
| `recordings/` | Your recordings, one folder per speaker and setup (gitignored, created on first use) |
| `test_commands.py` | Unit tests for the parser |
| `test_record_eval.py` | Tests for recording and loading takes, with a fake mic |
| `start.py` | Placeholder for the long-running assistant service |
