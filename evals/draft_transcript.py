"""
Draft transcript of a match recording with whisper-1, to find the speech
worth labelling.

    python -m evals.draft_transcript evals/clips/private/recordings/<name>.flac [--dry-run]

Sends the recording in 30 s chunks to the transcriptions endpoint and writes
<name>-api.tsv next to it: start, end, detected language, no_speech
probability, average log probability and text per segment. Open it in
evals/review_server.py to listen and label.

It costs money: whisper-1 bills every second sent, about $0.36 for an hour.
--dry-run prints the cost and stops. The draft is a guide, not a label:
whisper-1 invents text over game audio and misnames the language of short
lines.
"""

import argparse
import io
import os
from pathlib import Path

import numpy as np
import soundfile as sf
import soxr
from openai import OpenAI

from config_manager import load_api_key
from evals.run import PRICE_PER_MINUTE

CHUNK_SECONDS = 30
SR = 16000


def _fmt(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:05.2f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recording", type=Path)
    ap.add_argument("--dry-run", action="store_true", help="print the cost and stop")
    args = ap.parse_args()

    minutes = sf.info(args.recording).duration / 60
    print(f"{minutes:.1f} min, about ${minutes * PRICE_PER_MINUTE['whisper-1']:.2f}")
    if args.dry_run:
        return
    api_key = os.environ.get("OPENAI_API_KEY") or load_api_key()
    if not api_key:
        raise SystemExit("No API key: set OPENAI_API_KEY or save a key in the app")
    client = OpenAI(api_key=api_key, max_retries=2, timeout=60)

    x, sr = sf.read(args.recording, dtype="float32")
    mono = soxr.resample(x.mean(axis=1) if x.ndim > 1 else x, sr, SR).astype(np.float32)
    rows, n = [], SR * CHUNK_SECONDS
    for i in range(0, len(mono), n):
        part = mono[i:i + n]
        if len(part) < SR:  # the API rejects clips under a second
            break
        buf = io.BytesIO()
        sf.write(buf, part, SR, format="WAV", subtype="PCM_16")
        buf.name = "chunk.wav"
        r = client.audio.transcriptions.create(model="whisper-1", file=buf, response_format="verbose_json")
        t0 = i / SR
        for s in r.segments or []:
            if s.text.strip():
                rows.append((t0 + s.start, t0 + s.end, r.language, s.no_speech_prob, s.avg_logprob, s.text.strip()))
        print(f"  {_fmt(t0)[:-3]}  {str(r.language):<10} {len(r.segments or [])} segments", flush=True)

    out = args.recording.with_name(args.recording.stem + "-api.tsv")
    with open(out, "w", encoding="utf-8") as f:
        f.write("start\tend\tlanguage\tno_speech\tlogprob\ttext\n")
        for a, b, lang, ns, lp, text in rows:
            f.write(f"{_fmt(a)}\t{_fmt(b)}\t{lang}\t{ns:.2f}\t{lp:.2f}\t{text}\n")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
