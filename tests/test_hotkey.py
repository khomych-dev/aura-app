from __future__ import annotations

import ctypes
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

import aura.config as _config
from aura.hotkey import (  # noqa: I001
    _VK_MAP,
    LLKHF_INJECTED,
    WM_KEYDOWN,
    WM_KEYUP,
    HotkeyListener,
    _resolve_trigger_vk,
)

if sys.platform == "win32":
    from aura.hotkey import _KBDLLHOOKSTRUCT  # type: ignore[attr-defined]


@pytest.fixture()
def listener(qt_app: object) -> HotkeyListener:
    """HotkeyListener with default config (trigger = ctrl_r, VK 0xA3).

    No mocks needed: the new ctypes-based implementation installs the OS hook
    only when ``start()`` is called.  Unit tests exercise the state-machine
    methods (``_on_trigger_down`` / ``_on_trigger_up``) directly, so the hook
    is never actually installed during the test suite.
    """
    return HotkeyListener()


# ------------------------------------------------------------------
# VK map — key name resolution
# ------------------------------------------------------------------


def test_resolve_all_known_key_names() -> None:
    assert _resolve_trigger_vk("ctrl_r") == 0xA3
    assert _resolve_trigger_vk("menu") == 0x5D
    assert _resolve_trigger_vk("f13") == 0x7C
    assert _resolve_trigger_vk("f14") == 0x7D
    assert _resolve_trigger_vk("f15") == 0x7E


def test_vk_map_keys_match_resolve_output() -> None:
    for name, vk in _VK_MAP.items():
        assert _resolve_trigger_vk(name) == vk


def test_unknown_key_name_falls_back_to_ctrl_r_vk() -> None:
    assert _resolve_trigger_vk("nonexistent_key") == _VK_MAP["ctrl_r"]


def test_trigger_vk_resolved_from_config_menu(qt_app: object) -> None:
    with patch.object(_config, "HOTKEY_KEY_NAME", "menu"):
        lst = HotkeyListener()
    assert lst._trigger_vk == 0x5D


def test_trigger_vk_resolved_from_config_ctrl_r(qt_app: object) -> None:
    with patch.object(_config, "HOTKEY_KEY_NAME", "ctrl_r"):
        lst = HotkeyListener()
    assert lst._trigger_vk == 0xA3


# ------------------------------------------------------------------
# Key-repeat debounce (OS fires repeated keydown while trigger is held)
# ------------------------------------------------------------------


def test_key_repeat_does_not_start_recording(listener: HotkeyListener) -> None:
    started: list[bool] = []
    listener.recording_started.connect(lambda: started.append(True))

    listener._on_trigger_down()
    listener._on_trigger_down()  # OS key-repeat
    listener._on_trigger_down()

    assert len(started) == 1
    assert listener._recording is True


def test_key_repeat_does_not_stop_recording(listener: HotkeyListener) -> None:
    stopped: list[bool] = []
    listener.recording_stopped.connect(lambda: stopped.append(True))

    listener._on_trigger_down()
    listener._on_trigger_down()  # OS key-repeat while recording
    listener._on_trigger_down()

    assert len(stopped) == 0
    assert listener._recording is True


def test_held_flag_set_on_trigger_down(listener: HotkeyListener) -> None:
    assert listener._held is False
    listener._on_trigger_down()
    assert listener._held is True


def test_held_flag_cleared_on_trigger_up(listener: HotkeyListener) -> None:
    listener._on_trigger_down()
    assert listener._held is True
    listener._on_trigger_up()
    assert listener._held is False


# ------------------------------------------------------------------
# recording_started signal
# ------------------------------------------------------------------


def test_recording_starts_on_trigger_down(listener: HotkeyListener) -> None:
    started: list[bool] = []
    listener.recording_started.connect(lambda: started.append(True))

    listener._on_trigger_down()

    assert len(started) == 1
    assert listener._recording is True


def test_recording_does_not_double_start_while_active(listener: HotkeyListener) -> None:
    started: list[bool] = []
    listener.recording_started.connect(lambda: started.append(True))

    listener._on_trigger_down()
    listener._on_trigger_up()
    # Artificially keep recording active (simulates slow worker not yet cleared)
    listener._recording = True
    listener._held = False
    listener._on_trigger_down()

    assert len(started) == 1


# ------------------------------------------------------------------
# recording_stopped signal
# ------------------------------------------------------------------


def test_recording_stops_on_trigger_up(listener: HotkeyListener) -> None:
    stopped: list[bool] = []
    listener.recording_stopped.connect(lambda: stopped.append(True))

    listener._on_trigger_down()
    listener._on_trigger_up()

    assert len(stopped) == 1
    assert listener._recording is False


def test_up_without_recording_emits_nothing(listener: HotkeyListener) -> None:
    stopped: list[bool] = []
    listener.recording_stopped.connect(lambda: stopped.append(True))

    listener._on_trigger_up()

    assert len(stopped) == 0


def test_full_press_release_cycle(listener: HotkeyListener) -> None:
    started: list[bool] = []
    stopped: list[bool] = []
    listener.recording_started.connect(lambda: started.append(True))
    listener.recording_stopped.connect(lambda: stopped.append(True))

    listener._on_trigger_down()
    listener._on_trigger_up()

    assert len(started) == 1
    assert len(stopped) == 1
    assert listener._recording is False
    assert listener._held is False


# ------------------------------------------------------------------
# Debounce (time-based, post-stop window)
# ------------------------------------------------------------------


def test_debounce_prevents_immediate_restart(listener: HotkeyListener) -> None:
    started: list[bool] = []
    listener.recording_started.connect(lambda: started.append(True))

    listener._on_trigger_down()
    listener._on_trigger_up()
    listener._on_trigger_down()  # within debounce window

    assert len(started) == 1


def test_debounce_allows_restart_after_wait(listener: HotkeyListener) -> None:
    started: list[bool] = []
    listener.recording_started.connect(lambda: started.append(True))

    listener._on_trigger_down()
    listener._on_trigger_up()

    # Back-date last_stop_ts to simulate 300 ms elapsed (> HOTKEY_DEBOUNCE_MS)
    listener._last_stop_ts = time.monotonic() - 0.3

    listener._on_trigger_down()

    assert len(started) == 2


# ------------------------------------------------------------------
# Menu-key trigger (hardware compatibility)
# ------------------------------------------------------------------


def test_menu_key_triggers_recording(qt_app: object) -> None:
    with patch.object(_config, "HOTKEY_KEY_NAME", "menu"):
        lst = HotkeyListener()
        started: list[bool] = []
        lst.recording_started.connect(lambda: started.append(True))

        lst._on_trigger_down()

        assert len(started) == 1
        assert lst._recording is True


def test_menu_key_stops_recording(qt_app: object) -> None:
    with patch.object(_config, "HOTKEY_KEY_NAME", "menu"):
        lst = HotkeyListener()
        stopped: list[bool] = []
        lst.recording_stopped.connect(lambda: stopped.append(True))

        lst._on_trigger_down()
        lst._on_trigger_up()

        assert len(stopped) == 1
        assert lst._recording is False


# ------------------------------------------------------------------
# start / stop lifecycle
# ------------------------------------------------------------------


def test_start_does_not_start_twice(listener: HotkeyListener) -> None:
    """Calling start() when a hook thread already exists is a no-op."""
    sentinel = MagicMock()
    listener._hook_thread = sentinel
    listener.start()
    assert listener._hook_thread is sentinel  # unchanged


def test_stop_when_no_thread_is_safe(listener: HotkeyListener) -> None:
    listener._hook_thread = None
    listener._thread_id = 0
    listener.stop()  # must not raise


def test_stop_joins_hook_thread(listener: HotkeyListener) -> None:
    mock_thread = MagicMock()
    listener._hook_thread = mock_thread
    listener._thread_id = 0  # 0 is falsy — skips PostThreadMessageW
    listener.stop()

    mock_thread.join.assert_called_once()
    assert listener._hook_thread is None
    assert listener._thread_id == 0


# ------------------------------------------------------------------
# _hook_callback — should_swallow regression (Bug 2 fix)
# Windows-only: requires _KBDLLHOOKSTRUCT ctypes structure.
# ------------------------------------------------------------------


def _make_kbd_struct(vk: int, injected: bool = False) -> ctypes.Structure:
    """Build a fake KBDLLHOOKSTRUCT for direct _hook_callback testing."""
    kbd = _KBDLLHOOKSTRUCT()
    kbd.vkCode = vk
    kbd.flags = LLKHF_INJECTED if injected else 0
    return kbd


@pytest.mark.skipif(sys.platform != "win32", reason="WH_KEYBOARD_LL structs are Win32-only")
def test_hook_callback_swallows_trigger_keydown_normally(
    listener: HotkeyListener,
) -> None:
    kbd = _make_kbd_struct(listener._trigger_vk)
    result = listener._hook_callback(0, WM_KEYDOWN, ctypes.addressof(kbd))
    assert result == 1


@pytest.mark.skipif(sys.platform != "win32", reason="WH_KEYBOARD_LL structs are Win32-only")
def test_hook_callback_swallows_trigger_keyup_normally(
    listener: HotkeyListener,
) -> None:
    listener._held = True
    listener._recording = True
    kbd = _make_kbd_struct(listener._trigger_vk)
    result = listener._hook_callback(0, WM_KEYUP, ctypes.addressof(kbd))
    assert result == 1


@pytest.mark.skipif(sys.platform != "win32", reason="WH_KEYBOARD_LL structs are Win32-only")
def test_hook_callback_swallows_trigger_keydown_even_when_state_machine_raises(
    listener: HotkeyListener,
) -> None:
    """Regression: should_swallow is set BEFORE _on_trigger_down(), so a raised
    exception in the state machine can never let the OS see the trigger key."""
    kbd = _make_kbd_struct(listener._trigger_vk)
    with patch.object(listener, "_on_trigger_down", side_effect=RuntimeError("boom")):
        result = listener._hook_callback(0, WM_KEYDOWN, ctypes.addressof(kbd))
    assert result == 1, "trigger KEYDOWN must be swallowed even if state machine raises"


@pytest.mark.skipif(sys.platform != "win32", reason="WH_KEYBOARD_LL structs are Win32-only")
def test_hook_callback_swallows_trigger_keyup_even_when_state_machine_raises(
    listener: HotkeyListener,
) -> None:
    """Regression: should_swallow is set BEFORE _on_trigger_up(), so a raised
    exception (e.g. logger.exception failing with sys.stderr=None) never causes
    CallNextHookEx to be reached — closing the context-menu leak."""
    listener._held = True
    listener._recording = True
    kbd = _make_kbd_struct(listener._trigger_vk)
    with patch.object(listener, "_on_trigger_up", side_effect=RuntimeError("boom")):
        result = listener._hook_callback(0, WM_KEYUP, ctypes.addressof(kbd))
    assert result == 1, "trigger KEYUP must be swallowed even if state machine raises"


@pytest.mark.skipif(sys.platform != "win32", reason="WH_KEYBOARD_LL structs are Win32-only")
def test_hook_callback_forwards_non_trigger_key(listener: HotkeyListener) -> None:
    kbd = _make_kbd_struct(0x41)  # 'A' key — not the trigger
    with patch("aura.hotkey._user32") as mock_u32:
        mock_u32.CallNextHookEx.return_value = 0
        listener._hook_callback(0, WM_KEYDOWN, ctypes.addressof(kbd))
    mock_u32.CallNextHookEx.assert_called_once()


@pytest.mark.skipif(sys.platform != "win32", reason="WH_KEYBOARD_LL structs are Win32-only")
def test_hook_callback_forwards_injected_trigger_event(
    listener: HotkeyListener,
) -> None:
    """LLKHF_INJECTED events from TextInjector must pass through unchanged."""
    kbd = _make_kbd_struct(listener._trigger_vk, injected=True)
    with patch("aura.hotkey._user32") as mock_u32:
        mock_u32.CallNextHookEx.return_value = 0
        listener._hook_callback(0, WM_KEYDOWN, ctypes.addressof(kbd))
    mock_u32.CallNextHookEx.assert_called_once()


@pytest.mark.skipif(sys.platform != "win32", reason="WH_KEYBOARD_LL structs are Win32-only")
def test_hook_callback_forwards_when_ncode_negative(
    listener: HotkeyListener,
) -> None:
    """n_code < 0 means the hook MUST call CallNextHookEx per MSDN contract."""
    kbd = _make_kbd_struct(listener._trigger_vk)
    with patch("aura.hotkey._user32") as mock_u32:
        mock_u32.CallNextHookEx.return_value = 0
        listener._hook_callback(-1, WM_KEYDOWN, ctypes.addressof(kbd))
    mock_u32.CallNextHookEx.assert_called_once()
