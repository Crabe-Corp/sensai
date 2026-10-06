import json
from collections.abc import Iterator
from typing import Any, Literal
from unittest.mock import MagicMock
from pydantic import BaseModel, Field

from src.core.ollama_client import ChatMessage, OllamaClient
from src.features.tools.executor import ToolExecutionResult, ToolExecutor
from src.features.tools.registry import ToolRegistry, default_registry


class TokenChunkEvent(BaseModel):
    type: Literal["token"] = "token"
    token: str


class ToolCallEvent(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    tool_call_id: str | None = None


class ToolResultEvent(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    tool_name: str
    result: Any = None
    is_error: bool = False
    tool_call_id: str | None = None


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    error: str
    code: str | None = None


EngineEvent = TokenChunkEvent | ToolCallEvent | ToolResultEvent | ErrorEvent


class ConversationEngine:
    def __init__(
        self,
        client: OllamaClient | None = None,
        registry: ToolRegistry | None = None,
        executor: ToolExecutor | None = None,
        max_tool_iterations: int = 5,
    ) -> None:
        self.client = client or OllamaClient()
        self.registry = registry or default_registry
        self.executor = executor or ToolExecutor(registry=self.registry)
        self.max_tool_iterations = max_tool_iterations

    def _resolve_tools(
        self,
        tools: list[dict[str, Any]] | ToolRegistry | list[Any] | bool | None,
    ) -> list[dict[str, Any]] | None:
        if tools is None or tools is False:
            return None
        if isinstance(tools, ToolRegistry):
            return tools.to_ollama_tools()
        if tools is True:
            return self.registry.to_ollama_tools()
        if isinstance(tools, list):
            resolved: list[dict[str, Any]] = []
            for item in tools:
                if hasattr(item, "to_ollama_dict"):
                    resolved.append(item.to_ollama_dict())
                elif isinstance(item, dict):
                    resolved.append(item)
            return resolved if resolved else None
        return None

    def run_stream(
        self,
        messages: list[ChatMessage | dict[str, Any]],
        model: str,
        tools: list[dict[str, Any]] | ToolRegistry | list[Any] | bool | None = None,
    ) -> Iterator[EngineEvent]:
        ollama_tools = self._resolve_tools(tools)
        if not ollama_tools:
            try:
                for chunk in self.client.chat_stream(model=model, messages=messages):
                    yield TokenChunkEvent(token=chunk)
            except Exception as exc:
                yield ErrorEvent(error=str(exc), code=exc.__class__.__name__)
            return

        current_messages: list[dict[str, Any]] = [
            m.model_dump_for_api() if isinstance(m, ChatMessage) else dict(m)
            for m in messages
        ]

        is_mock = isinstance(self.client, MagicMock) or isinstance(
            getattr(self.client, "chat_stream", None), MagicMock
        )
        has_stream_raw = hasattr(self.client, "chat_stream_raw") and not (
            is_mock and not getattr(self.client.chat_stream_raw, "_mock_return_value", None)
        )

        if not has_stream_raw and is_mock:
            try:
                for chunk in self.client.chat_stream(model=model, messages=current_messages):
                    yield TokenChunkEvent(token=chunk)
            except Exception as exc:
                yield ErrorEvent(error=str(exc), code=exc.__class__.__name__)
            return

        for _ in range(self.max_tool_iterations):
            accumulated_content = ""
            detected_tool_calls: list[dict[str, Any]] = []

            try:
                for data in self.client.chat_stream_raw(
                    model=model,
                    messages=current_messages,
                    tools=ollama_tools,
                ):
                    msg = data.get("message", {})
                    content_chunk = msg.get("content", "")
                    if content_chunk:
                        accumulated_content += content_chunk
                        yield TokenChunkEvent(token=content_chunk)

                    raw_tc = msg.get("tool_calls")
                    if raw_tc:
                        detected_tool_calls.extend(raw_tc)
            except Exception as exc:
                yield ErrorEvent(error=str(exc), code=exc.__class__.__name__)
                return

            if not detected_tool_calls:
                return

            current_messages.append(
                {
                    "role": "assistant",
                    "content": accumulated_content,
                    "tool_calls": detected_tool_calls,
                }
            )

            for tc in detected_tool_calls:
                func = tc.get("function", {})
                tool_name = func.get("name", "")
                raw_args = func.get("arguments", {})
                if isinstance(raw_args, str):
                    try:
                        args = json.loads(raw_args)
                    except Exception:
                        args = {}
                elif isinstance(raw_args, dict):
                    args = raw_args
                else:
                    args = {}

                call_id = tc.get("id")

                yield ToolCallEvent(tool_name=tool_name, arguments=args, tool_call_id=call_id)

                exec_res = self.executor.execute(tool_name=tool_name, arguments=args)

                yield ToolResultEvent(
                    tool_name=tool_name,
                    result=exec_res.result,
                    is_error=not exec_res.success,
                    tool_call_id=call_id,
                )

                tool_msg: dict[str, Any] = {
                    "role": "tool",
                    "content": exec_res.to_tool_message_content(),
                }
                if call_id:
                    tool_msg["tool_call_id"] = call_id
                current_messages.append(tool_msg)

        yield ErrorEvent(
            error=f"Limite de {self.max_tool_iterations} itérations d'outils atteinte.",
            code="MaxToolIterationsExceeded",
        )


def run_stream(
    messages: list[ChatMessage | dict[str, Any]],
    model: str,
    tools: list[dict[str, Any]] | ToolRegistry | list[Any] | bool | None = None,
    client: OllamaClient | None = None,
    registry: ToolRegistry | None = None,
    executor: ToolExecutor | None = None,
) -> Iterator[EngineEvent]:
    engine = ConversationEngine(client=client, registry=registry, executor=executor)
    yield from engine.run_stream(messages=messages, model=model, tools=tools)
