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
