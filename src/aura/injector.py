from __future__ import annotations

import logging
import sys
import time

import pyperclip
from pynput.keyboard import Controller, Key

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Win32 direct modifier-release (Windows only)
# ---------------------------------------------------------------------------
#
# pynput's Controller.release() does NOT set KEYEVENTF_EXTENDEDKEY for extended
# virtual-key codes.  Without that flag the OS scan-code matching fails for
# Right Ctrl (0xA3), Right Alt (0xA5), and the Application/Menu key (0x5D):
# the key's extended-key slot stays logically "down", so subsequent character
# injections via keyboard.type() arrive with a modifier held — triggering
# accidental OS shortcuts (Ctrl+Z, Ctrl+V, …).
#
# Using a private WinDLL instance avoids argtypes/restype conflicts with pynput
# or any other library that may have mutated the shared ctypes.windll.user32
# function objects.

if sys.platform == "win32":
    import ctypes
    import ctypes.wintypes

    _user32_inj = ctypes.WinDLL("user32")  # type: ignore[attr-defined]
    _user32_inj.keybd_event.restype = None
    _user32_inj.keybd_event.argtypes = [
        ctypes.wintypes.BYTE,   # bVk
        ctypes.wintypes.BYTE,   # bScan
        ctypes.wintypes.DWORD,  # dwFlags
        ctypes.POINTER(ctypes.wintypes.ULONG),  # dwExtraInfo
    ]

    _KEYEVENTF_KEYUP: int = 0x0002
    _KEYEVENTF_EXTENDEDKEY: int = 0x0001

    # (vk_code, is_extended_key) — extended keys require KEYEVENTF_EXTENDEDKEY
    # so the OS can match the scan-code slot and clear the "held" state.
    _MODIFIER_VKS: tuple[tuple[int, bool], ...] = (
        (0x11, False),  # VK_CONTROL
        (0xA2, False),  # VK_LCONTROL
        (0xA3, True),   # VK_RCONTROL  (extended)
        (0x12, False),  # VK_MENU (Alt)
        (0xA4, False),  # VK_LMENU
        (0xA5, True),   # VK_RMENU     (extended)
        (0x10, False),  # VK_SHIFT
        (0xA0, False),  # VK_LSHIFT
        (0xA1, False),  # VK_RSHIFT
        (0x5D, True),   # VK_APPS / Application / Context-Menu key (extended)
    )
else:
    _user32_inj = None  # type: ignore[assignment]
    _KEYEVENTF_KEYUP: int = 0  # type: ignore[misc]
    _KEYEVENTF_EXTENDEDKEY: int = 0  # type: ignore[misc]
    _MODIFIER_VKS: tuple[tuple[int, bool], ...] = ()  # type: ignore[misc]

# ---------------------------------------------------------------------------
# pynput modifier list (secondary release layer / non-Windows fallback)
# ---------------------------------------------------------------------------

# Sending KeyUp for an already-released key is a no-op at the OS level, so it
# is safe to unconditionally release the full list as a belt-and-suspenders
# measure after the Win32 direct-release pass above.
_MODIFIER_KEYS: tuple[Key, ...] = (
    Key.alt,
    Key.alt_l,
    Key.alt_r,
    Key.shift,
    Key.shift_l,
    Key.shift_r,
    Key.ctrl,
    Key.ctrl_l,
    Key.ctrl_r,
    Key.cmd,
    Key.menu,
)


class TextInjector:
    """Injects text at the current cursor position in the active application.

    Primary method: direct keystroke injection via ``keyboard.type()``.
    On Windows, pynput uses ``SendInput`` with ``KEYEVENTF_UNICODE``, so every
    character is an independent OS-level event that:
    - requires no clipboard interaction (no race conditions, no restore step)
    - is unaffected by modifier ghosting (the hotkey key can remain latched at
      the OS level after release; typing each character avoids this entirely)
    - works natively with Ukrainian, Russian and any other Unicode script

    Fallback: clipboard (pyperclip + Ctrl+V + restore).  Retained for edge
    cases where ``SendInput`` is blocked (e.g. some privileged terminal
    emulators or UAC dialogs).
    """

    def __init__(self) -> None:
        self._keyboard = Controller()

    def paste(self, text: str) -> None:
        """Inject *text* at the active cursor position."""
        if not text:
            return
        try:
            self._paste_via_typing(text)
        except Exception:
            logger.warning("Direct typing failed — falling back to clipboard paste", exc_info=True)
            try:
                self._paste_via_clipboard(text)
            except Exception:
                logger.exception("Clipboard paste fallback also failed")

    # ------------------------------------------------------------------
    # Strategies
    # ------------------------------------------------------------------

    def _paste_via_typing(self, text: str) -> None:
        """Primary: inject each character via SendInput + KEYEVENTF_UNICODE."""
        self._release_modifiers()
        time.sleep(0.05)  # give the OS a moment to clear the modifier state
        self._keyboard.type(text)
        logger.debug("Text injected via keyboard.type() (%d chars)", len(text))

    def _paste_via_clipboard(self, text: str) -> None:
        """Fallback: place text in clipboard and simulate Ctrl+V."""
        previous: str = ""
        try:
            previous = pyperclip.paste() or ""
        except Exception:
            logger.debug("Could not read current clipboard contents")

        pyperclip.copy(text)
        time.sleep(0.1)  # allow clipboard to propagate to all processes

        self._release_modifiers()
        time.sleep(0.05)  # give the OS a moment to clear the modifier state

        with self._keyboard.pressed(Key.ctrl):
            self._keyboard.press("v")
            self._keyboard.release("v")

        # Wait long enough for the target app to fully read the clipboard
        # before we overwrite it with the restored content.
        time.sleep(0.3)

        try:
            pyperclip.copy(previous)
        except Exception:
            logger.debug("Could not restore previous clipboard contents")

        logger.debug("Text injected via clipboard (%d chars)", len(text))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _release_modifiers(self) -> None:
        """Send KeyUp for every modifier key that could be ghosting.

        On Windows the primary pass uses Win32 keybd_event with the correct
        KEYEVENTF_EXTENDEDKEY flag for extended-key VK codes (Right Ctrl,
        Right Alt, VK_APPS).  Without that flag the OS does not clear the
        extended-key scan-code slot, leaving those modifiers logically "down"
        when keyboard.type() injects characters — triggering phantom shortcuts.

        The pynput pass follows as a secondary layer: sending KeyUp for a key
        that is already released is a no-op at the OS level, so it is safe
        and covers any modifier not in the Win32 table (e.g. Windows/Cmd key).
        """
        if sys.platform == "win32" and _user32_inj is not None:
            for vk, extended in _MODIFIER_VKS:
                flags = _KEYEVENTF_KEYUP | (_KEYEVENTF_EXTENDEDKEY if extended else 0)
                try:
                    _user32_inj.keybd_event(vk, 0, flags, None)
                except Exception:
                    pass
        for key in _MODIFIER_KEYS:
            try:
                self._keyboard.release(key)
            except Exception:
                pass  # unknown key on this layout — skip silently
