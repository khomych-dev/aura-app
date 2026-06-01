from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from aura import lang_detector


def test_returns_none_on_non_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Early exit on non-Windows platforms."""
    monkeypatch.setattr(sys, "platform", "linux")
    assert lang_detector.get_active_language() is None


@pytest.mark.skipif(sys.platform != "win32", reason="requires ctypes.windll (Windows only)")
def test_returns_none_when_no_foreground_window() -> None:
    """Returns None when GetForegroundWindow returns NULL (no active window)."""
    with patch("aura.lang_detector.ctypes") as mock_ctypes:
        mock_user32 = MagicMock()
        mock_ctypes.windll.user32 = mock_user32
        mock_ctypes.c_void_p = MagicMock()
        mock_user32.GetForegroundWindow.return_value = 0

        result = lang_detector.get_active_language()

    assert result is None


@pytest.mark.skipif(sys.platform != "win32", reason="requires ctypes.windll (Windows only)")
def test_returns_mapped_language_ukrainian() -> None:
    """Maps LANGID 0x0422 → 'uk'."""
    with patch("aura.lang_detector.ctypes") as mock_ctypes:
        mock_user32 = MagicMock()
        mock_ctypes.windll.user32 = mock_user32
        mock_ctypes.c_void_p = MagicMock()
        mock_user32.GetForegroundWindow.return_value = 0x12345
        mock_user32.GetWindowThreadProcessId.return_value = 0xABCD
        # HKL: upper bits are ignored, lower 16 bits = 0x0422 (Ukrainian)
        mock_user32.GetKeyboardLayout.return_value = 0x04220422

        result = lang_detector.get_active_language()

    assert result == "uk"


@pytest.mark.skipif(sys.platform != "win32", reason="requires ctypes.windll (Windows only)")
def test_returns_mapped_language_english() -> None:
    """Maps LANGID 0x0409 → 'en'."""
    with patch("aura.lang_detector.ctypes") as mock_ctypes:
        mock_user32 = MagicMock()
        mock_ctypes.windll.user32 = mock_user32
        mock_ctypes.c_void_p = MagicMock()
        mock_user32.GetForegroundWindow.return_value = 0x12345
        mock_user32.GetWindowThreadProcessId.return_value = 0xABCD
        mock_user32.GetKeyboardLayout.return_value = 0x04090409

        result = lang_detector.get_active_language()

    assert result == "en"


@pytest.mark.skipif(sys.platform != "win32", reason="requires ctypes.windll (Windows only)")
def test_returns_none_for_unmapped_langid() -> None:
    """Returns None when LANGID is not in LANGUAGE_MAP."""
    with patch("aura.lang_detector.ctypes") as mock_ctypes:
        mock_user32 = MagicMock()
        mock_ctypes.windll.user32 = mock_user32
        mock_ctypes.c_void_p = MagicMock()
        mock_user32.GetForegroundWindow.return_value = 0x12345
        mock_user32.GetWindowThreadProcessId.return_value = 0xABCD
        # LANGID 0x9999 is not in LANGUAGE_MAP
        mock_user32.GetKeyboardLayout.return_value = 0x99999999

        result = lang_detector.get_active_language()

    assert result is None


@pytest.mark.skipif(sys.platform != "win32", reason="requires ctypes.windll (Windows only)")
def test_returns_none_on_win32_exception() -> None:
    """Returns None and does not propagate exceptions from Win32 calls."""
    with patch("aura.lang_detector.ctypes") as mock_ctypes:
        mock_user32 = MagicMock()
        mock_ctypes.windll.user32 = mock_user32
        mock_ctypes.c_void_p = MagicMock()
        mock_user32.GetForegroundWindow.side_effect = OSError("access denied")

        result = lang_detector.get_active_language()

    assert result is None
