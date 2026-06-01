from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from aura.app import AppController, _TranscriptionWorker


@pytest.fixture()
def controller(qt_app: object, mocker) -> AppController:  # type: ignore[type-arg]
    """AppController with all heavy dependencies mocked out."""
    mocker.patch("aura.app.AudioRecorder")
    mocker.patch("aura.app.Transcriber")
    mocker.patch("aura.app.TextInjector")
    mocker.patch("aura.app.RecordingIndicator")
    mocker.patch("aura.app.TrayIcon")
    mocker.patch("aura.app.HotkeyListener")
    return AppController()


# ------------------------------------------------------------------
# _TranscriptionWorker
# ------------------------------------------------------------------


def test_worker_emits_finished_on_success(qt_app: object, mocker) -> None:  # type: ignore[type-arg]
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.return_value = "hello world"

    worker = _TranscriptionWorker(mock_transcriber, "/fake/audio.wav", language="uk")
    results: list[str] = []
    worker.finished.connect(lambda t: results.append(t))

    mocker.patch("aura.app.AudioRecorder.cleanup")
    worker.run()

    assert results == ["hello world"]
    mock_transcriber.transcribe.assert_called_once_with("/fake/audio.wav", language="uk")


def test_worker_emits_finished_with_no_language(qt_app: object, mocker) -> None:  # type: ignore[type-arg]
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.return_value = "hello"

    worker = _TranscriptionWorker(mock_transcriber, "/fake/audio.wav")
    worker.finished.connect(lambda _: None)

    mocker.patch("aura.app.AudioRecorder.cleanup")
    worker.run()

    mock_transcriber.transcribe.assert_called_once_with("/fake/audio.wav", language=None)


def test_worker_emits_error_on_exception(qt_app: object, mocker) -> None:  # type: ignore[type-arg]
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.side_effect = RuntimeError("API timeout")

    worker = _TranscriptionWorker(mock_transcriber, "/fake/audio.wav")
    errors: list[str] = []
    worker.error.connect(lambda e: errors.append(e))

    mocker.patch("aura.app.AudioRecorder.cleanup")
    worker.run()

    assert len(errors) == 1
    assert "API timeout" in errors[0]


def test_worker_always_cleans_up_temp_file(qt_app: object, mocker) -> None:  # type: ignore[type-arg]
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.side_effect = RuntimeError("fail")

    worker = _TranscriptionWorker(mock_transcriber, "/fake/audio.wav")
    worker.error.connect(lambda _: None)

    mock_cleanup = mocker.patch("aura.app.AudioRecorder.cleanup")
    worker.run()

    mock_cleanup.assert_called_once_with("/fake/audio.wav")


def test_worker_cleans_up_on_success(qt_app: object, mocker) -> None:  # type: ignore[type-arg]
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.return_value = "text"

    worker = _TranscriptionWorker(mock_transcriber, "/fake/audio.wav")
    worker.finished.connect(lambda _: None)

    mock_cleanup = mocker.patch("aura.app.AudioRecorder.cleanup")
    worker.run()

    mock_cleanup.assert_called_once_with("/fake/audio.wav")


# ------------------------------------------------------------------
# AppController — recording_started
# ------------------------------------------------------------------


def test_on_recording_started_starts_recorder_and_shows_indicator(controller: AppController) -> None:
    controller._on_recording_started()

    controller._recorder.start.assert_called_once()
    controller._indicator.show.assert_called_once()


def test_on_recording_started_does_not_show_indicator_on_mic_error(controller: AppController) -> None:
    controller._recorder.start.side_effect = RuntimeError("no microphone")

    controller._on_recording_started()

    controller._indicator.show.assert_not_called()


# ------------------------------------------------------------------
# AppController — recording_stopped
# ------------------------------------------------------------------


def test_on_recording_stopped_hides_indicator(controller: AppController, mocker) -> None:  # type: ignore[type-arg]
    controller._recorder.stop.return_value = None
    mocker.patch.object(controller, "_resolve_language", return_value=None)

    controller._on_recording_stopped()

    controller._indicator.hide.assert_called_once()


def test_on_recording_stopped_returns_early_on_no_audio(controller: AppController, mocker) -> None:  # type: ignore[type-arg]
    controller._recorder.stop.return_value = None
    mocker.patch.object(controller, "_resolve_language", return_value=None)
    mock_start = mocker.patch.object(controller, "_start_transcription")

    controller._on_recording_stopped()

    mock_start.assert_not_called()


def test_on_recording_stopped_discards_audio_when_transcription_running(
    controller: AppController,
    mocker,  # type: ignore[type-arg]
) -> None:
    controller._recorder.stop.return_value = "/tmp/aura_test.wav"
    mocker.patch.object(controller, "_resolve_language", return_value=None)
    mock_thread = MagicMock()
    mock_thread.isRunning.return_value = True
    controller._worker_thread = mock_thread

    mock_cleanup = mocker.patch("aura.app.AudioRecorder.cleanup")
    controller._on_recording_stopped()

    mock_cleanup.assert_called_once_with("/tmp/aura_test.wav")


def test_on_recording_stopped_starts_transcription_with_audio(
    controller: AppController,
    mocker,  # type: ignore[type-arg]
) -> None:
    controller._recorder.stop.return_value = "/tmp/aura_test.wav"
    controller._worker_thread = None
    mocker.patch.object(controller, "_resolve_language", return_value="uk")
    mock_start = mocker.patch.object(controller, "_start_transcription")

    controller._on_recording_stopped()

    mock_start.assert_called_once_with("/tmp/aura_test.wav", "uk")


# ------------------------------------------------------------------
# AppController — _resolve_language
# ------------------------------------------------------------------


def test_resolve_language_auto_calls_detector(controller: AppController, mocker) -> None:  # type: ignore[type-arg]
    controller._tray.language = "auto"
    mock_detect = mocker.patch("aura.app.lang_detector.get_active_language", return_value="uk")

    result = controller._resolve_language()

    mock_detect.assert_called_once()
    assert result == "uk"


def test_resolve_language_auto_returns_none_when_undetected(
    controller: AppController, mocker  # type: ignore[type-arg]
) -> None:
    controller._tray.language = "auto"
    mocker.patch("aura.app.lang_detector.get_active_language", return_value=None)

    result = controller._resolve_language()

    assert result is None


def test_resolve_language_explicit_bypasses_detector(
    controller: AppController, mocker  # type: ignore[type-arg]
) -> None:
    controller._tray.language = "uk"
    mock_detect = mocker.patch("aura.app.lang_detector.get_active_language")

    result = controller._resolve_language()

    mock_detect.assert_not_called()
    assert result == "uk"


def test_resolve_language_explicit_english(controller: AppController) -> None:
    controller._tray.language = "en"
    assert controller._resolve_language() == "en"


# ------------------------------------------------------------------
# AppController — transcription callbacks
# ------------------------------------------------------------------


def test_on_transcription_done_pastes_text(controller: AppController) -> None:
    controller._on_transcription_done("dictated text")

    controller._injector.paste.assert_called_once_with("dictated text")


def test_on_transcription_done_skips_empty_text(controller: AppController) -> None:
    controller._on_transcription_done("")

    controller._injector.paste.assert_not_called()


def test_on_transcription_done_handles_injector_exception(controller: AppController) -> None:
    controller._injector.paste.side_effect = RuntimeError("clipboard locked")

    controller._on_transcription_done("some text")  # must not raise


def test_on_transcription_error_logs_message(
    controller: AppController, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="aura.app"):
        controller._on_transcription_error("connection refused")

    assert "connection refused" in caplog.text


# ------------------------------------------------------------------
# AppController — _start_transcription
# ------------------------------------------------------------------


def test_start_transcription_creates_and_starts_thread(
    controller: AppController,
    mocker,  # type: ignore[type-arg]
) -> None:
    mock_thread = MagicMock()
    mock_worker = MagicMock()
    mocker.patch("aura.app.QThread", return_value=mock_thread)
    mocker.patch("aura.app._TranscriptionWorker", return_value=mock_worker)

    controller._start_transcription("/tmp/aura_test.wav", language=None)

    mock_thread.start.assert_called_once()
    assert controller._worker_thread is mock_thread


# ------------------------------------------------------------------
# AppController — shutdown
# ------------------------------------------------------------------


def test_shutdown_stops_hotkey_listener(controller: AppController) -> None:
    controller._worker_thread = None

    controller.shutdown()

    controller._hotkey.stop.assert_called_once()


def test_shutdown_waits_for_running_thread(controller: AppController) -> None:
    mock_thread = MagicMock()
    mock_thread.isRunning.return_value = True
    controller._worker_thread = mock_thread

    controller.shutdown()

    mock_thread.quit.assert_called_once()
    mock_thread.wait.assert_called_once_with(3_000)
