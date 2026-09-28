"""
Build the committed eval clip set in evals/clips/.

Downloads a few FLEURS test utterances per language (CC BY 4.0) and writes
synthetic non-speech clips. Every clip is stored as 48 kHz stereo 16-bit FLAC,
the format a WASAPI loopback device delivers, so evals/run.py can push it
through the app's own conversion code.

    python -m evals.build_clips

The output is deterministic for a given FLEURS revision. Clips you record
yourself (callouts, game audio) are added to manifest.jsonl by hand and are
not touched by this script, except that it rewrites the rows it owns.
"""

import csv
import io
import json
import sys
import tarfile
import urllib.request
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

CLIPS_DIR = Path(__file__).parent / "clips"
MANIFEST = CLIPS_DIR / "manifest.jsonl"

FLEURS_URL = "https://huggingface.co/datasets/google/fleurs/resolve/main/data/{code}/{name}"
FLEURS_RATE = 16000
OUT_RATE = 48000
MIN_SECONDS = 3.0
MAX_SECONDS = 12.0

# FLEURS config -> the language name whisper-1 reports in verbose_json.
SPEECH_LANGUAGES = {
    "ru_ru": "russian",
    "pt_br": "portuguese",
    "pl_pl": "polish",
    "es_419": "spanish",
    "tr_tr": "turkish",
    "de_de": "german",
    "uk_ua": "ukrainian",
    "cmn_hans_cn": "chinese",
}
CLIPS_PER_LANGUAGE = 4
ENGLISH_CLIPS = 10
# The first clip of each language, 2 English and 2 non-speech clips form "smoke".
SMOKE_ENGLISH = 2
SMOKE_NONSPEECH = {"nonspeech-silence-3s", "nonspeech-pink-quiet"}

# Manifest rows with these sources are regenerated; all others are kept.
OWNED_SOURCES = {"fleurs", "synthetic"}


def _fetch(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "cs2-translator-evals"})
    return urllib.request.urlopen(req, timeout=60)


def _read_tsv(code: str) -> list[list[str]]:
    with _fetch(FLEURS_URL.format(code=code, name="test.tsv")) as resp:
        text = resp.read().decode("utf-8")
    return list(csv.reader(io.StringIO(text), delimiter="\t", quoting=csv.QUOTE_NONE))


def _stream_wavs(code: str, wanted: dict[str, str], count: int) -> dict[str, np.ndarray]:
    """Read the test tarball as a stream and stop after `count` distinct ids.

    wanted maps file name -> sentence id. Only the start of the tarball is
    downloaded, so this costs a few MB instead of the full ~400 MB archive.
    """
    found: dict[str, np.ndarray] = {}
    url = FLEURS_URL.format(code=code, name="audio/test.tar.gz")
    with _fetch(url) as resp, tarfile.open(fileobj=resp, mode="r|gz") as tar:
        for member in tar:
            name = Path(member.name).name
            sid = wanted.get(name)
            if sid is None or sid in found:
                continue
            data, rate = sf.read(io.BytesIO(tar.extractfile(member).read()), dtype="float32")
            assert rate == FLEURS_RATE, (name, rate)
            found[sid] = data
            if len(found) >= count:
                break
    if len(found) < count:
        sys.exit(f"{code}: only found {len(found)} of {count} clips")
    return found


def _to_loopback(mono16k: np.ndarray) -> np.ndarray:
    """Upsample to 48 kHz with a proper filter and duplicate to stereo."""
    up = resample_poly(mono16k, OUT_RATE // FLEURS_RATE, 1)
    up = np.clip(up, -1.0, 1.0)
    return np.stack([up, up], axis=1)


def _write(clip_id: str, audio: np.ndarray) -> str:
    rel = f"{clip_id}.flac"
    sf.write(CLIPS_DIR / rel, audio, OUT_RATE, subtype="PCM_16")
    return rel


def _candidates(rows: list[list[str]], allowed_ids: set[str]) -> dict[str, str]:
    """File name -> sentence id for rows within the duration limits."""
    out = {}
    for row in rows:
        sid, fname, samples = row[0], row[1], int(row[5])
        if sid in allowed_ids and MIN_SECONDS <= samples / FLEURS_RATE <= MAX_SECONDS:
            out[fname] = sid
    return out


def build_fleurs() -> list[dict]:
    en_rows = _read_tsv("en_us")
    en_ref: dict[str, str] = {}
    for row in en_rows:
        en_ref.setdefault(row[0], row[2])

    entries = []
    for code, lang in SPEECH_LANGUAGES.items():
        print(f"FLEURS {code} ...", flush=True)
        rows = _read_tsv(code)
        audio = _stream_wavs(code, _candidates(rows, set(en_ref)), CLIPS_PER_LANGUAGE)
        for i, sid in enumerate(sorted(audio, key=int)):
            clip_id = f"speech-{code}-{sid}"
            entries.append({
                "id": clip_id,
                "file": _write(clip_id, _to_loopback(audio[sid])),
                "category": "speech",
                "language": lang,
                "reference": en_ref[sid],
                "expect": "caption",
                "smoke": i == 0,
                "source": "fleurs",
            })

    print("FLEURS en_us ...", flush=True)
    audio = _stream_wavs("en_us", _candidates(en_rows, set(en_ref)), ENGLISH_CLIPS)
    for i, sid in enumerate(sorted(audio, key=int)):
        clip_id = f"english-{sid}"
        entries.append({
            "id": clip_id,
            "file": _write(clip_id, _to_loopback(audio[sid])),
            "category": "english",
            "language": "english",
            "reference": en_ref[sid],
            "expect": "skip_english",
            "smoke": i < SMOKE_ENGLISH,
            "source": "fleurs",
        })
    return entries


def _pink(rng: np.random.Generator, n: int) -> np.ndarray:
    spectrum = np.fft.rfft(rng.standard_normal(n))
    freqs = np.fft.rfftfreq(n)
    freqs[0] = freqs[1]
    x = np.fft.irfft(spectrum / np.sqrt(freqs), n)
    return x / np.max(np.abs(x))


def _db(level_db: float) -> float:
    return 10 ** (level_db / 20)


def build_synthetic() -> list[dict]:
    """Non-speech clips that must never produce a caption.

    These are stand-ins until recorded CS2 game audio is added.
    """
    rng = np.random.default_rng(1234)
    sec = lambda s: int(OUT_RATE * s)  # noqa: E731
    t6 = np.arange(sec(6)) / OUT_RATE

    clicks = np.zeros(sec(6))
    for pos in rng.integers(0, sec(6) - 400, 40):
        clicks[pos:pos + 400] += rng.standard_normal(400) * np.exp(-np.arange(400) / 60)
    clicks = clicks / np.max(np.abs(clicks)) * _db(-20)

    bursts = _pink(rng, sec(6)) * _db(-10)
    envelope = np.zeros(sec(6))
    for pos in rng.integers(0, sec(6) - sec(0.15), 12):
        envelope[pos:pos + sec(0.15)] = np.exp(-np.arange(sec(0.15)) / sec(0.03))
    bursts *= envelope

    signals = {
        "nonspeech-silence-3s": np.zeros(sec(3)),
        "nonspeech-silence-6s": np.zeros(sec(6)),
        "nonspeech-white-quiet": rng.standard_normal(sec(6)) * _db(-60),
        "nonspeech-white-loud": rng.standard_normal(sec(6)) * _db(-30),
        "nonspeech-pink-quiet": _pink(rng, sec(6)) * _db(-45),
        "nonspeech-pink-loud": _pink(rng, sec(6)) * _db(-20),
        "nonspeech-hum-50hz": sum(np.sin(2 * np.pi * 50 * k * t6) / k for k in range(1, 6)) * _db(-30),
        "nonspeech-tone-1khz": np.sin(2 * np.pi * 1000 * t6) * _db(-25),
        "nonspeech-clicks": clicks,
        "nonspeech-bursts": bursts,
    }
    entries = []
    for clip_id, mono in signals.items():
        audio = np.stack([mono, mono], axis=1).clip(-1.0, 1.0)
        entries.append({
            "id": clip_id,
            "file": _write(clip_id, audio),
            "category": "nonspeech",
            "language": None,
            "reference": "",
            "expect": "suppress",
            "smoke": clip_id in SMOKE_NONSPEECH,
            "source": "synthetic",
        })
    return entries


def main():
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    kept = []
    if MANIFEST.exists():
        for line in MANIFEST.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("source") not in OWNED_SOURCES:
                    kept.append(row)
    for old in CLIPS_DIR.glob("*.flac"):
        if not any(row["file"] == old.name for row in kept):
            old.unlink()

    entries = build_fleurs() + build_synthetic() + kept
    with MANIFEST.open("w", encoding="utf-8", newline="\n") as f:
        for row in entries:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Wrote {len(entries)} clips to {MANIFEST}")


if __name__ == "__main__":
    main()
