"""
CS2 Real-time Voice Translator
OpenAI Whisper API integration for speech translation
"""

import queue
import threading
import time
import logging
from openai import OpenAI, APIError, AuthenticationError, RateLimitError

logger = logging.getLogger(__name__)


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
    """Daemon thread that takes WAV buffers and calls OpenAI's translation API."""

    def __init__(
        self,
        api_key: str,
        source_language: str,
        skip_english: bool,
        input_queue: queue.Queue,
        on_translation: callable,
        on_error: callable,
        stop_event: threading.Event,
    ):
        super().__init__(daemon=True)
        self.client = OpenAI(api_key=api_key)
        self.source_language = source_language
        self.skip_english = skip_english
        self.input_queue = input_queue
        self.on_translation = on_translation
        self.on_error = on_error
        self.stop_event = stop_event

    def run(self):
        while not self.stop_event.is_set():
            try:
                wav_buffer = self.input_queue.get(timeout=1)
            except queue.Empty:
                continue

            retries = 0
            while retries < 3:
                try:
                    if self.skip_english:
                        # Transcribe first to detect language
                        response = self.client.audio.transcriptions.create(
                            model="whisper-1",
                            file=wav_buffer,
                            response_format="verbose_json",
                        )

                        detected_lang = getattr(response, "language", "unknown")
                        text = getattr(response, "text", "").strip()

                        if not text:
                            break

                        if _is_hallucination(text, detected_lang):
                            logger.info("Filtered hallucination [%s]: %s", detected_lang, text)
                            break

                        if detected_lang == "english":
                            logger.info("Skipped (English): %s", text)
                            break

                        # Translate non-English audio
                        logger.info("Detected [%s]: %s", detected_lang, text)
                        wav_buffer.seek(0)
                        translation = self.client.audio.translations.create(
                            model="whisper-1",
                            file=wav_buffer,
                            response_format="text",
                        )
                        translated = translation.strip()
                        if translated:
                            logger.info("Translation: %s", translated)
                            self.on_translation(translated)
                    else:
                        # Translate everything directly (single API call)
                        response = self.client.audio.translations.create(
                            model="whisper-1",
                            file=wav_buffer,
                            response_format="text",
                        )
                        text = response.strip()
                        if text and not _is_hallucination(text, ""):
                            logger.info("Translation: %s", text)
                            self.on_translation(text)
                        elif text:
                            logger.info("Filtered hallucination: %s", text)
                    break

                except AuthenticationError:
                    self.on_error("Invalid API key. Please check your OpenAI API key.")
                    self.stop_event.set()
                    return

                except RateLimitError:
                    retries += 1
                    if retries < 3:
                        time.sleep(1)
                    else:
                        self.on_error("Rate limited by OpenAI. Please try again shortly.")

                except APIError as e:
                    self.on_error(f"OpenAI API error: {e.message}")
                    break

                except Exception as e:
                    self.on_error(f"Translation error: {e}")
                    break
