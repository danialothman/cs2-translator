# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CS2 Translator is a Windows desktop app that translates foreign-language voice chat in Counter-Strike 2 into English captions. It captures audio from an input device or a WASAPI loopback device, sends fixed-length chunks to the OpenAI Whisper API (`whisper-1`), and shows the results in an always-on-top Tkinter overlay. It does not touch the game process.

## Running

```bash
pip install -r requirements.txt
python app.py        # opens the settings window
python build.py      # packages dist/CS2Translator/ with PyInstaller (needs `pip install pyinstaller`)
```

Windows only: `pyaudiowpatch` (WASAPI loopback) and the keyring Windows backend have no Linux or macOS equivalents here. Pushing a `v*` tag runs `.github/workflows/release.yml`, which builds the .exe and publishes a GitHub release.

## Architecture

- **app.py** — entry point; starts `SettingsWindow`.
- **settings_window.py** — `SettingsWindow`: main Tk window (API key, device picker, buffer duration, Skip English toggle, log panel). Owns the session lifecycle in `_start`/`_stop`.
- **audio_capture.py** — `list_audio_devices()` and `AudioCaptureThread`: reads PCM, downmixes and resamples to 16 kHz mono, and emits WAV `bytes` once per buffer duration.
- **translator.py** — `TranslatorThread`: sends each chunk to the translations endpoint. With Skip English on, it first calls the transcriptions endpoint to detect the language. Also filters known Whisper hallucinations.
- **overlay.py** — `TranslationOverlay`: draggable, semi-transparent `Toplevel` showing the last N timestamped captions.
- **config_manager.py** — settings in `%APPDATA%\CS2Translator\settings.json` (atomic write; only keys in `DEFAULTS` are loaded or saved). The API key lives in Windows Credential Manager via `keyring`, never in the JSON file.

Data flow: audio device → `AudioCaptureThread` → bounded `queue.Queue` → `TranslatorThread` → `root.after` → overlay.

## Threading Rules

- Tk runs on the main thread. Worker threads never touch widgets; they post through the `post()` helper in `_start`, which uses `root.after`.
- Each Start creates a new `threading.Event`, queue, and overlay. Never reuse or `clear()` a session's stop event: threads from a stopped session may still be finishing an API call.
- `post()` runs a callback only while `self.overlay` is still that session's overlay. This drops late results after Stop, yet still shows errors that a worker reports after it sets its own stop event (for example, an auth failure).
- The audio queue holds `AUDIO_QUEUE_SIZE` (2) chunks. When it is full, the capture thread drops the oldest chunk so latency stays bounded.
- Retries and timeouts come from the OpenAI client (`MAX_RETRIES`, `REQUEST_TIMEOUT` in `translator.py`). Do not add a manual retry loop around it.

## Constraints

- The translations endpoint takes no `language` parameter; Whisper auto-detects the source language. Do not add a source-language setting unless something consumes it.
- Keep the app free of game-process access (no injection, no memory reads). That is the basis of the README's anti-cheat claim.
- Never log or persist the API key.

## Planning Docs

- **NEXT.md** — pending work and roadmap. Remove an item when it ships; add new work there.
- **DECISION.md** — append-only decision log. Add a new `D-NNN` entry at the bottom for any design choice or trade-off. Never edit or delete earlier entries; to reverse one, add an entry that supersedes it.

## No Test Suite or Linter

There are no automated tests or lint configuration. Audio capture and the GUI need Windows to run end to end.
