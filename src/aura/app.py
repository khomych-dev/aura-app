from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot

from aura import config, lang_detector
from aura.hotkey import HotkeyListener
from aura.indicator import RecordingIndicator
from aura.injector import TextInjector
from aura.recorder import AudioRecorder
from aura.transcriber import Transcriber
from aura.tray import TrayIcon

logger = logging.getLogger(__name__)


class _TranscriptionWorker(QObject):
    """Runs Whisper transcription in a dedicated QThread.

    Always cleans up the temp audio file on completion, regardless of
    whether transcription succeeded or failed.
    """

    finished = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        transcriber: Transcriber,
        audio_path: str,
        language: str | None = None,
    ) -> None:
        super().__init__()
        self._transcriber = transcriber
        self._audio_path = audio_path
        self._language = language

    @Slot()
    def run(self) -> None:
        try:
            text = self._transcriber.transcribe(self._audio_path, language=self._language)
            self.finished.emit(text)
        except Exception as exc:
            logger.exception("Transcription failed")
            try:
                self.error.emit(str(exc))
            except Exception:
                logger.exception("error signal emit failed")
        finally:
            try:
                AudioRecorder.cleanup(self._audio_path)
            except Exception:
                logger.exception("Temp file cleanup failed")


class AppController(QObject):
    """Central orchestrator — wires all components together.

    Lifecycle::

        controller = AppController()
        # ... Qt event loop runs ...
        controller.shutdown()   # called by app.aboutToQuit
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._recorder = AudioRecorder()
        self._transcriber = Transcriber()
        self._injector = TextInjector()

        self._indicator = RecordingIndicator()
        self._tray = TrayIcon()
        self._hotkey = HotkeyListener()

        self._worker_thread: QThread | None = None
        # Strong Python reference to the worker — prevents GC from destroying
        # the QObject before QThread's event loop can invoke run().
        self._current_worker: _TranscriptionWorker | None = None

        # pynput runs in a plain Python threading.Thread (not a QThread).
        # AutoConnection does not reliably produce QueuedConnection in that
        # case — PySide6 may fall back to DirectConnection, executing the slot
        # in the pynput daemon thread.  Constructing QThread/QObject from a
        # foreign thread deadlocks Qt internally.  Forcing QueuedConnection
        # guarantees the slots always run in the Qt main-thread event loop.
        self._hotkey.recording_started.connect(
            self._on_recording_started, Qt.ConnectionType.QueuedConnection
        )
        self._hotkey.recording_stopped.connect(
            self._on_recording_stopped, Qt.ConnectionType.QueuedConnection
        )

        self._hotkey.start()
        logger.info("AppController ready — hold Right Ctrl to dictate")

    # ------------------------------------------------------------------
    # Hotkey slots  (run in Qt main thread via QueuedConnection)
    # ------------------------------------------------------------------

    @Slot()
    def _on_recording_started(self) -> None:
        logger.debug("Recording started")
        try:
            self._recorder.start()
        except RuntimeError:
            logger.exception("Cannot start recording")
            return
        self._indicator.show()

    @Slot()
    def _on_recording_stopped(self) -> None:
        logger.debug("Recording stopped")
        self._indicator.hide()

        audio_path = self._recorder.stop()
        if audio_path is None:
            return

        if self._is_worker_running():
            logger.warning("Previous transcription still in progress — discarding new audio")
            AudioRecorder.cleanup(audio_path)
            return

        # Resolve language while the user's window is still the foreground window.
        language = self._resolve_language()
        self._start_transcription(audio_path, language)

    # ------------------------------------------------------------------
    # Language resolution
    # ------------------------------------------------------------------

    def _resolve_language(self) -> str | None:
        """Return the ISO code to pass to Whisper, or ``None`` for auto-detect.

        If the tray is set to ``'auto'``, the active window's keyboard layout
        is probed via Win32 API.  An explicit tray selection bypasses detection.
        """
        selected = self._tray.language
        if selected == config.DEFAULT_LANGUAGE:  # "auto"
            detected = lang_detector.get_active_language()
            if detected:
                logger.debug("Auto-detected language: %s", detected)
            return detected
        logger.debug("Using manually selected language: %s", selected)
        return selected

    # ------------------------------------------------------------------
    # Transcription
    # ------------------------------------------------------------------

    def _is_worker_running(self) -> bool:
        """Return True only if the previous QThread is still alive.

        Guards against ``RuntimeError: Internal C++ object already deleted``
        that PySide6 raises when calling methods on a QThread whose C++ side
        has been destroyed by ``deleteLater`` while the Python wrapper still
        exists.
        """
        if self._worker_thread is None:
            return False
        try:
            return self._worker_thread.isRunning()
        except RuntimeError:
            self._worker_thread = None
            return False

    def _start_transcription(self, audio_path: str, language: str | None = None) -> None:
        thread = QThread(self)
        worker = _TranscriptionWorker(self._transcriber, audio_path, language)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_transcription_done)
        worker.error.connect(self._on_transcription_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        # _clear_worker_ref fires after deleteLater is scheduled, clearing both
        # Python-side references so the next recording sees a clean slate.
        thread.finished.connect(self._clear_worker_ref)

        # Keep a strong Python reference so GC cannot destroy the worker between
        # _start_transcription() returning and QThread calling run().
        self._current_worker = worker
        self._worker_thread = thread
        thread.start()

    @Slot()
    def _clear_worker_ref(self) -> None:
        """Release Python references after the QThread has finished.

        Called via thread.finished signal.  Clears both the worker and the
        thread wrapper so ``_is_worker_running`` sees None on the next call
        and ``deleteLater`` can fully reclaim the C++ objects without the
        Python wrapper holding a stale pointer.
        """
        self._current_worker = None
        self._worker_thread = None

    @Slot(str)
    def _on_transcription_done(self, text: str) -> None:
        if not text:
            logger.debug("Empty transcription — nothing to insert")
            return
        try:
            self._injector.paste(text)
        except Exception:
            logger.exception("Text injection failed")

    @Slot(str)
    def _on_transcription_error(self, message: str) -> None:
        logger.error("Transcription error: %s", message)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        logger.info("Shutting down Aura")
        self._hotkey.stop()
        if self._is_worker_running():
            self._worker_thread.quit()  # type: ignore[union-attr]  # guarded above
            self._worker_thread.wait(3_000)  # type: ignore[union-attr]
