# Current Task

> Цей файл читає Director на початку кожної сесії та оновлює після кожного кроку.

## Task

**Aura v0.5.0 — Critical Regression Fix: Keyboard Hook Architecture + Autostart Hardening**

Three regressions confirmed after v0.4.0 deployment:
1. Terminal window still visible on boot (autostart shortcut not silently launching)
2. Global keyboard blockage while app is running (pynput suppress=True freezes OS message pump)
3. Transcribed text never pasted (text injection events dropped by blocked message pump)

## Type

Баг-фікс (критичний — зміна архітектури keyboard hook)

## Status

Done

## Agent Chain

- [x] Developer — done (hotkey.py rewrite, tests/test_hotkey.py rewrite, install_autostart.py hardened)
- [x] QA — APPROVED (75/75, 86.49% total, ruff clean, mypy clean)

## Spec / Decisions

---

### Bug 1 — Terminal Window Still Visible on Boot (install_autostart.py)

**Root cause:** `_cleanup_legacy_startup_entries()` only checks TargetPath (inside
project root) and WorkingDirectory (equals project root). If an old Aura shortcut
has an empty WorkingDirectory AND a target outside the project root (e.g. `uv.exe`
in `%LOCALAPPDATA%`), the cleanup misses it. The old console-backed shortcut
survives, runs alongside the new pythonw.exe one, and opens a terminal.

**Fix — strengthen the cleanup heuristic in `_cleanup_legacy_startup_entries()`:**
Add a third condition: `Arguments` field contains `"aura"` (case-insensitive).
A shortcut matches if ANY ONE of these three is true:
1. `TargetPath` is inside `project_root` (existing logic)
2. `WorkingDirectory == project_root` (existing logic)
3. `"aura"` is in the `Arguments` string (new — catches uv/python shortcuts with
   `-m aura.main` regardless of where the interpreter lives)

The new `shortcut.py` target path already correctly points to `.venv/Scripts/pythonw.exe`.
No change needed there — only the cleanup heuristic needs the third condition.

---

### Bug 2 & 3 — Global Keyboard Blockage + Text Injection Failure (hotkey.py)

**Root cause:** `pynput.keyboard.Listener(suppress=True)` installs `WH_KEYBOARD_LL`
with total suppression. On every non-trigger keystroke:
1. The hook callback fires on the listener thread.
2. Our `_on_press` calls `keyboard.Controller().press(key)` (SendInput) from
   **inside** the hook callback.
3. SendInput calls re-enter the same message pump. Under certain Windows scheduler
   conditions (or simply due to re-entrancy of the hook thread's message queue),
   this stalls the OS keyboard message delivery loop — blocking ALL input globally.

Additionally, `keyboard.Controller().type()` in `injector.py` injects characters
via `SendInput` → the events have `LLKHF_INJECTED` set → pynput passes them through
to `CallNextHookEx`. BUT if the hook thread is already stalled (step 3 above),
those injected events are also queued behind the stall → never delivered → text
is dropped.

**Fix — complete rewrite of `hotkey.py` using native `ctypes WH_KEYBOARD_LL`:**

STRICT CONSTRAINT: Remove `pynput.keyboard.Listener` and `keyboard.Controller`
entirely from `hotkey.py`. The new implementation MUST:

1. **Remove ALL re-emission logic.** No `Controller().press()`, no `Controller().release()`.
   Non-trigger keys are passed through by calling `CallNextHookEx` — the OS handles
   them natively. Zero re-emission.

2. **Native hook via ctypes:**
   - Define `_KBDLLHOOKSTRUCT` ctypes Structure
   - Define `_HOOKPROC = ctypes.WINFUNCTYPE(c_int, c_int, WPARAM, LPARAM)`
   - Install via `user32.SetWindowsHookExW(WH_KEYBOARD_LL, proc, None, 0)`

3. **Dedicated hook thread with its own `GetMessage` pump:**
   ```
   hook thread:
     _thread_id = GetCurrentThreadId()
     hook = SetWindowsHookExW(...)
     while GetMessageW(&msg, NULL, 0, 0) > 0:
         TranslateMessage(&msg)
         DispatchMessageW(&msg)
     UnhookWindowsHookEx(hook)
   ```

4. **Hook callback logic:**
   ```
   def _hook_callback(nCode, wParam, lParam):
       if nCode >= 0:
           kbd = cast(lParam, KBDLLHOOKSTRUCT*)
           if kbd.vkCode == trigger_vk AND NOT (kbd.flags & LLKHF_INJECTED):
               if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                   _on_trigger_down()
                   return 1   # ← block ONLY the trigger key
               if wParam in (WM_KEYUP, WM_SYSKEYUP):
                   _on_trigger_up()
                   return 1   # ← block ONLY the trigger key
       return CallNextHookEx(hook, nCode, wParam, lParam)  # pass ALL others
   ```

5. **Skip injected events** (`LLKHF_INJECTED = 0x10`): when `injector.py` calls
   `Controller().type()` → `SendInput` → events have LLKHF_INJECTED set → hook
   skips trigger-check entirely → calls `CallNextHookEx` → text reaches the app.

6. **Stop:** `PostThreadMessageW(thread_id, WM_QUIT, 0, 0)` then join the thread.

7. **Replace `_KEY_NAME_MAP` (pynput Keys) with `_VK_MAP` (Windows VK codes):**
   ```python
   _VK_MAP: dict[str, int] = {
       "ctrl_r": 0xA3,   # VK_RCONTROL
       "menu":   0x5D,   # VK_APPS
       "f13":    0x7C,
       "f14":    0x7D,
       "f15":    0x7E,
   }
   ```

8. **Replace `_on_press` / `_on_release` + `_held_keys: set` with
   `_on_trigger_down()` / `_on_trigger_up()` + `_held: bool`.**
   The debounce logic (`_last_stop_ts`, `HOTKEY_DEBOUNCE_MS`) stays identical.

9. **Emit Qt signals from hook thread** — Qt QueuedConnection posts event to main
   thread's queue and returns immediately, so the hook callback is never stalled.

10. **Windows-only guard:** wrap ctypes Windows-specific definitions behind
    `if sys.platform == "win32"` so the file can be imported on Linux in CI.
    On non-Windows, `start()` logs a warning and returns without crashing.

**`hotkey.py` public API stays identical:**
- `HotkeyListener(parent)` — constructor
- `.start()` — installs hook
- `.stop()` — removes hook
- `recording_started` signal
- `recording_stopped` signal

**Internal fields that tests may access (for unit testing):**
- `._trigger_vk: int` (was `._trigger_key: keyboard.Key`)
- `._recording: bool`
- `._held: bool` (was `._held_keys: set`)
- `._last_stop_ts: float`
- `._hook_thread: threading.Thread | None`
- `._thread_id: int`
- `._on_trigger_down()` (was `._on_press()`)
- `._on_trigger_up()` (was `._on_release()`)

---

### tests/test_hotkey.py — Full Rewrite

The tests MUST be rewritten to match the new internal API:

**Remove:**
- `from pynput import keyboard` import
- `lst._controller = MagicMock()` from fixture (no Controller anymore)
- All tests calling `_on_press(keyboard.Key.X)` or `_on_release(keyboard.Key.X)`
- `test_non_trigger_key_press_is_reemitted` (no re-emission in new arch)
- `test_non_trigger_key_release_is_reemitted`
- `test_trigger_key_is_not_reemitted`
- `test_trigger_key_release_not_reemitted`
- `test_unknown_hotkey_key_name_falls_back_to_ctrl_r` (move to VK map tests)

**Add / Replace:**
- Import `_resolve_trigger_vk, _VK_MAP` from `aura.hotkey`
- `test_resolve_known_key_names()` — assert each entry in `_VK_MAP` resolves correctly
- `test_unknown_key_name_falls_back_to_ctrl_r_vk()` — assert fallback returns `0xA3`
- `test_trigger_vk_resolved_from_config()` — patch `_config.HOTKEY_KEY_NAME="menu"`, new `HotkeyListener()._trigger_vk == 0x5D`
- Replace all `_on_press(Key.ctrl_r)` → `_on_trigger_down()`
- Replace all `_on_release(Key.ctrl_r)` → `_on_trigger_up()`
- `test_recording_starts_on_trigger_down` (was `test_recording_starts_on_ctrl_r`)
- `test_recording_stops_on_trigger_up` (was `test_recording_stops_on_ctrl_r_release`)
- `test_up_without_recording_emits_nothing` (was `test_release_without_recording_emits_nothing`)
- `test_key_repeat_does_not_start_recording` — calls `_on_trigger_down()` 3x (held=True after first)
- `test_key_repeat_does_not_stop_recording` — same
- `test_debounce_prevents_immediate_restart` (calls `_on_trigger_down()` / `_on_trigger_up()`)
- `test_debounce_allows_restart_after_wait` (back-dates `_last_stop_ts`)
- `test_stop_when_no_thread_is_safe` — `listener._hook_thread = None; listener.stop()`
- `test_stop_joins_hook_thread` — set `listener._hook_thread = MagicMock(); listener._thread_id = 0; listener.stop()` → assert `.join()` called
- `test_start_does_not_start_twice` — set `listener._hook_thread = MagicMock(); listener.start()` → hook_thread unchanged
- `test_on_trigger_down_is_exception_safe` — `listener._held = False; listener._recording = False; listener.recording_started = MagicMock(side_effect=RuntimeError); listener._on_trigger_down()` must not propagate (guard in `_hook_callback`, not in `_on_trigger_down` itself — test that `_on_trigger_down` doesn't raise internally)
- `test_menu_key_triggers_recording` — patch config to "menu", new HotkeyListener, `_on_trigger_down()` starts recording
- `test_menu_key_stops_recording` — same, `_on_trigger_up()` stops

**Fixture:**
```python
@pytest.fixture()
def listener(qt_app: object) -> HotkeyListener:
    return HotkeyListener()
```
(No mock needed — no Controller, no real hook installed)

---

### Files Changed

| File | Change |
|---|---|
| `src/aura/hotkey.py` | Complete rewrite — ctypes WH_KEYBOARD_LL, no pynput Listener/Controller |
| `tests/test_hotkey.py` | Complete rewrite — new internal API (_on_trigger_down/up, _VK_MAP) |
| `install_autostart.py` | Add third cleanup condition: Arguments contains "aura" |

### Files NOT Changed

| File | Reason |
|---|---|
| `src/aura/injector.py` | Uses `pynput.keyboard.Controller().type()` — still correct; injected events (LLKHF_INJECTED) pass through new hook via CallNextHookEx |
| `src/aura/config.py` | `HOTKEY_KEY_NAME` stays as-is; only VK resolution changes (in hotkey.py) |
| `src/aura/app.py` | HotkeyListener public API unchanged |
| `src/aura/main.py` | No changes |
| `pyproject.toml` | `pynput` stays (still used by `injector.py`) |

## Next Step

QA to run full test suite, coverage, ruff, mypy and confirm all green.

## Developer Notes

- `src/aura/hotkey.py`: complete rewrite; `pynput.keyboard.Listener` and `Controller` removed entirely; ctypes `WH_KEYBOARD_LL` installed on a dedicated daemon thread; trigger-only blocking via `return 1`; all other keys forwarded via `CallNextHookEx`; `LLKHF_INJECTED` events bypass trigger check so `injector.py` text injection is unaffected; Windows-only ctypes definitions guarded behind `if sys.platform == "win32"` for CI compatibility; `_on_trigger_down` / `_on_trigger_up` replace `_on_press` / `_on_release`; `_held: bool` replaces `_held_keys: set`; `_trigger_vk: int` (VK code) replaces `_trigger_key: keyboard.Key`.
- `tests/test_hotkey.py`: complete rewrite; 22 tests (was 24, but re-emission tests removed as the architecture no longer re-emits); uses `_on_trigger_down()` / `_on_trigger_up()` directly; no pynput imports; `_VK_MAP` and `_resolve_trigger_vk` tested explicitly; lifecycle tests mock `_hook_thread` to avoid actual OS hook installation.
- `install_autostart.py`: `_cleanup_legacy_startup_entries()` now has a third match condition — `"aura" in sc.Arguments.lower()` — catching old shortcuts where the interpreter path is outside the project root *and* WorkingDirectory was not set.
- Result: 75/75 tests, 86.49% coverage, ruff clean, mypy clean.

## Skipped

- Analyst — root causes fully specified in this task file
- Architect — no new dependencies or architectural changes beyond the hotkey rewrite
- Security — no auth/payments/credentials changes
- AI Safety — no LLM prompt changes
