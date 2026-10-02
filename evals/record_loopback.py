"""
Record what the PC plays (WASAPI loopback) to 48 kHz stereo FLAC, the format
of the eval clips, for cutting private clips from a real match.

    python -m evals.record_loopback            # window with Start / Stop
    python -m evals.record_loopback --cli [--minutes 60] [--device Speakers]

Writes evals/clips/private/recordings/<timestamp>.flac. The command-line mode
stops at the time limit, on Ctrl+C, or when a file named STOP appears in that
folder. Both modes always close the FLAC cleanly.

It records everything the PC plays: game sound, teammates' voices, and any
other app. Your microphone is not included. WASAPI loopback delivers no data
while nothing plays, so silent stretches are shorter than they were.
Recordings contain other players' voices: the folder is gitignored, never
commit it.
"""

import argparse
import os
import threading
import time
from pathlib import Path

import numpy as np
import pyaudiowpatch as pyaudio
import soundfile as sf
import soxr

OUT_DIR = Path(__file__).parent / "clips" / "private" / "recordings"
SR = 48000


def loopback_devices() -> list:
    p = pyaudio.PyAudio()
    try:
        default = p.get_default_wasapi_loopback()["index"]
        devs = list(p.get_loopback_device_info_generator())
    finally:
        p.terminate()
    return sorted(devs, key=lambda d: d["index"] != default)  # default first


class Recorder:
    """Records one loopback device to FLAC on a worker thread."""

    def __init__(self, device: dict):
        self.device = device
        self.out = OUT_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}.flac"
        self.seconds = 0.0  # audio written so far
        self.level = 0.0    # peak of the latest read, 0..1
        self.error = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join()

    def _run(self):
        rate, channels = int(self.device["defaultSampleRate"]), self.device["maxInputChannels"]
        block = rate // 10
        p = pyaudio.PyAudio()
        try:
            stream = p.open(format=pyaudio.paInt16, channels=channels, rate=rate, input=True,
                            input_device_index=self.device["index"], frames_per_buffer=block)
            resampler = soxr.ResampleStream(rate, SR, 2, dtype="float32")
            with sf.SoundFile(self.out, "w", SR, 2, subtype="PCM_16", format="FLAC") as f:
                while not self._stop.is_set():
                    # Poll: a blocking read never returns while nothing plays.
                    if stream.get_read_available() < block:
                        self.level = 0.0
                        time.sleep(0.05)
                        continue
                    raw = stream.read(block, exception_on_overflow=False)
                    x = np.frombuffer(raw, np.int16).reshape(-1, channels).astype(np.float32) / 32768
                    x = x[:, :2] if channels >= 2 else np.repeat(x, 2, axis=1)
                    y = resampler.resample_chunk(x)
                    f.write(y)
                    self.seconds += len(y) / SR
                    self.level = float(np.abs(x).max())
                f.write(resampler.resample_chunk(np.zeros((0, 2), np.float32), last=True))
            stream.stop_stream()
            stream.close()
        except Exception as e:  # shown in the window or printed by the CLI
            self.error = e
        finally:
            p.terminate()


def run_cli(args):
    devs = loopback_devices()
    dev = devs[0] if not args.device else next(
        (d for d in devs if args.device.lower() in d["name"].lower()), None)
    if dev is None:
        raise SystemExit(f"No loopback device matching {args.device!r}")
    stop_file = OUT_DIR / "STOP"
    stop_file.unlink(missing_ok=True)
    rec = Recorder(dev)
    rec.start()
    print(f"Recording {dev['name']} to {rec.out}")
    print(f"Stop: Ctrl+C, create {stop_file}, or wait {args.minutes:g} min")
    deadline, next_report = time.monotonic() + args.minutes * 60, time.monotonic() + 60
    try:
        while time.monotonic() < deadline and not stop_file.exists() and rec.error is None:
            time.sleep(0.2)
            if time.monotonic() > next_report:
                print(f"  {rec.seconds / 60:5.1f} min recorded")
                next_report += 60
    except KeyboardInterrupt:
        pass
    rec.stop()
    stop_file.unlink(missing_ok=True)
    if rec.error:
        raise SystemExit(f"Recording failed: {rec.error}")
    print(f"Saved {rec.seconds / 60:.1f} min to {rec.out}")


def run_gui():
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("Loopback Recorder")
    root.resizable(False, False)
    frm = ttk.Frame(root, padding=12)
    frm.pack()

    devs = loopback_devices()
    names = [d["name"] for d in devs]
    ttk.Label(frm, text="Device").grid(row=0, column=0, sticky="w")
    device = ttk.Combobox(frm, values=names, state="readonly", width=48)
    device.current(0)
    device.grid(row=0, column=1, columnspan=2, sticky="we", pady=(0, 8))

    button = ttk.Button(frm, text="Start", width=12)
    button.grid(row=1, column=0, sticky="w")
    clock = ttk.Label(frm, text="0:00", font=("Segoe UI", 16, "bold"))
    clock.grid(row=1, column=1, sticky="w", padx=12)
    meter = ttk.Progressbar(frm, length=180, maximum=1.0)
    meter.grid(row=1, column=2, sticky="e")
    status = ttk.Label(frm, text="Pause other audio (browser, Discord) before you start.",
                       wraplength=420, foreground="#555")
    status.grid(row=2, column=0, columnspan=3, sticky="w", pady=(10, 0))
    ttk.Button(frm, text="Open folder",
               command=lambda: (OUT_DIR.mkdir(parents=True, exist_ok=True), os.startfile(OUT_DIR))
               ).grid(row=3, column=0, sticky="w", pady=(8, 0))

    state = {"rec": None}

    def tick():
        rec = state["rec"]
        if rec is None:
            return
        if rec.error:
            stop()
            return
        s = int(rec.seconds)
        clock.config(text=f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}")
        meter["value"] = rec.level
        root.after(200, tick)

    def start():
        rec = Recorder(devs[device.current()])
        rec.start()
        state["rec"] = rec
        button.config(text="Stop")
        device.config(state="disabled")
        status.config(text=f"Recording to {rec.out.name}. Silence is skipped.", foreground="#b00")
        tick()

    def stop():
        rec, state["rec"] = state["rec"], None
        rec.stop()
        button.config(text="Start")
        device.config(state="readonly")
        meter["value"] = 0
        if rec.error:
            status.config(text=f"Recording failed: {rec.error}", foreground="#b00")
        else:
            status.config(text=f"Saved {rec.seconds / 60:.1f} min to {rec.out.name}", foreground="#070")

    button.config(command=lambda: stop() if state["rec"] else start())

    def on_close():
        if state["rec"]:
            stop()  # close the FLAC before exiting
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cli", action="store_true", help="record from the terminal instead of a window")
    ap.add_argument("--minutes", type=float, default=60, help="--cli: stop after this long")
    ap.add_argument("--device", help="--cli: part of the loopback device name (default: the default output)")
    args = ap.parse_args()
    run_cli(args) if args.cli else run_gui()


if __name__ == "__main__":
    main()
