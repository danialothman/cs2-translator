"""
CS2 Real-time Voice Translator
Overlay window for displaying captions
"""

import tkinter as tk
from collections import deque
import time


class TranslationOverlay:
    def __init__(self, parent, settings: dict):
        """Initialize the overlay as a Toplevel window."""
        self.root = tk.Toplevel(parent)
        self.settings = settings
        self.captions = deque(maxlen=settings.get("max_captions", 5))

        max_captions = settings.get("max_captions", 5)
        alpha = settings.get("overlay_alpha", 0.8)
        font_family = settings.get("font_family", "Segoe UI")
        font_size = settings.get("font_size", 11)
        text_color = settings.get("text_color", "#00FF00")
        timestamp_color = settings.get("timestamp_color", "#FFD700")
        bg_color = settings.get("background_color", "black")

        # Window setup
        self.root.title("CS2 Translation Overlay")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", alpha)
        self.root.configure(bg=bg_color)

        # Make window draggable
        self.root.bind("<Button-1>", self._start_move)
        self.root.bind("<B1-Motion>", self._on_move)

        # Caption display
        self.text_widget = tk.Text(
            self.root,
            font=(font_family, font_size, "bold"),
            bg=bg_color,
            fg=text_color,
            wrap=tk.WORD,
            height=max_captions,
            width=70,
            relief=tk.FLAT,
            padx=15,
            pady=10,
            borderwidth=0,
            highlightthickness=0,
        )
        self.text_widget.pack(expand=True, fill=tk.BOTH)
        self.text_widget.config(state=tk.DISABLED, cursor="")

        self.text_widget.tag_configure("timestamp", foreground=timestamp_color)
        self.text_widget.tag_configure("text", foreground=text_color)

        self._position_window()
        self._drag_data = {"x": 0, "y": 0}
        self._add_initial_message()

    def _position_window(self):
        """Position the window at bottom center of screen."""
        self.root.update_idletasks()
        w = self.settings.get("window_width", 500)
        h = self.settings.get("window_height", 150)
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - w) // 2
        y = screen_h - h - 100
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _add_initial_message(self):
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.insert(tk.END, "CS2 Translation Overlay Ready\n", "text")
        self.text_widget.insert(tk.END, "Waiting for voice chat...\n", "text")
        self.text_widget.insert(tk.END, "Drag this window to reposition", "text")
        self.text_widget.config(state=tk.DISABLED)

    def _start_move(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def _on_move(self, event):
        x = self.root.winfo_x() + (event.x - self._drag_data["x"])
        y = self.root.winfo_y() + (event.y - self._drag_data["y"])
        self.root.geometry(f"+{x}+{y}")

    def add_caption(self, text: str):
        """Add a new caption to the display (must be called from main thread)."""
        timestamp = time.strftime("%H:%M:%S")

        if len(self.captions) == 0:
            self.text_widget.config(state=tk.NORMAL)
            self.text_widget.delete(1.0, tk.END)
            self.text_widget.config(state=tk.DISABLED)

        self.captions.append({"timestamp": timestamp, "text": text})
        self._update_display()

    def _update_display(self):
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.delete(1.0, tk.END)
        for caption in self.captions:
            self.text_widget.insert(tk.END, f"[{caption['timestamp']}] ", "timestamp")
            self.text_widget.insert(tk.END, f"{caption['text']}\n", "text")
        self.text_widget.config(state=tk.DISABLED)
        self.text_widget.see(tk.END)

    def show(self):
        self.root.deiconify()

    def hide(self):
        self.root.withdraw()

    def destroy(self):
        self.root.destroy()
