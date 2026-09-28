"""
Run the eval clip set through the app's translation pipeline with a real API key.

    python -m evals.run --set smoke --dry-run
    python -m evals.run --set full --compare evals/baseline-full.json

Clips go through audio_capture.ChunkAssembler and translator.translate_chunk,
the same code the app runs. API responses are cached in evals/.cache/, so a
rerun with no pipeline change makes no API calls. See evals/README.md.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import soundfile as sf
from openai import AuthenticationError, OpenAIError
from sacrebleu.metrics import CHRF

from audio_capture import CHUNK, SAMPLE_RATE, ChunkAssembler
from config_manager import DEFAULTS, load_api_key
from translator import MODEL, make_client, translate_chunk

EVALS_DIR = Path(__file__).parent
CLIPS_DIR = EVALS_DIR / "clips"
CACHE_DIR = EVALS_DIR / ".cache"
RESULTS_DIR = EVALS_DIR / "results"
THRESHOLDS = EVALS_DIR / "thresholds.json"

# USD per minute of audio. Check https://openai.com/api/pricing before trusting it.
PRICE_PER_MINUTE = {"whisper-1": 0.006}

# Pipeline name -> Skip English setting.
PIPELINES = {"whisper1": False, "whisper1-skip-en": True}


# --- audio -----------------------------------------------------------------

def clip_chunks(path: Path, buffer_duration: float) -> list[bytes]:
    """Cut a clip into WAV chunks exactly as live capture would.

    The clip is fed in device reads of CHUNK frames. The last partial buffer
    is padded with silence, as if the speaker stopped talking.
    """
    audio, rate = sf.read(path, dtype="int16", always_2d=True)
    channels = audio.shape[1]
    assembler = ChunkAssembler(channels, rate, buffer_duration)
    chunks = []
    reads = [audio[i:i + CHUNK] for i in range(0, len(audio), CHUNK)]
    silence = np.zeros((CHUNK, channels), dtype=np.int16)
    for block in reads:
        if len(block) < CHUNK:
            block = np.concatenate([block, silence[:CHUNK - len(block)]])
        wav = assembler.feed(block.tobytes())
        if wav is not None:
            chunks.append(wav)
    while assembler.frames:
        wav = assembler.feed(silence.tobytes())
        if wav is not None:
            chunks.append(wav)
    return chunks


def wav_seconds(wav: bytes) -> float:
    return (len(wav) - 44) / 2 / SAMPLE_RATE  # 16-bit mono, 44-byte header


# --- caching client --------------------------------------------------------

def _cache_key(endpoint: str, kwargs: dict) -> str:
    name, data, mime = kwargs["file"]
    params = {k: v for k, v in sorted(kwargs.items()) if k != "file"}
    h = hashlib.sha256()
    h.update(json.dumps({"endpoint": endpoint, "params": params}, sort_keys=True).encode())
    h.update(data)
    return h.hexdigest()


class _Endpoint:
    def __init__(self, owner: "CachingClient", name: str, real):
        self.owner, self.name, self.real = owner, name, real

    def create(self, **kwargs):
        return self.owner.call(self.name, self.real, kwargs)


class CachingClient:
    """Stands in for OpenAI inside translate_chunk and caches its two calls."""

    def __init__(self, api_key: str | None, use_cache: bool):
        self.real = make_client(api_key) if api_key else None
        self.use_cache = use_cache
        self.live_calls = 0
        self.cached_calls = 0
        self.billed_seconds = 0.0
        real_audio = self.real.audio if self.real else None
        self.audio = SimpleNamespace(
            transcriptions=_Endpoint(self, "transcriptions", real_audio and real_audio.transcriptions),
            translations=_Endpoint(self, "translations", real_audio and real_audio.translations),
        )

    def is_cached(self, endpoint: str, kwargs: dict) -> bool:
        return (CACHE_DIR / f"{_cache_key(endpoint, kwargs)}.json").exists()

    def call(self, endpoint: str, real, kwargs: dict):
        path = CACHE_DIR / f"{_cache_key(endpoint, kwargs)}.json"
        if self.use_cache and path.exists():
            self.cached_calls += 1
            stored = json.loads(path.read_text(encoding="utf-8"))
        else:
            if real is None:
                raise RuntimeError("No API key and the response is not cached")
            response = real.create(**kwargs)
            self.live_calls += 1
            self.billed_seconds += wav_seconds(kwargs["file"][1])
            if isinstance(response, str):
                stored = {"kind": "text", "value": response}
            else:
                stored = {"kind": "json", "value": response.model_dump()}
            CACHE_DIR.mkdir(exist_ok=True)
            path.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
        if stored["kind"] == "text":
            return stored["value"]
        return SimpleNamespace(**stored["value"])


# --- running ---------------------------------------------------------------

def load_manifest(set_name: str) -> list[dict]:
    rows = []
    for line in (CLIPS_DIR / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if set_name == "full" or row.get("smoke"):
                rows.append(row)
    private = CLIPS_DIR / "private" / "manifest.jsonl"
    if set_name == "full" and private.exists():
        for line in private.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                row["file"] = f"private/{row['file']}"
                rows.append(row)
    return rows


def first_call_kwargs(wav: bytes, skip_english: bool) -> tuple[str, dict]:
    """The first request translate_chunk makes for a chunk, for cache lookups."""
    audio_file = ("audio.wav", wav, "audio/wav")
    if skip_english:
        return "transcriptions", {"model": MODEL, "file": audio_file, "response_format": "verbose_json"}
    return "translations", {"model": MODEL, "file": audio_file, "response_format": "text"}


def estimate_cost(client: CachingClient, clips: list[dict], pipelines: list[str]) -> tuple[int, float]:
    """Upper bound on live calls and USD. Skip English counts two calls per chunk."""
    calls, seconds = 0, 0.0
    for clip in clips:
        for wav in clip["chunks"]:
            for name in pipelines:
                skip = PIPELINES[name]
                endpoint, kwargs = first_call_kwargs(wav, skip)
                if client.use_cache and client.is_cached(endpoint, kwargs):
                    continue
                n = 2 if skip else 1
                calls += n
                seconds += n * wav_seconds(wav)
    return calls, seconds / 60 * PRICE_PER_MINUTE[MODEL]


def run_pipeline(client: CachingClient, name: str, clips: list[dict]) -> dict:
    skip = PIPELINES[name]
    per_clip = []
    latencies = []
    errors = 0
    for clip in clips:
        chunk_rows = []
        for wav in clip["chunks"]:
            live_before, cached_before = client.live_calls, client.cached_calls
            start = time.perf_counter()
            try:
                result = translate_chunk(client, wav, skip)
                row = {"text": result.text, "reason": result.reason, "language": result.language}
            except AuthenticationError:
                sys.exit("Invalid API key.")
            except OpenAIError as e:
                errors += 1
                row = {"text": None, "reason": "error", "language": None, "error": type(e).__name__}
            elapsed = time.perf_counter() - start
            # Only chunks served fully live show real latency.
            fully_live = client.live_calls > live_before and client.cached_calls == cached_before
            if fully_live and row["reason"] != "error":
                latencies.append(elapsed)
            chunk_rows.append(row)
        per_clip.append({
            "id": clip["id"],
            "category": clip["category"],
            "expect": resolve_expect(clip["expect"], skip),
            "language": clip.get("language"),
            "reference": clip.get("reference", ""),
            "chunks": chunk_rows,
            "caption": " ".join(r["text"] for r in chunk_rows if r["text"]),
        })
        print(".", end="", flush=True)
    print()
    return {"skip_english": skip, "clips": per_clip, "latencies": latencies, "errors": errors}


def resolve_expect(expect: str, skip_english: bool) -> str:
    if expect == "skip_english":
        return "suppress" if skip_english else "caption"
    return expect


# --- scoring ---------------------------------------------------------------

def _rate(hits: int, total: int) -> float | None:
    return round(hits / total, 4) if total else None


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    return round(float(np.percentile(values, q)), 3)


def score(run: dict) -> dict:
    clips = run["clips"]
    suppress = [c for c in clips if c["expect"] == "suppress"]
    caption = [c for c in clips if c["expect"] == "caption"]
    speech = [c for c in caption if c["category"] != "english"]

    summary = {
        "clips": len(clips),
        "false_caption_rate": _rate(sum(bool(c["caption"]) for c in suppress), len(suppress)),
        "false_caption_by_category": {
            cat: _rate(sum(bool(c["caption"]) for c in suppress if c["category"] == cat),
                       sum(c["category"] == cat for c in suppress))
            for cat in sorted({c["category"] for c in suppress})
        },
        "missed_caption_rate": _rate(sum(not c["caption"] for c in caption), len(caption)),
        "chrf": None,
        "language_accuracy": None,
        "latency_p50": _pct(run["latencies"], 50),
        "latency_p95": _pct(run["latencies"], 95),
        "latency_samples": len(run["latencies"]),
        "errors": run["errors"],
    }
    if speech:
        chrf = CHRF()
        summary["chrf"] = round(chrf.corpus_score(
            [c["caption"] for c in speech], [[c["reference"] for c in speech]]).score, 2)
        for c in speech:
            c["chrf"] = round(chrf.sentence_score(c["caption"], [c["reference"]]).score, 2)

    if run["skip_english"]:
        labelled = [c for c in clips if c.get("language")]
        correct = 0
        for c in labelled:
            votes = Counter(r["language"] for r in c["chunks"]
                            if r["language"] and r["reason"] != "empty")
            c["detected_language"] = votes.most_common(1)[0][0] if votes else None
            correct += c["detected_language"] == c["language"]
        summary["language_accuracy"] = _rate(correct, len(labelled))
    return summary


# --- comparing and reporting -----------------------------------------------

def compare(results: dict, baseline_path: Path) -> list[str]:
    """Return a failure message for each metric that regressed past its threshold."""
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    thresholds = json.loads(THRESHOLDS.read_text(encoding="utf-8"))
    failures = []
    for name, cur in results["pipelines"].items():
        base = baseline["pipelines"].get(name)
        if not base:
            continue
        cur, base = cur["summary"], base["summary"]
        for metric, limit in thresholds.items():
            if cur.get(metric) is None or base.get(metric) is None:
                continue
            higher_is_better = metric in ("chrf", "language_accuracy")
            delta = cur[metric] - base[metric]
            if (-delta if higher_is_better else delta) > limit:
                failures.append(f"{name}: {metric} {base[metric]} -> {cur[metric]} (limit {limit})")
    return failures


def _fmt(v) -> str:
    return "n/a" if v is None else str(v)


def report_markdown(results: dict) -> str:
    cfg = results["config"]
    lines = [
        f"# Eval run {cfg['timestamp']}",
        "",
        f"Set `{cfg['set']}`, model `{cfg['model']}`, buffer {cfg['buffer_duration']} s, "
        f"commit `{cfg['commit']}`.",
        f"Live calls {results['live_calls']}, cached calls {results['cached_calls']}, "
        f"billed audio {results['billed_seconds']:.0f} s, cost about ${results['cost_usd']:.3f}.",
        "",
        "| Metric | " + " | ".join(results["pipelines"]) + " |",
        "|---|" + "---|" * len(results["pipelines"]),
    ]
    metrics = ["false_caption_rate", "missed_caption_rate", "chrf", "language_accuracy",
               "latency_p50", "latency_p95", "errors"]
    for m in metrics:
        row = [_fmt(p["summary"][m]) for p in results["pipelines"].values()]
        lines.append(f"| {m} | " + " | ".join(row) + " |")
    lines.append("")
    for name, p in results["pipelines"].items():
        bad = [c for c in p["clips"]
               if (c["expect"] == "suppress") == bool(c["caption"])]
        if bad:
            lines += [f"## {name}: wrong outcomes", ""]
            for c in bad:
                what = f"captioned: {c['caption']!r}" if c["caption"] else "missed"
                lines.append(f"- `{c['id']}` ({c['expect']}) {what}")
            lines.append("")
    return "\n".join(lines)


def git_commit() -> str:
    try:
        sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
        dirty = subprocess.run(["git", "diff", "--quiet", "HEAD"]).returncode != 0
        return sha + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", choices=["smoke", "full"], default="smoke")
    ap.add_argument("--pipeline", default=",".join(PIPELINES),
                    help="comma-separated: " + ", ".join(PIPELINES))
    ap.add_argument("--buffer", type=float, default=DEFAULTS["buffer_duration"],
                    help="chunk length in seconds (the app's Buffer Duration)")
    ap.add_argument("--max-cost", type=float, default=0.25, help="abort if the estimate exceeds this, in USD")
    ap.add_argument("--dry-run", action="store_true", help="print the cost estimate and exit")
    ap.add_argument("--no-cache", action="store_true", help="call the API for every chunk")
    ap.add_argument("--compare", type=Path, help="baseline JSON; exit 1 on regression")
    ap.add_argument("--save-baseline", action="store_true",
                    help="also write evals/baseline-<set>.json")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    pipelines = [p.strip() for p in args.pipeline.split(",") if p.strip()]
    unknown = [p for p in pipelines if p not in PIPELINES]
    if unknown:
        ap.error(f"unknown pipeline(s): {', '.join(unknown)}")

    clips = load_manifest(args.set)
    for clip in clips:
        clip["chunks"] = clip_chunks(CLIPS_DIR / clip["file"], args.buffer)
    n_chunks = sum(len(c["chunks"]) for c in clips)

    api_key = os.environ.get("OPENAI_API_KEY") or load_api_key()
    client = CachingClient(api_key or None, use_cache=not args.no_cache)
    calls, cost = estimate_cost(client, clips, pipelines)
    print(f"{len(clips)} clips, {n_chunks} chunks, pipelines: {', '.join(pipelines)}")
    print(f"Estimate: up to {calls} live API calls, about ${cost:.3f}")
    if args.dry_run:
        return
    if cost > args.max_cost:
        sys.exit(f"Estimate ${cost:.3f} exceeds --max-cost ${args.max_cost:.2f}")
    if calls and not api_key:
        sys.exit("No API key: set OPENAI_API_KEY or save a key in the app")

    started = datetime.now()
    results = {"config": {
        "timestamp": started.isoformat(timespec="seconds"),
        "set": args.set,
        "model": MODEL,
        "buffer_duration": args.buffer,
        "commit": git_commit(),
        "cache": not args.no_cache,
    }, "pipelines": {}}
    for name in pipelines:
        print(f"Running {name} ", end="", flush=True)
        run = run_pipeline(client, name, clips)
        summary = score(run)
        results["pipelines"][name] = {"summary": summary, "clips": run["clips"]}

    results["live_calls"] = client.live_calls
    results["cached_calls"] = client.cached_calls
    results["billed_seconds"] = round(client.billed_seconds, 1)
    results["cost_usd"] = round(client.billed_seconds / 60 * PRICE_PER_MINUTE[MODEL], 4)

    RESULTS_DIR.mkdir(exist_ok=True)
    stem = f"{started:%Y%m%d-%H%M%S}-{args.set}"
    json_text = json.dumps(results, ensure_ascii=False, indent=2)
    (RESULTS_DIR / f"{stem}.json").write_text(json_text, encoding="utf-8")
    md = report_markdown(results)
    (RESULTS_DIR / f"{stem}.md").write_text(md, encoding="utf-8")
    if args.save_baseline:
        (EVALS_DIR / f"baseline-{args.set}.json").write_text(json_text, encoding="utf-8")
        (EVALS_DIR / f"baseline-{args.set}.md").write_text(md, encoding="utf-8")
    print()
    print(md)
    print(f"Saved {RESULTS_DIR / stem}.json")

    if args.compare:
        failures = compare(results, args.compare)
        if failures:
            print("\nREGRESSIONS:")
            for f in failures:
                print(f"- {f}")
            sys.exit(1)
        print(f"\nNo regressions against {args.compare}")


if __name__ == "__main__":
    main()
