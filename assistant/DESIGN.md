# Design notes: push-to-talk prototype

Why the voice path is built the way it is. Each section gives the choice, the reason, and what was traded away. Numbers come from `run_eval.py --audio` on an M1 Mac (8 GB) on 2026-10-16. See [Measurements](#measurements).

## The shape of the system

**Push-to-talk, not a wake word.** A wake word means a mic that's always listening, a second model running all night, and false wake-ups in a bedroom. With a button, the mic is only open while you hold it, nothing runs between commands, and it can't trigger on its own. The button press also marks where speech starts and stops, so there's no end-of-speech detection to get wrong. On the Pi the button is the Pico. Here, Enter stands in for it. Hold-to-talk on the Mac would need `pynput` plus macOS Accessibility permission, which isn't worth it for a stand-in.

**Stages with plain data between them.** The stages pass a numpy array, then a string, then a dict. Each one runs and tests on its own: `--text` skips audio, `--file` skips the mic, `run_eval.py` replaces the mic with `say` or your recordings. In milestone 6, the LLM replaces `commands.parse()` and nothing upstream changes. When the socket exists, a socket client replaces `FakeDevice` and nothing upstream changes.

**The assistant decides, the device acts.** The assistant turns speech into an intent. The C++ device owns state and defaults: what's playing, timers, alarms. That's why `play` without a color has empty `args` (the device picks), and why `set_alarm` doesn't ring here. Alarms have to survive an assistant crash, so they belong in the C++ program.

## Audio

**16 kHz, mono, float32, in memory.** Whisper is trained on 16 kHz mono audio. Asking the OS for that rate means CoreAudio does the resampling, not Python. float32 in [-1, 1] is the format faster-whisper takes, so no conversion is needed. Five seconds is 320 KB. The audio never touches the disk, which keeps the privacy goal by construction: there's no recording to leak. The one exception is `record_eval.py`, which saves your voice on purpose so the eval can use it (see [Recording your own voice](#recording-your-own-voice)). On the Pi, USB mics through ALSA often only offer 44.1 or 48 kHz. Then you either record at 48 kHz and resample, or use ALSA's `plughw` device, which converts.

**Callback plus queue.** PortAudio calls `on_audio()` on its own real-time thread every few milliseconds. If that callback is slow, samples get dropped and you see `input overflow`. So it only copies the block (PortAudio reuses the buffer) and puts it on a `queue.Queue`. The main thread joins the blocks afterwards. It's the same producer/consumer split as the lock-free ring buffer in device milestone 2. Python's queue uses a lock, which is fine at this data rate.

**Silence check.** Without mic permission, macOS hands you zeros instead of an error. `ptt.py` checks the peak level and says so, rather than letting Whisper hallucinate on silence.

## Speech-to-text

**faster-whisper.** The options considered:

| Option | Why not (for now) |
|---|---|
| openai-whisper | Runs on PyTorch: a much bigger install, and slower on CPU than int8 CTranslate2. Same models. |
| whisper.cpp | C++ and very fast on ARM. A good candidate if speech moves into the C++ program later. From Python it needs third-party bindings. |
| mlx-whisper | Fast on the Mac's GPU, but MLX doesn't exist on the Pi, so Mac numbers wouldn't predict the Pi. |
| Vosk | Small and streaming, but less accurate. |
| Cloud APIs | Break the rule that voice is processed on the device. |

faster-whisper runs the same engine (CTranslate2) with the same code on the Mac and the Pi, and ships ARM64 wheels.

**int8 on the CPU, 4 threads.** The Pi 5 has no GPU that helps here, and it has 4 Cortex-A76 cores. int8 weights are 4x smaller than float32 and faster for CPU matrix math, with little accuracy loss. Pinning 4 threads keeps the Mac run the same shape as the Pi's. Each M1 core is still faster than an A76 core, so treat Mac latency as a lower bound and measure on the Pi.

**Whisper always processes 30 seconds.** The encoder pads every input to a 30-second window, so its cost is about the same for a 1-second command as for a 10-second one. Shorter commands barely help. The model size is the main lever on latency.

**Model: `base.en`.** `tiny.en` is about twice as fast (median 0.18 s vs 0.32 s), but it writes "7:15" as "715", which the parser doesn't read, so it misses 2 `basic` alarm phrases. `base.en` gets every `basic` phrase right. `small.en` (484 MB) wasn't measured because the Mac didn't have the disk space. Expect everything to be several times slower on the Pi. If `base.en` is too slow there, the fallback is `tiny.en` plus a normalizer rule for "715". The `.en` models are English-only, and more accurate than the multilingual ones of the same size on English.

**Greedy decoding (beam size 1).** Beam search keeps the 5 most likely transcripts as it decodes, instead of only the best one. On this eval it produced the same transcripts and took about 15% longer (median 0.37 s vs 0.32 s), so greedy wins. Short, clear commands leave beam search little to fix.

**VAD filter on.** faster-whisper's built-in Silero VAD (a small ONNX model) trims silence before decoding. Whisper invents text on silence or noise, often "Thank you." or "you", and a hallucinated command at 3 a.m. is the worst failure this device can have. Trimming also means less audio to decode.

**No temperature fallback.** By default, when a decode looks unsure (average log-probability below -1.0, or too repetitive), faster-whisper throws it away and decodes again with more randomness, up to 6 times. That helps rescue long recordings. For a 1-second command it only adds latency. One eval phrase, "the brown dog is sleeping", took 2.4 to 4.6 s instead of 0.6 s and came out with the same text. `temperature=0.0` decodes once, so the worst case is bounded and every run gives the same transcript. If that transcript is wrong, the parser returns nothing and you say it again.

**A vocabulary prompt.** `stt.PROMPT` is fed to Whisper as if it were text spoken just before the audio, so it leans toward this app's words. Without it, `base.en` hears the `say` voice's "white" as "wide", WER rises from 0.9% to 2.8%, and 2 `basic` phrases fail. One of them counts as wrong rather than missed: "Play wide noise" becomes `play` with no color, so the device plays its default. The prompt costs no measurable time here. The risks: a prompt can make Whisper add words ("The brown dog is sleeping. anything."), and on near-silent audio Whisper can echo the prompt back, which would be a phantom command. The VAD filter guards against the second risk, since silence never reaches the decoder. Set `PROMPT = None` to turn it off. This choice was made after seeing the "wide noise" error, so its gain on this eval set is optimistic. See "Don't tune on the eval" below.

**Download once, then offline.** `Transcriber` first loads the model with `local_files_only=True` and only downloads it if that fails. After the first run, there's no network call at startup, which matters for a device that should work with Wi-Fi down. The model lives in `~/.cache/huggingface`, not in the repo.

**How latency is measured.** `time.perf_counter()` wraps the `transcribe()` call *and* the loop over its results. faster-whisper returns a lazy generator, and the decoding happens while you iterate, so timing only the call would measure almost nothing. The timing includes the VAD. Model load time is reported separately: on the Pi the assistant will be a long-running service, so it loads once at boot, not on every command.

## Parsing

**Rules first, the LLM later.** The rule-based parser is the baseline that milestone 6's LLM has to beat. It takes microseconds, it's deterministic, and it needs no model. It's brittle with paraphrases, though (`hard`: 3/10). The interesting question for milestone 6 is how much the LLM gains on `hard` without losing `basic` or `negative`, and at what latency.

**Normalize, then match.** Whisper writes the same thing many ways ("7:30 a.m.", "7.30am", "seven thirty"). `normalize()` maps them to one spelling (`7:30 am`, `7 30`) so each rule only handles one form.

**Ordered rules; the first match wins.** "Turn it off in 20 minutes" contains the stop phrase "turn it off", and "turn off the white noise" contains a color. So the order is alarm, then sleep timer, then stop, then play: commands with arguments before the ones without. `test_commands.py` pins each of these conflicts down.

**Return nothing rather than guess.** If a rule isn't sure, it returns `None`. A missed command costs you saying it again. A wrong one might start an alarm or stop the noise you're sleeping to. On the text eval, all 7 failures are misses and none are wrong. A bare number only counts as a time after "at" or "for", and "in 8 hours" never becomes an 08:00 alarm.

**The command shape matches a tool call.** `{"command": ..., "args": {...}}` is a name plus JSON arguments: the same thing an LLM produces when it calls a tool (Claude's `tool_use` has `name` and `input`; Ollama's has `function.name` and `arguments`). So in milestone 6, the parser and the LLM are scored by the same eval with a plain `==`. It's also the message the C++ device will receive over the socket. Times are 24-hour `"HH:MM"` strings and durations are whole minutes: unambiguous and easy to parse in C++.

**No am/pm means the hour as said.** "Set an alarm for 7" is 07:00. That's the right guess for a wake-up alarm, and "19:00" still works.

## Evaluation

**JSONL.** One case per line, with `id`, `text`, `expected` (`null` for non-commands) and `tags`. Adding a case is a one-line diff, and it's the usual format for eval sets.

**Three tags, reported separately.** `basic` is the direct phrasing the rules target. `hard` is paraphrases that need understanding ("put on some static" is white noise; "quarter to seven" is 06:45). `negative` is things a bedroom mic will hear that must not trigger anything. One overall number would hide that the parser is perfect on `basic` and weak on `hard`.

**Metrics.**

- **Accuracy:** an exact match on the command and its arguments.
- **Missed vs wrong:** a wrong command is the dangerous kind of failure (see above).
- **False triggers:** non-commands that produced a command.
- **Word error rate:** word edits divided by reference words, after normalizing both sides. On 3- to 8-word commands, one wrong word is a big percentage, so look at the transcripts in the failure list too.
- **Latency:** mean, median, p95 and max. The slow outliers are what you notice when using it, so p95 matters more than the mean.
- **Real-time factor:** transcription time divided by audio length. Under 1 means faster than real time.

**Synthetic speech is optimistic.** The `say` voice is clean, with no room noise, no accent variation and no sleepy mumbling. Its errors are its own, too: Whisper hears its "white" as "wide". So the eval also takes a second audio set, recorded in your own voice. Record it first with the Mac's mic, then from bed with the USB mic the Pi will use.

**Don't tune on the eval.** If you add a rule for every `hard` failure, the score goes up but stops telling you how the parser handles phrasings it hasn't seen. Before tuning, write a few new phrases you haven't looked at, and score on those.

### Recording your own voice

**A separate script, not a `run_eval.py` flag.** You record once, by hand. You score many times, unattended: after every change to the model, the prompt or the parser. `record_eval.py` owns the mic and writes files. `run_eval.py --audio-dir` only reads them, so scoring never waits for a keypress and can run over SSH on the Pi.

**The same path as the live loop.** Takes come from `recorder.record_until_enter()`, the function `ptt.py` uses, at the same 16 kHz, and nothing trims them. A take holds exactly what the live loop would hand Whisper: your reaction time before and after speaking, and the click of the Enter key. The VAD filter has to deal with those in both. On the Pi, the Pico button won't click next to the mic, so the Mac set is slightly harder there.

**Keep, redo or play back each take.** A misread phrase would be scored as a transcription error, which makes Whisper look worse than it is. So each take waits for Enter before it's saved, and `p` plays it back. The other side of this: only redo a take for a misread, a cough or a cut-off, never because you expect Whisper to fail on it. Otherwise the set fills with your clearest delivery, and that's tuning on the eval (see above).

**Read the words as written, say numbers your way.** Word error rate compares the transcript against the phrase's text, so a paraphrase counts as errors that Whisper didn't make. Numbers are different: `normalize()` maps "6:30", "six thirty" and "6.30" to the same words, so say them however you naturally would.

**16-bit WAV with Python's `wave` module.** 16-bit has far more range than speech needs. It's half the size of float32, any player opens it, and it needs no new dependency. It's also what `say` writes for `--audio`, so both sets reach Whisper through the same `decode_audio()` call. The live loop hands Whisper float32 directly. The round trip to 16-bit changes each sample by at most 3e-5, which `test_record_eval.py` checks.

**One file per phrase, named by id, plus `takes.json`.** `<id>.wav` makes resuming trivial: a phrase is done when its file exists. `takes.json` records the words and the mic behind each take. The words matter because the phrase's text is the reference for word error rate. If a phrase is edited after it was recorded, its take would be scored against words you never said. Scoring skips those takes, and `record_eval.py` asks for them again. The mic name appears in the report and the `--out` JSON, so you can tell a MacBook set from a USB-mic set later. Both are written after every take, so Ctrl+C loses nothing.

**Partial sets still score, with a warning.** A folder with 10 of 43 phrases recorded gets a report on those 10, plus a line saying not to compare it with a full run. That's handy for checking the mic after the first few takes. The accuracy covers only those phrases, though.

**Keeping recordings private.** The recordings are your voice, so they're handled more carefully than the eval's other files. `record_eval.py` only writes inside `assistant/recordings/`, since the name you give it has to be a single folder name. Two gitignore rules cover that folder: `recordings/` and `*.wav`. Neither script makes a network call: Whisper loads from the local cache, and `takes.json` stays next to the audio. The repo lives in `~/raspberrypi_rhett`, outside `~/Desktop` and `~/Documents`, so iCloud's Desktop & Documents sync doesn't upload it either.

## Measurements

All runs: the 43 phrases spoken by the default `say` voice, int8, 4 threads, temperature 0, on an M1 Mac (8 GB) with macOS background indexing running. Each configuration ran twice; the table shows the first run, and the medians of the second run were within 0.02 s. To reproduce a row: `run_eval.py --audio --model base.en --beam-size 1 --out base.json`.

| Model | Beam | Prompt | Correct (of 43) | `basic` (of 27) | WER | Median | p95 | Max |
|---|---|---|---|---|---|---|---|---|
| tiny.en | 1 | on | 34 | 25 | 1.8% | 0.18 s | 0.21 s | 0.45 s |
| **base.en** | **1** | **on** | **36** | **27** | **0.9%** | **0.32 s** | **0.36 s** | **0.62 s** |
| base.en | 5 | on | 36 | 27 | 0.9% | 0.37 s | 0.50 s | 0.72 s |
| base.en | 1 | off | 34 | 25 | 2.8% | 0.33 s | 0.38 s | 0.83 s |

The bold row is the default. Every row gets all 6 `negative` phrases right and 3 of the 10 `hard` ones. The parser alone (text in) also scores 36/43, so with the defaults transcription loses nothing on this set: every remaining failure is the parser's. Before `temperature=0.0`, the default row's max was 2.4 s. The mean phrase is 1.4 s of audio, so the default's real-time factor is 0.23. Loading `base.en` from the local cache takes about 0.5 s.

### Your voice vs `say`

Not measured yet: the recordings come next. To fill in the table, record a set with `record_eval.py`, then score it and the `say` set back to back with the default flags:

```
run_eval.py --audio --out say.json
run_eval.py --audio-dir assistant/recordings/rhett --out rhett.json
```

| Audio (defaults: base.en, beam 1, prompt on) | Correct (of 43) | `basic` (of 27) | `hard` (of 10) | `negative` (of 6) | Wrong | WER | Median | p95 |
|---|---|---|---|---|---|---|---|---|
| `say`, default voice (2026-10-18) | 36 | 27 | 3 | 6 | 0 | 0.9% | 0.35 s | 0.45 s |
| Your voice, Mac mic | not recorded yet | | | | | | | |
| Your voice, from bed, USB mic | not recorded yet | | | | | | | |

What to look at once it's filled in:

- **Wrong commands and false triggers first.** Both are 0 on `say`. Any on your voice matter more than a lower score, since those are the 3 a.m. failures.
- **"Lost to transcription."** The report counts phrases the parser gets right from the text but not from your audio. On `say` it's 0, so every failure there is the parser's. On your voice, that count is what Whisper costs, and the Failures list shows what it heard.
- **Latency, not real-time factor.** Your takes include the pauses around the words, so they're longer than `say`'s. Their real-time factor drops even though Whisper does the same work, because Whisper pads everything to 30 s anyway. Latency should stay close to `say`'s.

**How the tooling was checked**, with `say` audio standing in for recordings, on 2026-10-18:

- The cached `say` WAVs, copied into a folder as `<id>.wav` and scored with `--audio-dir`, give the same 43 transcripts as `--audio`. So the two paths feed Whisper identically.
- The same audio written through `record_eval.save_wav()`, with 0.6 s of quiet noise before and 0.5 s after (like a push-to-talk take), still scores 36/43 with the same commands. Median latency stayed about the same (0.33 s vs 0.35 s), but the real-time factor halved (0.13 vs 0.26), because the clips grew from 1.4 s to 2.5 s on average. 4 of the 43 transcripts changed: "sleek timer" became "sleep timer", the prompt's stray "anything." went away, "5-mile" became "5 mile", and "rumbly one" became "rumbly wand".

Two things to keep in mind when you read your numbers:

- Small changes to the audio flip individual transcripts, and with 43 phrases each one is worth 2.3 points. So between two sets, a difference of 1 or 2 phrases is noise. One speaker in one room is also one data point, not a general accuracy figure.
- Latency drifts with what else the Mac is doing. The same `say` run had a median of 0.44 s once and 0.35 s a few minutes later (and 0.32 s on 2026-10-16). Only compare runs made back to back.

## Not done yet

- `noise_gen` writes empty WAV files until `WavWriter::write()` is finished, so `--play` reports that instead of playing.
- On the Pi: `sudo apt install libportaudio2`, the USB mic's sample rate, and latency measured there.
- Your voice: `record_eval.py` is ready and was tested with `say` stand-ins, but nothing is recorded yet. Then a second set from bed with the Pi's USB mic.
- Milestone 6: LLM tool calling, scored on the same `commands.jsonl`.
