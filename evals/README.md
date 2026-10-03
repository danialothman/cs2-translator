# Evals

Runs a fixed clip set through the app's own pipeline with a real OpenAI API key and scores the output. Use it to get a before and after number for any change to capture, chunking, filtering or the model.

```bash
pip install -r requirements.txt -r evals/requirements.txt
python -m evals.run --set smoke --dry-run                         # cost estimate only
python -m evals.run --set smoke                                   # 12 clips, about $0.02
python -m evals.run --set full --compare evals/baseline-full.json # 52 clips, about $0.10 uncached
```

The key comes from `OPENAI_API_KEY`, or from the key saved in the app (Windows Credential Manager). It is never printed or written to disk.

## What it tests

Each clip is 48 kHz stereo FLAC, the format a WASAPI loopback device delivers. `run.py` feeds it in reads of 1024 frames to `audio_capture.ChunkAssembler` and sends each chunk to `translator.translate_chunk`. The app runs both, so the eval covers resampling, chunk boundaries, the hallucination filter and Skip English. It does not cover the device, threads or overlay.

Pipelines:

| Name | Skip English |
|---|---|
| `whisper1` | off: one translation call per chunk |
| `whisper1-skip-en` | on: a transcription call, then a translation call unless the chunk is dropped |

## Clip set

`clips/manifest.jsonl` has one row per clip:

| Field | Meaning |
|---|---|
| `id`, `file` | Clip name and FLAC file in `clips/` |
| `category` | `speech`, `english`, `nonspeech` or `callout` |
| `language` | The language name whisper-1 reports, or null |
| `reference` | English reference translation |
| `expect` | `caption`, `suppress`, or `skip_english` (suppress with Skip English on, caption with it off) |
| `smoke` | In the `smoke` set |
| `source` | `fleurs`, `synthetic` or `recorded` |
| `note` | Optional. Where the reference came from when nobody checked it by ear |

- **speech** (32): 4 FLEURS test utterances each in Russian, Portuguese, Polish, Spanish, Turkish, German, Ukrainian and Chinese. FLEURS sentences are parallel across languages, so the English reference is the same sentence from the English split.
- **english** (10): FLEURS English utterances.
- **nonspeech** (10): synthetic silence, white, pink and burst noise, hum, a tone and clicks. They stand in for recorded CS2 game audio until that is added.

`python -m evals.build_clips` rebuilds the `fleurs` and `synthetic` rows and keeps every other row. FLEURS audio is 16 kHz, so it has no content above 8 kHz. It exercises the 48 kHz to 16 kHz path but cannot show all of its aliasing.

FLEURS is by Google, licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/): Conneau et al., "FLEURS: Few-shot Learning Evaluation of Universal Representations of Speech", 2022. The clips here are resampled to 48 kHz stereo.

### Private clips

Recordings from real matches contain other players' voices. Put them in `clips/private/` with their own `manifest.jsonl` (same fields, `file` relative to that folder). The folder is gitignored and only the `full` set loads it. Never commit these clips.

### Voice from CS2 demos

A CS2 demo stores team voice chat as Opus packets when the server records voice. Some FACEIT servers do; Valve matchmaking demos have none. `demo_voice.py` extracts it per player, so you can cut real voice-chat clips without recording a match yourself:

```bash
pip install -r evals/requirements-demo.txt
python -m evals.demo_voice evals/clips/private/demos/<match>.dem.zst --lang
```

It writes each player's voice on the match timeline, a mix of all players, `segments.tsv` (one row per burst of speech) and `listen-longest.wav` (the longest bursts back to back) to `clips/private/demos/<match>/`. A `.dem.zst` is unpacked to a temporary file that is deleted afterwards.

`--lang` runs Whisper language detection on each player's longest bursts, offline on the CPU. Use it to find players worth cutting clips from, then listen: short, noisy callouts fool it, and it can name a language from a hallucinated transcript.

Demo voice has no game audio under it. It tests the codec and real speech, not noise robustness.

### Recording a match

`record_loopback.py` records what the PC plays through WASAPI loopback, the same capture the app uses, to 48 kHz stereo FLAC in `clips/private/recordings/`:

```bash
pythonw -m evals.record_loopback                    # window with Start / Stop
python -m evals.record_loopback --cli --minutes 60  # terminal
```

It records every app's sound, so pause browsers and chat apps first. Your microphone is not included. Loopback delivers nothing while nothing plays, so silent stretches are dropped and timestamps run ahead of the match clock.

Much of the English in a match is the game's own radio voice ("Roger that", "Need help"), not players. Label both: Skip English must drop either.

### Finding and labelling the speech

Player voice sits under game audio, so an offline voice detector finds little of it. A whisper-1 draft finds far more, then you listen and label:

```bash
python -m evals.draft_transcript evals/clips/private/recordings/<name>.flac --dry-run  # cost
python -m evals.draft_transcript evals/clips/private/recordings/<name>.flac            # about $0.36 per hour
python -m evals.review_server                                                         # http://127.0.0.1:5005
```

The draft (`<name>-api.tsv`) has one row per line whisper-1 heard, with its time and detected language. The review page plays each row's snippet and saves your labels to `<name>-review.json` as you type: player, radio, junk or unsure, plus the language, the words and their English meaning. **Boost quiet clips** normalizes each snippet, and **Add segment** covers speech the draft missed.

Treat the draft as a pointer, not a label. whisper-1 invents text over game audio (a whole run of "five… of… death"), and names the wrong language for short lines: real Chinese came back as Spanish, Swedish and Portuguese. When nobody can check a language by ear, note in the manifest row that the reference comes from the draft.

## Metrics

- **false_caption_rate**: share of `suppress` clips that produced any caption (hallucinations, English that leaked through).
- **missed_caption_rate**: share of `caption` clips that produced no caption at all.
- **chrf**: corpus chrF of each speech clip's joined captions against its reference. It is character-based, so it works for any language pair and needs no judge model. A caption dropped mid-clip lowers it.
- **language_accuracy**: Skip English only. Majority language over a clip's chunks against the expected language.
- **latency_p50 / p95**: seconds per chunk for chunks served fully live, run one at a time.

Each run writes `results/<timestamp>-<set>.json` (per chunk text, reason and language) and a `.md` summary. `results/` is gitignored.

## Cost control

- Responses are cached in `.cache/`, keyed by SHA-256 of the WAV bytes, endpoint and request params. A rerun with no pipeline change makes no calls. Identical chunks (the silence padding, the translation call shared by both pipelines) are paid once. `--no-cache` forces live calls.
- The estimate is printed before the first call. The run aborts if it exceeds `--max-cost` (default $0.25). It counts two calls for every Skip English chunk, so it is an upper bound.
- `PRICE_PER_MINUTE` in `run.py` is the whisper-1 list price at the time of writing. Check current pricing.

## Baseline and regressions

`evals/baseline-full.json` is the committed reference. `--compare <file>` exits 1 when a metric moves the wrong way by more than its limit in `thresholds.json`. The limits sit above the spread of 3 uncached runs of the same code, so a failure is unlikely to be noise. After an intended change, rerun with `--save-baseline` and commit the new baseline with the change.

## CI

`.github/workflows/eval.yml` runs the eval by hand from the Actions tab (**Eval**, then **Run workflow**). It needs an `OPENAI_API_KEY` repository secret. It never runs on pull requests: fork PRs cannot read secrets, and each run spends money.

- The `full` set is compared against `baseline-full.json` and the job fails on a regression. The `smoke` set only reports, because its thresholds are not calibrated: one clip changes a rate by 0.1 or more.
- The response cache is kept between runs with `actions/cache`, so a rerun with no pipeline change is free. Tick **no_cache** to measure run-to-run noise.
- The summary appears on the run page, and the full JSON is uploaded as the `eval-results` artifact.
- Latency is measured from GitHub's runner, not a player's PC. Compare it only with other CI runs.
