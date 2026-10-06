import json
from collections.abc import Iterator
from typing import Any, Literal, TypeVar

import httpx
from pydantic import BaseModel, Field, ValidationError

from src.features.structured_output import (
    StructuredOutputError,
    chat_structured_flow,
)

T = TypeVar("T", bound=BaseModel)


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[dict[str, Any]] | None = None

    def model_dump_for_api(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls is not None:
            payload["tool_calls"] = self.tool_calls
        return payload


class OllamaError(Exception):
    pass


class OllamaConnectionError(OllamaError):
    pass


class OllamaModelNotFoundError(OllamaError):
    pass


class OllamaAPIError(OllamaError):
    pass


class OllamaStructuredOutputError(OllamaError, StructuredOutputError):
    def __init__(
        self,
        message: str,
        raw_response: str | None = None,
        validation_error: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.raw_response = raw_response
        self.validation_error = validation_error


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def check_connection(self) -> bool:
        try:
            response = self._client.get(f"{self.base_url}/api/version", timeout=2.0)
            return response.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    def list_models(self) -> list[str]:
        try:
            response = self._client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
            return [model["name"] for model in data.get("models", [])]
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise OllamaConnectionError(f"Serveur Ollama inaccessible sur {self.base_url}") from exc
        except httpx.HTTPError as exc:
            raise OllamaAPIError(f"Erreur de récupération des modèles: {exc}") from exc

    def _format_messages(self, messages: list[ChatMessage | dict[str, Any]]) -> list[dict[str, Any]]:
        formatted: list[dict[str, Any]] = []
        for m in messages:
            if isinstance(m, ChatMessage):
                formatted.append(m.model_dump_for_api())
            elif isinstance(m, dict):
                formatted.append(m)
        return formatted

    def chat_stream_raw(
        self,
        model: str,
        messages: list[ChatMessage | dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        format: str | dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        formatted_messages = self._format_messages(messages)
        payload: dict[str, Any] = {"model": model, "messages": formatted_messages, "stream": True}
        if tools:
            payload["tools"] = tools
        if format is not None:
            payload["format"] = format

        try:
            with self._client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                if response.status_code == 404:
                    raise OllamaModelNotFoundError(
                        f"Le modèle '{model}' est introuvable sur le serveur Ollama."
                    )
                if response.is_error:
                    response.read()
                    raise OllamaAPIError(
                        f"Erreur HTTP {response.status_code} d'Ollama: {response.text}"
                    )
                for line in response.iter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if "error" in data:
                        err_msg = data["error"]
                        if "not found" in err_msg.lower():
                            raise OllamaModelNotFoundError(f"Modèle '{model}' introuvable: {err_msg}")
                        raise OllamaAPIError(err_msg)
                    yield data
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise OllamaConnectionError(
                f"Serveur Ollama inaccessible sur {self.base_url}. Vérifiez qu'Ollama est bien démarré."
            ) from exc
        except httpx.HTTPError as exc:
            if not isinstance(exc, (OllamaError,)):
                raise OllamaAPIError(f"Erreur de communication avec Ollama: {exc}") from exc

    def chat_stream(
        self,
        model: str,
        messages: list[ChatMessage | dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Iterator[str]:
        for data in self.chat_stream_raw(model=model, messages=messages, tools=tools):
            chunk = data.get("message", {}).get("content", "")
            if chunk:
                yield chunk

    def chat(
        self,
        model: str,
        messages: list[ChatMessage | dict[str, Any]],
        format: str | dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        formatted_messages = self._format_messages(messages)
        payload: dict[str, Any] = {"model": model, "messages": formatted_messages, "stream": False}
        if format is not None:
            payload["format"] = format
        if tools is not None:
            payload["tools"] = tools

        try:
            response = self._client.post(f"{self.base_url}/api/chat", json=payload)
            if response.status_code == 404:
                raise OllamaModelNotFoundError(
                    f"Le modèle '{model}' est introuvable sur le serveur Ollama."
                )
            if response.is_error:
                raise OllamaAPIError(
                    f"Erreur HTTP {response.status_code} d'Ollama: {response.text}"
                )
            data = response.json()
            if "error" in data:
                err_msg = data["error"]
                if "not found" in err_msg.lower():
                    raise OllamaModelNotFoundError(f"Modèle '{model}' introuvable: {err_msg}")
                raise OllamaAPIError(err_msg)
            return data
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise OllamaConnectionError(
                f"Serveur Ollama inaccessible sur {self.base_url}. Vérifiez qu'Ollama est bien démarré."
            ) from exc
        except httpx.HTTPError as exc:
            if not isinstance(exc, (OllamaError,)):
                raise OllamaAPIError(f"Erreur de communication avec Ollama: {exc}") from exc

    def chat_structured(
        self,
        model: str,
        messages: list[ChatMessage | dict[str, Any]],
        response_format: type[T],
        max_retries: int = 1,
    ) -> T:
        try:
            return chat_structured_flow(
                client_chat_fn=self.chat,
                model=model,
                messages=messages,
                response_format=response_format,
                max_retries=max_retries,
            )
        except StructuredOutputError as exc:
            raise OllamaStructuredOutputError(
                str(exc),
                raw_response=exc.raw_response,
                validation_error=exc.validation_error,
            ) from exc

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "OllamaClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
