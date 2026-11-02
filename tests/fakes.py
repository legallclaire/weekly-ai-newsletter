from __future__ import annotations

from collections.abc import Callable, Mapping

from pydantic import BaseModel

Handler = Callable[[str], BaseModel] | BaseModel | Exception


class FakeLLM:
    """LLMClient double: answers by output model type, records every call."""

    def __init__(self, responses: Mapping[type[BaseModel], Handler]) -> None:
        self._responses = dict(responses)
        self.calls: list[tuple[str, str, type[BaseModel]]] = []

    def structured[M: BaseModel](self, *, system: str, prompt: str, output_model: type[M]) -> M:
        self.calls.append((system, prompt, output_model))
        handler = self._responses[output_model]
        if isinstance(handler, Exception):
            raise handler
        result = handler if isinstance(handler, BaseModel) else handler(prompt)
        assert isinstance(result, output_model)
        return result
