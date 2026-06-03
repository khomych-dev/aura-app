from __future__ import annotations

import logging
import time
from typing import Any

import openai

from aura import config

logger = logging.getLogger(__name__)


class Transcriber:
    """Sends a WAV file to OpenAI Whisper API and returns the transcribed text.

    Pass an ISO 639-1 *language* code to :meth:`transcribe` to constrain
    Whisper to a specific language.  Omit it (or pass ``None``) to let
    Whisper auto-detect the spoken language.
    """

    def __init__(
        self,
        api_key: str = config.OPENAI_API_KEY,
        model: str = config.WHISPER_MODEL,
        timeout: float = config.WHISPER_API_TIMEOUT,
    ) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is empty.  Set it in your .env file.")
        self._client = openai.OpenAI(
            api_key=api_key,
            # Hard deadline for the entire request (connect + upload + processing).
            timeout=timeout,
            max_retries=0,
        )
        self._model = model

    def transcribe(self, audio_path: str, language: str | None = None) -> str:
        """Transcribe *audio_path* and return the text, stripped of whitespace.

        Args:
            audio_path: Path to the WAV file to transcribe.
            language: ISO 639-1 code (e.g. ``"uk"``, ``"en"``) to pass to the
                Whisper API.  ``None`` (default) lets Whisper auto-detect.

        Raises :class:`openai.OpenAIError` on API failures (including
        :class:`openai.APITimeoutError`) — the caller is responsible for
        catching and logging these.
        """
        logger.debug(
            "Sending audio to Whisper API (model=%s, language=%s, timeout=%.0fs)",
            self._model,
            language or "auto",
            self._client.timeout,
        )

        max_attempts = config.WHISPER_MAX_RETRIES
        for attempt in range(1, max_attempts + 1):
            try:
                with open(audio_path, "rb") as audio_file:
                    kwargs: dict[str, Any] = {"model": self._model, "file": audio_file}
                    if language:
                        kwargs["language"] = language
                    response = self._client.audio.transcriptions.create(**kwargs)
                    break
            except openai.APITimeoutError:
                if attempt == max_attempts:
                    logger.exception("Whisper API timed out after %d attempts", max_attempts)
                    raise

                backoff = 2 ** (attempt - 1)
                logger.warning(
                    "Whisper API timeout (attempt %d/%d). Retrying in %ds...", attempt, max_attempts, backoff
                )
                time.sleep(backoff)
            except Exception:
                logger.exception("Whisper API call failed unexpectedly")
                raise

        text = response.text.strip()
        logger.debug("Transcription received: %d chars", len(text))
        return text
