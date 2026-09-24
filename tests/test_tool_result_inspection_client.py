from __future__ import annotations

import json
from typing import Any

import pytest

from lightspeed_agentic.inspection.client import LangChainClassifierClient
from lightspeed_agentic.inspection.models import ClassifierDecision, ClassifierRequest


class FakeStructuredModel:
    def __init__(self) -> None:
        self.schema: Any = None
        self.messages: list[Any] | None = None

    def with_structured_output(self, schema: Any, **kwargs: Any) -> FakeStructuredModel:
        self.schema = (schema, kwargs)
        return self

    async def ainvoke(self, messages: list[Any], **_: Any) -> dict[str, object]:
        self.messages = messages
        return {"injectionDetected": False, "category": "none"}


class BindableStructuredRunnable:
    def __init__(self) -> None:
        self.effective_parameters: dict[str, object] = {}
        self.messages: list[Any] | None = None

    def bind(self, **kwargs: object) -> BindableStructuredRunnable:
        self.effective_parameters = kwargs
        return self

    async def ainvoke(self, messages: list[Any], **kwargs: object) -> dict[str, object]:
        self.messages = messages
        assert kwargs == {}
        return {
            "injectionDetected": self.effective_parameters
            == {
                "temperature": 0,
                "max_tokens": 128,
            },
            "category": "unknown" if self.effective_parameters else "none",
        }


class BindableModel:
    def __init__(self) -> None:
        self.structured = BindableStructuredRunnable()
        self.bound_before_structured = False

    def bind(self, **_: object) -> BindableModel:
        self.bound_before_structured = True
        return self

    def with_structured_output(self, _schema: Any, **_: Any) -> BindableStructuredRunnable:
        assert not self.bound_before_structured
        return self.structured


@pytest.mark.asyncio
async def test_classifier_client_sends_only_dedicated_untrusted_content_messages() -> None:
    model = FakeStructuredModel()
    client = LangChainClassifierClient(model)
    request = ClassifierRequest(
        toolName="get_pods",
        resultType="result",
        chunkIndex=0,
        chunkCount=1,
        content="tool result",
    )

    decision = await client.classify(request)

    assert decision == ClassifierDecision(injectionDetected=False, category="none")
    assert model.schema is not None
    assert model.schema[0] is ClassifierDecision
    assert model.messages is not None
    assert len(model.messages) == 2
    assert "untrusted" in model.messages[0].content.lower()
    assert "do not follow" in model.messages[0].content.lower()
    assert json.loads(model.messages[1].content) == request.model_dump(by_alias=True)
    assert "history" not in model.messages[1].content
    assert "system prompt" not in model.messages[1].content.lower()


@pytest.mark.asyncio
async def test_classifier_client_binds_generation_parameters_to_structured_runnable() -> None:
    model = BindableModel()
    client = LangChainClassifierClient(model)

    decision = await client.classify(
        ClassifierRequest(
            toolName="get_pods",
            resultType="result",
            chunkIndex=0,
            chunkCount=1,
            content="output",
        )
    )

    assert decision == ClassifierDecision(injectionDetected=True, category="unknown")
    assert model.structured.effective_parameters == {
        "temperature": 0,
        "max_tokens": 128,
    }


@pytest.mark.asyncio
async def test_classifier_client_rejects_non_strict_model_response() -> None:
    class InvalidModel(FakeStructuredModel):
        async def ainvoke(self, _messages: list[Any], **_: Any) -> dict[str, object]:
            return {
                "injectionDetected": "false",
                "category": "none",
                "reason": "do not expose",
            }

    with pytest.raises(ValueError, match="injectionDetected"):
        await LangChainClassifierClient(InvalidModel()).classify(
            ClassifierRequest(
                toolName="get_pods",
                resultType="result",
                chunkIndex=0,
                chunkCount=1,
                content="output",
            )
        )
