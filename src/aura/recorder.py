from __future__ import annotations

import logging
import os
import tempfile
import threading
import time

import numpy as np
import sounddevice as sd
import soundfile as sf

from aura import config

logger = logging.getLogger(__name__)


class AudioRecorder:
    """Streams microphone input to a WAV temp file."""

    def __init__(
        self,
        sample_rate: int = config.SAMPLE_RATE,
        channels: int = config.CHANNELS,
        min_duration: float = config.MIN_RECORDING_DURATION,
        max_duration: float = config.MAX_RECORDING_DURATION,
    ) -> None:
        self._sample_rate = sample_rate
        self._channels = channels
        self._min_duration = min_duration
        self._max_duration = max_duration

        self._frames: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._recording = False
        self._start_time: float = 0.0

        self._stream: sd.InputStream | None = None

    def _ensure_stream_running(self) -> None:
        """Opens the audio stream if it's not already open."""
        if self._stream is not None:
            return
        try:
            self._stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=self._channels,
                dtype="float32",
                callback=self._audio_callback,
            )
            self._stream.start()
            logger.debug("Background audio stream opened")
        except Exception as exc:
            self._stream = None
            raise RuntimeError(f"Microphone unavailable: {exc}") from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Begin recording."""
        self._ensure_stream_running()

        with self._lock:
            self._frames.clear()
            self._recording = True
            self._start_time = time.monotonic()
        logger.debug("Capture started")

    def stop(self) -> str | None:
        """Stop capturing and persist audio to a WAV temp file."""
        with self._lock:
            self._recording = False
            duration = time.monotonic() - self._start_time
            frames = list(self._frames)

        if duration < self._min_duration or not frames:
            logger.debug("Recording discarded: duration=%.2fs", duration)
            return None

        audio = np.concatenate(frames, axis=0)
        return self._write_temp(audio)

    def abort(self) -> None:
        """Cancel the current recording immediately."""
        with self._lock:
            self._recording = False
            self._frames.clear()
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None
        logger.debug("Capture aborted")

    @staticmethod
    def cleanup(path: str | None) -> None:
        """Delete the temp audio file."""
        if path and os.path.exists(path):
            try:
                os.unlink(path)
            except OSError:
                logger.warning("Could not delete temp file")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: object,
    ) -> None:
        if status:
            logger.warning("Audio callback status: %s", status)

        with self._lock:
            if not self._recording:
                return

            elapsed = time.monotonic() - self._start_time
            if elapsed > self._max_duration:
                logger.info("Max duration reached")
                self._recording = False
                return

            self._frames.append(indata.copy())

    def _write_temp(self, audio: np.ndarray) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False, prefix="aura_")
        path = tmp.name
        tmp.close()

        sf.write(path, audio, self._sample_rate, subtype="PCM_16")
        return path
