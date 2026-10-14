# Raspberry Pi Voice Assistant

A local, private voice assistant on a Raspberry Pi 5, built around sleep and fitness. The aim is to take the phone out of bedtime: noise, music and alarms play through a Bluetooth sleep mask, and workouts are logged by voice. Speech recognition and the language model run on the device.

**Status:** early setup.

## Goals

- **Sleep:** white, pink and brown noise and music streamed to the mask, sleep timers, and alarms that survive reboots and fall back to a speaker
- **Fitness:** log workouts by voice to my existing Django/React fitness app
- **Environment:** sense room noise, temperature and CO₂, and respond quietly (for example, by raising the noise level) instead of sending reports
- **Calm by design:** buttons at night, no screen, no speech after lights out, and no scoring of the sleeper
- **Private:** voice is processed locally, and recordings never leave the device

## What I'm learning

**C++ (the device):** the time-critical core: audio, noise generation, Bluetooth and alarms. Focus areas: RAII and smart pointers around C APIs (ALSA, BlueZ), move semantics, templates, threads and lock-free buffers, CMake, and testing with sanitizers.

**Python and LLMs (the assistant):** tool calling with small local models (Ollama) and a cloud fallback (Claude), measured against an eval set. Later: speech-to-text accuracy testing, fine-tuning a small model for on-device tool calling, and MCP.

## Architecture

Two programs that talk over a Unix socket:

- `device/` (C++): audio, Bluetooth, alarms and Pico buttons. Keeps working if the assistant crashes.
- `assistant/` (Python): the speech pipeline, LLM router and skills.

## Milestones

1. **Noise generator:** white, pink and brown noise in C++, checked with spectrum plots
2. **It plays:** noise streamed from the Pi to the mask over Bluetooth
3. **It survives the night:** reconnects, fades, speaker fallback, runs as a service
4. **It wakes me up:** alarms and Pico buttons (first complete device)
5. **It listens:** push-to-talk speech recognition and simple commands
6. **It thinks:** LLM tool calling with an eval set, the fitness skill, then a fine-tuned on-device model
7. **It notices:** room sensing and quiet adjustments

## Layout

| Folder | Contents |
|---|---|
| `assistant/` | Python: LLM router, skills, evals |
| `device/` | C++: audio, Bluetooth, alarms *(planned)* |
| `firmware/` | Raspberry Pi Pico buttons and LEDs *(planned)* |
| `docs/` | Design notes and wiring diagrams *(planned)* |

Models and audio recordings aren't committed; see `.gitignore`.
