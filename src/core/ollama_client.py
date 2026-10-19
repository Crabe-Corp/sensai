import json
from collections.abc import Iterator
from typing import Any, Literal, TypeVar
import httpx
from pydantic import BaseModel, Field, ValidationError
from qdrant_client import QdrantClient
from src.RAG.RAG_embedding import get_embedding, COLLECTION_NAME
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
        """Convertit le message de chat en dictionnaire conforme à l'API d'Ollama.
                PARAMS: Aucun
                RETURN: dictionnaire contenant le rôle, le contenu et d'éventuels appels d'outils"""
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
        """Initialise l'exception d'erreur de sortie structurée spécifique au client Ollama.
                PARAMS: - message - STR: message décrivant l'erreur
                        - raw_response - STR: chaîne brute retournée par Ollama
                        - validation_error - EXCEPTION: erreur d'origine de validation Pydantic
                RETURN: None"""
        super().__init__(message)
        self.raw_response = raw_response
        self.validation_error = validation_error


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", timeout: float = 180.0) -> None:
        """Initialise le client HTTP direct pour l'API locale d'Ollama.
                PARAMS: - base_url - STR: adresse racine du serveur Ollama
                        - timeout - FLOAT: délai maximal d'attente des requêtes en secondes
                RETURN: None"""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def check_connection(self) -> bool:
        """Vérifie la disponibilité et l'accessibilité du serveur Ollama local.
                PARAMS: Aucun
                RETURN: booléen indiquant si le serveur répond correctement"""
        try:
            response = self._client.get(f"{self.base_url}/api/version", timeout=2.0)
            return response.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    def list_models(self) -> list[str]:
        """Récupère la liste des noms de modèles installés localement sur le serveur Ollama.
                PARAMS: Aucun
                RETURN: liste des identifiants de modèles disponibles"""
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
        """Convertit une liste de messages mixtes en liste de dictionnaires pour l'API Ollama.
                PARAMS: - messages - LIST: liste contenant des ChatMessage ou dictionnaires bruts
                RETURN: liste de dictionnaires formatés pour l'API Ollama"""
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
        """Émet les morceaux de réponse bruts en streaming ndjson depuis l'API /api/chat d'Ollama.
                PARAMS: - model - STR: nom du modèle à interroger
                        - messages - LIST: historique des messages
                        - tools - LIST: outils déclarés pour function calling
                        - format - STR | DICT: format de sortie (ex: JSON Schema)
                RETURN: itérateur de dictionnaires représentant les réponses brutes d'Ollama"""
        formatted_messages = [dict(m) for m in self._format_messages(messages)]

        derniere_question = formatted_messages[-1].get("content", "") if formatted_messages else ""
        try:
            if not formatted_messages or formatted_messages[-1].get("role") != "user":
                raise ValueError("RAG réservé aux messages utilisateur")
            client = QdrantClient("localhost", port=6333)
            vecteur_question = get_embedding(derniere_question)

            reponse_qdrant = client.query_points(
                collection_name=COLLECTION_NAME,
                query=vecteur_question,
                limit=3
            )

            resultats = reponse_qdrant.points
            contexte_historique = ""
            for hit in resultats:
                source = hit.payload.get("source", "")
                texte = hit.payload.get("texte", "")
                contexte_historique += f"[Source : {source}]\n{texte}\n\n"
            
            if contexte_historique:
                prompt_final = (
                    f"Tu es un conseiller stratégique de la période des Royaumes Combattants. "
                    f"Réponds à la question exclusivement en utilisant ce contexte historique :\n\n"
                    f"{contexte_historique}\n\n"
                    f"Question : {derniere_question}"
                )
                formatted_messages[-1]["content"] = prompt_final
        except Exception:
            pass

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
        """Émet directement les fragments textuels (tokens) de la réponse en streaming.
                PARAMS: - model - STR: nom du modèle à interroger
                        - messages - LIST: historique des messages
                        - tools - LIST: outils optionnels
                RETURN: itérateur de chaînes de caractères correspondant aux tokens générés"""
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
        """Effectue un appel synchrone bloquant et non streamé à l'API /api/chat d'Ollama.
                PARAMS: - model - STR: nom du modèle à interroger
                        - messages - LIST: historique des messages
                        - format - STR | DICT: contrainte de format optionnelle
                        - tools - LIST: outils déclarés optionnels
                RETURN: dictionnaire contenant la réponse complète d'Ollama"""
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
        """Interroge Ollama avec garantie de conformité stricte au modèle Pydantic response_format.
                PARAMS: - model - STR: nom du modèle à interroger
                        - messages - LIST: historique des messages
                        - response_format - TYPE[T]: classe Pydantic attendue en sortie
                        - max_retries - INT: nombre de tentatives de relance en cas d'erreur de schéma
                RETURN: instance validée du modèle Pydantic de type T"""
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
        """Ferme le client HTTP sous-jacent et libère les connexions actives.
                PARAMS: Aucun
                RETURN: None"""
        self._client.close()

    def __enter__(self) -> "OllamaClient":
        """Initialise le contexte d'utilisation du client Ollama.
                PARAMS: Aucun
                RETURN: l'instance d'OllamaClient"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Clôture le client HTTP à la sortie du bloc de contexte.
                PARAMS: - exc_type - ANY: type de l'exception
                        - exc_val - ANY: instance de l'exception
                        - exc_tb - ANY: traceback de l'exception
                RETURN: None"""
        self.close()
