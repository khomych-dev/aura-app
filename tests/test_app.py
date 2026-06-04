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
    worker.signals.finished.connect(lambda t: results.append(t))

    mocker.patch("aura.app.AudioRecorder.cleanup")
    worker.run()

    assert results == ["hello world"]
    mock_transcriber.transcribe.assert_called_once_with("/fake/audio.wav", language="uk")


def test_worker_emits_finished_with_no_language(qt_app: object, mocker) -> None:  # type: ignore[type-arg]
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.return_value = "hello"

    worker = _TranscriptionWorker(mock_transcriber, "/fake/audio.wav")
    worker.signals.finished.connect(lambda _: None)

    mocker.patch("aura.app.AudioRecorder.cleanup")
    worker.run()

    mock_transcriber.transcribe.assert_called_once_with("/fake/audio.wav", language=None)


def test_worker_emits_error_on_exception(qt_app: object, mocker) -> None:  # type: ignore[type-arg]
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.side_effect = RuntimeError("API timeout")

    worker = _TranscriptionWorker(mock_transcriber, "/fake/audio.wav")
    errors: list[str] = []
    worker.signals.error.connect(lambda e: errors.append(e))

    mocker.patch("aura.app.AudioRecorder.cleanup")
    worker.run()

    assert len(errors) == 1
    assert "API timeout" in errors[0]


def test_worker_always_cleans_up_temp_file(qt_app: object, mocker) -> None:  # type: ignore[type-arg]
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.side_effect = RuntimeError("fail")

    worker = _TranscriptionWorker(mock_transcriber, "/fake/audio.wav")
    worker.signals.error.connect(lambda _: None)

    mock_cleanup = mocker.patch("aura.app.AudioRecorder.cleanup")
    worker.run()

    mock_cleanup.assert_called_once_with("/fake/audio.wav")


def test_worker_cleans_up_on_success(qt_app: object, mocker) -> None:  # type: ignore[type-arg]
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.return_value = "text"

    worker = _TranscriptionWorker(mock_transcriber, "/fake/audio.wav")
    worker.signals.finished.connect(lambda _: None)

    mock_cleanup = mocker.patch("aura.app.AudioRecorder.cleanup")
    worker.run()

    mock_cleanup.assert_called_once_with("/fake/audio.wav")


# ------------------------------------------------------------------
# AppController — recording_started
# ------------------------------------------------------------------


def test_on_recording_started_starts_recorder_and_shows_indicator(controller: AppController) -> None:
    controller._on_recording_started()

    controller._recorder.start.assert_called_once()  # type: ignore
    controller._indicator.show.assert_called_once()  # type: ignore


def test_on_recording_started_does_not_show_indicator_on_mic_error(controller: AppController) -> None:
    controller._recorder.start.side_effect = RuntimeError("no microphone")  # type: ignore

    controller._on_recording_started()

    controller._indicator.show.assert_not_called()  # type: ignore


def test_on_recording_started_cancels_active_post_roll_and_aborts_recorder(
    controller: AppController,
    mocker,  # type: ignore[type-arg]
) -> None:
    """Rapid re-press during post-roll must cancel the timer and abort the stream."""
    mocker.patch.object(controller, "_resolve_language", return_value=None)
    controller._on_recording_stopped()  # arms the timer
    assert controller._post_roll_timer is not None
    assert controller._post_roll_timer.isActive()

    controller._on_recording_started()

    assert not controller._post_roll_timer.isActive()
    controller._recorder.abort.assert_called_once()  # type: ignore
    controller._recorder.start.assert_called_once()  # type: ignore


# ------------------------------------------------------------------
# AppController — recording_stopped
# ------------------------------------------------------------------


def test_on_recording_stopped_hides_indicator_immediately(
    controller: AppController,
    mocker,  # type: ignore[type-arg]
) -> None:
    mocker.patch.object(controller, "_resolve_language", return_value=None)

    controller._on_recording_stopped()

    controller._indicator.hide.assert_called_once()  # type: ignore
    # Cleanup: stop timer so it doesn't fire after the test
    controller._post_roll_timer.stop()  # type: ignore[union-attr]


def test_on_recording_stopped_schedules_post_roll_timer(
    controller: AppController,
    mocker,  # type: ignore[type-arg]
) -> None:
    """stop() on the recorder must NOT be called immediately — only after the timer fires."""
    mocker.patch.object(controller, "_resolve_language", return_value="uk")

    controller._on_recording_stopped()

    assert controller._post_roll_timer is not None
    assert controller._post_roll_timer.isActive()
    controller._recorder.stop.assert_not_called()  # type: ignore
    # Cleanup
    controller._post_roll_timer.stop()


def test_on_recording_stopped_saves_pending_language(
    controller: AppController,
    mocker,  # type: ignore[type-arg]
) -> None:
    mocker.patch.object(controller, "_resolve_language", return_value="uk")

    controller._on_recording_stopped()

    assert controller._pending_language == "uk"
    controller._post_roll_timer.stop()  # type: ignore[union-attr]


def test_on_recording_stopped_reuses_timer_across_recordings(
    controller: AppController,
    mocker,  # type: ignore[type-arg]
) -> None:
    mocker.patch.object(controller, "_resolve_language", return_value=None)

    controller._on_recording_stopped()
    timer_first = controller._post_roll_timer
    controller._post_roll_timer.stop()  # type: ignore[union-attr]

    controller._on_recording_stopped()
    timer_second = controller._post_roll_timer
    controller._post_roll_timer.stop()  # type: ignore[union-attr]

    assert timer_first is timer_second


# ------------------------------------------------------------------
# AppController — _finalize_recording
# ------------------------------------------------------------------


def test_finalize_recording_returns_early_on_no_audio(
    controller: AppController,
    mocker,  # type: ignore[type-arg]
) -> None:
    controller._recorder.stop.return_value = None  # type: ignore
    controller._pending_language = None
    mock_start = mocker.patch.object(controller, "_start_transcription")

    controller._finalize_recording()

    mock_start.assert_not_called()


def test_finalize_recording_starts_transcription_with_audio(
    controller: AppController,
    mocker,  # type: ignore[type-arg]
) -> None:
    controller._recorder.stop.return_value = "/tmp/aura_test.wav"  # type: ignore
    controller._pending_language = "uk"
    controller._transcription_active = False
    mock_start = mocker.patch.object(controller, "_start_transcription")

    controller._finalize_recording()

    mock_start.assert_called_once_with("/tmp/aura_test.wav", "uk")


def test_finalize_recording_discards_audio_when_transcription_running(
    controller: AppController,
    mocker,  # type: ignore[type-arg]
) -> None:
    controller._recorder.stop.return_value = "/tmp/aura_test.wav"  # type: ignore
    controller._pending_language = None
    controller._transcription_active = True

    mock_cleanup = mocker.patch("aura.app.AudioRecorder.cleanup")
    controller._finalize_recording()

    mock_cleanup.assert_called_once_with("/tmp/aura_test.wav")


# ------------------------------------------------------------------
# AppController — _resolve_language
# ------------------------------------------------------------------


def test_resolve_language_auto_returns_none(controller: AppController) -> None:
    controller._tray.language = "auto"  # type: ignore
    assert controller._resolve_language() is None


def test_resolve_language_explicit_bypasses_auto(controller: AppController) -> None:
    controller._tray.language = "uk"  # type: ignore
    assert controller._resolve_language() == "uk"


def test_resolve_language_explicit_english(controller: AppController) -> None:
    controller._tray.language = "en"  # type: ignore
    assert controller._resolve_language() == "en"


# ------------------------------------------------------------------
# AppController — transcription callbacks
# ------------------------------------------------------------------


def test_on_transcription_done_pastes_text(controller: AppController) -> None:
    controller._on_transcription_done("dictated text")

    controller._injector.paste.assert_called_once_with("dictated text")  # type: ignore


def test_on_transcription_done_skips_empty_text(controller: AppController) -> None:
    controller._on_transcription_done("")

    controller._injector.paste.assert_not_called()  # type: ignore


def test_on_transcription_done_handles_injector_exception(controller: AppController) -> None:
    controller._injector.paste.side_effect = RuntimeError("clipboard locked")  # type: ignore

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
    mock_pool = MagicMock()
    mock_worker = MagicMock()
    mocker.patch("aura.app.QThreadPool.globalInstance", return_value=mock_pool)
    mocker.patch("aura.app._TranscriptionWorker", return_value=mock_worker)

    controller._start_transcription("/tmp/aura_test.wav", language=None)

    mock_pool.start.assert_called_once_with(mock_worker)
    assert controller._transcription_active is True


# ------------------------------------------------------------------
# AppController — shutdown
# ------------------------------------------------------------------


def test_shutdown_stops_hotkey_listener(controller: AppController) -> None:
    controller._transcription_active = False

    controller.shutdown()

    controller._hotkey.stop.assert_called_once()  # type: ignore


def test_shutdown_waits_for_running_thread(controller: AppController, mocker) -> None:  # type: ignore[type-arg]
    controller._transcription_active = True
    mock_pool = MagicMock()
    mocker.patch("aura.app.QThreadPool.globalInstance", return_value=mock_pool)

    controller.shutdown()

    mock_pool.waitForDone.assert_called_once_with(3000)


def test_shutdown_cancels_active_post_roll_and_aborts_recorder(
    controller: AppController,
    mocker,  # type: ignore[type-arg]
) -> None:
    """shutdown() must stop a pending post-roll timer and discard in-progress audio."""
    mocker.patch.object(controller, "_resolve_language", return_value=None)
    controller._on_recording_stopped()  # arms the timer
    assert controller._post_roll_timer is not None
    assert controller._post_roll_timer.isActive()
    controller._transcription_active = False

    controller.shutdown()

    assert not controller._post_roll_timer.isActive()
    controller._recorder.abort.assert_called_once()  # type: ignore
