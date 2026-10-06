import json
from typing import Any, TypeVar
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class StructuredOutputError(Exception):
    def __init__(
        self,
        message: str,
        raw_response: str | None = None,
        validation_error: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.raw_response = raw_response
        self.validation_error = validation_error


def generate_json_schema(schema_cls: type[BaseModel]) -> dict[str, Any]:
    return schema_cls.model_json_schema()


def validate_structured_json(raw_content: str, response_format: type[T]) -> T:
    return response_format.model_validate_json(raw_content)


def build_retry_correction_message(raw_content: str, error: Exception) -> dict[str, str]:
    return {
        "role": "user",
        "content": (
            "La réponse précédente est invalide et ne respecte pas le schéma JSON attendu. "
            f"Erreur de validation : {error}. "
            "Veuillez corriger et renvoyer exclusivement l'objet JSON conforme au schéma."
        ),
    }


def chat_structured_flow(
    client_chat_fn: Any,
    model: str,
    messages: list[Any],
    response_format: type[T],
    max_retries: int = 1,
) -> T:
    schema = generate_json_schema(response_format)
    current_messages = list(messages)
    last_raw_content: str | None = None
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        response_data = client_chat_fn(model=model, messages=current_messages, format=schema)
        raw_content = response_data.get("message", {}).get("content", "")
        last_raw_content = raw_content

        try:
            return validate_structured_json(raw_content, response_format)
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < max_retries:
                current_messages.append({"role": "assistant", "content": raw_content})
                current_messages.append(build_retry_correction_message(raw_content, exc))

    raise StructuredOutputError(
        f"Échec de validation de la réponse structurée ({response_format.__name__}) "
        f"après {max_retries + 1} tentative(s).",
        raw_response=last_raw_content,
        validation_error=last_error,
    )
