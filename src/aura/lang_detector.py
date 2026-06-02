from __future__ import annotations

import logging
import sys

from aura import config

logger = logging.getLogger(__name__)


def get_active_language() -> str | None:
    """Return the ISO 639-1 code for the active window's current keyboard layout.

    Calls Win32 API chain::

        GetForegroundWindow() → HWND
        GetWindowThreadProcessId(hwnd, NULL) → thread_id
        GetKeyboardLayout(thread_id) → HKL
        HKL & 0xFFFF → LANGID  →  config.LANGUAGE_MAP lookup

    Returns ``None`` on non-Windows, Win32 failure, or an unmapped LANGID
    so that callers can fall back to Whisper auto-detection.
    """
    if sys.platform != "win32":
        return None

    try:
        import ctypes.wintypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]

        # 1. Declare exact types to prevent 64-bit pointer truncation
        user32.GetForegroundWindow.restype = ctypes.wintypes.HWND
        user32.GetForegroundWindow.argtypes = []

        user32.GetWindowThreadProcessId.restype = ctypes.wintypes.DWORD
        user32.GetWindowThreadProcessId.argtypes = [
            ctypes.wintypes.HWND,
            ctypes.POINTER(ctypes.wintypes.DWORD),
        ]

        user32.GetKeyboardLayout.restype = ctypes.c_void_p
        user32.GetKeyboardLayout.argtypes = [ctypes.wintypes.DWORD]

        # 2. Get active window
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            logger.debug("GetForegroundWindow returned NULL — no active window")
            return None

        # 3. Get thread ID of that window
        thread_id = user32.GetWindowThreadProcessId(hwnd, None)
        if not thread_id:
            logger.debug("Failed to get thread ID for HWND")
            return None

        # 4. Get keyboard layout for that thread
        hkl = user32.GetKeyboardLayout(thread_id)

        # Lower 16 bits of HKL encode the primary LANGID.
        langid: int = (hkl if hkl is not None else 0) & 0xFFFF

        iso = config.LANGUAGE_MAP.get(langid)
        if iso is None:
            logger.debug(
                "LANGID 0x%04X not in LANGUAGE_MAP — falling back to Whisper auto-detect",
                langid,
            )
        else:
            logger.debug("Detected keyboard language: %s (LANGID=0x%04X)", iso, langid)
        return iso

    except Exception:
        logger.exception("Failed to detect active keyboard layout — falling back to auto-detect")
        return None
