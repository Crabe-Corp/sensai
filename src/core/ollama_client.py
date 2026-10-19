import json
import requests
from collections.abc import Iterator
import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, Prefetch, FusionQuery, Fusion
from src.RAG.RAG_embedding import get_embedding, COLLECTION_NAME
from typing import Any, List, Union, TypeVar, Literal
from pydantic import BaseModel, Field, ValidationError
from fastembed import SparseTextEmbedding
from src.core import memory_management
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
        self.bm25_model = SparseTextEmbedding(model_name="Qdrant/bm25")

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

    def get_character(self, prompt : str):
        prompt_systeme = """
        Tu es un extracteur d'entités. Ton seul but est d'analyser la question de l'utilisateur 
        et d'extraire le nom du personnage historique principal mentionné.
        Retourne UNIQUEMENT un JSON strict.
        Si un personnage est trouvé : {"personnage": "Nom du personnage"}
        Si aucun personnage n'est clairement mentionné : {"personnage": null}
        """
        
        try:
            response = requests.post("http://localhost:11434/api/generate", json={
                "model": "qwen2.5:1.5b", # Utilisez votre modèle le plus rapide ici
                "prompt": f"{prompt_systeme}\nQuestion : {prompt}",
                "stream": False,
                "format": "json"
            })
            
            data = response.json()
            resultat_json = json.loads(data.get("response", "{}"))
            
            personnage = resultat_json.get("personnage")
            
            # Nettoyage basique
            if personnage and isinstance(personnage, str):
                return personnage.strip()
                
            return None
            
        except Exception as e:
            print(f"[!] Erreur lors de l'extraction de l'entité : {e}")
            return None

    def chat_stream(
        self,
        model: str,
        messages: list[ChatMessage | dict[str, str]],
    ) -> Iterator[str]:
        formatted_messages = [
            m.model_dump() if isinstance(m, ChatMessage) else m
            for m in messages
        ]
        
        derniere_question = formatted_messages[-1]["content"] if formatted_messages else ""
        
        client = QdrantClient("localhost", port=6333)

        personnage_cible = self.get_character(derniere_question)
        if personnage_cible:
            if personnage_cible.lower() not in derniere_question.lower():
                    print(f"[!] Hallucination détectée : l'IA a inventé '{personnage_cible}'. Ignoré.")
                    personnage_cible = None
        
        vecteur_question = get_embedding(derniere_question)
        sparse_vector_question = list(self.bm25_model.embed([derniere_question]))[0]

        qdrant_filter = None
        if personnage_cible:
            print(f"[*] Entité détectée : {personnage_cible}")
            qdrant_filter = Filter(
                must=[
                    FieldCondition(
                        key="personnage_principal",
                        match=MatchValue(value=personnage_cible.lower()) 
                    )
                ]
            )
        else:
            print("[*] Aucune entité spécifique détectée, recherche globale.")


        reponse_qdrant = client.query_points(
            collection_name="royaumes_combattants",
            query_filter=qdrant_filter,
            prefetch=[
                # Pré-recherche sémantique (Dense)
                Prefetch(
                    query=vecteur_question,
                    using="dense",
                    limit=20
                ),
                # Pré-recherche mots-clés exacts (BM25)
                Prefetch(
                    query=sparse_vector_question.as_object(),
                    using="sparse",
                    limit=20
                )
            ],
            # Fusion des deux listes avec l'algorithme RRF
            query=FusionQuery(fusion=Fusion.RRF),
            limit=5
        )

        # reponse_qdrant = client.query_points(
        #     collection_name="royaumes_combattants",
        #     query=vecteur_question,
        #     query_filter=qdrant_filter,
        #     limit=5
        # )

        resultats = reponse_qdrant.points
        
        contexte_historique = ""
        for hit in resultats:
            source = hit.payload["source"]
            texte = hit.payload ["texte"]
            contexte_historique += f"[Source : {source}]\n{texte}\n\n"
        
    
            
        if contexte_historique:
            prompt_final = (
                f"Tu es un conseiller stratégique de la période des Royaumes Combattants. "
                f"Réponds à la question exclusivement en utilisant ce contexte historique :\n\n"
                f"{contexte_historique}\n\n"
                f"Question : {derniere_question}"
            )
            formatted_messages[-1]["content"] = prompt_final

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
                    if data.get("done") == True:
                        input_tokens = data.get("prompt_eval_count", 0)
                        output_tokens = data.get("eval_count", 0)
                        budget_consomme = input_tokens + output_tokens
                        memory_management.consommer_tokens(budget_consomme)
                        # print(f"Tokens consommés pour ce message : {budget_consomme}")
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

    def call_model(self, model: str, messages: Union[List[Any], str], response_format: str = None):
        formatted_messages = []
        for msg in messages:
            if hasattr(msg, "role") and hasattr(msg, "content"):
                formatted_messages.append({"role": msg.role, "content": msg.content})
            elif isinstance(msg, dict):
                formatted_messages.append(msg)
            else:
                formatted_messages.append(msg)

        payload: dict[str, Any] = {"model": model, "messages": formatted_messages, "stream": False}
        
        if response_format is not None:
            payload["format"] = response_format

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
