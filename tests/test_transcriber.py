from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from aura.transcriber import Transcriber


def test_init_raises_on_empty_api_key() -> None:
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        Transcriber(api_key="")


def test_transcribe_returns_stripped_text(tmp_path) -> None:
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"RIFF....fake")

    mock_response = MagicMock()
    mock_response.text = "  Hello world.  "

    with patch("openai.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.audio.transcriptions.create.return_value = mock_response

        transcriber = Transcriber(api_key="sk-test")
        result = transcriber.transcribe(str(audio_file))

    assert result == "Hello world."


def test_transcribe_passes_correct_model(tmp_path) -> None:
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"RIFF....fake")

    mock_response = MagicMock()
    mock_response.text = "text"

    with patch("openai.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.audio.transcriptions.create.return_value = mock_response

        transcriber = Transcriber(api_key="sk-test", model="whisper-1")
        transcriber.transcribe(str(audio_file))

        call_kwargs = mock_client.audio.transcriptions.create.call_args
        assert call_kwargs.kwargs["model"] == "whisper-1"


def test_transcribe_no_language_kwarg_by_default(tmp_path) -> None:
    """When language is omitted, the API call must NOT include a 'language' key."""
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"RIFF....fake")

    mock_response = MagicMock()
    mock_response.text = "text"

    with patch("openai.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.audio.transcriptions.create.return_value = mock_response

        transcriber = Transcriber(api_key="sk-test")
        transcriber.transcribe(str(audio_file))

        call_kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
        assert "language" not in call_kwargs


def test_transcribe_no_language_kwarg_when_none(tmp_path) -> None:
    """Explicit language=None must also NOT include a 'language' key (auto-detect)."""
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"RIFF....fake")

    mock_response = MagicMock()
    mock_response.text = "text"

    with patch("openai.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.audio.transcriptions.create.return_value = mock_response

        transcriber = Transcriber(api_key="sk-test")
        transcriber.transcribe(str(audio_file), language=None)

        call_kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
        assert "language" not in call_kwargs


def test_transcribe_passes_language_to_api(tmp_path) -> None:
    """When an ISO code is supplied, it must be forwarded to the Whisper API."""
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"RIFF....fake")

    mock_response = MagicMock()
    mock_response.text = "Привіт"

    with patch("openai.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.audio.transcriptions.create.return_value = mock_response

        transcriber = Transcriber(api_key="sk-test")
        result = transcriber.transcribe(str(audio_file), language="uk")

        call_kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
        assert call_kwargs["language"] == "uk"
    assert result == "Привіт"


def test_transcribe_propagates_api_error(tmp_path) -> None:
    import openai

    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"RIFF....fake")

    with patch("openai.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.audio.transcriptions.create.side_effect = openai.APIConnectionError(
            request=MagicMock()
        )

        transcriber = Transcriber(api_key="sk-test")
        with pytest.raises(openai.APIConnectionError):
            transcriber.transcribe(str(audio_file))


def test_init_passes_timeout_and_max_retries_to_client() -> None:
    with patch("openai.OpenAI") as mock_openai_cls:
        Transcriber(api_key="sk-test", timeout=15.0)

        call_kwargs = mock_openai_cls.call_args.kwargs
        assert call_kwargs["timeout"] == 15.0
        assert call_kwargs["max_retries"] == 0


def test_transcribe_propagates_timeout_error(tmp_path) -> None:
    import openai

    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"RIFF....fake")

    with patch("openai.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_client.timeout = 30.0
        mock_openai_cls.return_value = mock_client
        mock_client.audio.transcriptions.create.side_effect = openai.APITimeoutError(
            request=MagicMock()
        )

        transcriber = Transcriber(api_key="sk-test")
        with pytest.raises(openai.APITimeoutError):
            transcriber.transcribe(str(audio_file))
