# Aura

> Hold Right Ctrl to record your voice — Aura transcribes it and types the text wherever your cursor is.

Aura is a lightweight Windows background app. It lives in the system tray and stays out of your way until you need it. Press and hold **Right Ctrl**, speak, release — your words appear at the active cursor position in any application.

## What it does

1. You hold **Right Ctrl** — a small red dot appears at the top of the screen, recording starts.
2. You release **Right Ctrl** — recording stops, the dot disappears.
3. Aura sends the audio to **OpenAI Whisper** and receives the transcription.  Language is either auto-detected from your active keyboard layout or set manually via the tray menu.
4. The text is typed at your current cursor position.

No window, no UI, no distraction — just your words appearing as text.

## Tech Stack

- **Language:** Python 3.11+
- **UI:** PySide6 (frameless overlay, system tray)
- **Hotkey:** pynput (global press-and-hold, no admin rights needed)
- **Audio:** sounddevice + soundfile (WAV streaming, no external DLLs)
- **STT:** OpenAI Whisper API (`whisper-1`)
- **Config:** python-dotenv
- **Package manager:** uv
- **Distribution:** PyInstaller (portable single `.exe`)

## Quick Start

### Requirements

- **Python 3.11+** and [uv](https://docs.astral.sh/uv/getting-started/installation/) — install uv with:
  ```
  winget install astral-sh.uv
  ```
- **OpenAI API key** — get one at [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
- **Microphone** connected and set as the default recording device in Windows

### Installation

```bash
# Clone the repository
git clone https://github.com/your/aura-app.git
cd aura-app

# Install dependencies
uv sync

# Set up your API key
copy .env.example .env
```

Open `.env` and replace `sk-...` with your actual OpenAI API key:

```
OPENAI_API_KEY=sk-your-actual-key-here
```

### Run

```bash
uv run aura
```

Aura starts silently. Look for the **Aura icon in the system tray** (bottom-right of the taskbar). Right-click it → **Exit Aura** to quit.

## Usage

| Action | Result |
|--------|--------|
| Hold **Right Ctrl** | Recording starts — red dot appears at top of screen |
| Release **Right Ctrl** | Recording stops — text is transcribed and typed |
| Recording < 0.5 s | Discarded (too short) |
| Recording > 5 min | Auto-stopped (soft limit) |
| Right-click tray icon → Exit | Quits the app |

**Works in:** Notepad, Word, Chrome, VS Code, Telegram, Slack — any app that accepts keyboard input.

**Languages:** Auto-detected from the active Windows keyboard layout (Ukrainian, English, Russian and more). Override at any time via the tray icon **Language** submenu.

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENAI_API_KEY` | Your OpenAI API key — required | `sk-proj-...` |

The `.env` file must be in the same folder as the `.exe` (for the portable build) or in the project root (for the source run).

## Project Structure

```
aura-app/
├── src/aura/
│   ├── main.py         # Entry point: QApplication, DPI policy, startup
│   ├── app.py          # AppController: wires all components, manages threads
│   ├── config.py       # Constants and .env loading
│   ├── hotkey.py       # HotkeyListener: Right Ctrl press-and-hold via pynput
│   ├── recorder.py     # AudioRecorder: sounddevice WAV streaming to tempfile
│   ├── transcriber.py  # Transcriber: OpenAI Whisper API client
│   ├── injector.py     # TextInjector: clipboard paste with restore, fallback typing
│   ├── indicator.py    # RecordingIndicator: frameless red dot overlay
│   └── tray.py         # TrayIcon: system tray with Exit action
├── tests/              # 51 unit tests, 93% coverage
├── assets/
│   └── tray_icon.ico   # Tray icon (replace with your own)
├── .env.example        # API key template
├── aura.spec           # PyInstaller build spec
└── pyproject.toml      # Dependencies and tool config
```

## Tests

```bash
# Run all tests with coverage report
uv run pytest --cov=aura --cov-report=term-missing

# Lint
uv run ruff check src/ tests/

# Type check
uv run mypy src/
```

## Build portable .exe

**Requires Windows.** Run once after `uv sync`:

```bash
uv run pyinstaller aura.spec
```

The output is `dist/Aura.exe` — a single portable executable (~60–80 MB). Copy it anywhere along with a `.env` file in the same folder.

```
Aura.exe          ← the app
.env              ← your API key (never share this)
```

Double-click `Aura.exe` to run. No Python or other software needed on the target machine.

## Logs

Aura writes a rotating log to `aura.log` next to the executable (or in the project root when running from source). Maximum size: 1 MB × 3 backup files. Useful for diagnosing transcription or microphone issues.

## Troubleshooting

**"OPENAI_API_KEY is not set"** — Create a `.env` file next to `Aura.exe` containing:
```
OPENAI_API_KEY=sk-your-key-here
```

**No text pasted after speaking** — Check `aura.log` for transcription errors. Ensure your microphone is the default recording device in Windows Settings → Sound.



**Recording indicator not visible** — It appears at the very top-center of your primary monitor. Check if another window is covering it (it's always-on-top, but some fullscreen apps may override this).

## License

MIT — see [LICENSE](LICENSE).
