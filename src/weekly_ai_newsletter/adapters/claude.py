from __future__ import annotations

import logging
from typing import Any

import anthropic
from anthropic import transform_schema
from pydantic import BaseModel, ValidationError

from weekly_ai_newsletter.domain.errors import LLMOutputError

logger = logging.getLogger(__name__)

# On a safety decline, the API re-runs the request on a fallback model chosen by category.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeClient:
    """LLMClient backed by the Anthropic API, using native JSON-schema structured outputs."""

    def __init__(
        self,
        client: anthropic.Anthropic,
        *,
        model: str,
        max_tokens: int,
        max_attempts: int = 2,
    ) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._max_attempts = max_attempts

    @classmethod
    def from_api_key(cls, api_key: str, *, model: str, max_tokens: int) -> ClaudeClient:
        client = anthropic.Anthropic(api_key=api_key, max_retries=3, timeout=300.0)
        return cls(client, model=model, max_tokens=max_tokens)

    def structured[M: BaseModel](self, *, system: str, prompt: str, output_model: type[M]) -> M:
        schema = transform_schema(output_model)
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            response = self._client.beta.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_config={"format": {"type": "json_schema", "schema": schema}},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
            if response.stop_reason in ("refusal", "max_tokens"):
                last_error = LLMOutputError(f"generation stopped: {response.stop_reason}")
            else:
                try:
                    return output_model.model_validate_json(_final_text(response.content))
                except ValidationError as exc:
                    last_error = exc
            logger.warning(
                "Invalid %s from Claude (attempt %d/%d): %s",
                output_model.__name__,
                attempt,
                self._max_attempts,
                last_error,
            )
        raise LLMOutputError(
            f"no valid {output_model.__name__} after {self._max_attempts} attempts"
        ) from last_error


def _final_text(content: list[Any]) -> str:
    """Text written by the model that produced the final answer (after any fallback)."""
    parts: list[str] = []
    for block in content:
        if block.type == "fallback":
            parts = []
        elif block.type == "text":
            parts.append(block.text)
    return "".join(parts)
