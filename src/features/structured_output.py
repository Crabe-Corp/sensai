import json
from typing import Any, TypeVar
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class StructuredOutputError(Exception):
    def __init__(self, message: str, raw_response: str | None = None, validation_error: Exception | None = None,) -> None:
        """Initialise une exception d'erreur de sortie structurée avec la réponse brute et l'erreur interne.
                PARAMS: - message - STR: message d'erreur
                        - raw_response - STR: réponse textuelle brute du modèle
                        - validation_error - EXCEPTION: erreur d'origine levée lors de la validation
                RETURN: None"""
        super().__init__(message)
        self.raw_response = raw_response
        self.validation_error = validation_error

def generate_json_schema(schema_cls: type[BaseModel]) -> dict[str, Any]:
    """Génère le schéma JSON Schema correspondant à un modèle Pydantic donné.
            PARAMS: - schema_cls - TYPE[BASEMODEL]: classe du modèle Pydantic
            RETURN: dictionnaire représentant le JSON Schema complet"""
    return schema_cls.model_json_schema()


def validate_structured_json(raw_content: str, response_format: type[T]) -> T:
    """Valide et désérialise une chaîne JSON brute dans le modèle Pydantic attendu.
            PARAMS: - raw_content - STR: contenu textuel JSON à valider
                    - response_format - TYPE[T]: classe Pydantic cible
            RETURN: instance validée du modèle Pydantic de type T"""
    return response_format.model_validate_json(raw_content)


def build_retry_correction_message(raw_content: str, error: Exception) -> dict[str, str]:
    """Construit un message d'instruction de relance invitant le LLM à corriger son JSON.
            PARAMS: - raw_content - STR: contenu brut ayant échoué
                    - error - EXCEPTION: exception levée lors de la validation
            RETURN: dictionnaire de message utilisateur contenant les consignes de correction"""
    return {
        "role": "user",
        "content": (
            "The previous response is invalid and does not adhere to the expected JSON schema. "
            f"Validation error (Erreur de validation) : {error}. "
            "Please correct and return exclusively the JSON object matching the schema."
        ),
    }


def chat_structured_flow(client_chat_fn: Any, model: str, messages: list[Any], response_format: type[T], max_retries: int = 1) -> T:
    """Orchestre l'appel chat avec format JSON et mécanisme d'auto-correction en boucle de retry.
            PARAMS: - client_chat_fn - ANY: fonction d'appel synchrone du client LLM
                    - model - STR: nom du modèle Ollama
                    - messages - LIST: liste de messages du dialogue
                    - response_format - TYPE[T]: classe Pydantic ciblée
                    - max_retries - INT: nombre maximal de tentatives de correction autorisées
            RETURN: instance validée du modèle Pydantic de type T"""

    schema = generate_json_schema(response_format)
    current_messages = list(messages)
    last_raw_content: str | None = None
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        response_data = client_chat_fn(model=model, messages=current_messages, format=schema)
        raw_content = response_data.get("message", {}).get("content", "")
        last_raw_content = raw_content
        try:
            return response_format.model_validate_json(raw_content)
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
