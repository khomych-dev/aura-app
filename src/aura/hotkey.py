from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import sys
import threading

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

_VK_MAP: dict[str, int] = {
    "ctrl_r": 0xA3,
    "menu": 0x5D,
    "f13": 0x7C,
    "f14": 0x7D,
    "f15": 0x7E,
}

# ---------------------------------------------------------------------------
# Platform-specific ctypes setup
# ---------------------------------------------------------------------------

if sys.platform == "win32":  # pragma: no cover
    _user32 = ctypes.WinDLL("user32")  # type: ignore[attr-defined]
    _kernel32 = ctypes.WinDLL("kernel32")  # type: ignore[attr-defined]

    class _KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode", ctypes.wintypes.DWORD),
            ("scanCode", ctypes.wintypes.DWORD),
            ("flags", ctypes.wintypes.DWORD),
            ("time", ctypes.wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    _HOOKPROC = ctypes.WINFUNCTYPE(  # type: ignore[attr-defined]
        ctypes.c_long,
        ctypes.c_int,
        ctypes.wintypes.WPARAM,
        ctypes.wintypes.LPARAM,
    )

    _user32.SetWindowsHookExW.restype = ctypes.wintypes.HANDLE
    _user32.SetWindowsHookExW.argtypes = [
        ctypes.c_int,
        _HOOKPROC,
        ctypes.wintypes.HINSTANCE,
        ctypes.wintypes.DWORD,
    ]

    _user32.CallNextHookEx.restype = ctypes.c_long
    _user32.CallNextHookEx.argtypes = [
        ctypes.wintypes.HANDLE,
        ctypes.c_int,
        ctypes.wintypes.WPARAM,
        ctypes.wintypes.LPARAM,
    ]

    _user32.UnhookWindowsHookEx.restype = ctypes.wintypes.BOOL
    _user32.UnhookWindowsHookEx.argtypes = [ctypes.wintypes.HANDLE]

    _user32.GetMessageW.restype = ctypes.wintypes.BOOL
    _user32.GetMessageW.argtypes = [
        ctypes.POINTER(ctypes.wintypes.MSG),
        ctypes.wintypes.HWND,
        ctypes.wintypes.UINT,
        ctypes.wintypes.UINT,
    ]

    _user32.TranslateMessage.restype = ctypes.wintypes.BOOL
    _user32.TranslateMessage.argtypes = [ctypes.POINTER(ctypes.wintypes.MSG)]

    _user32.DispatchMessageW.restype = ctypes.c_long
    _user32.DispatchMessageW.argtypes = [ctypes.POINTER(ctypes.wintypes.MSG)]

    _user32.PostThreadMessageW.restype = ctypes.wintypes.BOOL
    _user32.PostThreadMessageW.argtypes = [
        ctypes.wintypes.DWORD,
        ctypes.wintypes.UINT,
        ctypes.wintypes.WPARAM,
        ctypes.wintypes.LPARAM,
    ]

    _kernel32.GetCurrentThreadId.restype = ctypes.wintypes.DWORD
    _kernel32.GetCurrentThreadId.argtypes = []

    _kernel32.GetLastError.restype = ctypes.wintypes.DWORD
    _kernel32.GetLastError.argtypes = []

else:
    _user32 = None  # type: ignore[assignment]
    _kernel32 = None  # type: ignore[assignment]
    _KBDLLHOOKSTRUCT = None  # type: ignore[assignment, misc]
    _HOOKPROC = None  # type: ignore[assignment]


def _resolve_trigger_vk(name: str) -> int:
    vk = _VK_MAP.get(name)
    if vk is None:
        logger.warning(
            "Unknown HOTKEY_KEY %r — falling back to ctrl_r. Valid values: %s",
            name,
            ", ".join(_VK_MAP),
        )
        return _VK_MAP["ctrl_r"]
    return vk


class HotkeyListener(QObject):
    recording_started = Signal()
    recording_stopped = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._trigger_vk: int = _resolve_trigger_vk(config.HOTKEY_KEY_NAME)
        self._recording: bool = False
        self._held: bool = False
        self._hook_handle: int = 0
        self._hook_thread: threading.Thread | None = None
        self._thread_id: int = 0
        self._hook_proc_ref: object = None

    def start(self) -> None:
        if self._hook_thread is not None:
            return
        if sys.platform != "win32":
            logger.warning("HotkeyListener requires Windows")
            return
        self._hook_thread = threading.Thread(
            target=self._run_hook_thread,
            name="aura-hotkey",
            daemon=True,
        )
        self._hook_thread.start()
        logger.info("Hotkey listener started (trigger vk=0x%02X)", self._trigger_vk)

    def stop(self) -> None:
        if self._thread_id and sys.platform == "win32":
            _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._hook_thread is not None:
            self._hook_thread.join(timeout=2.0)
            self._hook_thread = None
        self._thread_id = 0
        logger.info("Hotkey listener stopped")

    def _run_hook_thread(self) -> None:
        self._thread_id = _kernel32.GetCurrentThreadId()
        proc = _HOOKPROC(self._hook_callback)
        self._hook_proc_ref = proc

        hook = _user32.SetWindowsHookExW(WH_KEYBOARD_LL, proc, None, 0)
        if not hook:
            logger.error("SetWindowsHookExW failed")
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

    def _hook_callback(self, n_code: int, w_param: int, l_param: int) -> int:
        should_swallow = False
        if n_code >= 0:
            try:
                kbd = ctypes.cast(l_param, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
                if kbd.vkCode == self._trigger_vk:
                    if not (kbd.flags & LLKHF_INJECTED):
                        should_swallow = True
                        if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                            self._on_trigger_down()
                        elif w_param in (WM_KEYUP, WM_SYSKEYUP):
                            self._on_trigger_up()
            except Exception:
                logger.exception("Error in keyboard hook callback")
        if should_swallow:
            return 1
        return _user32.CallNextHookEx(self._hook_handle, n_code, w_param, l_param)

    def _on_trigger_down(self) -> None:
        if self._held:
            return
        self._held = True
        if not self._recording:
            self._recording = True
            self.recording_started.emit()

    def _on_trigger_up(self) -> None:
        self._held = False
        if self._recording:
            self._recording = False
            self.recording_stopped.emit()
