import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field


class ArtifactDocument(BaseModel):
    title: str = "Livrable de Session"
    metadata: dict[str, Any] = Field(default_factory=dict)
    sections: dict[str, str] = Field(default_factory=dict)

    def set_section(self, section_name: str, content: str) -> None:
        clean_name = section_name.strip()
        self.sections[clean_name] = content.strip()
        self.metadata["updated_at"] = datetime.now(timezone.utc).isoformat()

    def append_to_section(self, section_name: str, content: str) -> None:
        clean_name = section_name.strip()
        clean_content = content.strip()
        if not clean_content:
            return

        existing = self.sections.get(clean_name, "").strip()
        if existing:
            # Sépare par saut de ligne simple pour les listes et double pour les paragraphes
            sep = "\n" if (existing.endswith("-") or clean_content.startswith(("-", "*", "1."))) else "\n\n"
            self.sections[clean_name] = f"{existing}{sep}{clean_content}"
        else:
            self.sections[clean_name] = clean_content
        self.metadata["updated_at"] = datetime.now(timezone.utc).isoformat()

    def delete_section(self, section_name: str) -> bool:
        clean_name = section_name.strip()
        if clean_name in self.sections:
            del self.sections[clean_name]
            self.metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
            return True
        return False

    def render_markdown(self) -> str:
        lines: list[str] = [f"# {self.title}"]
        for name, content in self.sections.items():
            lines.append("")
            lines.append(f"## {name}")
            if content:
                lines.append(content)
        return "\n".join(lines).strip() + "\n"

    def save(self, path: Path | str) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_file = target.parent / f"{target.name}.tmp.{os.getpid()}"

        if target.suffix.lower() == ".json":
            payload = self.model_dump_json(indent=2)
        else:
            payload = self.render_markdown()

        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(temp_file, target)
        return target

    @classmethod
    def from_markdown(cls, text: str, default_title: str = "Livrable de Session") -> "ArtifactDocument":
        lines = text.splitlines()
        title = default_title
        metadata: dict[str, Any] = {}
        sections: dict[str, str] = {}

        idx = 0
        total = len(lines)

        # Extraction d'un éventuel frontmatter YAML
        if total > 0 and lines[0].strip() == "---":
            idx = 1
            while idx < total and lines[idx].strip() != "---":
                line = lines[idx].strip()
                if ":" in line:
                    k, v = line.split(":", 1)
                    metadata[k.strip()] = v.strip()
                idx += 1
            if idx < total and lines[idx].strip() == "---":
                idx += 1

        current_section: str | None = None
        current_lines: list[str] = []

        while idx < total:
            line = lines[idx]
            stripped = line.strip()

            if stripped.startswith("# ") and not stripped.startswith("## ") and title == default_title:
                title = stripped[2:].strip()
            elif stripped.startswith("## ") and not stripped.startswith("### "):
                if current_section is not None:
                    sections[current_section] = "\n".join(current_lines).strip()
                current_section = stripped[3:].strip()
                current_lines = []
            elif current_section is not None:
                current_lines.append(line)
            idx += 1

        if current_section is not None:
            sections[current_section] = "\n".join(current_lines).strip()

        return cls(title=title, metadata=metadata, sections=sections)

    @classmethod
    def load(cls, path: Path | str) -> "ArtifactDocument":
        target = Path(path)
        if not target.is_file():
            raise FileNotFoundError(f"Fichier d'artefact introuvable : {target}")

        raw = target.read_text(encoding="utf-8")
        if target.suffix.lower() == ".json":
            return cls.model_validate_json(raw)

        stripped = raw.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                return cls.model_validate_json(stripped)
            except Exception:
                pass

        return cls.from_markdown(raw)


class ArtifactManager:
    def __init__(self, storage_dir: Path | str = "storage/artifacts") -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_session_id(self, session_id: str) -> str:
        clean = re.sub(r"[^\w\-.]", "_", str(session_id).strip())
        return clean or "default"

    def get_storage_path(self, session_id: str, extension: str = "md") -> Path:
        safe_id = self._sanitize_session_id(session_id)
        return self.storage_dir / f"{safe_id}.{extension}"

    def get_or_create_artifact(self, session_id: str, title: str | None = None) -> ArtifactDocument:
        md_path = self.get_storage_path(session_id, "md")
        json_path = self.get_storage_path(session_id, "json")

        if md_path.is_file():
            try:
                return ArtifactDocument.load(md_path)
            except Exception:
                pass
        if json_path.is_file():
            try:
                return ArtifactDocument.load(json_path)
            except Exception:
                pass

        doc_title = title or f"Livrable — Session {session_id[:8]}"
        doc = ArtifactDocument(
            title=doc_title,
            metadata={
                "session_id": session_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        self.save_artifact(session_id, doc, extension="md")
        return doc

    def save_artifact(self, session_id: str, document: ArtifactDocument, extension: str = "md") -> Path:
        target_path = self.get_storage_path(session_id, extension)
        document.metadata["session_id"] = session_id
        return document.save(target_path)

    def load_artifact(self, session_id: str) -> ArtifactDocument:
        md_path = self.get_storage_path(session_id, "md")
        if md_path.is_file():
            return ArtifactDocument.load(md_path)
        json_path = self.get_storage_path(session_id, "json")
        if json_path.is_file():
            return ArtifactDocument.load(json_path)
        raise FileNotFoundError(f"Aucun livrable trouvé pour la session '{session_id}'.")

    def reset_artifact(self, session_id: str, title: str | None = None) -> ArtifactDocument:
        doc_title = title or f"Livrable — Session {session_id[:8]}"
        doc = ArtifactDocument(
            title=doc_title,
            metadata={
                "session_id": session_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            sections={},
        )
        self.save_artifact(session_id, doc, extension="md")
        return doc

    def list_artifacts(self) -> list[str]:
        if not self.storage_dir.is_dir():
            return []
        ids: set[str] = set()
        for f in self.storage_dir.iterdir():
            if f.is_file() and f.suffix in (".md", ".json"):
                ids.add(f.stem)
        return sorted(ids)
