# Changelog

All notable changes to Aura are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning: [Semantic Versioning](https://semver.org/) — MAJOR.MINOR.PATCH.

## [Unreleased]

## [0.1.0] — 2026-05-28

### Added

- Global hotkey **Alt+Space** (press-and-hold) to start/stop voice recording — no admin rights required
- Real-time audio recording via sounddevice; WAV tempfile streamed to disk
- Automatic transcription via **OpenAI Whisper API** (`whisper-1`); language auto-detected (Ukrainian, English, Russian)
- Text injection at the active cursor position via clipboard (Ctrl+V) with clipboard restore; fallback to character-by-character typing
- Frameless red dot recording indicator — always-on-top, click-through, DPI-aware, 15 px at 96 DPI
- System tray icon with **Exit Aura** action; no main window
- Debounce (200 ms) between recordings to prevent accidental re-triggers
- Minimum recording duration (0.5 s) — shorter clips are silently discarded
- Maximum recording duration (300 s) — soft auto-stop limit
- Rotating log file (`aura.log`, 1 MB × 3 backups) next to the executable
- Cleanup of orphaned `aura_*.wav` temp files on startup (crash recovery)
- Graceful shutdown: hotkey listener stopped, in-progress transcription awaited (3 s timeout)
- Portable single-file **`Aura.exe`** via PyInstaller — no Python required on the target machine
- GitHub Actions CI: ruff lint + mypy type-check + pytest (93% coverage) + pip-audit
