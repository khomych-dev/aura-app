# Aura

> Hold Right Ctrl to record your voice — Aura transcribes it and types the text wherever your cursor is.

Aura is a lightweight Windows background app. It lives in the system tray and stays out of your way until you need it. Press and hold **Right Ctrl**, speak, release — your words appear at the active cursor position in any application.

---

## How it works

1. Hold **Right Ctrl** — a small red dot appears at the top of the screen, recording starts.
2. Release **Right Ctrl** — recording continues for 400 ms of trailing silence (post-roll), then stops.
3. Aura sends the audio to **OpenAI Whisper** and receives the transcription. Language is auto-detected by Whisper from your speech, or can be set manually via the tray menu.
4. The transcribed text is injected at the current cursor position in any application.

No window, no UI, no distraction — just your words appearing as text.

---

## Features

- **Push-to-talk hotkey** — Right Ctrl (configurable); no admin rights required
- **Audio post-roll** — 400 ms of trailing silence after key release so Whisper never clips the last word
- **Language auto-detection** — Whisper automatically detects the spoken language from the audio itself; supports dozens of languages
- **Language override** — tray icon → Language submenu (Auto / UK / EN / RU)
- **Recording indicator** — always-on-top frameless red dot, DPI-aware, disappears immediately on key release
- **Modifier key release** — extended modifiers (Right Ctrl, Right Alt, Menu) are safely released before text injection so no ghost keys reach the target app
- **Single-instance guard** — named mutex prevents two copies from running simultaneously
- **Autostart** — optional Windows Startup shortcut via `install_autostart.py` (no console window)
- **Portable `.exe`** — single-file PyInstaller build, no Python required on the target machine

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| UI | PySide6 — frameless overlay, system tray (`QSystemTrayIcon`) |
| Global hotkey | Native Win32 `WH_KEYBOARD_LL` hook via `ctypes` — no admin rights, no key suppression side-effects |
| Audio capture | `sounddevice` + `soundfile` — WAV streaming to tempfile, no external DLLs |
| Speech-to-text | OpenAI Whisper API (`whisper-1`) |
| Text injection | `ctypes SendInput` (Unicode) + modifier release; clipboard fallback |
| Language detection | Built-in OpenAI Whisper auto-detection |
| Config | `python-dotenv` + `config.py` constants |
| Package manager | `uv` |
| Distribution | PyInstaller 6 — single portable `.exe` |
| CI | GitHub Actions on `windows-latest` — ruff · mypy · pytest · pip-audit |

---

## Requirements

- **Windows 10 or 11** (64-bit)
- **Python 3.11+** and [uv](https://docs.astral.sh/uv/getting-started/installation/):
  ```
  winget install astral-sh.uv
  ```
- **OpenAI API key** — get one at [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
- **Microphone** set as the default recording device in Windows Settings → Sound

---

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/khomych-dev/aura-app.git
cd aura-app

# 2. Install dependencies
uv sync

# 3. Configure your API key
copy .env.example .env
```

Open `.env` and replace the placeholder with your actual key:

```
OPENAI_API_KEY=sk-your-actual-key-here
```

```bash
# 4. Run
uv run aura
```

Aura starts silently. Look for the **Aura icon in the system tray** (bottom-right of the taskbar). Right-click → **Exit Aura** to quit.

---

## Usage

| Action | Result |
|---|---|
| Hold **Right Ctrl** | Recording starts — red dot appears at the top of the screen |
| Release **Right Ctrl** | Recording stops after 400 ms post-roll — text is transcribed and typed |
| Recording < 0.5 s | Silently discarded (too short for Whisper) |
| Recording > 5 min | Auto-stopped (soft limit) |
| Right-click tray → Language | Override transcription language (Auto / UK / EN / RU) |
| Right-click tray → Exit | Quit Aura |

**Works in:** Notepad, Word, Chrome, VS Code, Telegram, Slack — any app that accepts keyboard input.

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | Yes | — | Your OpenAI API key |
| `HOTKEY_KEY` | No | `ctrl_r` | Trigger key — see [Hotkey Configuration](#hotkey-configuration) |

The `.env` file must be in the same folder as `Aura.exe` (portable build) or in the project root (source run).

---

## Hotkey Configuration

The trigger key is controlled by the `HOTKEY_KEY` variable in `.env`:

| Value | Key |
|---|---|
| `ctrl_r` | Right Ctrl *(default)* |
| `menu` | Context Menu / App key (on keyboards that map Right Ctrl to Menu) |
| `f13` | F13 extended function key |
| `f14` | F14 extended function key |
| `f15` | F15 extended function key |

Example — switch to Context Menu key:
```
HOTKEY_KEY=menu
```

---

## Autostart (optional)

To launch Aura automatically when Windows starts:

```bash
uv run python install_autostart.py
```

This creates a shortcut in `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup` that runs Aura silently via `pythonw.exe` — no console window, no UAC prompt.

To remove autostart, delete the shortcut from that folder or re-run the script (it cleans up legacy entries automatically).

---

## Project Structure

```
aura-app/
├── src/aura/
│   ├── main.py           # Entry point: QApplication, DPI policy, single-instance lock
│   ├── app.py            # AppController: wires all components, manages QThread lifecycle
│   ├── config.py         # All constants and .env loading
│   ├── hotkey.py         # HotkeyListener: native WH_KEYBOARD_LL hook via ctypes
│   ├── recorder.py       # AudioRecorder: sounddevice WAV streaming to tempfile
│   ├── transcriber.py    # Transcriber: OpenAI Whisper API client
│   ├── injector.py       # TextInjector: SendInput Unicode injection + modifier release
│   ├── indicator.py      # RecordingIndicator: frameless always-on-top red dot
│   └── tray.py           # TrayIcon: QSystemTrayIcon + Language submenu + Exit
├── tests/                # 94 unit tests, 88.9% coverage
├── assets/
│   └── tray_icon.ico
├── install_autostart.py  # Windows Startup shortcut installer
├── .env.example          # API key template
├── aura.spec             # PyInstaller build spec
└── pyproject.toml        # Dependencies and tool configuration
```

---

## Development

### Run tests

```bash
# All tests with coverage report
uv run pytest --cov=aura --cov-report=term-missing
```

### Lint and type-check

```bash
uv run ruff check src/ tests/
uv run mypy src/
```

### Dependency audit

```bash
uv run pip-audit
```

---

## Build portable .exe

**Requires Windows.** Run once after `uv sync`:

```bash
uv run pyinstaller aura.spec
```

Output: `dist/Aura.exe` — a single portable executable (~60–80 MB). Copy it anywhere with a `.env` file in the same folder:

```
Aura.exe     ← the app
.env         ← your API key (never share this)
```

Double-click `Aura.exe` to run. No Python or other software required on the target machine.

---

## Logs

Aura writes a rotating log to `aura.log` next to the executable (or in the project root when running from source).

| Setting | Value |
|---|---|
| Location | Same folder as `Aura.exe` / project root |
| Max file size | 1 MB |
| Backup count | 3 |

Useful for diagnosing transcription failures, microphone issues, or hotkey conflicts.

---

## Troubleshooting

**"OPENAI_API_KEY is not set"**
Create a `.env` file next to `Aura.exe`:
```
OPENAI_API_KEY=sk-your-key-here
```

**No text appears after speaking**
- Check `aura.log` for transcription errors.
- Ensure your microphone is set as the **default recording device** in Windows Settings → Sound → Input.
- Make sure the recording was at least 0.5 seconds long.

**Recording indicator not visible**
It appears at the very top-center of your primary monitor. It is always-on-top, but some exclusive fullscreen apps may override this.

**Hotkey doesn't trigger**
- Confirm no other application is consuming Right Ctrl globally.
- Try switching to a different trigger via `HOTKEY_KEY=menu` or `HOTKEY_KEY=f13`.

**Two instances running**
Aura uses a named mutex to prevent this. If you see a duplicate, check for leftover processes in Task Manager and kill them before restarting.

---

## CI

GitHub Actions runs on every push to `main` / `develop` and on all pull requests to `main`:

- `ruff check` — style and import linting
- `mypy` — static type checking
- `pytest --cov` — 94 tests, coverage ≥ 70% enforced
- `pip-audit` — dependency vulnerability scan

Runs on `windows-latest` (native Win32 APIs required).

---

## License

MIT — see [LICENSE](LICENSE).
