# Project Memory

> Цей файл читає Director на початку кожної сесії.
> Оновлюється після завершення кожного завдання.

## Stack

- Language: Python 3.11+
- Framework: PySide6 (UI), pynput (hotkey), sounddevice + soundfile (audio), openai SDK (Whisper API)
- Database: —
- Infrastructure: PyInstaller (portable .exe)
- Package manager: uv
- Deploy platform: Windows 10/11 portable .exe

## Architecture Decisions

- [ADR-001] PySide6 як UI бібліотека — LGPL ліцензія дозволяє .exe дистрибуцію; Qt.WA_ShowWithoutActivating вирішує no-focus вимогу; нативний QSystemTrayIcon; правильна DPI підтримка
- [ADR-002] pynput для global hotkey (press-and-hold) — єдина бібліотека з нативним on_press/on_release без адмін прав; daemon thread не блокує Qt loop
- [ADR-003] sounddevice + soundfile для аудіо — без зовнішніх DLL, numpy-based streaming, PyInstaller-friendly
- [ADR-004] Event-driven архітектура з Qt signals/slots (QueuedConnection) — thread-safe cross-thread комунікація без ручного mutex
- [ADR-005] keyboard.type() як primary injection strategy — SendInput+KEYEVENTF_UNICODE обходить clipboard race condition і Alt-ghosting (Ctrl+Alt+V з tray-only процесу); clipboard залишений як fallback
- [ADR-006] ~~pynput suppress=True~~ — SUPERSEDED by ADR-008
- [ADR-008] Native ctypes WH_KEYBOARD_LL replaces pynput Listener: hook installed on dedicated daemon thread with GetMessage pump; only trigger VK blocked (return 1); all other keys forwarded via CallNextHookEx; LLKHF_INJECTED events bypass trigger-check entirely so injector.py SendInput reaches apps; trigger key mapped via _VK_MAP (string→VK code); configured via HOTKEY_KEY env var (default ctrl_r; also supports menu/f13-f15)
- [ADR-007] Language detection via ctypes Win32 API — GetKeyboardLayout на foreground window дає LANGID активної розкладки; резолюція в момент keyup (foreground window ще належить користувачу); fallback None = Whisper auto-detect

## Project Structure

```
aura-app/
├── src/
│   └── aura/
│       ├── __init__.py
│       ├── main.py           # точка входу: QApplication, AppController, event loop
│       ├── app.py            # AppController: оркеструє всі компоненти
│       ├── config.py         # константи: HOTKEY, SUPPORTED_LANGUAGES, SAMPLE_RATE, MAX_DURATION
│       ├── hotkey.py         # HotkeyListener: pynput wrapper, on_press/on_release сигнали
│       ├── recorder.py       # AudioRecorder: sounddevice запис, tempfile управління
│       ├── transcriber.py    # Transcriber: OpenAI Whisper API клієнт
│       ├── injector.py       # TextInjector: pyperclip + Ctrl+V + restore, fallback
│       ├── indicator.py      # RecordingIndicator: PySide6 frameless, червоний кружечок
│       ├── lang_detector.py  # Win32 ctypes: активна мова клавіатури → ISO code
│       └── tray.py           # TrayIcon: QSystemTrayIcon, Language submenu + Exit
├── assets/
│   └── tray_icon.ico
├── tests/
├── .env.example
├── .env                      # gitignored
├── pyproject.toml
├── aura.spec                 # PyInstaller spec
└── README.md
```

## Completed

- 2026-05-28 Сесія 1: Виправлено 3 системних баги (uv venv isolation, pip→uv, @тег handoff для 01/02/03)
- 2026-05-28 Сесія 2: Повний static prompt audit — виправлено 22 вразливості у всіх 10 agent files (00–09)
- 2026-05-28 Сесія 3: Aura MVP — повний цикл Analyst→Architect→Developer→Security→QA→DevOps
  - 51/51 тести green, coverage 93.79%, ruff+mypy clean
  - CI/CD: .github/workflows/ci.yml (ubuntu + offscreen Qt)
  - Distribution: aura.spec (PyInstaller 6, single .exe)

## Completed

- 2026-05-29 Sесія 4: Bug fix — 3 root-cause threading bugs in Whisper transcription flow resolved:
  - `Qt.ConnectionType.QueuedConnection` for pynput→AppController signals (cross-thread deadlock)
  - `self._current_worker` strong reference prevents GC from killing worker before `run()` (silent C++ crash)
  - `_is_worker_running()` helper + `_clear_worker_ref` clears both refs (stale wrapper RuntimeError on 2nd recording)

## Completed (continued)

- 2026-06-01 Сесія 9: Critical Regression Fix v0.5.0 — Keyboard Hook Architecture + Autostart Hardening:
  - `hotkey.py`: complete rewrite; `pynput suppress=True` + re-emission replaced by native `ctypes WH_KEYBOARD_LL`; dedicated daemon thread with `GetMessage` pump; only trigger key blocked (`return 1`); all other keys forwarded via `CallNextHookEx`; `LLKHF_INJECTED` guard ensures `injector.py` text injection passes through; `_VK_MAP` replaces pynput Key enum; `_on_trigger_down/_on_trigger_up` replace `_on_press/_on_release`; `_held: bool` replaces `_held_keys: set`
  - `tests/test_hotkey.py`: complete rewrite — 22 tests, no pynput imports, covers VK map, debounce, recording state, lifecycle, menu key
  - `install_autostart.py`: `_cleanup_legacy_startup_entries()` gains third match condition: `"aura" in sc.Arguments.lower()` — catches old shortcuts where interpreter is outside project root with empty WorkingDirectory
  - ADR updated: [ADR-002] and [ADR-006] superseded — see ADR-008
  - 75/75 tests, 86.49% coverage, ruff clean, mypy clean

## Known Issues

<!-- all known issues resolved as of 2026-06-01 -->

## Completed (continued)

- 2026-06-01 Сесія 11: Critical Fix v0.5.2 — Modifier Latching + Context Menu Leak + pythonw Crash:
  - `injector.py`: private `_user32_inj = ctypes.WinDLL("user32")`; `_MODIFIER_VKS` with per-entry `(vk, is_extended)` flag; `_release_modifiers()` sends `keybd_event` with `KEYEVENTF_EXTENDEDKEY` for extended VK codes (VK_RCONTROL, VK_RMENU, VK_APPS) BEFORE pynput secondary layer; `Key.space` removed from `_MODIFIER_KEYS`
  - `hotkey.py`: `_hook_callback` refactored with `should_swallow` flag set BEFORE signal emitter calls — trigger key always consumed even if state machine raises (context menu leak fix)
  - `main.py`: `sys.stdout`/`sys.stderr` → devnull guard moved to module level before first third-party import (PySide6, python-dotenv write to stderr during import)
  - 11 regression tests added (7 `_hook_callback` + 4 Win32 modifier release)
  - 86/86 tests, 88.68% coverage, ruff clean, mypy clean

## Completed (continued)

- 2026-06-01 Сесія 10: Post-Deploy Critical Fix v0.5.1 — ctypes Hook Crash + Silent Autostart + CI Platform:
  - `hotkey.py`: `ctypes.windll.user32/kernel32` → private `ctypes.WinDLL("user32"/"kernel32")` instances; explicit `.argtypes`/`.restype` for all 9 Win32 functions (`SetWindowsHookExW`, `CallNextHookEx`, `UnhookWindowsHookEx`, `GetMessageW`, `TranslateMessage`, `DispatchMessageW`, `PostThreadMessageW`, `GetCurrentThreadId`, `GetLastError`); `_HOOKPROC` return type → `c_long` (mypy-safe LRESULT substitute); `argtypes[1]` references same `_HOOKPROC` type object used to create `proc` → ctypes type-identity check passes
  - `install_autostart.py`: `Path(__file__).parent.resolve()` → `Path(__file__).resolve().parent`; pythonw path built with `.resolve()` — guaranteed fully-resolved absolute path to `.venv/Scripts/pythonw.exe`
  - `ci.yml`: `runs-on: ubuntu-latest` → `runs-on: windows-latest`; removed `apt-get` Linux step; Windows runner installs pywin32 and all Windows-only deps from their native wheels
  - 75/75 tests, 86.49% coverage, ruff clean, mypy clean

## Completed (continued)

- 2026-05-30 Сесія 7: Silent Autostart Fix + Right Ctrl Hotkey (v0.3.0):
  - `install_autostart.py`: bypass uv entirely; shortcut targets `.venv/Scripts/pythonw.exe -m aura.main` directly — guaranteed no console window
  - `hotkey.py`: trigger → Right Ctrl only; key-repeat debounce via `if key in _held_keys: return` at top of `_on_press`; removed `_CTRL_KEYS`, `_SHIFT_KEYS`, `_ctrl_held()`, `_shift_held()`
  - String refs updated in 7 files: hotkey.py, app.py, main.py, tray.py, injector.py, config.py, README.md
  - `tests/test_hotkey.py`: rewritten for Right Ctrl; 16 tests including 2 new key-repeat debounce tests
  - 70/70 tests pass, 92.78% coverage, ruff+mypy clean

## Completed (continued)

- 2026-05-30 Сесія 8: Critical Bug Fix — Autostart & Hotkey v0.4.0:
  - `main.py`: StreamHandler guarded behind `sys.stdout is not None` (pythonw.exe fix);
    `_acquire_single_instance_lock()` named mutex prevents duplicate instances.
  - `install_autostart.py`: `_cleanup_legacy_startup_entries()` scans ALL `.lnk`
    files in Startup folder and deletes any targeting the project root;
    `_cleanup_registry_run_key()` removes `HKCU\…\Run\Aura` if present.
  - `config.py`: `HOTKEY_KEY_NAME = HOTKEY_KEY env var` (default `"ctrl_r"`).
  - `hotkey.py`: `suppress=True` listener; non-trigger keys re-emitted via
    `keyboard.Controller()` (no infinite loop — pynput skips LLKHF_INJECTED events);
    `_KEY_NAME_MAP` supports `ctrl_r`, `menu`, `f13`-`f15`; unknown names fall back.
  - `injector.py`: `Key.menu` added to `_MODIFIER_KEYS`.
  - `tests/test_hotkey.py`: `_controller` mocked in fixture; 8 new tests (24 total).
  - 78/78 tests, 92.65% coverage, ruff+mypy clean.

- 2026-05-29 Сесія 6: Deployment Polish — Silent Autostart & Log Fix:
  - `src/aura/main.py` line 85: log string corrected to `"Hold Ctrl+Shift+Space to record."`
  - `install_autostart.py` (new, project root): creates Windows Startup `.lnk` shortcut via pywin32; silent launch via `uvw run aura`; falls back to `.venv/Scripts/pythonw.exe -m aura.main`; WindowStyle=7; all error paths guarded with explicit messages
  - 79/79 tests pass, ruff+mypy clean

## Completed (continued)

- 2026-05-29 Сесія 5: UX & Stability Update v0.2.0 — Developer+QA:
  - Bug 1: Hotkey змінено Alt+Space → Ctrl+Shift+Space (Windows System Menu conflict fix)
  - Bug/Feature 2: Language detection — новий lang_detector.py (ctypes Win32 API); Language submenu у tray (Auto/UK/EN/RU); language propagated через transcriber до Whisper API
  - 79/79 тести, 92.88% coverage, ruff+mypy clean
