import json
import requests
from collections.abc import Iterator
from typing import Literal
import httpx
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, Prefetch, NamedVector, NamedSparseVector, FusionQuery, Fusion
from src.RAG.RAG_embedding import get_embedding, COLLECTION_NAME
from typing import Any, Literal, TypeVar
import httpx
from pydantic import BaseModel, Field, ValidationError
from fastembed import SparseTextEmbedding

T = TypeVar("T", bound=BaseModel)


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class OllamaError(Exception):
    pass


class OllamaConnectionError(OllamaError):
    pass


class OllamaModelNotFoundError(OllamaError):
    pass


class OllamaAPIError(OllamaError):
    pass


class OllamaStructuredOutputError(OllamaError):
    def __init__(self, message: str, raw_response: str | None = None, validation_error: Exception | None = None) -> None:
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
        
        prompt_final = (
            f"Tu es un conseiller stratégique de la période des Royaumes Combattants. "
            f"Réponds à la question exclusivement en utilisant ce contexte historique :\n\n"
            f"{contexte_historique}\n\n"
            f"Question : {derniere_question}"
        )
            
        # 4. Remplacer le contenu du dernier message par le prompt enrichi
        formatted_messages[-1]["content"] = prompt_final

        payload = {
            "model": model,
            "messages": formatted_messages, # On passe bien la liste complète à l'API Chat
            "stream": True,
        }
   
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

                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        yield chunk
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise OllamaConnectionError(
                f"Serveur Ollama inaccessible sur {self.base_url}. Vérifiez qu'Ollama est bien démarré."
            ) from exc
        except httpx.HTTPError as exc:
            if not isinstance(exc, (OllamaError,)):
                raise OllamaAPIError(f"Erreur de communication avec Ollama: {exc}") from exc

    def chat(self, model: str, messages: list[ChatMessage | dict[str, str]], format: str | dict[str, Any] | None = None) -> dict[str, Any]:
        formatted_messages = [m.model_dump() if isinstance(m, ChatMessage) else m for m in messages]
        payload: dict[str, Any] = {"model": model, "messages": formatted_messages, "stream": False}
        if format is not None:
            payload["format"] = format

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

    def chat_structured(self, model: str, messages: list[ChatMessage | dict[str, str]], response_format: type[T], max_retries: int = 1) -> T:
        schema = response_format.model_json_schema()
        current_messages: list[ChatMessage | dict[str, str]] = list(messages)
        last_raw_content: str | None = None
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            response_data = self.chat(model=model, messages=current_messages, format=schema)
            raw_content = response_data.get("message", {}).get("content", "")
            last_raw_content = raw_content

            try:
                return response_format.model_validate_json(raw_content)
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < max_retries:
                    current_messages.append({"role": "assistant", "content": raw_content})
                    current_messages.append(
                        {"role": "user", "content": (f"La réponse précédente est invalide et ne respecte pas le schéma JSON attendu. " f"Erreur de validation : {exc}. " f"Veuillez corriger et renvoyer exclusivement l'objet JSON conforme au schéma."),}
                    )
        raise OllamaStructuredOutputError(
            f"Échec de validation de la réponse structurée ({response_format.__name__}) après {max_retries + 1} tentative(s).",
            raw_response=last_raw_content,
            validation_error=last_error,
        )

    def call_model(self, model: str, messages: str):
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
        if format is not None:
            payload["format"] = format

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
        self._client.close()

    def __enter__(self) -> "OllamaClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
