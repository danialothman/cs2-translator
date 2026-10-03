# Contributing

Thanks for helping. This page covers how the code fits together and the rules a change must keep.

## Setup

Windows only: `pyaudiowpatch` (WASAPI loopback) and the keyring Windows backend have no Linux or macOS equivalents here.

```bash
pip install -r requirements.txt
python app.py        # opens the settings window
python build.py      # packages dist/CS2Translator/ with PyInstaller (needs `pip install pyinstaller`)
```

## Architecture

CS2 Translator captures audio from an input device or a WASAPI loopback device, sends fixed-length chunks to the OpenAI Whisper API (`whisper-1`), and shows English captions in an always-on-top Tkinter overlay. It does not touch the game process.

- **app.py** — entry point; starts `SettingsWindow`.
- **settings_window.py** — `SettingsWindow`: main Tk window (API key, device picker, buffer duration, Skip English toggle, log panel). Owns the session lifecycle in `_start`/`_stop`.
- **audio_capture.py** — `list_audio_devices()`, `ChunkAssembler` (downmixes and resamples each read to 16 kHz mono and emits WAV `bytes` once per buffer duration) and `AudioCaptureThread`, which feeds device reads to it.
- **translator.py** — `translate_chunk()` sends one chunk to the translations endpoint and decides whether to show it. With Skip English on, it first calls the transcriptions endpoint to detect the language. It also filters known Whisper hallucinations. `TranslatorThread` pulls chunks from the queue and calls it.
- **overlay.py** — `TranslationOverlay`: draggable, semi-transparent `Toplevel` showing the last N timestamped captions.
- **config_manager.py** — settings in `%APPDATA%\CS2Translator\settings.json` (atomic write; only keys in `DEFAULTS` are loaded or saved). The API key lives in Windows Credential Manager via `keyring`, never in the JSON file.
- **version.py** — `__version__`, bumped by release-please and shown in the window title.
- **evals/** — live evaluation against the real API. See [evals/README.md](evals/README.md).

Data flow: audio device → `AudioCaptureThread` → bounded `queue.Queue` → `TranslatorThread` → `root.after` → overlay.

## Threading rules

- Tk runs on the main thread. Worker threads never touch widgets; they post through the `post()` helper in `_start`, which uses `root.after`.
- Each Start creates a new `threading.Event`, queue and overlay. Never reuse or `clear()` a session's stop event: threads from a stopped session may still be finishing an API call.
- `post()` runs a callback only while `self.overlay` is still that session's overlay. This drops late results after Stop, yet still shows errors that a worker reports after it sets its own stop event (for example, an auth failure).
- The audio queue holds `AUDIO_QUEUE_SIZE` (2) chunks. When it is full, the capture thread drops the oldest chunk so latency stays bounded.
- Retries and timeouts come from the OpenAI client (`MAX_RETRIES`, `REQUEST_TIMEOUT` in `translator.py`). Do not add a manual retry loop around it.

## Constraints

- The translations endpoint takes no `language` parameter; Whisper detects the source language. Do not add a source-language setting unless something consumes it.
- Keep the app free of game-process access (no injection, no memory reads). The README's anti-cheat statement depends on it.
- Never log or persist the API key.

## Evals

There are no unit tests or lint configuration yet. Audio capture and the GUI need Windows to run end to end.

`evals/` measures translation quality with a real API key. Keep per-chunk decisions in `translate_chunk` and chunking in `ChunkAssembler`, so the evals keep covering the code that ships. Run this before and after any change to capture, chunking, filtering or the model:

```bash
pip install -r evals/requirements.txt
python -m evals.run --set full --dry-run                           # cost estimate
python -m evals.run --set full --compare evals/baseline-full.json  # live run
```

A live run costs money. Start with `--dry-run`. Responses are cached, so a rerun with no pipeline change is free.

## Commits and versions

- The project follows [Semantic Versioning](https://semver.org/). The version lives only in `version.py` and `.release-please-manifest.json`; release-please bumps both. Do not edit them or released `CHANGELOG.md` entries by hand.
- Every commit on `main` must follow [Conventional Commits](https://www.conventionalcommits.org/), because release-please reads them to pick the version and write the changelog. `feat:` bumps minor, `fix:` and `perf:` bump patch, and `feat!:` or a `BREAKING CHANGE:` footer bumps major. `docs:`, `refactor:`, `test:`, `ci:`, `build:` and `chore:` do not appear in the changelog.
- Pull requests are merged with a merge commit, so the commit messages decide the changelog. Write the PR title in plain English, not as a conventional commit ("Extract voice chat from CS2 demos", not "feat(evals): ..."): the merge commit's body is the PR title, and release-please would count a conventional title as a second commit and list the change twice.
- Releases: each push to `main` updates a release PR. Merging it tags the version, creates the GitHub release and attaches the Windows build.

## GitHub Actions

The repo is public, so workflows must not let a fork run code with the repo's token or secrets.

- Pin every action to a full commit SHA, with the version in a comment. The repo only allows GitHub-owned actions and `googleapis/release-please-action`; a new third-party action needs a maintainer to allow it.
- Start each workflow with `permissions: {}` and grant permissions per job.
- Set `persist-credentials: false` on `actions/checkout`.
- Pass `workflow_dispatch` inputs to scripts through `env`, never inline with `${{ }}`.
- Never use `pull_request_target`.
