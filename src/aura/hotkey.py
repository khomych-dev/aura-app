from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import sys
import threading
import time

from PySide6.QtCore import QObject, Signal

from aura import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Windows constants
# ---------------------------------------------------------------------------

WH_KEYBOARD_LL: int = 13
WM_KEYDOWN: int = 0x0100
WM_KEYUP: int = 0x0101
WM_SYSKEYDOWN: int = 0x0104
WM_SYSKEYUP: int = 0x0105
WM_QUIT: int = 0x0012
LLKHF_INJECTED: int = 0x10

# Maps HOTKEY_KEY config string → Windows virtual-key code.
# Extend this table to support additional trigger key choices.
_VK_MAP: dict[str, int] = {
    "ctrl_r": 0xA3,  # VK_RCONTROL
    "menu":   0x5D,  # VK_APPS (Application / Context-Menu key)
    "f13":    0x7C,  # VK_F13
    "f14":    0x7D,  # VK_F14
    "f15":    0x7E,  # VK_F15
}

# ---------------------------------------------------------------------------
# Platform-specific ctypes setup (Windows only)
# ---------------------------------------------------------------------------

if sys.platform == "win32":  # pragma: no cover
    _user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    _kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    class _KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode",      ctypes.wintypes.DWORD),
            ("scanCode",    ctypes.wintypes.DWORD),
            ("flags",       ctypes.wintypes.DWORD),
            ("time",        ctypes.wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),   # ULONG_PTR
        ]

    _HOOKPROC = ctypes.WINFUNCTYPE(  # type: ignore[attr-defined]
        ctypes.c_int,
        ctypes.c_int,
        ctypes.wintypes.WPARAM,
        ctypes.wintypes.LPARAM,
    )
else:
    _user32 = None   # type: ignore[assignment]
    _kernel32 = None  # type: ignore[assignment]
    _KBDLLHOOKSTRUCT = None  # type: ignore[assignment, misc]
    _HOOKPROC = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Key resolution
# ---------------------------------------------------------------------------


def _resolve_trigger_vk(name: str) -> int:
    """Return the Windows virtual-key code for *name*, falling back to ctrl_r."""
    vk = _VK_MAP.get(name)
    if vk is None:
        logger.warning(
            "Unknown HOTKEY_KEY %r — falling back to ctrl_r. Valid values: %s",
            name,
            ", ".join(_VK_MAP),
        )
        return _VK_MAP["ctrl_r"]
    return vk


# ---------------------------------------------------------------------------
# HotkeyListener
# ---------------------------------------------------------------------------


class HotkeyListener(QObject):
    """Listens for a configurable trigger key globally via a native WH_KEYBOARD_LL hook.

    Emits :attr:`recording_started` on keydown and :attr:`recording_stopped`
    on keyup.  Both signals are emitted from the hook thread; Qt routes them
    to the main thread via QueuedConnection automatically.

    **Trigger key** is configured via ``HOTKEY_KEY`` in ``.env``
    (default: ``ctrl_r``).  Use ``HOTKEY_KEY=menu`` for keyboards that emit
    the Application/Context-Menu key from the physical Right-Ctrl position.

    **Hook architecture:** a native ``WH_KEYBOARD_LL`` hook installed via
    ctypes on a dedicated daemon thread that owns its own ``GetMessage`` pump.
    Only the trigger key is intercepted and blocked (returns 1 to the OS).
    All other keystrokes are forwarded immediately via ``CallNextHookEx`` with
    no re-emission and no SendInput from inside the hook callback.

    This replaces the previous ``pynput suppress=True`` approach which stalled
    the OS keyboard message pump: pynput called ``Controller().press(key)``
    (SendInput) from inside the hook callback for every non-trigger keystroke,
    creating re-entrant message-queue pressure that froze all keyboard input
    globally and caused text injection events to be dropped.

    **Text injection compatibility:** ``injector.py`` injects via
    ``SendInput + KEYEVENTF_UNICODE``, which sets ``LLKHF_INJECTED`` on every
    event.  This hook detects that flag and forwards injected events directly
    via ``CallNextHookEx``, so typed characters always reach the target
    application unmodified.

    **Key-repeat debounce:** OS key-repeat fires repeated keydown events while
    the trigger is held.  The ``_held`` flag deduplicates them so
    ``recording_started`` is emitted exactly once per physical key press.
    A secondary time-based debounce (``HOTKEY_DEBOUNCE_MS``) prevents
    re-triggering immediately after a recording stops.
    """

    recording_started = Signal()
    recording_stopped = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._trigger_vk: int = _resolve_trigger_vk(config.HOTKEY_KEY_NAME)
        self._recording: bool = False
        self._held: bool = False
        self._last_stop_ts: float = 0.0
        self._hook_handle: int = 0
        self._hook_thread: threading.Thread | None = None
        self._thread_id: int = 0
        # Strong reference prevents the ctypes callback from being garbage-
        # collected while the hook is active.  Freeing the callable object
        # while Windows holds a pointer to it causes an access violation.
        self._hook_proc_ref: object = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Install the low-level keyboard hook on a dedicated message-pump thread."""
        if self._hook_thread is not None:
            return
        if sys.platform != "win32":
            logger.warning(
                "HotkeyListener: WH_KEYBOARD_LL requires Windows — listener not started"
            )
            return
        self._hook_thread = threading.Thread(
            target=self._run_hook_thread,
            name="aura-hotkey",
            daemon=True,
        )
        self._hook_thread.start()
        logger.info(
            "Hotkey listener started (trigger vk=0x%02X, suppress=trigger-only)",
            self._trigger_vk,
        )

    def stop(self) -> None:
        """Remove the hook and shut down the message-pump thread."""
        if self._thread_id and sys.platform == "win32":
            _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._hook_thread is not None:
            self._hook_thread.join(timeout=2.0)
            self._hook_thread = None
        self._thread_id = 0
        logger.info("Hotkey listener stopped")

    # ------------------------------------------------------------------
    # Hook thread — owns the Windows message pump
    # ------------------------------------------------------------------

    def _run_hook_thread(self) -> None:
        self._thread_id = _kernel32.GetCurrentThreadId()

        proc = _HOOKPROC(self._hook_callback)
        self._hook_proc_ref = proc  # keep alive for the hook's lifetime

        hook = _user32.SetWindowsHookExW(WH_KEYBOARD_LL, proc, None, 0)
        if not hook:
            err = _kernel32.GetLastError()
            logger.error(
                "SetWindowsHookExW failed (GetLastError=%d) — hotkey will not work",
                err,
            )
            return

        self._hook_handle = hook
        msg = ctypes.wintypes.MSG()
        try:
            while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                _user32.TranslateMessage(ctypes.byref(msg))
                _user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            _user32.UnhookWindowsHookEx(hook)
            self._hook_handle = 0
            self._hook_proc_ref = None

    # ------------------------------------------------------------------
    # Hook callback (invoked by the OS on the hook thread)
    # ------------------------------------------------------------------

    def _hook_callback(
        self, n_code: int, w_param: int, l_param: int
    ) -> int:
        if n_code >= 0:
            try:
                kbd = ctypes.cast(
                    l_param, ctypes.POINTER(_KBDLLHOOKSTRUCT)
                ).contents
                if kbd.vkCode == self._trigger_vk and not (kbd.flags & LLKHF_INJECTED):
                    if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                        self._on_trigger_down()
                        return 1  # consumed — do not deliver to other hooks or apps
                    if w_param in (WM_KEYUP, WM_SYSKEYUP):
                        self._on_trigger_up()
                        return 1  # consumed
            except Exception:
                logger.exception("Error in keyboard hook callback")

        return _user32.CallNextHookEx(self._hook_handle, n_code, w_param, l_param)

    # ------------------------------------------------------------------
    # Trigger-key state machine (called from hook callback on hook thread)
    # ------------------------------------------------------------------

    def _on_trigger_down(self) -> None:
        if self._held:
            return  # OS key-repeat for held trigger — ignore
        self._held = True
        if not self._recording:
            elapsed_ms = (time.monotonic() - self._last_stop_ts) * 1000
            if elapsed_ms >= config.HOTKEY_DEBOUNCE_MS:
                self._recording = True
                logger.debug("Hotkey: recording_started emitted")
                self.recording_started.emit()

    def _on_trigger_up(self) -> None:
        self._held = False
        if self._recording:
            self._recording = False
            self._last_stop_ts = time.monotonic()
            logger.debug("Hotkey: recording_stopped emitted")
            self.recording_stopped.emit()
