# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CS2 Translator is a Windows desktop app that translates foreign-language voice chat in Counter-Strike 2 into English captions. It captures audio from an input device or a WASAPI loopback device, sends fixed-length chunks to the OpenAI Whisper API (`whisper-1`), and shows the results in an always-on-top Tkinter overlay. It does not touch the game process.

## Running

```bash
pip install -r requirements.txt
python app.py        # opens the settings window
python build.py      # packages dist/CS2Translator/ with PyInstaller (needs `pip install pyinstaller`)
python -m evals.run --set smoke   # live eval with a real API key; see evals/README.md
```

Windows only: `pyaudiowpatch` (WASAPI loopback) and the keyring Windows backend have no Linux or macOS equivalents here. Releases are automated by release-please in `.github/workflows/release.yml`: each push to `main` updates a release PR that bumps `version.py` and `CHANGELOG.md`. Merging that PR tags the version, creates the GitHub release and attaches the .exe. `.github/workflows/eval.yml` runs the live eval by hand (needs the `OPENAI_API_KEY` secret).

## Architecture

- **app.py** — entry point; starts `SettingsWindow`.
- **settings_window.py** — `SettingsWindow`: main Tk window (API key, device picker, buffer duration, Skip English toggle, log panel). Owns the session lifecycle in `_start`/`_stop`.
- **audio_capture.py** — `list_audio_devices()`, `ChunkAssembler` (downmixes and resamples each read to 16 kHz mono and emits WAV `bytes` once per buffer duration) and `AudioCaptureThread`, which feeds device reads to it.
- **translator.py** — `translate_chunk()` sends one chunk to the translations endpoint and decides whether to show it. With Skip English on, it first calls the transcriptions endpoint to detect the language. It also filters known Whisper hallucinations. `TranslatorThread` pulls chunks from the queue and calls it.
- **overlay.py** — `TranslationOverlay`: draggable, semi-transparent `Toplevel` showing the last N timestamped captions.
- **evals/** — `run.py` feeds `clips/` through `ChunkAssembler` and `translate_chunk` against the real API, caches responses and scores them. `build_clips.py` rebuilds the FLEURS and synthetic clips.
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
- The repo is public (D-017). In workflows: pin every action to a full commit SHA with the version in a comment, start with `permissions: {}` and grant per job, set `persist-credentials: false` on checkout, pass inputs through `env`, and never use `pull_request_target`. A new third-party action must also be added to the repo's allowed-actions list.

## Versioning and Commits

- The project follows Semantic Versioning. The version lives only in `version.py` (and `.release-please-manifest.json`); release-please bumps both. Never edit them or released `CHANGELOG.md` entries by hand.
- Every commit that lands on `main` must use Conventional Commits, since release-please reads them to pick the version and write the changelog. `feat:` bumps minor, `fix:` and `perf:` bump patch, and `feat!:` or a `BREAKING CHANGE:` footer bumps major. `docs:`, `refactor:`, `test:`, `ci:`, `build:` and `chore:` do not appear in the changelog.
- PRs are merged with a merge commit (D-008), so the individual commit messages are what count, not the PR title.

## Planning Docs

- **NEXT.md** — pending work and roadmap. Remove an item when it ships; add new work there.
- **DECISION.md** — append-only decision log. Add a new `D-NNN` entry at the bottom for any design choice or trade-off. Never edit or delete earlier entries; to reverse one, add an entry that supersedes it.

## Evals, No Test Suite or Linter

There are no unit tests or lint configuration. Audio capture and the GUI need Windows to run end to end.

`evals/` measures translation quality with a real API key (see `evals/README.md`). Keep per-chunk decisions in `translate_chunk` and chunking in `ChunkAssembler` so the evals keep covering the code that ships. Run `python -m evals.run --set full --compare evals/baseline-full.json` before and after changes to capture, chunking, filtering or the model. A live run costs money: start with `--dry-run`, and ask before running uncached.
