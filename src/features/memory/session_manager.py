import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from pydantic import BaseModel, Field

from src.core.ollama_client import ChatMessage
from src.features.memory.profile_manager import UserProfile


class SessionMetadata(BaseModel):
    session_id: str
    title: str
    created_at: str
    updated_at: str
    model: str
    username: str | None = None


class ChatSession(BaseModel):
    metadata: SessionMetadata
    messages: list[ChatMessage] = Field(default_factory=list)

    def add_message(self, message: ChatMessage) -> None:
        """Ajoute un message à l'historique et actualise l'horodatage de mise à jour."""
        self.messages.append(message)
        self.metadata.updated_at = datetime.now(timezone.utc).isoformat()

    def update_timestamp(self) -> None:
        """Actualise l'horodatage de dernière modification de la session."""
        self.metadata.updated_at = datetime.now(timezone.utc).isoformat()


class SessionManager:
    def __init__(self, storage_dir: Path | str = "storage/sessions") -> None:
        """Initialise le gestionnaire de sessions conversationnelles.
        PARAMS: - storage_dir - PATH | STR: répertoire de persistance des sessions JSON
        RETURN: None"""
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_session_id(self, session_id: str) -> str:
        clean = re.sub(r"[^\w\-.]", "_", session_id.strip())
        return clean or uuid.uuid4().hex[:8]

    def _get_session_path(self, session_id: str) -> Path:
        clean_id = self._sanitize_session_id(session_id)
        return self.storage_dir / f"{clean_id}.json"

    def create_session(
        self,
        profile: UserProfile | None = None,
        model: str = "qwen2.5:1.5b",
        title: str | None = None,
    ) -> ChatSession:
        """Crée une nouvelle session de chat et y injecte le profil utilisateur si fourni.
        PARAMS: - profile - USERPROFILE | NONE: profil utilisateur contenant les consignes
                - model - STR: modèle d'IA sélectionné pour cette session
                - title - STR | NONE: libellé descriptif de la session
        RETURN: instance ChatSession initialisée et immédiatement persistée"""
        session_id = uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc).isoformat()
        session_title = title.strip() if title and title.strip() else f"Session {session_id}"

        messages: list[ChatMessage] = []
        if profile is not None:
            prompt_content = profile.format_system_prompt()
            messages.append(ChatMessage(role="system", content=prompt_content))

        metadata = SessionMetadata(
            session_id=session_id,
            title=session_title,
            created_at=now,
            updated_at=now,
            model=model,
            username=profile.username if profile else None,
        )
        session = ChatSession(metadata=metadata, messages=messages)
        self.save_session(session)
        return session

    def save_session(self, session: ChatSession) -> None:
        """Sauvegarde atomique d'une session au format JSON sur le disque.
        PARAMS: - session - CHATSESSION: objet session complet à persister
        RETURN: None"""
        target_path = self._get_session_path(session.metadata.session_id)
        temp_path = self.storage_dir / f"{target_path.name}.tmp.{uuid.uuid4().hex[:6]}"

        session.metadata.updated_at = datetime.now(timezone.utc).isoformat()
        payload = session.model_dump_json(indent=2)
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(temp_path, target_path)

    def load_session(self, session_id: str) -> ChatSession:
        """Charge une session et son historique intégral depuis le stockage disque.
        PARAMS: - session_id - STR: identifiant unique de la session
        RETURN: instance ChatSession reconstituée"""
        path = self._get_session_path(session_id)
        if not path.is_file():
            raise FileNotFoundError(f"Session '{session_id}' introuvable dans {self.storage_dir}")
        with open(path, "r", encoding="utf-8") as f:
            return ChatSession.model_validate_json(f.read())

    def list_sessions(self) -> list[SessionMetadata]:
        """Retourne la liste de toutes les sessions sauvegardées, ordonnées par date de mise à jour.
        PARAMS: Aucun
        RETURN: liste des métadonnées SessionMetadata de la plus récente à la plus ancienne"""
        sessions_meta: list[SessionMetadata] = []
        for file_path in self.storage_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    meta_raw = data.get("metadata", data)
                    sessions_meta.append(SessionMetadata.model_validate(meta_raw))
            except Exception:
                continue

        return sorted(sessions_meta, key=lambda s: s.updated_at, reverse=True)

    def delete_session(self, session_id: str) -> bool:
        """Supprime une session sauvegardée du système de fichiers.
        PARAMS: - session_id - STR: identifiant de la session à effacer
        RETURN: True si supprimée avec succès, False si le fichier n'existait pas"""
        path = self._get_session_path(session_id)
        if path.is_file():
            path.unlink()
            return True
        return False

    def rename_session(self, session_id: str, new_title: str) -> ChatSession:
        """Renomme le titre descriptif d'une session existante.
        PARAMS: - session_id - STR: identifiant de la session à renommer
                - new_title - STR: nouveau libellé
        RETURN: instance ChatSession mise à jour"""
        session = self.load_session(session_id)
        session.metadata.title = new_title.strip()
        self.save_session(session)
        return session
