from __future__ import annotations

import glob
import logging
import logging.handlers
import os
import signal
import sys
import tempfile

# Under pythonw.exe sys.stdout and sys.stderr are None.  Redirect both to
# devnull before the first third-party import — PySide6 and python-dotenv
# both write to stderr during initialisation, which crashes with AttributeError
# or OSError before _setup_logging() is ever called.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from aura import config

# Held for the process lifetime to prevent the OS from releasing the mutex
# when the handle is garbage-collected.
_SINGLE_INSTANCE_MUTEX: object = None
_MUTEX_NAME = "Global\\AuraApp_SingleInstance"


def _setup_logging() -> None:
    file_handler = logging.handlers.RotatingFileHandler(
        config.LOG_FILE,
        maxBytes=config.LOG_MAX_BYTES,
        backupCount=config.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    file_handler.setFormatter(fmt)

    # Under pythonw.exe sys.stdout is None — only add the console handler when
    # a real stream is available (i.e. when running from a developer terminal).
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    root.addHandler(file_handler)
    if sys.stdout is not None:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(fmt)
        root.addHandler(stream_handler)


def _acquire_single_instance_lock() -> bool:
    """Create a named Windows mutex and return True if this is the only instance.

    The mutex handle is stored in the module-level ``_SINGLE_INSTANCE_MUTEX``
    variable so the OS does not release it when this function returns.  On
    non-Windows platforms the function always returns True.
    """
    global _SINGLE_INSTANCE_MUTEX
    if sys.platform != "win32":
        return True
    import ctypes  # noqa: PLC0415

    handle = ctypes.windll.kernel32.CreateMutexW(None, True, _MUTEX_NAME)
    _SINGLE_INSTANCE_MUTEX = handle
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def _cleanup_orphaned_temp_files() -> None:
    """Delete any aura_*.wav files left over from a previous crash."""
    pattern = os.path.join(tempfile.gettempdir(), "aura_*.wav")
    logger = logging.getLogger(__name__)
    for path in glob.glob(pattern):
        try:
            os.unlink(path)
            logger.info("Deleted orphaned temp file from previous session")
        except OSError:
            logger.warning("Could not delete orphaned temp file")


def main() -> None:
    _setup_logging()
    logger = logging.getLogger(__name__)

    if not _acquire_single_instance_lock():
        logger.warning("Another Aura instance is already running — exiting.")
        sys.exit(0)

    if not config.OPENAI_API_KEY:
        logger.error(
            "OPENAI_API_KEY is not set.  "
            "Create a .env file next to the executable with: OPENAI_API_KEY=sk-..."
        )
        sys.exit(1)

    _cleanup_orphaned_temp_files()

    # Enable fractional DPI scaling for accurate indicator size on all monitors
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    app.setApplicationName("Aura")
    app.setApplicationVersion("0.1.0")
    # Keep the process alive even when all windows are hidden (tray-only app)
    app.setQuitOnLastWindowClosed(False)

    # Import here to ensure QApplication is created first
    from aura.app import AppController  # noqa: PLC0415

    controller = AppController()
    app.aboutToQuit.connect(controller.shutdown)

    # QApplication replaces the default SIGINT handler, making Ctrl+C a no-op.
    # Restoring SIG_DFL lets the OS deliver the signal normally so the process
    # can be killed from the terminal during development.
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    logger.info("Aura v%s started.  Hold Right Ctrl to record.", app.applicationVersion())
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
