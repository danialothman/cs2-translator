# CS2 Real-time Mandarin Translation

Real-time voice translation overlay for CS2 (Counter-Strike 2) that translates Mandarin Chinese teammates to English using local AI processing.

## Features

- 🎮 **Non-intrusive overlay** - Transparent window that sits on top of CS2
- 🚀 **Local processing** - Runs on your RTX 3060 Ti, no cloud costs
- 🔒 **VAC-safe** - No game process injection, just a display overlay
- ⚡ **Real-time** - 2-3 second latency for translations
- 🎯 **Mandarin focused** - Optimized for Chinese voice chat

## Requirements

- Windows 10/11
- Python 3.10 or higher
- NVIDIA GPU (RTX 3060 Ti or better)
- 8GB+ RAM
- VB-Audio Virtual Cable (free software)

## Installation

### 1. Install VB-Audio Virtual Cable

1. Download from [vb-audio.com](https://vb-audio.com/Cable/)
2. Run the installer
3. **Restart your computer** (important!)

### 2. Configure Audio Routing

After restart:

1. Right-click the speaker icon in Windows taskbar → **Sounds**
2. **Playback tab**:
   - Right-click "CABLE Input" → Set as Default Device
3. **Recording tab**:
   - Right-click "CABLE Output" → Properties
   - Go to "Listen" tab
   - Check "Listen to this device"
   - Select your actual headphones/speakers in the dropdown
   - Click Apply

Now game audio routes through the virtual cable, and you can still hear it!

### 3. Install Python Dependencies

Open Command Prompt or PowerShell:

```bash
# Clone or download this project
cd cs2-translator

# Install required packages
pip install -r requirements.txt
```

This will install:

- `faster-whisper` - Optimized Whisper implementation
- `pyaudio` - Audio capture
- `numpy` - Audio processing
- `torch` - GPU acceleration

**Note**: First run will download the Whisper model (~1.5GB for medium model), this is one-time only.

### 4. Test Your Setup

```bash
python main.py
```

You should see:

- GPU detection message
- Model loading progress
- List of audio devices
- "Transcription started!" message

The overlay window will appear. Try speaking some Mandarin to test it!

## Usage

### Starting the Translator

1. **Start CS2** first (so the overlay appears on top)
2. Run the translator:
   ```bash
   python main.py
   ```
3. The overlay window appears at the bottom center of your screen
4. **Drag the window** to position it where you want
5. Captions will appear as teammates speak

### In CS2

- Join a game as normal
- The overlay shows recent translations (last 5 messages)
- Each caption has a timestamp
- Captions fade out as new ones arrive

### Stopping

- Close the overlay window, or
- Press `Ctrl+C` in the terminal

## Configuration

Edit `config.py` to customize:

```python
# Whisper model size: "tiny", "base", "small", "medium", "large"
# medium = good balance for RTX 3060 Ti
MODEL_SIZE = "medium"

# Max captions shown at once
MAX_CAPTIONS = 5

# Audio buffer duration (seconds)
BUFFER_DURATION = 3.0

# Overlay transparency (0.0 to 1.0)
OVERLAY_ALPHA = 0.8

# Window size
WINDOW_WIDTH = 500
WINDOW_HEIGHT = 150
```

### Model Size Guide

| Model      | GPU VRAM | Latency | Accuracy  |
| ---------- | -------- | ------- | --------- |
| tiny       | 1GB      | ~1s     | Fair      |
| base       | 1GB      | ~1.5s   | Good      |
| small      | 2GB      | ~2s     | Good      |
| **medium** | 5GB      | ~2-3s   | Very Good |
| large      | 10GB     | ~4-5s   | Excellent |

**Recommended**: `medium` for RTX 3060 Ti (6GB VRAM)

## Troubleshooting

### "CABLE Output not found"

- Install VB-Audio Virtual Cable
- Restart your computer
- Check Windows Sound Settings to verify it's there

### "No GPU detected"

- Update NVIDIA drivers
- Install CUDA Toolkit 11.8 or later
- Reinstall PyTorch: `pip install torch --index-url https://download.pytorch.org/whl/cu118`

### "Out of memory" error

- Use smaller model: change `MODEL_SIZE = "small"` in config.py
- Close other GPU-intensive programs
- Lower CS2 graphics settings

### Overlay doesn't stay on top

- Run Python as administrator
- Check if CS2 is in fullscreen (try borderless windowed)

### Can't hear game audio

- In Windows Sound Settings → Recording tab
- Find "CABLE Output" → Properties → Listen tab
- Make sure "Listen to this device" is checked
- Select your actual audio device

### Translations are slow

- Use smaller model (small or base)
- Increase `BUFFER_DURATION` in config.py
- Close background applications

### No captions appearing

- Check audio levels in Windows mixer
- Speak louder or increase CS2 voice volume
- Verify CABLE Output is capturing audio (look for green bars in Sound Settings)

## File Structure

```
cs2-translator/
├── main.py           # Main application
├── overlay.py        # Overlay window UI
├── config.py         # Configuration settings
├── requirements.txt  # Python dependencies
└── README.md         # This file
```

## Performance Tips

- Use **borderless windowed** mode in CS2 for best overlay performance
- Position overlay where it won't block critical UI elements
- If FPS drops, use a smaller Whisper model
- Close browser/Discord when gaming for more VRAM

## Is This Bannable?

**No.** This tool:

- ✅ Does not inject code into CS2
- ✅ Does not modify game files
- ✅ Does not access game memory
- ✅ Only displays a window overlay
- ✅ Works exactly like Discord overlay, MSI Afterburner, etc.

It's equivalent to having a translation app open on a second monitor.

## Privacy

- Everything runs locally on your PC
- No audio is sent to the internet
- No data collection
- No cloud APIs

## Credits

- Built with [faster-whisper](https://github.com/guillaumekln/faster-whisper)
- Uses OpenAI's Whisper model
- VB-Audio Virtual Cable by VB-Audio Software

## License

MIT License - Free to use and modify

## Support

Having issues? Common solutions:

1. Restart computer after installing Virtual Cable
2. Run as administrator
3. Update GPU drivers
4. Check audio routing in Windows Sound Settings

---

**Note**: Translation accuracy depends on audio quality, accents, and background noise. Results may vary!
