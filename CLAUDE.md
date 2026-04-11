# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CS2 Translator is a real-time Mandarin-to-English speech translator for Counter-Strike 2. It captures game audio via VB-Audio Virtual Cable, transcribes/translates using faster-whisper (OpenAI Whisper), and displays English captions in a draggable Tkinter overlay.

## Running

```bash
# Install dependencies
pip install -r requirements.txt

# Verify GPU/CUDA setup
python test_gpu.py

# Run the translator
python main.py
```

Requires VB-Audio Virtual Cable installed at OS level. First run downloads the Whisper model (~1.5GB).

## Architecture

Three-file application with a linear audio pipeline:

- **config.py** — All tunable parameters (model size, buffer duration, overlay style, VAD settings). Single source of truth; no other file defines constants.
- **main.py** — `AudioTranscriber` class: initializes the Whisper model (GPU with float16, CPU fallback), captures audio from the "CABLE Output" device via PyAudio, buffers chunks, runs Whisper with `task="translate"` and `language="zh"`, and feeds results to the overlay.
- **overlay.py** — `TranslationOverlay` class: always-on-top Tkinter window showing the last N timestamped captions. Draggable, semi-transparent, green-on-black styling.

Data flow: VB-Audio Virtual Cable → PyAudio capture → audio buffer (numpy) → faster-whisper translate → overlay caption deque → Tkinter display.

## Key Technical Details

- Whisper runs with VAD (Voice Activity Detection) filtering enabled and beam search (size 5) by default.
- Audio is sampled at 16kHz (Whisper's expected rate), buffered in configurable-length chunks (default 3s).
- The overlay runs on the main thread (Tkinter requirement); audio processing runs in a separate daemon thread.
- GPU detection uses PyTorch (`torch.cuda.is_available()`); compute type is float16 on GPU, int8 on CPU.

## No Test Suite or Linter

There are no automated tests or linting configuration. `test_gpu.py` is a manual diagnostic, not part of a test framework.
