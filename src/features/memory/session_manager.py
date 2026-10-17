import json
import os
import re
import socket
import time
from urllib.parse import urlparse
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.core.ollama_client import ChatMessage
from src.features.memory.profile_manager import UserProfile


class SessionMetadata(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    session_id: str = Field(alias="id")
    title: str = "Nouvelle session"
    created_at: str = ""
    updated_at: str = ""
    model: str = Field(default="qwen2.5:1.5b", alias="model_name")
    username: str | None = None
    source: str = "local"

    @property
    def id(self) -> str:
        return self.session_id

    @property
    def model_name(self) -> str:
        return self.model


class ChatSession(BaseModel):
    metadata: SessionMetadata
    messages: list[ChatMessage] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_input(cls, data: Any) -> Any:
        if isinstance(data, dict) and "metadata" not in data and ("id" in data or "session_id" in data):
            sid = data.get("id") or data.get("session_id")
            title = data.get("title") or f"Session {str(sid)[:8]}"
            model = data.get("model_name") or data.get("model") or "qwen2.5:1.5b"
            meta = {
                "id": str(sid),
                "title": title,
                "model_name": model,
                "created_at": data.get("created_at") or "",
                "updated_at": data.get("updated_at") or "",
                "username": data.get("username"),
                "source": data.get("source", "web"),
            }
            return {"metadata": meta, "messages": data.get("messages", [])}
        return data

    def add_message(self, message: ChatMessage) -> None:
        self.messages.append(message)
        self.metadata.updated_at = datetime.now(timezone.utc).isoformat()

    def update_timestamp(self) -> None:
        self.metadata.updated_at = datetime.now(timezone.utc).isoformat()


class SessionManager:
    def __init__(
        self,
        storage_dir: Path | str = "storage/sessions",
        backend_url: str | None = None,
    ) -> None:
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

    def _find_session_path(self, session_id: str) -> Path | None:
        clean_id = self._sanitize_session_id(session_id)
        exact_path = self.storage_dir / f"{clean_id}.json"
        if exact_path.is_file():
            return exact_path
        matches = list(self.storage_dir.glob(f"{clean_id}*.json"))
        return matches[0] if matches else None

    def create_session(
        self,
        profile: UserProfile | None = None,
        model: str = "qwen2.5:1.5b",
        title: str | None = None,
    ) -> ChatSession:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        session_title = title.strip() if title and title.strip() else f"Session {session_id[:8]}"

        messages: list[ChatMessage] = []
        if profile is not None:
            messages.append(ChatMessage(role="system", content=profile.format_system_prompt()))

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
        target_path = self.storage_dir / f"{session.metadata.session_id}.json"
        temp_path = self.storage_dir / f"{target_path.name}.tmp.{uuid.uuid4().hex[:6]}"
        session.metadata.updated_at = datetime.now(timezone.utc).isoformat()
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(session.model_dump_json(indent=2))
        os.replace(temp_path, target_path)

        if sync_remote and self._is_backend_available():
            try:
                with httpx.Client(timeout=1.0) as client:
                    client.post(
                        f"{self.backend_url}/api/conversations/{session.metadata.session_id}",
                        json=session.model_dump(),
                    )
            except Exception:
                pass

    def load_session(self, session_id: str) -> ChatSession:
        path = self._find_session_path(session_id)
        if path and path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                return ChatSession.model_validate_json(f.read())

        if self._is_backend_available():
            clean_id = self._sanitize_session_id(session_id)
            try:
                with httpx.Client(timeout=1.5) as client:
                    resp = client.get(f"{self.backend_url}/api/conversations/{clean_id}")
                    if resp.status_code == 200:
                        session = ChatSession.model_validate(resp.json())
                        session.metadata.source = "web"
                        self.save_session(session, sync_remote=False)
                        return session
            except Exception:
                pass

        raise FileNotFoundError(f"Session '{session_id}' introuvable localement ou sur le serveur Web.")

    def list_sessions(self) -> list[SessionMetadata]:
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

        # 2. Conversations Web depuis l'API REST standard
        if self._is_backend_available():
            try:
                with httpx.Client(timeout=1.0) as client:
                    resp = client.get(f"{self.backend_url}/api/conversations")
                    if resp.status_code == 200:
                        for item in resp.json():
                            sid = item.get("id") or item.get("session_id")
                            if sid and sid not in sessions_map:
                                sessions_map[sid] = SessionMetadata(
                                    session_id=sid,
                                    title=item.get("title", f"Session {sid[:8]}"),
                                    created_at=item.get("created_at") or "",
                                    updated_at=item.get("updated_at") or "",
                                    model=item.get("model_name") or item.get("model") or "qwen2.5:1.5b",
                                    username=item.get("username"),
                                    source="web",
                                )
            except Exception:
                pass

        return sorted(sessions_map.values(), key=lambda s: s.updated_at, reverse=True)

    def delete_session(self, session_id: str) -> bool:
        path = self._find_session_path(session_id)
        clean_id = path.stem if path else self._sanitize_session_id(session_id)
        deleted_local = False
        if path and path.is_file():
            path.unlink()
            deleted_local = True

        deleted_remote = False
        if self._is_backend_available():
            try:
                with httpx.Client(timeout=1.0) as client:
                    resp = client.delete(f"{self.backend_url}/api/conversations/{clean_id}")
                    deleted_remote = (resp.status_code == 200)
            except Exception:
                pass

        return deleted_local or deleted_remote

    def rename_session(self, session_id: str, new_title: str) -> ChatSession:
        session = self.load_session(session_id)
        session.metadata.title = new_title.strip()
        self.save_session(session)
        return session
