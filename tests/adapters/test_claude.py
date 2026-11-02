import json
from typing import Any, cast

import anthropic
import pytest
from anthropic import transform_schema
from anthropic.types.beta import BetaTextBlock
from pydantic import BaseModel

from weekly_ai_newsletter.adapters.claude import ClaudeClient
from weekly_ai_newsletter.domain.errors import LLMOutputError


class Answer(BaseModel):
    value: int


class FakeBlock:
    def __init__(self, type: str) -> None:
        self.type = type


class FakeResponse:
    def __init__(self, content: list[Any], stop_reason: str = "end_turn") -> None:
        self.content = content
        self.stop_reason = stop_reason


def text(payload: object) -> BetaTextBlock:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    return BetaTextBlock(type="text", text=raw)


class FakeMessages:
    def __init__(self, *responses: FakeResponse) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeBeta:
    def __init__(self, messages: FakeMessages) -> None:
        self.messages = messages


class FakeAnthropic:
    def __init__(self, messages: FakeMessages) -> None:
        self.beta = FakeBeta(messages)


def claude_with(messages: FakeMessages) -> ClaudeClient:
    client = cast(anthropic.Anthropic, FakeAnthropic(messages))
    return ClaudeClient(client, model="claude-sonnet-5-5", max_tokens=1000)


def test_requests_json_schema_output_with_refusal_fallback() -> None:
    messages = FakeMessages(FakeResponse([text({"value": 42})]))
    answer = claude_with(messages).structured(system="sys", prompt="hi", output_model=Answer)
    assert answer == Answer(value=42)
    call = messages.calls[0]
    assert call["model"] == "claude-sonnet-5-5"
    assert call["system"] == "sys"
    assert call["messages"] == [{"role": "user", "content": "hi"}]
    assert call["output_config"] == {
        "format": {"type": "json_schema", "schema": transform_schema(Answer)}
    }
    assert call["betas"] == ["server-side-fallback-2026-07-01"]
    assert call["fallbacks"] == "default"
    assert "tool_choice" not in call


def test_reads_the_answer_written_after_a_fallback() -> None:
    response = FakeResponse([text("{partial"), FakeBlock("fallback"), text({"value": 7})])
    answer = claude_with(FakeMessages(response)).structured(
        system="s", prompt="p", output_model=Answer
    )
    assert answer.value == 7


def test_retries_once_on_invalid_output() -> None:
    messages = FakeMessages(
        FakeResponse([text({"value": "not a number"})]), FakeResponse([text({"value": 1})])
    )
    assert claude_with(messages).structured(system="s", prompt="p", output_model=Answer).value == 1
    assert len(messages.calls) == 2


def test_raises_after_refusal_and_invalid_output() -> None:
    messages = FakeMessages(
        FakeResponse([], stop_reason="refusal"), FakeResponse([text({"wrong": 1})])
    )
    with pytest.raises(LLMOutputError, match="Answer"):
        claude_with(messages).structured(system="s", prompt="p", output_model=Answer)
