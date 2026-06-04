from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from aura.injector import TextInjector


@pytest.fixture()
def injector() -> TextInjector:
    with patch("aura.injector.threading.Thread"):
        return TextInjector()


def test_paste_empty_string_is_noop(injector: TextInjector) -> None:
    injector.paste("")
    assert injector._queue.empty()


@pytest.mark.skipif(sys.platform != "win32", reason="Requires Windows")
def test_paste_puts_text_in_queue(injector: TextInjector) -> None:
    injector.paste("hello world")
    assert not injector._queue.empty()
    assert injector._queue.get_nowait() == "hello world"


@pytest.mark.skipif(sys.platform != "win32", reason="Requires Windows")
def test_paste_worker_calls_dependencies(injector: TextInjector) -> None:
    with (
        patch.object(injector, "_release_modifiers") as mock_release,
        patch.object(injector, "_inject_unicode") as mock_inject,
        patch("aura.injector.time.sleep"),
    ):
        injector._paste_worker("test")

    mock_release.assert_called_once()
    mock_inject.assert_called_once_with("test")


@pytest.mark.skipif(sys.platform != "win32", reason="Requires Windows")
def test_inject_unicode_calls_sendinput(injector: TextInjector) -> None:
    with (
        patch("aura.injector._user32_inj") as mock_u32,
        patch("aura.injector.time.sleep"),
    ):
        injector._inject_unicode("a")

    # 2 calls per character: keydown and keyup
    assert mock_u32.SendInput.call_count == 2


@pytest.mark.skipif(sys.platform != "win32", reason="Requires Windows")
def test_release_modifiers_calls_keybd_event_for_every_modifier_vk(
    injector: TextInjector,
) -> None:
    from aura.injector import _MODIFIER_VKS

    with patch("aura.injector._user32_inj") as mock_u32:
        injector._release_modifiers()

    assert mock_u32.keybd_event.call_count == len(_MODIFIER_VKS)


@pytest.mark.skipif(sys.platform != "win32", reason="Requires Windows")
def test_release_modifiers_sets_extendedkey_flag_for_rmenu(
    injector: TextInjector,
) -> None:
    """VK_RMENU (0xA5) is flagged as extended in _MODIFIER_VKS."""
    from aura.injector import KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP

    captured: list[tuple] = []
    with patch("aura.injector._user32_inj") as mock_u32:
        mock_u32.keybd_event.side_effect = lambda *a: captured.append(a)
        injector._release_modifiers()

    vk_rmenu = [c for c in captured if c[0] == 0xA5]
    assert len(vk_rmenu) == 1
    flags = vk_rmenu[0][2]
    assert flags & KEYEVENTF_KEYUP
    assert flags & KEYEVENTF_EXTENDEDKEY


@pytest.mark.skipif(sys.platform != "win32", reason="Requires Windows")
def test_release_modifiers_no_extendedkey_flag_for_lcontrol(
    injector: TextInjector,
) -> None:
    """VK_LCONTROL (0xA2) is NOT an extended key."""
    from aura.injector import KEYEVENTF_EXTENDEDKEY

    captured: list[tuple] = []
    with patch("aura.injector._user32_inj") as mock_u32:
        mock_u32.keybd_event.side_effect = lambda *a: captured.append(a)
        injector._release_modifiers()

    vk_lctrl = [c for c in captured if c[0] == 0xA2]
    assert len(vk_lctrl) == 1
    assert not (vk_lctrl[0][2] & KEYEVENTF_EXTENDEDKEY)
