"""
CS2 Real-time Voice Translator
OpenAI Whisper API integration for speech translation
"""

import queue
import threading
import logging
from openai import OpenAI, APIError, AuthenticationError, RateLimitError

logger = logging.getLogger(__name__)

MODEL = "whisper-1"
REQUEST_TIMEOUT = 20.0  # seconds per attempt
MAX_RETRIES = 2


# Common Whisper hallucinations on silence/noise
HALLUCINATIONS = {
    "thank you for watching",
    "thanks for watching",
    "thank you for listening",
    "thanks for listening",
    "please subscribe",
    "like and subscribe",
    "see you next time",
    "see you in the next video",
    "bye bye",
    "you",
    "the end",
}

# Languages Whisper commonly misdetects from noise
BOGUS_LANGUAGES = {"nynorsk", "hawaiian", "maori", "haitian creole", "latin"}


def _is_hallucination(text: str, language: str) -> bool:
    """Check if transcription is a known Whisper hallucination."""
    normalized = text.lower().strip().rstrip(".!,")
    if normalized in HALLUCINATIONS:
        return True
    if language in BOGUS_LANGUAGES:
        return True
    return False


class TranslatorThread(threading.Thread):
    """Daemon thread that takes WAV byte chunks and calls OpenAI's translation API.

    Whisper's translation endpoint detects the spoken language itself, so no
    source language is passed in.
    """

    def __init__(
        self,
        api_key: str,
        skip_english: bool,
        input_queue: queue.Queue,
        on_translation: callable,
        on_error: callable,
        stop_event: threading.Event,
    ):
        super().__init__(daemon=True)
        # The SDK retries rate limits, 5xx and connection errors with backoff.
        # A short timeout keeps a hung request from outliving a stopped session.
        self.client = OpenAI(
            api_key=api_key, timeout=REQUEST_TIMEOUT, max_retries=MAX_RETRIES,
        )
        self.skip_english = skip_english
        self.input_queue = input_queue
        self.on_translation = on_translation
        self.on_error = on_error
        self.stop_event = stop_event

    def run(self):
        while not self.stop_event.is_set():
            try:
                wav_bytes = self.input_queue.get(timeout=1)
            except queue.Empty:
                continue

            try:
                self._process(wav_bytes)
            except AuthenticationError:
                self.on_error("Invalid API key. Please check your OpenAI API key.")
                self.stop_event.set()
                return
            except RateLimitError as e:
                # Also raised for an exhausted quota, so show the API's message.
                self.on_error(f"Rate limited by OpenAI: {e.message}")
            except APIError as e:
                self.on_error(f"OpenAI API error: {e.message}")
            except Exception as e:
                self.on_error(f"Translation error: {e}")

    def _process(self, wav_bytes: bytes) -> None:
        """Translate one chunk and report the result."""
        # Raw bytes have no read position, so every attempt sends the full chunk.
        audio_file = ("audio.wav", wav_bytes, "audio/wav")

        if self.skip_english:
            # Transcribe first to detect the language
            response = self.client.audio.transcriptions.create(
                model=MODEL,
                file=audio_file,
                response_format="verbose_json",
            )
            detected_lang = getattr(response, "language", "unknown")
            text = getattr(response, "text", "").strip()

            if not text:
                return
            if _is_hallucination(text, detected_lang):
                logger.info("Filtered hallucination [%s]: %s", detected_lang, text)
                return
            if detected_lang == "english":
                logger.info("Skipped (English): %s", text)
                return
            logger.info("Detected [%s]: %s", detected_lang, text)

        translation = self.client.audio.translations.create(
            model=MODEL,
            file=audio_file,
            response_format="text",
        )
        text = translation.strip()
        if not text:
            return
        if not self.skip_english and _is_hallucination(text, ""):
            logger.info("Filtered hallucination: %s", text)
            return
        logger.info("Translation: %s", text)
        self.on_translation(text)
