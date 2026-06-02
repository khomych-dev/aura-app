from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

# Resolve base directory for both source and PyInstaller .exe contexts
if getattr(sys, "frozen", False):
    _APP_DIR = Path(sys.executable).parent
else:
    _APP_DIR = Path(__file__).resolve().parent.parent

if not os.environ.get("OPENAI_API_KEY"):
    load_dotenv(_APP_DIR / ".env")

# --- API ---
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
WHISPER_MODEL: str = "whisper-1"
# Total request timeout for the Whisper API call (connect + upload + processing).
# 30 s covers typical recordings up to ~2 min; raise if you regularly dictate longer.
WHISPER_API_TIMEOUT: float = 30.0

# Languages supported for transcription.
SUPPORTED_LANGUAGES: list[str] = ["uk", "en", "ru"]

# --- Language detection ---
# Maps Windows LANGID (lower 16 bits of HKL) to ISO 639-1 codes for Whisper.
# Extend as needed; unmapped LANGIDs fall back to Whisper auto-detect.
LANGUAGE_MAP: dict[int, str] = {
    0x0422: "uk",  # Ukrainian
    0x0409: "en",  # English (US)
    0x0809: "en",  # English (UK)
    0x0C09: "en",  # English (Australia)
    0x0419: "ru",  # Russian
    0x0407: "de",  # German
    0x040C: "fr",  # French
    0x0C0A: "es",  # Spanish (Modern Sort)
    0x0410: "it",  # Italian
    0x0415: "pl",  # Polish
}

# Sentinel value meaning "detect language from the active window keyboard layout".
DEFAULT_LANGUAGE: str = "auto"

# --- Audio ---
SAMPLE_RATE: int = 16_000  # Hz — optimal input rate for Whisper
CHANNELS: int = 1  # mono
MIN_RECORDING_DURATION: float = 0.5  # seconds — shorter clips are discarded
MAX_RECORDING_DURATION: float = 300.0  # seconds — soft stop limit
# Extra audio captured after key release so Whisper can decode the final token.
# Without trailing silence the last word is frequently clipped or misrecognised.
POST_ROLL_PADDING_MS: int = 400

# --- Hotkey ---
# Trigger key name — override via HOTKEY_KEY in .env.
# Supported values:  "ctrl_r"  (Right Ctrl, default)
#                    "menu"    (Context Menu / App key — for keyboards that send
#                               Key.menu from the physical Right-Ctrl position)
#                    "f13" / "f14" / "f15"  (extended function keys)
HOTKEY_KEY_NAME: str = os.environ.get("HOTKEY_KEY", "ctrl_r")
# Debounce window in ms: prevents re-triggering immediately after a recording stops.
HOTKEY_DEBOUNCE_MS: int = 200

# --- UI Indicator ---
# Logical pixel diameter of the recording dot (~4 mm at 96 DPI).
# Qt scales this automatically on high-DPI displays.
INDICATOR_SIZE_PX: int = 15
INDICATOR_TOP_MARGIN_PX: int = 15  # distance from screen top edge

# --- Logging ---
LOG_FILE: str = str(_APP_DIR / "aura.log")
LOG_MAX_BYTES: int = 1 * 1024 * 1024  # 1 MB per file
LOG_BACKUP_COUNT: int = 3
