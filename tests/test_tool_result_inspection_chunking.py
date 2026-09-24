from __future__ import annotations

import json

import pytest

from lightspeed_agentic.inspection.chunking import (
    ToolResultChunk,
    chunk_tool_result,
    serialize_tool_result,
)


class CharacterCodec:
    def encode(self, text: str) -> list[int]:
        return list(text.encode("utf-8"))

    def decode(self, tokens: list[int]) -> str:
        return bytes(tokens).decode("utf-8")


def test_serializes_strings_without_changing_content() -> None:
    assert serialize_tool_result("tool output") == "tool output"


def test_serializes_structured_results_without_losing_source_order() -> None:
    value = {"name": "pod", "labels": ["one", "two"]}

    assert serialize_tool_result(value) == json.dumps(
        value, ensure_ascii=False, separators=(",", ":")
    )


def test_serializes_bytes_as_utf8() -> None:
    assert serialize_tool_result(b"tool output") == "tool output"


def test_rejects_non_utf8_bytes() -> None:
    with pytest.raises(ValueError, match="UTF-8"):
        serialize_tool_result(b"\xff")


def test_chunking_preserves_complete_serialized_result() -> None:
    value = {"output": "abcdefghij"}
    serialized = serialize_tool_result(value)

    chunks = chunk_tool_result(
        value,
        codec=CharacterCodec(),
        context_window_tokens=300,
        instruction_tokens=20,
        output_tokens=20,
    )

    assert "".join(chunk.content for chunk in chunks) == serialized
    assert all(isinstance(chunk, ToolResultChunk) for chunk in chunks)


def test_adjacent_chunks_overlap_by_256_tokens() -> None:
    value = "x" * 1100

    chunks = chunk_tool_result(
        value,
        codec=CharacterCodec(),
        context_window_tokens=640,
        instruction_tokens=20,
        output_tokens=20,
    )

    assert len(chunks) == 3
    assert chunks[0].content[-256:] == chunks[1].content[:256]
    assert chunks[1].content[-256:] == chunks[2].content[:256]
    assert chunks[0].chunk_index == 0
    assert chunks[-1].chunk_count == len(chunks)


def test_small_result_uses_one_chunk_without_truncation() -> None:
    value = "short result"

    chunks = chunk_tool_result(
        value,
        codec=CharacterCodec(),
        context_window_tokens=1000,
        instruction_tokens=10,
        output_tokens=10,
    )

    assert [chunk.content for chunk in chunks] == [value]
    assert chunks[0].chunk_count == 1


def test_chunking_rejects_insufficient_reserved_budget() -> None:
    with pytest.raises(ValueError, match="overlap"):
        chunk_tool_result(
            "value",
            codec=CharacterCodec(),
            context_window_tokens=256,
            instruction_tokens=0,
            output_tokens=0,
        )
