"""
CS2 Real-time Voice Translator
Settings and control window — main GUI
"""

import tkinter as tk
from tkinter import ttk, messagebox
import queue
import threading
import logging
import time

from config_manager import load_settings, save_settings, load_api_key, save_api_key
from audio_capture import list_audio_devices, AudioCaptureThread
from translator import TranslatorThread
from overlay import TranslationOverlay
from version import __version__

# Audio chunks waiting for translation. Kept small so captions stay current:
# when the API falls behind, the capture thread drops the oldest chunk.
AUDIO_QUEUE_SIZE = 2


class _TkLogHandler(logging.Handler):
    """Logging handler that forwards records to a callback."""

    def __init__(self, callback):
        super().__init__()
        self._callback = callback

    def emit(self, record):
        try:
            self._callback(self.format(record))
        except Exception:
            pass


class SettingsWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"CS2 Voice Translator v{__version__}")
        self.root.geometry("460x650")
        self.root.resizable(False, True)

        self.settings = load_settings()
        self.devices = []
        self.overlay = None
        self.capture_thread = None
        self.translator_thread = None
        self.stop_event = threading.Event()
        self.is_running = False

        self._build_ui()
        self._refresh_devices()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI construction ─────────────────────────────────────────────

    def _build_ui(self):
        pad = {"padx": 12, "pady": 4}

        # ─ API Key ─
        ttk.Label(self.root, text="OpenAI API Key").pack(anchor="w", **pad)
        self.api_key_var = tk.StringVar(value=load_api_key())
        key_frame = ttk.Frame(self.root)
        key_frame.pack(fill="x", padx=12)
        self.api_key_entry = ttk.Entry(key_frame, textvariable=self.api_key_var, show="*")
        self.api_key_entry.pack(side="left", fill="x", expand=True)
        self.show_key_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            key_frame, text="Show", variable=self.show_key_var,
            command=self._toggle_key_visibility,
        ).pack(side="right", padx=(6, 0))

        # ─ Audio device ─
        ttk.Label(self.root, text="Audio Input Device").pack(anchor="w", **pad)
        device_frame = ttk.Frame(self.root)
        device_frame.pack(fill="x", padx=12)
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(
            device_frame, textvariable=self.device_var, state="readonly", width=40,
        )
        self.device_combo.pack(side="left", fill="x", expand=True)
        ttk.Button(device_frame, text="Refresh", command=self._refresh_devices, width=8).pack(
            side="right", padx=(6, 0),
        )

        # ─ Buffer duration ─
        ttk.Label(self.root, text="Buffer Duration (seconds)").pack(anchor="w", **pad)
        buf_frame = ttk.Frame(self.root)
        buf_frame.pack(fill="x", padx=12)
        self.buffer_var = tk.DoubleVar(value=self.settings.get("buffer_duration", 3.0))
        self.buffer_scale = ttk.Scale(
            buf_frame, from_=2.0, to=6.0, variable=self.buffer_var,
            orient="horizontal", command=self._on_buffer_change,
        )
        self.buffer_scale.pack(side="left", fill="x", expand=True)
        self.buffer_label = ttk.Label(buf_frame, text=f"{self.buffer_var.get():.1f}s", width=5)
        self.buffer_label.pack(side="right")

        # ─ Skip English toggle ─
        self.skip_english_var = tk.BooleanVar(value=self.settings.get("skip_english", True))
        ttk.Checkbutton(
            self.root, text="Skip English audio (don't translate English to English)",
            variable=self.skip_english_var,
        ).pack(anchor="w", padx=12, pady=(8, 0))
        ttk.Label(
            self.root,
            text="OFF = 1 API call/chunk ($0.006/min)  |  ON = 2 calls for foreign speech ($0.012/min)",
            foreground="gray",
            font=("Segoe UI", 8),
        ).pack(anchor="w", padx=28)

        # ─ Start / Stop ─
        ttk.Separator(self.root).pack(fill="x", padx=12, pady=10)
        self.start_btn = ttk.Button(
            self.root, text="Start Translating", command=self._toggle,
        )
        self.start_btn.pack(pady=4)

        # ─ Status ─
        self.status_var = tk.StringVar(value="Ready")
        self.status_label = ttk.Label(
            self.root, textvariable=self.status_var, foreground="gray",
        )
        self.status_label.pack(pady=(0, 4))

        # ─ Log panel ─
        ttk.Label(self.root, text="Log").pack(anchor="w", padx=12)
        log_frame = ttk.Frame(self.root)
        log_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self.log_text = tk.Text(
            log_frame,
            height=10,
            font=("Consolas", 9),
            bg="#1e1e1e",
            fg="#cccccc",
            wrap=tk.WORD,
            relief=tk.FLAT,
            borderwidth=1,
            highlightthickness=1,
            highlightbackground="#555",
        )
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)
        self.log_text.config(state=tk.DISABLED)

        # Color tags for log
        self.log_text.tag_configure("translation", foreground="#4ec9b0")
        self.log_text.tag_configure("skipped", foreground="#888888")
        self.log_text.tag_configure("filtered", foreground="#666666")
        self.log_text.tag_configure("error", foreground="#f44747")
        self.log_text.tag_configure("info", foreground="#cccccc")
        self.log_text.tag_configure("timestamp", foreground="#888888")

        # Set up logging to route into this panel
        self._setup_logging()

    # ── Logging ───────────────────────────────────────────────────────

    def _setup_logging(self):
        """Route Python logging into the log panel."""
        handler = _TkLogHandler(self._append_log)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

        # Suppress noisy HTTP request logs from openai/httpx
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("openai").setLevel(logging.WARNING)

    def _append_log(self, message: str):
        """Thread-safe: schedule log append on main thread."""
        self.root.after(0, self._write_log, message)

    def _write_log(self, message: str):
        """Write a log line to the panel with color coding."""
        self.log_text.config(state=tk.NORMAL)

        ts = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{ts}] ", "timestamp")

        msg_lower = message.lower()
        if "translation:" in msg_lower:
            tag = "translation"
        elif "skipped" in msg_lower:
            tag = "skipped"
        elif "filtered" in msg_lower:
            tag = "filtered"
        elif "error" in msg_lower:
            tag = "error"
        else:
            tag = "info"

        self.log_text.insert(tk.END, message + "\n", tag)
        self.log_text.config(state=tk.DISABLED)
        self.log_text.see(tk.END)

    # ── Helpers ──────────────────────────────────────────────────────

    def _toggle_key_visibility(self):
        self.api_key_entry.config(show="" if self.show_key_var.get() else "*")

    def _on_buffer_change(self, _):
        self.buffer_label.config(text=f"{self.buffer_var.get():.1f}s")

    def _refresh_devices(self):
        self.devices = list_audio_devices()
        names = [d["name"] for d in self.devices]
        self.device_combo["values"] = names if names else ["No input devices found"]

        saved_idx = self.settings.get("audio_device_index")
        saved_loopback = self.settings.get("audio_loopback", False)
        selected = False
        if saved_idx is not None:
            for i, d in enumerate(self.devices):
                if d["index"] == saved_idx and d["loopback"] == saved_loopback:
                    self.device_combo.current(i)
                    selected = True
                    break
        if not selected and self.devices:
            self.device_combo.current(0)

    def _selected_device(self) -> dict | None:
        idx = self.device_combo.current()
        if idx < 0 or idx >= len(self.devices):
            return None
        return self.devices[idx]

    # ── Start / Stop ─────────────────────────────────────────────────

    def _toggle(self):
        if self.is_running:
            self._stop()
        else:
            self._start()

    def _start(self):
        api_key = self.api_key_var.get().strip()
        if not api_key:
            messagebox.showwarning("Missing API Key", "Please enter your OpenAI API key.")
            return

        device = self._selected_device()
        if not device:
            messagebox.showwarning("No Audio Device", "No audio input devices found.")
            return

        buffer_dur = self.buffer_var.get()
        skip_english = self.skip_english_var.get()

        # Persist settings. A failure here must not block translation.
        save_api_key(api_key)
        self.settings["audio_device_index"] = device["index"]
        self.settings["audio_loopback"] = device["loopback"]
        self.settings["buffer_duration"] = buffer_dur
        self.settings["skip_english"] = skip_english
        try:
            save_settings(self.settings)
        except OSError as e:
            logging.error("Could not save settings: %s", e)

        # Each session gets its own stop event, queue and overlay. Threads from
        # a stopped session may still be finishing an API call; they hold the
        # old, set event, so they exit and cannot feed the new session.
        stop_event = threading.Event()
        audio_queue = queue.Queue(maxsize=AUDIO_QUEUE_SIZE)
        overlay = TranslationOverlay(self.root, self.settings)
        self.stop_event = stop_event
        self.overlay = overlay

        def post(callback, *args):
            """Run callback on the Tk thread while this session is current.

            self.overlay changes only on the Tk thread, so the check inside
            run_if_current is exact. The early check skips root.after() once
            the session is over, when the window may already be destroyed.
            """
            def run_if_current():
                if self.overlay is overlay:
                    callback(*args)

            if self.overlay is overlay:
                self.root.after(0, run_if_current)

        def on_error(message):
            post(self._show_error, message)

        self.capture_thread = AudioCaptureThread(
            device_index=device["index"],
            buffer_duration=buffer_dur,
            output_queue=audio_queue,
            stop_event=stop_event,
            on_error=on_error,
            loopback=device["loopback"],
            device_channels=device["channels"],
            device_rate=device["default_rate"],
        )
        self.translator_thread = TranslatorThread(
            api_key=api_key,
            skip_english=skip_english,
            input_queue=audio_queue,
            on_translation=lambda text: post(overlay.add_caption, text),
            on_error=on_error,
            stop_event=stop_event,
        )

        self.capture_thread.start()
        self.translator_thread.start()

        self.is_running = True
        self.start_btn.config(text="Stop Translating")
        self.status_var.set("Translating...")
        self.status_label.config(foreground="green")

    def _stop(self):
        self.stop_event.set()
        if self.overlay:
            self.overlay.destroy()
            self.overlay = None
        self.is_running = False
        self.start_btn.config(text="Start Translating")
        self.status_var.set("Stopped")
        self.status_label.config(foreground="gray")

    def _show_error(self, message: str):
        self.status_var.set(f"Error: {message}")
        self.status_label.config(foreground="red")
        logging.error(message)

    def _on_close(self):
        if self.is_running:
            self._stop()
        self.root.destroy()

    # ── Main loop ────────────────────────────────────────────────────

    def run(self):
        self.root.mainloop()
