from __future__ import annotations

import sys
from unittest.mock import MagicMock, call, patch

import pytest

from aura.injector import TextInjector


@pytest.fixture()
def injector() -> TextInjector:
    with patch("pynput.keyboard.Controller"):
        return TextInjector()


# ---------------------------------------------------------------------------
# Empty-string guard
# ---------------------------------------------------------------------------


def test_paste_empty_string_is_noop(injector: TextInjector) -> None:
    injector._keyboard = MagicMock()
    with patch("pyperclip.copy") as mock_copy:
        injector.paste("")
    mock_copy.assert_not_called()
    injector._keyboard.type.assert_not_called()


# ---------------------------------------------------------------------------
# Primary strategy: keyboard.type()
# ---------------------------------------------------------------------------


def test_paste_primary_uses_keyboard_type(injector: TextInjector) -> None:
    injector._keyboard = MagicMock()
    with patch("time.sleep"):
        injector.paste("hello world")
    injector._keyboard.type.assert_called_once_with("hello world")


def test_paste_primary_releases_modifiers_before_typing(injector: TextInjector) -> None:
    injector._keyboard = MagicMock()
    with patch("time.sleep"):
        injector.paste("test")

    calls = injector._keyboard.mock_calls
    release_indices = [i for i, c in enumerate(calls) if c[0] == "release"]
    type_indices = [i for i, c in enumerate(calls) if c[0] == "type"]

    assert len(release_indices) > 0, "Expected modifier release() calls before type()"
    assert len(type_indices) == 1, "Expected exactly one type() call"
    # Every release must happen before the type() call
    assert max(release_indices) < type_indices[0]


def test_paste_primary_does_not_touch_clipboard(injector: TextInjector) -> None:
    injector._keyboard = MagicMock()
    with (
        patch("pyperclip.copy") as mock_copy,
        patch("pyperclip.paste") as mock_paste,
        patch("time.sleep"),
    ):
        injector.paste("no clipboard please")
    mock_copy.assert_not_called()
    mock_paste.assert_not_called()


# ---------------------------------------------------------------------------
# Fallback strategy: clipboard
# ---------------------------------------------------------------------------


def test_paste_falls_back_to_clipboard_on_typing_error(injector: TextInjector) -> None:
    injector._keyboard = MagicMock()
    injector._keyboard.type.side_effect = Exception("SendInput failed")
    with (
        patch("pyperclip.paste", return_value=""),
        patch("pyperclip.copy") as mock_copy,
        patch("time.sleep"),
    ):
        injector.paste("fallback text")
    mock_copy.assert_any_call("fallback text")


def test_paste_clipboard_fallback_copies_and_restores(injector: TextInjector) -> None:
    injector._keyboard = MagicMock()
    injector._keyboard.type.side_effect = Exception("SendInput failed")
    with (
        patch("pyperclip.paste", return_value="old content") as mock_paste,
        patch("pyperclip.copy") as mock_copy,
        patch("time.sleep"),
    ):
        injector.paste("new text")

    mock_paste.assert_called_once()
    assert mock_copy.call_args_list[0] == call("new text")
    assert mock_copy.call_args_list[1] == call("old content")


def test_paste_does_not_raise_when_both_strategies_fail(injector: TextInjector) -> None:
    injector._keyboard = MagicMock()
    injector._keyboard.type.side_effect = Exception("SendInput failed")
    with (
        patch("pyperclip.paste", side_effect=Exception("clipboard locked")),
        patch("pyperclip.copy", side_effect=Exception("clipboard locked")),
        patch("time.sleep"),
    ):
        # Must not propagate — errors are logged, not raised
        injector.paste("text")


# ---------------------------------------------------------------------------
# Win32 modifier-release regression (Bug 1 fix — KEYEVENTF_EXTENDEDKEY)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 keybd_event path is Windows-only")
def test_release_modifiers_calls_keybd_event_for_every_modifier_vk(
    injector: TextInjector,
) -> None:
    from aura.injector import _MODIFIER_VKS  # type: ignore[attr-defined]

    with patch("aura.injector._user32_inj") as mock_u32:
        mock_u32.keybd_event = MagicMock()
        injector._release_modifiers()

    assert mock_u32.keybd_event.call_count == len(_MODIFIER_VKS)


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 keybd_event path is Windows-only")
def test_release_modifiers_sets_extendedkey_flag_for_vk_apps(
    injector: TextInjector,
) -> None:
    """Regression: VK_APPS (0x5D) requires KEYEVENTF_EXTENDEDKEY.
    Without it the OS context-menu state machine does not clear the key slot."""
    from aura.injector import _KEYEVENTF_EXTENDEDKEY, _KEYEVENTF_KEYUP  # type: ignore[attr-defined]

    captured: list[tuple] = []
    with patch("aura.injector._user32_inj") as mock_u32:
        mock_u32.keybd_event.side_effect = lambda *a: captured.append(a)
        injector._release_modifiers()

    vk_apps = [c for c in captured if c[0] == 0x5D]
    assert len(vk_apps) == 1, "Expected exactly one keybd_event call for VK_APPS (0x5D)"
    flags = vk_apps[0][2]
    assert flags & _KEYEVENTF_KEYUP, "KEYEVENTF_KEYUP must be set"
    assert flags & _KEYEVENTF_EXTENDEDKEY, "KEYEVENTF_EXTENDEDKEY must be set for VK_APPS"


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 keybd_event path is Windows-only")
def test_release_modifiers_sets_extendedkey_flag_for_vk_rcontrol(
    injector: TextInjector,
) -> None:
    """Regression: VK_RCONTROL (0xA3) requires KEYEVENTF_EXTENDEDKEY.
    Without it the OS scan-code slot for Right Ctrl stays stuck 'down'."""
    from aura.injector import _KEYEVENTF_EXTENDEDKEY, _KEYEVENTF_KEYUP  # type: ignore[attr-defined]

    captured: list[tuple] = []
    with patch("aura.injector._user32_inj") as mock_u32:
        mock_u32.keybd_event.side_effect = lambda *a: captured.append(a)
        injector._release_modifiers()

    vk_rctrl = [c for c in captured if c[0] == 0xA3]
    assert len(vk_rctrl) == 1, "Expected exactly one keybd_event call for VK_RCONTROL (0xA3)"
    flags = vk_rctrl[0][2]
    assert flags & _KEYEVENTF_KEYUP
    assert flags & _KEYEVENTF_EXTENDEDKEY, "KEYEVENTF_EXTENDEDKEY must be set for VK_RCONTROL"


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 keybd_event path is Windows-only")
def test_release_modifiers_no_extendedkey_flag_for_vk_lcontrol(
    injector: TextInjector,
) -> None:
    """VK_LCONTROL (0xA2) is NOT an extended key — EXTENDEDKEY flag must be absent."""
    from aura.injector import _KEYEVENTF_EXTENDEDKEY  # type: ignore[attr-defined]

    captured: list[tuple] = []
    with patch("aura.injector._user32_inj") as mock_u32:
        mock_u32.keybd_event.side_effect = lambda *a: captured.append(a)
        injector._release_modifiers()

    vk_lctrl = [c for c in captured if c[0] == 0xA2]
    assert len(vk_lctrl) == 1
    assert not (vk_lctrl[0][2] & _KEYEVENTF_EXTENDEDKEY), "VK_LCONTROL is not an extended key"
