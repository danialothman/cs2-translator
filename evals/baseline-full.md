# Eval run 2026-09-28T23:14:25

Set `full`, model `whisper-1`, buffer 3.0 s, commit `044127b-dirty`.
Live calls 0, cached calls 444, billed audio 0 s, cost about $0.000.

| Metric | whisper1 | whisper1-skip-en |
|---|---|---|
| false_caption_rate | 0.2 | 0.0 |
| missed_caption_rate | 0.0 | 0.0 |
| chrf | 39.9 | 39.73 |
| language_accuracy | n/a | 0.9762 |
| latency_p50 | n/a | n/a |
| latency_p95 | n/a | n/a |
| errors | 0 | 0 |

## whisper1: wrong outcomes

- `nonspeech-white-quiet` (suppress) captioned: '. . .'
- `nonspeech-pink-quiet` (suppress) captioned: '. .'
