"""
Extract team voice chat from a CS2 demo (.dem or .dem.zst) for building
private eval clips.

    python -m evals.demo_voice path/to/match.dem.zst [--lang] [--listen 15]

Writes to evals/clips/private/demos/<demo name>/:

- player-<name>.flac   each player's voice on the match timeline (48 kHz mono)
- all-players.flac     every player mixed
- segments.tsv         one row per burst of speech: start, end, length, player
- listen-longest.wav   the longest bursts back to back, for a quick listen

--lang runs Whisper language detection on each player's longest bursts,
offline on the CPU (faster-whisper), so you can tell which players are worth
cutting clips from. It is a hint: short, noisy callouts fool it.

The demo is only read as a file. Nothing here touches the game process.
A server records voice only when it is set up to, so many demos have none.
Recordings contain other players' voices: the output folder is gitignored,
never commit it.
"""

import argparse
import collections
import os
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

OUT_DIR = Path(__file__).parent / "clips" / "private" / "demos"
SR = 48000
TICK_RATE = 64
BURST_GAP_TICKS = 32  # a pause longer than 0.5 s starts a new burst


def _sec(t: str) -> float:
    m, s = t.split(":")
    return int(m) * 60 + float(s)


def _fmt(sec: float) -> str:
    return f"{int(sec // 60)}:{sec % 60:05.2f}"


def _safe(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)


def decode(dem: Path, out: Path) -> list:
    """Write per-player tracks and segments.tsv; return bursts (start, end, player)."""
    import av
    from demoparser2 import DemoParser

    parser = DemoParser(str(dem))
    header = parser.parse_header()
    print(f"{header.get('map_name')} | {header.get('server_name')}")
    info = parser.parse_player_info()
    names = dict(zip(info["steamid"].astype(int), info["name"]))
    by_player = collections.defaultdict(list)
    for packet in parser.parse_voice():
        by_player[packet["steamid"]].append(packet)
    if not by_player:
        print("No voice packets: the server did not record voice.")
        return []

    out.mkdir(parents=True, exist_ok=True)
    end = max(p["tick"] for ps in by_player.values() for p in ps) / TICK_RATE + 2
    mix = np.zeros(int(end * SR), np.float32)
    bursts = []
    for steamid, packets in by_player.items():
        name = _safe(names.get(steamid, str(steamid)))
        # One Opus decoder per player: each packet is one 10 ms frame and the
        # decoder state carries over between frames.
        codec = av.CodecContext.create("libopus", "r")
        codec.sample_rate = SR
        codec.layout = "mono"
        track = np.zeros_like(mix)
        cursor, start, last_tick = 0, None, None
        for p in packets:
            if last_tick is None or p["tick"] - last_tick > BURST_GAP_TICKS:
                if start is not None:
                    bursts.append((start / SR, cursor / SR, name))
                # Place each burst at its tick. Within a burst, frames are
                # contiguous, so the decoded audio is laid end to end.
                cursor = start = max(cursor, int(p["tick"] / TICK_RATE * SR))
            last_tick = p["tick"]
            for frame in codec.decode(av.Packet(bytes(p["bytes"]))):
                a = frame.to_ndarray().reshape(-1)
                # libopus decodes to s16. Scale every frame, including
                # near-silent ones, or they play back as full-scale crackle.
                a = a.astype(np.float32) / 32768 if a.dtype == np.int16 else a.astype(np.float32)
                n = min(len(a), len(track) - cursor)
                track[cursor:cursor + n] = a[:n]
                cursor += n
        bursts.append((start / SR, cursor / SR, name))
        sf.write(out / f"player-{name}.flac", track, SR)
        mix += track
        print(f"  {name:<20} {len(packets) * 0.01 / 60:5.1f} min speech")

    sf.write(out / "all-players.flac", mix / max(np.abs(mix).max(), 1.0), SR)
    bursts.sort()
    with open(out / "segments.tsv", "w", encoding="utf-8") as f:
        f.write("start\tend\tdur\tplayer\n")
        for a, b, name in bursts:
            f.write(f"{_fmt(a)}\t{_fmt(b)}\t{b - a:.1f}\t{name}\n")
    print(f"{len(bursts)} bursts")
    return bursts


def read_bursts(out: Path) -> list:
    rows = (out / "segments.tsv").read_text(encoding="utf-8").splitlines()[1:]
    return [(_sec(a), _sec(b), name) for a, b, _, name in (r.split("\t") for r in rows)]


def write_listen(out: Path, bursts: list, count: int) -> None:
    """The longest bursts with 1 s gaps, so you can hear the language without seeking."""
    mix, _ = sf.read(out / "all-players.flac", dtype="float32")
    longest = sorted(bursts, key=lambda b: b[0] - b[1])[:count]
    gap = np.zeros(SR, np.float32)
    parts, t = [], 0.0
    for a, b, name in sorted(longest):
        clip = mix[max(0, int((a - 0.3) * SR)):int((b + 0.3) * SR)]
        print(f"  {int(t // 60)}:{int(t % 60):02d}  (match {_fmt(a)[:-3]})  {name}  {b - a:.1f}s")
        parts += [clip, gap]
        t += len(clip) / SR + 1
    x = np.concatenate(parts)
    sf.write(out / "listen-longest.wav", x / max(np.abs(x).max(), 1e-6) * 0.9, SR, subtype="PCM_16")


def detect_languages(out: Path, bursts: list, model_size: str) -> None:
    """Whisper language ID on up to 30 s of each player's longest bursts."""
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    by_player = collections.defaultdict(list)
    for a, b, name in bursts:
        by_player[name].append((b - a, a, b))
    for name, segs in sorted(by_player.items(), key=lambda kv: -sum(s[0] for s in kv[1])):
        track, _ = sf.read(out / f"player-{name}.flac", dtype="float32")
        picked, total = [], 0.0
        for dur, a, b in sorted(segs, reverse=True):
            if dur < 0.8 or total > 30:
                continue
            picked += [track[int(a * SR):int(b * SR)], np.zeros(SR // 4, np.float32)]
            total += dur
        if total < 2:
            print(f"  {name:<20} too little speech ({total:.1f}s)")
            continue
        audio = resample_poly(np.concatenate(picked), 1, 3).astype(np.float32)  # 16 kHz
        segments, info = model.transcribe(audio, beam_size=1)
        top = sorted(info.all_language_probs, key=lambda p: -p[1])[:3]
        text = " ".join(s.text.strip() for s in segments)[:80]
        langs = "  ".join(f"{lang} {p:.2f}" for lang, p in top)
        print(f"  {name:<20} {total:4.0f}s  {langs}  | {text}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("demo", type=Path, help=".dem or .dem.zst")
    ap.add_argument("--listen", type=int, default=15, metavar="N",
                    help="bursts in listen-longest.wav (0 to skip)")
    ap.add_argument("--lang", action="store_true", help="detect each player's language offline")
    ap.add_argument("--model", default="base", help="faster-whisper model for --lang")
    args = ap.parse_args()

    out = OUT_DIR / args.demo.name.split(".")[0]
    if (out / "segments.tsv").exists():
        print(f"Already decoded: {out}")
        bursts = read_bursts(out)
    elif args.demo.name.endswith(".zst"):
        import zstandard

        # Unpack to a temporary file next to the demo and delete it after:
        # an unpacked demo is 300-500 MB.
        fd, tmp = tempfile.mkstemp(suffix=".dem", dir=args.demo.parent)
        try:
            with open(args.demo, "rb") as src, os.fdopen(fd, "wb") as dst:
                zstandard.ZstdDecompressor().copy_stream(src, dst)
            bursts = decode(Path(tmp), out)
        finally:
            os.remove(tmp)
    else:
        bursts = decode(args.demo, out)
    if not bursts:
        return
    if args.listen:
        print("listen-longest.wav:")
        write_listen(out, bursts, args.listen)
    if args.lang:
        print("Languages:")
        detect_languages(out, bursts, args.model)
    print(f"Output: {out}")


if __name__ == "__main__":
    main()
