from __future__ import annotations

import os
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from aura.recorder import AudioRecorder


@pytest.fixture()
def recorder() -> AudioRecorder:
    return AudioRecorder(sample_rate=16_000, channels=1, min_duration=0.1, max_duration=5.0)


# ------------------------------------------------------------------
# cleanup()
# ------------------------------------------------------------------

def test_cleanup_none_is_safe(recorder: AudioRecorder) -> None:
    recorder.cleanup(None)


def test_cleanup_removes_file(tmp_path, recorder: AudioRecorder) -> None:
    f = tmp_path / "audio.wav"
    f.write_bytes(b"dummy")
    recorder.cleanup(str(f))
    assert not f.exists()


def test_cleanup_missing_file_is_safe(recorder: AudioRecorder) -> None:
    recorder.cleanup("/nonexistent/path/audio.wav")


# ------------------------------------------------------------------
# start() / stop()
# ------------------------------------------------------------------

def test_stop_without_start_returns_none(recorder: AudioRecorder) -> None:
    result = recorder.stop()
    assert result is None


def test_start_raises_on_no_microphone(recorder: AudioRecorder) -> None:
    with patch("sounddevice.InputStream", side_effect=Exception("no device")):
        with pytest.raises(RuntimeError, match="Microphone unavailable"):
            recorder.start()


def test_recording_too_short_discarded(recorder: AudioRecorder) -> None:
    mock_stream = MagicMock()
    with patch("sounddevice.InputStream", return_value=mock_stream):
        recorder.start()
        result = recorder.stop()
    assert result is None


def test_full_record_stop_creates_and_returns_file(recorder: AudioRecorder) -> None:
    """Simulate a 0.2s recording and verify a WAV temp file is created."""
    fake_audio = np.zeros((3200, 1), dtype="float32")
    mock_stream = MagicMock()

    with patch("sounddevice.InputStream", return_value=mock_stream):
        recorder.start()
        recorder._frames.append(fake_audio)
        recorder._start_time -= 0.2
        path = recorder.stop()

    try:
        assert path is not None
        assert os.path.exists(path)
        assert path.endswith(".wav")
    finally:
        recorder.cleanup(path)


# ------------------------------------------------------------------
# _audio_callback()
# ------------------------------------------------------------------

def test_audio_callback_appends_frame_when_recording(recorder: AudioRecorder) -> None:
    recorder._recording = True
    recorder._start_time = time.monotonic()
    frame = np.zeros((160, 1), dtype="float32")

    recorder._audio_callback(frame, 160, {}, None)

    assert len(recorder._frames) == 1


def test_audio_callback_ignores_frame_when_not_recording(recorder: AudioRecorder) -> None:
    recorder._recording = False
    frame = np.zeros((160, 1), dtype="float32")

    recorder._audio_callback(frame, 160, {}, None)

    assert len(recorder._frames) == 0


def test_audio_callback_stops_at_max_duration(recorder: AudioRecorder) -> None:
    recorder._recording = True
    recorder._start_time = time.monotonic() - 10.0  # well past 5s max
    frame = np.zeros((160, 1), dtype="float32")

    recorder._audio_callback(frame, 160, {}, None)

    assert recorder._recording is False
    assert len(recorder._frames) == 0
