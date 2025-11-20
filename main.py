"""
CS2 Real-time Mandarin to English Voice Translation
Main application file
"""

import sys
import queue
import numpy as np
import pyaudio
from faster_whisper import WhisperModel
import threading
import time
from overlay import TranslationOverlay
from config import *

class AudioTranscriber:
    def __init__(self, model_size=MODEL_SIZE, device="cuda"):
        """Initialize the transcriber with Whisper model"""
        print(f"Loading Whisper {model_size} model on {device}...")
        self.model = WhisperModel(model_size, device=device, compute_type="float16")
        print("Model loaded successfully!")
        
        self.audio_queue = queue.Queue()
        self.is_running = False
        
        # Audio settings
        self.CHUNK = 1024
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = 16000
        
    def audio_callback(self, in_data, frame_count, time_info, status):
        """Callback for audio stream"""
        self.audio_queue.put(in_data)
        return (in_data, pyaudio.paContinue)
    
    def start_audio_stream(self):
        """Start capturing audio from virtual cable"""
        p = pyaudio.PyAudio()
        
        # List available devices
        print("\nAvailable audio devices:")
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            print(f"{i}: {info['name']}")
        
        # Find CABLE Output device
        device_index = None
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if "CABLE Output" in info['name'] or "cable" in info['name'].lower():
                device_index = i
                print(f"\nUsing device: {info['name']}")
                break
        
        if device_index is None:
            print("\n⚠️  WARNING: CABLE Output not found!")
            print("Please install VB-Audio Virtual Cable and restart your computer.")
            print("Download from: https://vb-audio.com/Cable/")
            print("\nAttempting to use default input device...\n")
        
        stream = p.open(
            format=self.FORMAT,
            channels=self.CHANNELS,
            rate=self.RATE,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=self.CHUNK,
            stream_callback=self.audio_callback
        )
        
        stream.start_stream()
        return stream, p
    
    def process_audio(self, overlay):
        """Process audio chunks and transcribe"""
        audio_buffer = []
        samples_needed = int(self.RATE * BUFFER_DURATION)
        
        while self.is_running:
            try:
                data = self.audio_queue.get(timeout=1)
                audio_chunk = np.frombuffer(data, dtype=np.int16)
                audio_buffer.extend(audio_chunk)
                
                if len(audio_buffer) >= samples_needed:
                    # Convert to float32 and normalize
                    audio_data = np.array(audio_buffer[:samples_needed], dtype=np.float32) / 32768.0
                    
                    # Transcribe with Whisper
                    segments, info = self.model.transcribe(
                        audio_data,
                        language="zh",  # Chinese
                        task="translate",  # Translate to English
                        vad_filter=True,  # Voice activity detection
                        beam_size=5
                    )
                    
                    # Display results
                    for segment in segments:
                        text = segment.text.strip()
                        if text:
                            print(f"[{segment.start:.1f}s] {text}")
                            overlay.add_caption(text)
                    
                    # Clear buffer
                    audio_buffer = audio_buffer[samples_needed:]
                    
            except queue.Empty:
                continue
            except Exception as e:
                print(f"❌ Error processing audio: {e}")
    
    def run(self):
        """Main run loop"""
        self.is_running = True
        
        # Start overlay
        overlay = TranslationOverlay()
        
        # Start audio stream
        stream, p = self.start_audio_stream()
        
        # Start processing thread
        process_thread = threading.Thread(target=self.process_audio, args=(overlay,))
        process_thread.daemon = True
        process_thread.start()
        
        print("\n✅ Transcription started!")
        print("💡 Speak in Mandarin to test...")
        print("🎮 Launch CS2 and join a game")
        print("🖱️  Drag the overlay window to reposition it")
        print("❌ Close the overlay window to exit\n")
        
        try:
            # Run the overlay (blocking)
            overlay.run()
        except KeyboardInterrupt:
            print("\n\n🛑 Stopping...")
        finally:
            self.is_running = False
            stream.stop_stream()
            stream.close()
            p.terminate()
            print("✅ Stopped successfully")

def main():
    print("=" * 60)
    print("🎮 CS2 Mandarin to English Real-time Translator")
    print("=" * 60)
    print()
    
    # Check GPU availability
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            print(f"✅ GPU detected: {gpu_name}")
            print(f"   VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
            device = "cuda"
        else:
            print("⚠️  No GPU detected, using CPU (will be slower)")
            device = "cpu"
    except ImportError:
        print("⚠️  PyTorch not found, using CPU")
        device = "cpu"
    
    print()
    
    # Initialize transcriber
    try:
        transcriber = AudioTranscriber(model_size=MODEL_SIZE, device=device)
        transcriber.run()
    except KeyboardInterrupt:
        print("\n\n🛑 Interrupted by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        print("\nTroubleshooting tips:")
        print("1. Make sure VB-Audio Virtual Cable is installed")
        print("2. Restart your computer after installing Virtual Cable")
        print("3. Check that CUDA is properly installed for GPU support")
        print("4. Try running as administrator")
        sys.exit(1)

if __name__ == "__main__":
    main()