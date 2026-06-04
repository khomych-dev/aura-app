from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from aura.lang_detector import get_active_language


def test_returns_none_on_non_win32() -> None:
    with patch("sys.platform", "linux"):
        assert get_active_language() is None


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows")
def test_returns_none_when_no_foreground_window() -> None:
    with patch("aura.lang_detector._user32_lang") as mock_user32:
        mock_user32.GetForegroundWindow.return_value = 0
        assert get_active_language() is None


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows")
def test_returns_mapped_language_ukrainian() -> None:
    with patch("aura.lang_detector._user32_lang") as mock_user32:
        mock_user32.GetForegroundWindow.return_value = 12345
        mock_user32.GetWindowThreadProcessId.return_value = 67890
        mock_user32.GetKeyboardLayout.return_value = 0x0422
        assert get_active_language() == "uk"


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows")
def test_returns_mapped_language_english() -> None:
    with patch("aura.lang_detector._user32_lang") as mock_user32:
        mock_user32.GetForegroundWindow.return_value = 12345
        mock_user32.GetWindowThreadProcessId.return_value = 67890
        mock_user32.GetKeyboardLayout.return_value = 0x0409
        assert get_active_language() == "en"


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows")
def test_returns_none_for_unmapped_langid() -> None:
    with patch("aura.lang_detector._user32_lang") as mock_user32:
        mock_user32.GetForegroundWindow.return_value = 12345
        mock_user32.GetWindowThreadProcessId.return_value = 67890
        mock_user32.GetKeyboardLayout.return_value = 0x9999  # Unmapped
        assert get_active_language() is None


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows")
def test_returns_none_on_win32_exception() -> None:
    with patch("aura.lang_detector._user32_lang") as mock_user32:
        mock_user32.GetForegroundWindow.side_effect = Exception("Win32 error")
        assert get_active_language() is None
