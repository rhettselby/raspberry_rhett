# Raspberry Pi Voice Assistant

A local, private voice assistant on a Raspberry Pi 5, built around sleep and fitness. It plays noise and music to a Bluetooth sleep mask, runs alarms, and logs workouts by voice. Speech recognition and the language model run on the device.

**Status:** early setup.

## Layout

| Folder | What it holds |
|---|---|
| `assistant/` | Python: LLM router, tool calling, skills, evals |
| `device/` | C++: audio, Bluetooth, alarms (CMake) *(planned)* |
| `firmware/` | Raspberry Pi Pico buttons and LEDs *(planned)* |
| `docs/` | Design notes and wiring diagrams *(planned)* |

Models and audio recordings are not committed; see `.gitignore`.
