# NEXT

Pending work, in priority order. Edit this file freely: remove an item when it ships, and record the reason for any choice in [DECISION.md](DECISION.md).

## Now

- [ ] **Test Phase 0 on Windows.** Nobody has run the merged fixes on Windows yet. Run the app in CS2 and check:
  - [ ] WASAPI loopback capture produces captions.
  - [ ] Stop, then Start, 10 times. Captions do not repeat, and the log shows no errors.
  - [ ] Stop while speech is in flight. The app does not raise and shows no caption after Stop.
  - [ ] Settings save to `%APPDATA%\CS2Translator\settings.json`, and the file contains no API key.
  - [ ] An invalid API key shows "Invalid API key" in the status line.
  - [ ] The PyInstaller build from `python build.py` starts and saves settings.
- [ ] **Tag a release** only after the Windows test passes.
- [ ] **Add a LICENSE file.** The README says MIT, but the repo has no LICENSE file, so the code is not yet licensed. The copyright holder must choose the name and year.

## Evals

The harness is in [evals/](evals/README.md). Run it before and after every Phase 1 and 2 change.

- [ ] **Record CS2 audio.** Record game audio with no voices (gunfire, footsteps, utility) and 10 callouts ("rush B", "AWP mid") with references. Add the game audio as `nonspeech` clips, and mix it under half the FLEURS speech at 0–10 dB SNR in `build_clips.py`.
- [ ] **Add a manual CI job.** A `workflow_dispatch` job runs `python -m evals.run --set smoke` with an `OPENAI_API_KEY` repo secret.
- [ ] **Fix: punctuation-only captions.** With Skip English off, quiet white and pink noise produce captions like `". . ."` in every run (false caption rate 0.2 in the baseline). `_is_hallucination` strips only trailing punctuation. Update the baseline with the fix.
- [ ] **Investigate: Skip English drops foreign speech.** In the full baseline, 2 of 111 foreign speech chunks were detected as English and dropped, and one Ukrainian clip was detected as Russian. Silence-based cutting (Phase 1) may help. Track it with chrF and `language_accuracy`.

## Phase 1: Cost and latency

The app sends every chunk to the API, including silence. This is the rate-limiting step for cost.

- [ ] Add a voice activity detection (VAD) gate before upload (Silero VAD or `webrtcvad`). Target: send 70–90% fewer chunks (estimate, not measured).
- [ ] Cut chunks at silence, not at fixed 3 s boundaries. Keep about 0.2 s of overlap.
- [ ] Pass a `prompt` with CS2 vocabulary ("A site, B long, eco, rush B, AWP, rotate").
- [ ] Log API calls per minute and the time from speech to caption. Target: under 2.5 s p50.

## Phase 2: Accuracy

- [ ] Replace the index-picking resampler in `audio_capture._resample_mono` with a filtered one (`scipy.signal.resample_poly`). The current one aliases 48 kHz loopback audio.
- [ ] Filter hallucinations with `no_speech_prob` and `avg_logprob` from `verbose_json` segments, not only a phrase list.
- [ ] Compare `gpt-4o-mini-transcribe` plus LLM translation against `whisper-1` as a new eval pipeline. Check current OpenAI pricing and model docs first.
- [ ] Add about 50 private match clips to the eval set and score both pipelines by hand before switching models.

## Phase 3: UX

- [ ] Save the overlay position between sessions.
- [ ] Add a click-through mode and a hotkey to hide the overlay.
- [ ] Expose the overlay settings in the GUI (font, colours, alpha, caption count). They exist in `config_manager.DEFAULTS` but the GUI does not show them.

## Phase 4: Optional

- [ ] Add a local faster-whisper backend for offline use without API cost. Build it only if users ask; it brings back the GPU requirement.
- [ ] Add speaker labels.

## Hygiene

- [ ] Add a CI job on pull requests: lint, plus `python -c "import app"` on `windows-latest`.
- [ ] Add a small pytest suite. The Phase 0 checks (queue drop, retry, settings allowlist, session isolation under Xvfb) are a starting point.
- [ ] Fix the E501 long line in `settings_window.py` (the cost hint label).
- [ ] `Tk.after()` is called from worker threads. It works with threaded Tcl, but a `queue` polled by the Tk thread would be strictly safe.
