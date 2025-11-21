"""
CS2 Real-time Mandarin to English Voice Translation
Configuration file
"""

# Whisper Model Configuration
# Options: "tiny", "base", "small", "medium", "large"
# Recommended for RTX 3060 Ti: "medium"
# 
# Model Size Guide:
# - tiny:   ~1GB VRAM, ~1s latency, fair accuracy
# - base:   ~1GB VRAM, ~1.5s latency, good accuracy
# - small:  ~2GB VRAM, ~2s latency, good accuracy
# - medium: ~5GB VRAM, ~2-3s latency, very good accuracy (RECOMMENDED)
# - large:  ~10GB VRAM, ~4-5s latency, excellent accuracy
MODEL_SIZE = "base"

# Audio Processing Configuration
# Duration of audio buffer before processing (in seconds)
# Higher = better context but more latency
# Lower = faster but may miss words
BUFFER_DURATION = 3.0

# Overlay Window Configuration
# Maximum number of caption lines to display at once
MAX_CAPTIONS = 5

# Window transparency (0.0 = invisible, 1.0 = opaque)
OVERLAY_ALPHA = 0.8

# Window dimensions (pixels)
WINDOW_WIDTH = 500
WINDOW_HEIGHT = 150

# Audio Settings
# These generally shouldn't need to be changed
SAMPLE_RATE = 16000  # Whisper works best at 16kHz
AUDIO_CHUNK_SIZE = 1024

# Translation Settings
# Source language (ISO 639-1 code)
# "zh" = Chinese (Mandarin)
SOURCE_LANGUAGE = "zh"

# Target language is always English for Whisper's translate task

# Advanced Settings
# Voice Activity Detection (VAD) - filters out silence
# Recommended: True (reduces false positives)
USE_VAD = True

# Beam size for transcription (higher = more accurate but slower)
# Range: 1-10, Recommended: 5
BEAM_SIZE = 5

# Display Settings
# Font settings for overlay
FONT_FAMILY = "Segoe UI"
FONT_SIZE = 11
FONT_WEIGHT = "bold"

# Color scheme (hex colors)
TEXT_COLOR = "#00FF00"  # Green
TIMESTAMP_COLOR = "#FFD700"  # Gold
BACKGROUND_COLOR = "black"

# Performance Tuning
# If you experience lag, try these:
# - Reduce MODEL_SIZE to "small" or "base"
# - Increase BUFFER_DURATION to 4.0 or 5.0
# - Reduce BEAM_SIZE to 3 or 1
# - Close other GPU-intensive applications