"""
CS2 Real-time Voice Translator
Configuration manager — load/save user settings to settings.json
API key is stored in Windows Credential Manager via keyring.
"""

import json
import os
import tempfile
import keyring

# Per-user, writable location. The app directory is not: a packaged build
# may live under Program Files, and PyInstaller puts __file__ in _internal/.
SETTINGS_DIR = os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~"), "CS2Translator",
)
SETTINGS_PATH = os.path.join(SETTINGS_DIR, "settings.json")
KEYRING_SERVICE = "cs2-voice-translator"
KEYRING_USERNAME = "openai-api-key"

DEFAULTS = {
    "audio_device_index": None,
    "audio_loopback": False,
    "buffer_duration": 3.0,
    "skip_english": True,
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
            # Ignore keys this version does not use, such as an api_key
            # or source_language left in settings.json by an older version.
            settings.update({k: v for k, v in saved.items() if k in DEFAULTS})
        except (json.JSONDecodeError, OSError):
            pass
    return settings


def save_settings(settings: dict) -> None:
    """Save known settings to the JSON file. The API key is never written here.

    Writes to a temp file and renames it, so a crash cannot leave a
    half-written settings.json.
    """
    to_save = {k: v for k, v in settings.items() if k in DEFAULTS}
    os.makedirs(SETTINGS_DIR, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=SETTINGS_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(to_save, f, indent=2)
        os.replace(tmp_path, SETTINGS_PATH)
    except BaseException:
        os.unlink(tmp_path)
        raise
