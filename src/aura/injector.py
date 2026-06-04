from __future__ import annotations

import logging
import queue
import sys
import threading
import time

logger = logging.getLogger(__name__)

if sys.platform == "win32":
    import ctypes
    import ctypes.wintypes

    _user32_inj = ctypes.WinDLL("user32")  # type: ignore[attr-defined]

    INPUT_KEYBOARD = 1
    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_EXTENDEDKEY = 0x0001

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = (
            ("wVk", ctypes.wintypes.WORD),
            ("wScan", ctypes.wintypes.WORD),
            ("dwFlags", ctypes.wintypes.DWORD),
            ("time", ctypes.wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_void_p),
        )

    class _INPUT_UNION(ctypes.Union):  # noqa: N801
        _fields_ = (("ki", KEYBDINPUT), ("padding", ctypes.c_byte * 32))

    class INPUT(ctypes.Structure):
        _anonymous_ = ("_u",)
        _fields_ = (("type", ctypes.wintypes.DWORD), ("_u", _INPUT_UNION))

    _user32_inj.SendInput.restype = ctypes.wintypes.UINT
    _user32_inj.SendInput.argtypes = [ctypes.wintypes.UINT, ctypes.c_void_p, ctypes.c_int]

    _user32_inj.keybd_event.restype = None
    _user32_inj.keybd_event.argtypes = [
        ctypes.wintypes.BYTE,
        ctypes.wintypes.BYTE,
        ctypes.wintypes.DWORD,
        ctypes.c_void_p,
    ]

    _MODIFIER_VKS = (
        (0x11, False),  # VK_CONTROL
        (0xA2, False),  # VK_LCONTROL
        (0x12, False),  # VK_MENU (Alt)
        (0xA4, False),  # VK_LMENU
        (0xA5, True),  # VK_RMENU
        (0x10, False),  # VK_SHIFT
        (0xA0, False),  # VK_LSHIFT
        (0xA1, False),  # VK_RSHIFT
    )
else:
    _user32_inj = None  # type: ignore[assignment]


_PRE_INJECT_DELAY_SEC = 0.05
_KEY_DOWN_DELAY_SEC = 0.015
_KEY_UP_DELAY_SEC = 0.02


class TextInjector:
    """Injects text directly via native Windows Unicode API, avoiding the clipboard entirely."""

    def __init__(self) -> None:
        self._queue: queue.Queue[str] = queue.Queue()
        threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="aura-injector",
        ).start()

    def paste(self, text: str) -> None:
        if not text:
            return
        if sys.platform != "win32" or _user32_inj is None:
            logger.error("Text injection is only supported on Windows in this version.")
            return

        self._queue.put(text)

    def _worker_loop(self) -> None:
        while True:
            text = self._queue.get()
            self._paste_worker(text)
            self._queue.task_done()

    def _paste_worker(self, text: str) -> None:
        try:
            self._release_modifiers()
            time.sleep(_PRE_INJECT_DELAY_SEC)
            self._inject_unicode(text)
            logger.debug("Text injected successfully (%d chars)", len(text))
        except Exception:
            logger.exception("Native text injection failed")

    def _inject_unicode(self, text: str) -> None:
        """Uses Windows SendInput to type characters natively with a micro-delay."""
        for char in text:
            code = ord(char)

            # --- 1. Key Down ---
            input_down = (INPUT * 1)()
            input_down[0].type = INPUT_KEYBOARD
            input_down[0].ki.wVk = 0
            input_down[0].ki.wScan = code
            input_down[0].ki.dwFlags = KEYEVENTF_UNICODE

            _user32_inj.SendInput(1, ctypes.byref(input_down), ctypes.sizeof(INPUT))

            time.sleep(_KEY_DOWN_DELAY_SEC)

            # --- 2. Key Up ---
            input_up = (INPUT * 1)()
            input_up[0].type = INPUT_KEYBOARD
            input_up[0].ki.wVk = 0
            input_up[0].ki.wScan = code
            input_up[0].ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP

            _user32_inj.SendInput(1, ctypes.byref(input_up), ctypes.sizeof(INPUT))

            time.sleep(_KEY_UP_DELAY_SEC)

    def _release_modifiers(self) -> None:
        """Sends KeyUp for standard modifiers (Ctrl, Alt, Shift) to prevent shortcuts."""
        for vk, extended in _MODIFIER_VKS:
            flags = KEYEVENTF_KEYUP | (KEYEVENTF_EXTENDEDKEY if extended else 0)
            try:
                _user32_inj.keybd_event(vk, 0, flags, None)
            except Exception as exc:
                logger.warning("Failed to release modifier: %s", exc)
