# Current Task

> Цей файл читає Director на початку кожної сесії та оновлює після кожного кроку.

## Task

**Aura v0.5.1 — Post-Deploy Critical Fix: ctypes Hook Crash + Silent Autostart + CI Platform**

Three critical failures confirmed after v0.5.0 deploy:
1. `ctypes.ArgumentError` crash in keyboard hook — `.argtypes`/`.restype` not defined on Win32 functions
2. Terminal window still visible on boot — autostart shortcut not targeting `pythonw.exe` directly via absolute path
3. GitHub Actions CI failure — workflow running on Linux runner; `pywin32` has no Linux wheel

## Type

Баг-фікс (є опис) — критичний, production

## Status

Done

## Agent Chain

- [x] Developer — done (hotkey.py ctypes isolation, install_autostart.py path hardening, ci.yml windows-latest)
- [x] QA — APPROVED (75/75, 86.49% coverage, ruff clean, mypy clean; one mypy blocker found and fixed: ctypes.wintypes.LRESULT → ctypes.c_long)

## Spec / Decisions

---

### Bug 1 — ctypes.ArgumentError in SetWindowsHookExW

**Symptom:**
```
hook = _user32.SetWindowsHookExW(WH_KEYBOARD_LL, proc, None, 0)
ctypes.ArgumentError: argument 2: TypeError: expected WinFunctionType instance instead of WinFunctionType
```

**Root cause:** `SetWindowsHookExW` (and `CallNextHookEx`, `UnhookWindowsHookEx`) have no explicit `.argtypes` / `.restype` declared. Without these, ctypes cannot distinguish between two `WINFUNCTYPE`-derived types created in different scopes or import paths — type identity check fails even when the signatures are identical.

**Fix requirements:**
- Explicitly declare `.argtypes` and `.restype` for `SetWindowsHookExW`, `CallNextHookEx`, and `UnhookWindowsHookEx`.
- Define the callback type (`HOOKPROC`) as:
  `ctypes.WINFUNCTYPE(c_int, c_int, c_int, ctypes.POINTER(c_void_p))`
  (or the exact strict ctypes equivalents mapping to LRESULT, int, WPARAM, LPARAM).
- The `proc` instance passed to `SetWindowsHookExW` MUST be created from this same exact type definition.

---

### Bug 2 — Terminal Still Visible on Autostart

**Symptom:** Autostart still opens a console window on boot.

**Root cause:** The shortcut's `TargetPath` is not set to the absolute path of `pythonw.exe` inside the project's `.venv/Scripts/` directory — it may still be using `uv run`, `python.exe`, or a relative path that resolves to a console-backed interpreter.

**Fix requirements:**
- The script that creates the Windows startup shortcut (`.lnk`) must dynamically resolve the **absolute path** to `pythonw.exe` located inside the project's `.venv/Scripts/` directory.
- This absolute path MUST be set as the shortcut's `TargetPath`.
- Must NOT use `uv run`, `python.exe`, or any wrapper that spawns a console window.

---

### Bug 3 — GitHub Actions CI Failure (Linux Runner)

**Symptom:**
```
error: Distribution pywin32==311 ... can't be installed because it doesn't have a source
distribution or wheel for the current platform
hint: You're on Linux...
```

**Root cause:** The GitHub Actions workflow YAML is configured with a Linux/Ubuntu runner. `pywin32` (and other Windows-only deps) have no Linux wheels.

**Fix requirements:**
- Update the workflow YAML to use `runs-on: windows-latest` (or equivalent Windows runner).
- All steps (install, lint, test) must execute on Windows.

---

## Developer Notes

### Bug 1 — hotkey.py (ctypes crash)
- Root cause confirmed: `ctypes.windll.user32` is a process-global shared singleton. `pynput` (still imported transitively via `injector.py`) sets `.argtypes` on the shared `user32.SetWindowsHookExW` with its own `WINFUNCTYPE` type. Our `_HOOKPROC` callback instance — created from a *different* `WINFUNCTYPE` type object — fails ctypes' type-identity check at call time.
- Fix: replaced `ctypes.windll.user32/kernel32` with `ctypes.WinDLL("user32"/"kernel32")` (private, isolated instances). Added explicit `.argtypes` and `.restype` for all 9 Win32 functions called: `SetWindowsHookExW`, `CallNextHookEx`, `UnhookWindowsHookEx`, `GetMessageW`, `TranslateMessage`, `DispatchMessageW`, `PostThreadMessageW`, `GetCurrentThreadId`, `GetLastError`.
- `_HOOKPROC` return type updated from `c_int` to `ctypes.wintypes.LRESULT` (correct LONG_PTR type for LRESULT on x64).
- `argtypes[1]` of `SetWindowsHookExW` is the exact same `_HOOKPROC` type object → type-identity check now passes.

### Bug 2 — install_autostart.py (terminal on autostart)
- Changed `Path(__file__).parent.resolve()` → `Path(__file__).resolve().parent`: resolves symlinks in `__file__` itself before taking the parent, not after — guarantees the correct project root in all invocation scenarios.
- Changed `pythonw = project_root / ".venv" / "Scripts" / "pythonw.exe"` → `.resolve()` call on the result: final `shortcut.TargetPath` is the fully-resolved absolute path to `pythonw.exe` with no symlinks or relative components.

### Bug 3 — ci.yml (Linux runner)
- `runs-on: ubuntu-latest` → `runs-on: windows-latest`
- Removed `apt-get` system-package install step (Linux-only; Windows runner has all needed Qt DLLs via PySide6 wheel)
- `QT_QPA_PLATFORM: offscreen` retained (PySide6 offscreen platform works on Windows CI)
- All other steps (uv, ruff, mypy, pytest, pip-audit) are cross-platform; no changes needed

## Next Step

QA to run full test suite, coverage, ruff, mypy and verify ctypes argtypes are correctly declared.

## Skipped

- Analyst — full root causes and fix requirements specified above
- Architect — no architectural changes; targeted implementation fixes only
- Security — no auth/payments/credentials changes
- AI Safety — no LLM prompt changes
