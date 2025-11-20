"""
CS2 Real-time Mandarin to English Voice Translation
Overlay window for displaying captions
"""

import tkinter as tk
from collections import deque
import time
from config import *

class TranslationOverlay:
    def __init__(self):
        """Initialize the overlay window"""
        self.root = tk.Tk()
        self.captions = deque(maxlen=MAX_CAPTIONS)
        
        # Window setup
        self.root.title("CS2 Translation Overlay")
        self.root.attributes('-topmost', True)  # Always on top
        self.root.attributes('-alpha', OVERLAY_ALPHA)  # Semi-transparent
        
        # Remove window decorations for cleaner look (optional)
        # Uncomment the line below if you want no title bar
        # self.root.overrideredirect(True)
        
        # Make window draggable
        self.root.bind('<Button-1>', self.start_move)
        self.root.bind('<B1-Motion>', self.on_move)
        
        # Background
        self.root.configure(bg='black')
        
        # Caption display
        self.text_widget = tk.Text(
            self.root,
            font=('Segoe UI', 11, 'bold'),
            bg='black',
            fg='#00FF00',  # Matrix green color
            wrap=tk.WORD,
            height=MAX_CAPTIONS,
            width=70,
            relief=tk.FLAT,
            padx=15,
            pady=10,
            borderwidth=0,
            highlightthickness=0
        )
        self.text_widget.pack(expand=True, fill=tk.BOTH)
        self.text_widget.config(state=tk.DISABLED, cursor="")
        
        # Add some styling with tags
        self.text_widget.tag_configure("timestamp", foreground="#FFD700")  # Gold color
        self.text_widget.tag_configure("text", foreground="#00FF00")  # Green color
        
        # Position window (bottom center of screen)
        self.position_window()
        
        # Drag data
        self._drag_data = {"x": 0, "y": 0}
        
        # Add instructions label
        self.add_initial_message()
    
    def position_window(self):
        """Position the window at bottom center"""
        self.root.update_idletasks()  # Update to get accurate dimensions
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - WINDOW_WIDTH) // 2
        y = screen_height - WINDOW_HEIGHT - 100
        self.root.geometry(f'{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x}+{y}')
    
    def add_initial_message(self):
        """Show initial instructions"""
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.insert(tk.END, "🎮 CS2 Translation Overlay Ready\n", "text")
        self.text_widget.insert(tk.END, "💬 Waiting for voice chat...\n", "text")
        self.text_widget.insert(tk.END, "🖱️  Drag this window to reposition", "text")
        self.text_widget.config(state=tk.DISABLED)
    
    def start_move(self, event):
        """Record the starting position for dragging"""
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y
    
    def on_move(self, event):
        """Handle window dragging"""
        x = self.root.winfo_x() + (event.x - self._drag_data["x"])
        y = self.root.winfo_y() + (event.y - self._drag_data["y"])
        self.root.geometry(f"+{x}+{y}")
    
    def add_caption(self, text):
        """Add a new caption to the display"""
        timestamp = time.strftime("%H:%M:%S")
        
        # Clear initial message on first caption
        if len(self.captions) == 0:
            self.text_widget.config(state=tk.NORMAL)
            self.text_widget.delete(1.0, tk.END)
            self.text_widget.config(state=tk.DISABLED)
        
        caption = {
            "timestamp": timestamp,
            "text": text
        }
        self.captions.append(caption)
        self.update_display()
    
    def update_display(self):
        """Update the text display"""
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.delete(1.0, tk.END)
        
        for caption in self.captions:
            # Insert timestamp with special formatting
            self.text_widget.insert(tk.END, f"[{caption['timestamp']}] ", "timestamp")
            # Insert translation text
            self.text_widget.insert(tk.END, f"{caption['text']}\n", "text")
        
        self.text_widget.config(state=tk.DISABLED)
        self.text_widget.see(tk.END)  # Auto-scroll to bottom
    
    def run(self):
        """Start the overlay main loop"""
        self.root.mainloop()

# Test the overlay independently
if __name__ == "__main__":
    overlay = TranslationOverlay()
    
    # Add some test captions
    import threading
    def test_captions():
        time.sleep(2)
        overlay.add_caption("Rush B, don't stop!")
        time.sleep(2)
        overlay.add_caption("Enemy spotted at long A")
        time.sleep(2)
        overlay.add_caption("Need backup at mid")
        time.sleep(2)
        overlay.add_caption("Plant the bomb!")
    
    test_thread = threading.Thread(target=test_captions)
    test_thread.daemon = True
    test_thread.start()
    
    overlay.run()