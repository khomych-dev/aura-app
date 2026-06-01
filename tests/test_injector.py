from __future__ import annotations

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
