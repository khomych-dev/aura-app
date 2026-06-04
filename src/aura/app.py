from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal, Slot

from aura import config
from aura.hotkey import HotkeyListener
from aura.indicator import RecordingIndicator
from aura.injector import TextInjector
from aura.recorder import AudioRecorder
from aura.transcriber import Transcriber
from aura.tray import TrayIcon

logger = logging.getLogger(__name__)


class WorkerSignals(QObject):
    finished = Signal(str)
    error = Signal(str)


class _TranscriptionWorker(QRunnable):
    """Runs Whisper transcription in a QThreadPool.

    Always cleans up the temp audio file on completion, regardless of
    whether transcription succeeded or failed.
    """

    def __init__(
        self,
        transcriber: Transcriber,
        audio_path: str,
        language: str | None = None,
    ) -> None:
        super().__init__()
        self.signals = WorkerSignals()
        self._transcriber = transcriber
        self._audio_path = audio_path
        self._language = language

    @Slot()
    def run(self) -> None:
        try:
            text = self._transcriber.transcribe(self._audio_path, language=self._language)
            self.signals.finished.emit(text)
        except Exception as exc:
            logger.exception("Transcription failed")
            try:
                self.signals.error.emit(str(exc))
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

        self._transcription_active = False

        # Post-roll timer: fires POST_ROLL_PADDING_MS after key release to
        # finalise the recording.  Created once and reused across recordings.
        self._post_roll_timer: QTimer | None = None
        # Language resolved at key-release time (foreground window still belongs
        # to the user); read by _finalize_recording after the delay.
        self._pending_language: str | None = None

        # pynput runs in a plain Python threading.Thread (not a QThread).
        # AutoConnection does not reliably produce QueuedConnection in that
        # case — PySide6 may fall back to DirectConnection, executing the slot
        # in the pynput daemon thread.  Constructing QThread/QObject from a
        # foreign thread deadlocks Qt internally.  Forcing QueuedConnection
        # guarantees the slots always run in the Qt main-thread event loop.
        self._hotkey.recording_started.connect(self._on_recording_started, Qt.ConnectionType.QueuedConnection)
        self._hotkey.recording_stopped.connect(self._on_recording_stopped, Qt.ConnectionType.QueuedConnection)

        self._hotkey.start()
        logger.info("AppController ready — hold Right Ctrl to dictate")

    # ------------------------------------------------------------------
    # Hotkey slots  (run in Qt main thread via QueuedConnection)
    # ------------------------------------------------------------------

    @Slot()
    def _on_recording_started(self) -> None:
        # A new press while a post-roll is still pending means the user
        # immediately re-dictated.  Cancel the deferred stop and discard the
        # previous (incomplete) audio so the stream is free for a fresh start.
        if self._post_roll_timer is not None and self._post_roll_timer.isActive():
            self._post_roll_timer.stop()
            self._recorder.abort()
            logger.debug("Post-roll cancelled — new recording started immediately")

        logger.debug("Recording started")
        try:
            self._recorder.start()
        except RuntimeError:
            logger.exception("Cannot start recording")
            return
        self._indicator.show()

    @Slot()
    def _on_recording_stopped(self) -> None:
        logger.debug("Recording stopped — post-roll %dms", config.POST_ROLL_PADDING_MS)
        self._indicator.hide()

        # Resolve language now: the user's foreground window is still active at
        # the moment of key release.  After the 400ms post-roll delay the window
        # focus may have shifted.
        self._pending_language = self._resolve_language()

        # Lazy-create the timer once; reuse it across recordings.
        if self._post_roll_timer is None:
            self._post_roll_timer = QTimer(self)
            self._post_roll_timer.setSingleShot(True)
            self._post_roll_timer.timeout.connect(self._finalize_recording)
        self._post_roll_timer.start(config.POST_ROLL_PADDING_MS)

    @Slot()
    def _finalize_recording(self) -> None:
        """Called by the post-roll QTimer — runs on the Qt main thread."""
        audio_path = self._recorder.stop()
        if audio_path is None:
            return

        if self._is_worker_running():
            logger.warning("Previous transcription still in progress — discarding new audio")
            AudioRecorder.cleanup(audio_path)
            return

        self._start_transcription(audio_path, self._pending_language)

    # ------------------------------------------------------------------
    # Language resolution
    # ------------------------------------------------------------------

    def _resolve_language(self) -> str | None:
        """Return the ISO code to pass to Whisper, or ``None`` for auto-detect.

        If the tray is set to ``'auto'``, Whisper will auto-detect the spoken language.
        An explicit tray selection forces Whisper to use that language.
        """
        selected = self._tray.language
        if selected == config.DEFAULT_LANGUAGE:  # "auto"
            logger.debug("Using auto-detect (Spoken Language)")
            return None
        logger.debug("Using manually selected language: %s", selected)
        return selected

    # ------------------------------------------------------------------
    # Transcription
    # ------------------------------------------------------------------

    def _is_worker_running(self) -> bool:
        """Return True only if a transcription is currently active."""
        return self._transcription_active

    def _start_transcription(self, audio_path: str, language: str | None = None) -> None:
        self._transcription_active = True
        worker = _TranscriptionWorker(self._transcriber, audio_path, language)

        worker.signals.finished.connect(self._on_transcription_done)
        worker.signals.error.connect(self._on_transcription_error)
        worker.signals.finished.connect(self._clear_worker_ref)
        worker.signals.error.connect(self._clear_worker_ref)

        QThreadPool.globalInstance().start(worker)

    @Slot()
    def _clear_worker_ref(self) -> None:
        """Clear transcription active flag."""
        self._transcription_active = False

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
        if self._post_roll_timer is not None and self._post_roll_timer.isActive():
            self._post_roll_timer.stop()
            self._recorder.abort()
        if self._is_worker_running():
            QThreadPool.globalInstance().waitForDone(3000)
