import json
import os
import re
import socket
import time
from urllib.parse import urlparse
import uuid
from datetime import datetime, timezone
from pathlib import Path
from pydantic import BaseModel, Field
import httpx

from src.core.ollama_client import ChatMessage
from src.features.memory.profile_manager import UserProfile


class SessionMetadata(BaseModel):
    session_id: str
    title: str
    created_at: str
    updated_at: str
    model: str
    username: str | None = None
    source: str = "local"


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
    def __init__(
        self,
        storage_dir: Path | str = "storage/sessions",
        backend_url: str | None = None,
    ) -> None:
        """Initialise le gestionnaire de sessions conversationnelles avec support de synchro Web.
        PARAMS: - storage_dir - PATH | STR: répertoire de persistance des sessions JSON
                - backend_url - STR | NONE: URL de l'API backend pour synchronisation (défaut: SENSAI_BACKEND_URL ou http://localhost:8080)
        RETURN: None"""
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.backend_url = (
            backend_url
            if backend_url is not None
            else os.getenv("SENSAI_BACKEND_URL", "http://localhost:8080")
        )
        self._last_backend_check: float = 0.0
        self._backend_alive: bool = False

    def _is_backend_available(self) -> bool:
        if not self.backend_url:
            return False
        if self.backend_url.startswith(("http://test", "http://mock")):
            return True
        now = time.time()
        if now - self._last_backend_check < 5.0:
            return self._backend_alive
        self._last_backend_check = now
        try:
            parsed = urlparse(self.backend_url)
            host = parsed.hostname or "localhost"
            port = parsed.port or 8080
            with socket.create_connection((host, port), timeout=0.05):
                self._backend_alive = True
                return True
        except (OSError, TimeoutError):
            self._backend_alive = False
            return False

    def _sanitize_session_id(self, session_id: str) -> str:
        clean = re.sub(r"[^\w\-.]", "_", session_id.strip())
        return clean or uuid.uuid4().hex[:8]

    def _get_session_path(self, session_id: str) -> Path:
        clean_id = self._sanitize_session_id(session_id)
        return self.storage_dir / f"{clean_id}.json"

    def _find_session_path(self, session_id: str) -> Path | None:
        clean_id = self._sanitize_session_id(session_id)
        exact_path = self.storage_dir / f"{clean_id}.json"
        if exact_path.is_file():
            return exact_path

        matches = list(self.storage_dir.glob(f"{clean_id}*.json"))
        if matches:
            return matches[0]
        return None

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
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        session_title = title.strip() if title and title.strip() else f"Session {session_id[:8]}"

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
            source="local",
        )
        session = ChatSession(metadata=metadata, messages=messages)
        self.save_session(session)
        return session

    def save_session(self, session: ChatSession, sync_remote: bool = True) -> None:
        """Sauvegarde atomique d'une session au format JSON sur le disque et synchronisation Web.
        PARAMS: - session - CHATSESSION: objet session complet à persister
                - sync_remote - BOOL: indique si la session doit être poussée vers le backend Web
        RETURN: None"""
        target_path = self._get_session_path(session.metadata.session_id)
        temp_path = self.storage_dir / f"{target_path.name}.tmp.{uuid.uuid4().hex[:6]}"

        session.metadata.updated_at = datetime.now(timezone.utc).isoformat()
        payload = session.model_dump_json(indent=2)
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(temp_path, target_path)

        if sync_remote and self._is_backend_available():
            try:
                with httpx.Client(timeout=1.0) as client:
                    client.post(
                        f"{self.backend_url}/api/conversations/sync/{session.metadata.session_id}",
                        json=session.model_dump(),
                    )
            except Exception:
                pass

    def load_session(self, session_id: str) -> ChatSession:
        """Charge une session et son historique depuis le stockage disque ou l'API Web.
        PARAMS: - session_id - STR: identifiant unique ou préfixe de la session
        RETURN: instance ChatSession reconstituée"""
        path = self._find_session_path(session_id)
        if path and path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                return ChatSession.model_validate_json(f.read())

        if self._is_backend_available():
            clean_id = self._sanitize_session_id(session_id)
            try:
                with httpx.Client(timeout=1.5) as client:
                    resp = client.get(f"{self.backend_url}/api/conversations/sync/{clean_id}")
                    if resp.status_code == 200:
                        data = resp.json()
                        session = ChatSession.model_validate(data)
                        session.metadata.source = "web"
                        self.save_session(session, sync_remote=False)
                        return session
            except Exception:
                pass

        raise FileNotFoundError(f"Session '{session_id}' introuvable localement ou sur le serveur Web.")

    def list_sessions(self) -> list[SessionMetadata]:
        """Retourne la liste de toutes les sessions sauvegardées (locales et Web).
        PARAMS: Aucun
        RETURN: liste des métadonnées SessionMetadata ordonnée par date de mise à jour"""
        sessions_map: dict[str, SessionMetadata] = {}

        # 1. Sessions locales
        for file_path in self.storage_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    meta_raw = data.get("metadata", data)
                    meta = SessionMetadata.model_validate(meta_raw)
                    sessions_map[meta.session_id] = meta
            except Exception:
                continue

        if self._is_backend_available():
            try:
                with httpx.Client(timeout=1.0) as client:
                    resp = client.get(f"{self.backend_url}/api/conversations/sync/list")
                    if resp.status_code == 200:
                        remote_list = resp.json()
                        for item in remote_list:
                            sid = item.get("session_id") or item.get("id")
                            if sid and sid not in sessions_map:
                                meta = SessionMetadata(
                                    session_id=sid,
                                    title=item.get("title", f"Session {sid[:8]}"),
                                    created_at=item.get("created_at") or "",
                                    updated_at=item.get("updated_at") or "",
                                    model=item.get("model") or item.get("model_name") or "qwen2.5:1.5b",
                                    username=item.get("username"),
                                    source="web",
                                )
                                sessions_map[sid] = meta
            except Exception:
                pass

        return sorted(sessions_map.values(), key=lambda s: s.updated_at, reverse=True)

    def delete_session(self, session_id: str) -> bool:
        """Supprime une session sauvegardée du système de fichiers et du serveur Web.
        PARAMS: - session_id - STR: identifiant de la session à effacer
        RETURN: True si supprimée avec succès, False si inexistante"""
        deleted_local = False
        path = self._find_session_path(session_id)
        clean_id = path.stem if path else self._sanitize_session_id(session_id)
        if path and path.is_file():
            path.unlink()
            deleted_local = True

        deleted_remote = False
        if self._is_backend_available():
            try:
                with httpx.Client(timeout=1.0) as client:
                    resp = client.delete(f"{self.backend_url}/api/conversations/sync/{clean_id}")
                    deleted_remote = (resp.status_code == 200)
            except Exception:
                pass

        return deleted_local or deleted_remote

    def rename_session(self, session_id: str, new_title: str) -> ChatSession:
        """Renomme le titre descriptif d'une session existante.
        PARAMS: - session_id - STR: identifiant de la session à renommer
                - new_title - STR: nouveau libellé
        RETURN: instance ChatSession mise à jour"""
        session = self.load_session(session_id)
        session.metadata.title = new_title.strip()
        self.save_session(session)
        return session
