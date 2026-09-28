"""
CS2 Real-time Voice Translator
Audio device enumeration and capture thread

Uses PyAudioWPatch for WASAPI loopback support — this lets us capture
audio from output devices (speakers/headphones), not just microphones.
"""

import io
import wave
import queue
import logging
import threading
import numpy as np
import pyaudiowpatch as pyaudio

logger = logging.getLogger(__name__)


SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK = 1024
FORMAT = pyaudio.paInt16
SAMPLE_WIDTH = 2  # 16-bit = 2 bytes


def list_audio_devices() -> list[dict]:
    """Return available input devices and WASAPI loopback devices."""
    devices = []
    p = pyaudio.PyAudio()
    try:
        # Regular input devices (microphones, virtual cables)
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info["maxInputChannels"] > 0:
                devices.append({
                    "index": i,
                    "name": info["name"],
                    "loopback": False,
                    "channels": info["maxInputChannels"],
                    "default_rate": int(info["defaultSampleRate"]),
                })

        # WASAPI loopback devices (capture what speakers output)
        try:
            for loopback in p.get_loopback_device_info_generator():
                devices.append({
                    "index": loopback["index"],
                    "name": f"{loopback['name']} [Loopback]",
                    "loopback": True,
                    "channels": loopback["maxInputChannels"],
                    "default_rate": int(loopback["defaultSampleRate"]),
                })
        except Exception:
            pass  # WASAPI loopback not available on this system
    finally:
        p.terminate()
    return devices


def build_wav(frames: list[bytes]) -> bytes:
    """Wrap raw PCM frames into an in-memory WAV file and return its bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        for frame in frames:
            wf.writeframes(frame)
    return buf.getvalue()


def _put_latest(q: queue.Queue, item) -> None:
    """Put item on a bounded queue, discarding the oldest item if it is full.

    Live captions are only useful while they are current. When translation
    falls behind capture, old audio is dropped so latency cannot grow.
    """
    try:
        q.put_nowait(item)
    except queue.Full:
        try:
            q.get_nowait()
        except queue.Empty:
            pass
        logger.warning("Translation is falling behind; dropped a stale audio chunk")
        q.put_nowait(item)


def _resample_mono(data: bytes, src_channels: int, src_rate: int) -> bytes:
    """Convert multi-channel audio to mono 16kHz 16-bit PCM."""
    samples = np.frombuffer(data, dtype=np.int16)

    # Mix down to mono
    if src_channels > 1:
        samples = samples.reshape(-1, src_channels).mean(axis=1).astype(np.int16)

    # Resample if needed
    if src_rate != SAMPLE_RATE:
        num_samples = int(len(samples) * SAMPLE_RATE / src_rate)
        indices = np.linspace(0, len(samples) - 1, num_samples).astype(int)
        samples = samples[indices]

    return samples.tobytes()


class ChunkAssembler:
    """Turns device reads of CHUNK frames into WAV chunks of buffer_duration.

    Each read is converted to 16 kHz mono on its own, as it arrives. The evals
    in evals/run.py feed clip audio through this class, so keep all chunking
    and conversion here.
    """

    def __init__(self, channels: int, rate: int, buffer_duration: float):
        self.channels = channels
        self.rate = rate
        self.reads_needed = int(rate / CHUNK * buffer_duration)
        self.needs_conversion = channels > 1 or rate != SAMPLE_RATE
        self.frames: list[bytes] = []

    def feed(self, data: bytes) -> bytes | None:
        """Add one read. Return a WAV chunk when the buffer is full."""
        if self.needs_conversion:
            data = _resample_mono(data, self.channels, self.rate)
        self.frames.append(data)
        if len(self.frames) >= self.reads_needed:
            wav = build_wav(self.frames)
            self.frames = []
            return wav
        return None


class AudioCaptureThread(threading.Thread):
    """Daemon thread that captures audio and produces WAV byte chunks."""

    def __init__(
        self,
        device_index: int | None,
        buffer_duration: float,
        output_queue: queue.Queue,
        stop_event: threading.Event,
        on_error: callable,
        loopback: bool = False,
        device_channels: int = CHANNELS,
        device_rate: int = SAMPLE_RATE,
    ):
        super().__init__(daemon=True)
        self.device_index = device_index
        self.buffer_duration = buffer_duration
        self.output_queue = output_queue
        self.stop_event = stop_event
        self.on_error = on_error
        self.loopback = loopback
        self.device_channels = device_channels
        self.device_rate = device_rate

    def run(self):
        p = pyaudio.PyAudio()
        try:
            # Loopback devices are already registered as input devices by
            # PyAudioWPatch — just open them normally with their native settings.
            stream = p.open(
                format=FORMAT,
                channels=self.device_channels,
                rate=self.device_rate,
                input=True,
                input_device_index=self.device_index,
                frames_per_buffer=CHUNK,
            )
        except OSError as e:
            self.on_error(f"Could not open audio device: {e}")
            p.terminate()
            return

        assembler = ChunkAssembler(
            self.device_channels, self.device_rate, self.buffer_duration,
        )

        try:
            while not self.stop_event.is_set():
                try:
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    wav = assembler.feed(data)
                    if wav is not None:
                        _put_latest(self.output_queue, wav)
                except OSError as e:
                    self.on_error(f"Audio read error: {e}")
                    break
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()
