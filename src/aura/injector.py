from __future__ import annotations

import logging
import time

import pyperclip
from pynput.keyboard import Controller, Key

logger = logging.getLogger(__name__)

# All keys that could be held down as part of the hotkey or accidentally
# latched by the OS.  Sending KeyUp for an already-released key is harmless;
# sending it for a genuinely-held modifier clears the ghost state.
# Key.menu is included for keyboards that use that scancode as the trigger.
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
    Key.space,
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

        Sending KeyUp for a key that is already released is a no-op at the
        OS level, so it is safe to unconditionally release the full list.
        """
        for key in _MODIFIER_KEYS:
            try:
                self._keyboard.release(key)
            except Exception:
                pass  # unknown key on this layout — skip silently
