# Current Task

> Цей файл читає Director на початку кожної сесії та оновлює після кожного кроку.

## Task

**Aura v0.5.2 — Critical Fix: Modifier Latching + Context Menu Leak + pythonw Crash + CI Runner**

Four confirmed production bugs:
1. **Phantom Shortcuts** — OS shortcut keys (Ctrl+V, Ctrl+Z, etc.) fire during dictated text injection because trigger modifier keys are logically stuck "down" at OS level when `keyboard.Controller().type()` is called.
2. **Context Menu Leak** — `WH_KEYBOARD_LL` hook does not return `1` for `WM_KEYUP` / `WM_SYSKEYUP` of the trigger key (`VK_APPS`, 0x5D), so the OS opens a context menu on key release.
3. **pythonw.exe Crash** — `sys.stdout` / `sys.stderr` are `None` under `pythonw.exe`; third-party libraries (or logging) hit `AttributeError` / `OSError` on write attempts.
4. **GitHub Actions CI Runner** — pipeline still fails if any job/step runs on a non-Windows runner; all jobs must use `runs-on: windows-latest`.

## Type

Баг-фікс (є опис) — критичний, production

## Status

Done

## Agent Chain

- [x] Developer — done (main.py devnull guard, hotkey.py should_swallow, injector.py Win32 keybd_event+EXTENDEDKEY)
- [x] QA — APPROVED (86/86 tests, 88.68% coverage, ruff clean, mypy clean; 11 regression tests added)

## Spec / Decisions

---

### Bug 1 — Phantom Shortcuts (Modifier Latching)

**Symptom:** After the trigger key is pressed and dictated text is injected, the OS fires spurious shortcuts (Ctrl+V, Ctrl+Z, etc.) as if Ctrl/Alt/Shift/Menu are still held.

**Root cause:** Physical trigger key (Menu / Right Ctrl) or its associated modifiers remain logically "down" at the OS level at the moment `keyboard.Controller().type()` executes.

**Fix requirements:**
- Before ANY call to `keyboard.Controller().type()`, send explicit `KeyUp` events for all modifier keys: **Ctrl (left + right), Alt (left + right), Shift (left + right), and Menu** (VK_APPS).
- The release sequence must be complete and unconditional — not conditional on "is key held" — to handle edge cases where the OS state and Python state diverge.
- This must happen strictly BEFORE the `.type()` call, with no code between the releases and the type call that could re-latch a modifier.

---

### Bug 2 — Context Menu Leak (WH_KEYBOARD_LL)

**Symptom:** A Windows context menu appears at the cursor position when the trigger key (Menu key / VK_APPS) is released.

**Root cause:** The low-level keyboard hook (`WH_KEYBOARD_LL`) returns `1` (swallows) only for `WM_KEYDOWN` / `WM_SYSKEYDOWN` of the trigger key, but NOT for `WM_KEYUP` / `WM_SYSKEYUP`. The OS sees the unswallowed `KeyUp` and opens the context menu.

**Fix requirements:**
- The hook callback MUST return `1` for **both** `WM_KEYDOWN` (`0x100`) and `WM_SYSKEYDOWN` (`0x104`) **AND** `WM_KEYUP` (`0x101`) and `WM_SYSKEYUP` (`0x105`) when the key is the configured trigger VK.
- All other keys (non-trigger) must still be forwarded via `CallNextHookEx` as before.

---

### Bug 3 — pythonw.exe Crash (None stdout/stderr)

**Symptom:** App crashes silently immediately on startup when launched via `pythonw.exe` (headless / no console).

**Root cause:** Under `pythonw.exe`, `sys.stdout` and `sys.stderr` are `None`. Any logging `StreamHandler` or third-party library that writes to them will raise `AttributeError` or `OSError`.

**Fix requirements:**
- At the very start of the application entry point (before ANY logging setup or library imports that may write to stdout/stderr), check if `sys.stdout is None` or `sys.stderr is None`.
- If `None`, redirect them to `open(os.devnull, "w")` (or a rotating log file) so all subsequent writes are safely absorbed.
- This guard must be the **first executable code** in the entry point module.

---

### Bug 4 — GitHub Actions CI Runner

**Symptom:** CI pipeline fails on jobs that run on Linux/Ubuntu runners because Windows-only packages (e.g. `pywin32`) have no Linux wheels.

**Fix requirements:**
- In ALL `.github/workflows/*.yml` files, every `runs-on:` value (for every job and every step matrix) must be set to `windows-latest`.
- No job may run on `ubuntu-latest`, `ubuntu-*`, `macos-*`, or any other non-Windows runner.
- Verify that no Linux-specific setup steps (apt-get, etc.) remain after this change.

---

## Developer Notes

### Bug 1 — injector.py (modifier latching / phantom shortcuts)
- Root cause: `pynput.Controller.release()` omits `KEYEVENTF_EXTENDEDKEY` for extended VK codes. VK_RCONTROL (0xA3), VK_RMENU (0xA5), VK_APPS (0x5D) each require this flag so the OS clears the correct scan-code slot.
- Fix: private `_user32_inj = ctypes.WinDLL("user32")` with explicit `keybd_event.argtypes`; `_MODIFIER_VKS` tuple with per-entry `(vk, is_extended)` flag; Win32 `keybd_event` pass runs BEFORE pynput releases.
- `Key.space` removed from `_MODIFIER_KEYS` (not a modifier; was a remnant of the old Ctrl+Shift+Space hotkey).
- Secondary pynput release layer retained — existing `test_paste_primary_releases_modifiers_before_typing` test continues to pass unchanged.

### Bug 2 — hotkey.py (context menu leak)
- Root cause: `_hook_callback` called `_on_trigger_down()` / `_on_trigger_up()` INSIDE `try`, with `return 1` on the next line. If signal emission raised (e.g. because Bug 3's `sys.stderr is None` caused `logger.exception` to raise a secondary exception), the `except` swallowed it and fell through to `CallNextHookEx` — forwarding the trigger key to the OS.
- Fix: `should_swallow = False` declared before the `try`; set to `True` BEFORE the signal emitter call; `if should_swallow: return 1` checked AFTER the `except` — so the key is always consumed even when the state-machine raises.

### Bug 3 — main.py (pythonw.exe crash)
- Root cause: `sys.stdout is not None` guard was only in `_setup_logging()`. PySide6 and python-dotenv write to `sys.stderr` during their import phase — BEFORE `_setup_logging()` is called — causing `AttributeError`/`OSError` under `pythonw.exe`.
- Fix: guard added at module level between stdlib imports and `from PySide6...` — all third-party imports now see valid stream objects.

### Bug 4 — ci.yml (runner)
- Already `runs-on: windows-latest` from v0.5.1 fix. No change required.

## Next Step

QA to run full test suite, coverage, ruff, mypy and verify all three file changes.

## Skipped

- Analyst — full root causes and fix requirements specified in task
- Architect — no architectural changes; targeted implementation fixes only
- Security — no auth/payments/credentials changes
- AI Safety — no LLM prompt changes
