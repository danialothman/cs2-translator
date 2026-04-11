"""
CS2 Real-time Voice Translator
Configuration manager — load/save user settings to settings.json
API key is stored in Windows Credential Manager via keyring.
"""

import json
import os
import keyring

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")
KEYRING_SERVICE = "cs2-voice-translator"
KEYRING_USERNAME = "openai-api-key"

DEFAULTS = {
    "audio_device_index": None,
    "buffer_duration": 3.0,
    "source_language": "zh",
    "max_captions": 5,
    "overlay_alpha": 0.8,
    "window_width": 500,
    "window_height": 150,
    "font_family": "Segoe UI",
    "font_size": 11,
    "text_color": "#00FF00",
    "timestamp_color": "#FFD700",
    "background_color": "black",
}


def load_api_key() -> str:
    """Load API key from Windows Credential Manager."""
    return keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME) or ""


def save_api_key(api_key: str) -> None:
    """Save API key to Windows Credential Manager."""
    if api_key:
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, api_key)
    else:
        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
        except keyring.errors.PasswordDeleteError:
            pass


def load_settings() -> dict:
    """Load settings from JSON file, falling back to defaults."""
    settings = DEFAULTS.copy()
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r") as f:
                saved = json.load(f)
            # Remove api_key if it was left in settings.json from before
            saved.pop("api_key", None)
            settings.update(saved)
        except (json.JSONDecodeError, OSError):
            pass
    return settings


def save_settings(settings: dict) -> None:
    """Save settings dict to JSON file (without API key)."""
    to_save = {k: v for k, v in settings.items() if k != "api_key"}
    with open(SETTINGS_PATH, "w") as f:
        json.dump(to_save, f, indent=2)
