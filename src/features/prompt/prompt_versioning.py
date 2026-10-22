from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from pydantic import BaseModel, Field


class PromptVersion(BaseModel):
    """Représentation d'une révision horodatée et immuable d'un prompt système."""

    version: int
    persona_name: str
    timestamp: str
    content_hash: str
    content: str
    author: str = "user"
    message: str = ""


class PromptVersioningEngine:
    """Moteur de versioning, traçabilité et rollback des personas et prompts système."""

    def __init__(
        self,
        storage_dir: Path | str = "storage/prompt_versions",
        personas_dir: Path | str = "personnalites",
    ) -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.personas_dir = Path(personas_dir)
        self.personas_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_name(self, name: str) -> str:
        clean = Path(name).stem.lower().strip()
        clean = re.sub(r"[^\w\-.]", "_", clean)
        return clean or "default"

    def _get_persona_dir(self, persona_name: str) -> Path:
        clean = self._sanitize_name(persona_name)
        directory = self.storage_dir / clean
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _parse_version_number(self, target: int | str) -> int:
        if isinstance(target, int):
            return target
        clean_str = str(target).strip().lower()
        if clean_str.startswith("v"):
            clean_str = clean_str[1:]
        try:
            return int(clean_str)
        except ValueError as err:
            raise ValueError(f"Numéro de version invalide : '{target}'") from err

    def save_version(
        self,
        persona_name: str,
        content: str,
        author: str = "user",
        message: str = "",
    ) -> PromptVersion:
        """Enregistre une nouvelle version du prompt si le contenu a changé."""
        clean_name = self._sanitize_name(persona_name)
        target_dir = self._get_persona_dir(clean_name)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        history = self.get_history(clean_name)
        if history and history[-1].content_hash == content_hash:
            return history[-1]

        next_version = (history[-1].version + 1) if history else 1
        now_iso = datetime.now(timezone.utc).isoformat()

        prompt_version = PromptVersion(
            version=next_version,
            persona_name=clean_name,
            timestamp=now_iso,
            content_hash=content_hash,
            content=content,
            author=author,
            message=message,
        )

        version_file = target_dir / f"v{next_version}.json"
        temp_file = target_dir / f"v{next_version}.tmp.{os.getpid()}"
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(prompt_version.model_dump_json(indent=2))
        os.replace(temp_file, version_file)

        return prompt_version

    def get_history(self, persona_name: str) -> list[PromptVersion]:
        """Retourne l'ensemble des révisions enregistrées pour une persona, triées par version."""
        clean_name = self._sanitize_name(persona_name)
        target_dir = self.storage_dir / clean_name
        if not target_dir.is_dir():
            return []

        versions: list[PromptVersion] = []
        for file in target_dir.glob("v*.json"):
            match = re.match(r"^v(\d+)\.json$", file.name)
            if not match:
                continue
            try:
                with open(file, "r", encoding="utf-8") as f:
                    versions.append(PromptVersion.model_validate_json(f.read()))
            except (json.JSONDecodeError, OSError):
                continue

        versions.sort(key=lambda v: v.version)
        return versions

    def get_version(self, persona_name: str, target_version: int | str) -> PromptVersion:
        """Récupère une version spécifique d'un prompt par son identifiant numérique."""
        ver_num = self._parse_version_number(target_version)
        history = self.get_history(persona_name)
        for item in history:
            if item.version == ver_num:
                return item
        clean_name = self._sanitize_name(persona_name)
        raise ValueError(f"Version v{ver_num} introuvable pour la persona '{clean_name}'.")

    def get_diff(self, persona_name: str, v_from: int | str, v_to: int | str) -> str:
        """Calcule un diff unifié entre deux versions d'une même persona."""
        clean_name = self._sanitize_name(persona_name)
        ver_from = self.get_version(clean_name, v_from)
        ver_to = self.get_version(clean_name, v_to)

        lines_from = ver_from.content.splitlines(keepends=True)
        lines_to = ver_to.content.splitlines(keepends=True)

        diff_gen = difflib.unified_diff(
            lines_from,
            lines_to,
            fromfile=f"{clean_name} (v{ver_from.version})",
            tofile=f"{clean_name} (v{ver_to.version})",
        )
        return "".join(diff_gen)

    def _resolve_active_file(self, persona_name: str) -> Path:
        clean = self._sanitize_name(persona_name)
        exact_path = self.personas_dir / persona_name
        if exact_path.is_file():
            return exact_path

        for ext in (".md", ".json", ".txt"):
            candidate = self.personas_dir / f"{clean}{ext}"
            if candidate.is_file():
                return candidate

        for f in self.personas_dir.iterdir():
            if f.is_file() and f.stem.lower() == clean:
                return f

        return self.personas_dir / f"{clean}.md"

    def rollback(self, persona_name: str, target_version: int | str) -> str:
        """Restaure une version passée dans le fichier actif de personnalites/ et journalise l'opération."""
        clean_name = self._sanitize_name(persona_name)
        target = self.get_version(clean_name, target_version)
        active_path = self._resolve_active_file(clean_name)

        active_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = active_path.with_name(f"{active_path.name}.tmp.{os.getpid()}")
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(target.content)
        os.replace(temp_path, active_path)

        self.save_version(
            clean_name,
            target.content,
            author="system",
            message=f"Rollback vers la version v{target.version}",
        )
        return target.content


default_versioning_engine = PromptVersioningEngine()


def save_version(
    persona_name: str,
    content: str,
    author: str = "user",
    message: str = "",
) -> PromptVersion:
    return default_versioning_engine.save_version(persona_name, content, author=author, message=message)


def get_history(persona_name: str) -> list[PromptVersion]:
    return default_versioning_engine.get_history(persona_name)


def get_diff(persona_name: str, v_from: int | str, v_to: int | str) -> str:
    return default_versioning_engine.get_diff(persona_name, v_from, v_to)


def rollback(persona_name: str, target_version: int | str) -> str:
    return default_versioning_engine.rollback(persona_name, target_version)
