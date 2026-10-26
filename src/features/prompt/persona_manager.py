from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

from src.features.prompt.prompt_versioning import (
    PromptVersioningEngine,
    default_versioning_engine,
)

DEFAULT_SCRIBE_QIN_MD = """---
name: Scribe de Qin
role: Scribe officiel et légiste impérial
tone: Rigoureux, autoritaire, méthodique et solennel
description: Fonctionnaire impérial appliquant avec rigueur les décrets de l'École des Lois (Fajia).
scope: Administration, lois impériales, standardisation des poids et mesures, chroniques militaires.
---
Tu es un scribe officiel de la cour impériale de Qin, sous le règne du Premier Empereur Qin Shi Huang et les préceptes de Li Si.
Ton ton est rigoureux, autoritaire, protocolaire et précis.
Tu privilégies l'ordre, l'autorité centrale de l'État, la loi écrite absolue et l'efficacité administrative.
Lorsque tu réponds, adopte la posture solennelle d'un fonctionnaire impérial s'adressant aux sujets de l'Empire.
"""

DEFAULT_ERUDIT_ZHAO_MD = """---
name: Érudit de Zhao
role: Philosophe et stratège humaniste
tone: Critique, subtil, humaniste et réfléchi
description: Penseur de l'Académie de Handan valorisant l'éthique confucéenne et la résistance face à la tyrannie.
scope: Philosophie, diplomatie, éthique politique, analyse critique des conquêtes.
---
Tu es un maître philosophe et stratège issu de Handan, prestigieuse capitale du Royaume de Zhao.
Ton approche est humaniste, critique, empreinte de modération et de subtilité.
Tu analyses les ambitions expansionnistes avec scepticisme, valorisant le bien-être du peuple, la droiture morale et la ruse défensive.
Lorsque tu réponds, questionne les certitudes absolues et propose une analyse nuancée et philosophique de la période des Royaumes Combattants.
"""

DEFAULT_GENERAL_BAI_QI_JSON = """{
  "name": "Général Bai Qi",
  "role": "Général en chef invaincu de l'armée de Qin",
  "tone": "Martial, impitoyable, direct et concis",
  "description": "Le Dieu de la Guerre de Qin, craint par tous les royaumes pour sa rigueur tactique.",
  "scope": "Stratégie militaire, gestion logistique des troupes, siège et guerre d'usure.",
  "system_prompt": "Tu es le général Bai Qi, le boucher invaincu de l'armée de Qin. Tu t'exprimes avec concision militaire, sans flatterie ni hésitation. Tes réponses analysent froidement le rapport de force, l'approvisionnement en grain, le terrain et la destruction méthodique de l'ennemi."
}
"""


class Persona(BaseModel):
    """Modèle de données représentant une persona et son prompt système associé."""

    name: str
    description: str = ""
    role: str = ""
    tone: str = ""
    scope: str = ""
    system_prompt: str
    active_version: int = 1
    file_path: Path | None = None


class PersonaManager:
    """Gestionnaire de découverte dynamique, chargement et validation des personas."""

    def __init__(
        self,
        personas_dir: Path | str = "personnalites",
        versioning_engine: PromptVersioningEngine | None = None,
    ) -> None:
        """Initialise le gestionnaire de personas avec répertoire cible et moteur de versioning.
                PARAMS: - personas_dir - PATH | STR: répertoire de stockage des personas
                        - versioning_engine - PROMPTVERSIONINGENGINE | NONE: moteur de versioning associé
                RETURN: None"""
        self.personas_dir = Path(personas_dir)
        self.personas_dir.mkdir(parents=True, exist_ok=True)
        self.versioning_engine = (
            versioning_engine
            if versioning_engine is not None
            else default_versioning_engine
        )

    def ensure_default_personas(self) -> None:
        """Initialise les personas par défaut des Royaumes Combattants si elles sont absentes.
                PARAMS: Aucun
                RETURN: None"""
        defaults: dict[str, str] = {
            "scribe_qin.md": DEFAULT_SCRIBE_QIN_MD.strip() + "\n",
            "erudit_zhao.md": DEFAULT_ERUDIT_ZHAO_MD.strip() + "\n",
            "general_bai_qi.json": DEFAULT_GENERAL_BAI_QI_JSON.strip() + "\n",
        }
        for filename, content in defaults.items():
            path = self.personas_dir / filename
            if not path.exists():
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                self.versioning_engine.save_version(
                    persona_name=path.stem,
                    content=content,
                    author="system",
                    message="Initialisation persona par défaut",
                )

    def _parse_frontmatter(self, raw_text: str) -> tuple[dict[str, str], str]:
        """Extrait les métadonnées YAML d'en-tête (frontmatter) et le corps d'un texte Markdown.
                PARAMS: - raw_text - STR: texte brut à décomposer
                RETURN: tuple composé du dictionnaire de métadonnées et du corps de texte"""
        metadata: dict[str, str] = {}
        body = raw_text

        if raw_text.startswith("---"):
            parts = raw_text.split("---", 2)
            if len(parts) >= 3:
                header = parts[1]
                body = parts[2].strip()
                for line in header.splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        metadata[k.strip().lower()] = v.strip()
        return metadata, body

    def _build_system_prompt_from_meta(
        self,
        name: str,
        role: str,
        tone: str,
        scope: str,
        body: str,
    ) -> str:
        """Construit le prompt système complet à partir des métadonnées et du corps.
                PARAMS: - name - STR: nom de la persona
                        - role - STR: fonction ou titre de la persona
                        - tone - STR: tonalité et style d'élocution
                        - scope - STR: périmètre d'expertise ou de réponse
                        - body - STR: corps du texte ou instructions spécifiques
                RETURN: chaîne du prompt système assemblé"""
        parts: list[str] = []
        if body:
            parts.append(body)
        else:
            if role:
                parts.append(f"Rôle : {role}")
            if tone:
                parts.append(f"Ton et style : {tone}")
            if scope:
                parts.append(f"Périmètre de réponse : {scope}")
        return "\n\n".join(parts) if parts else f"Tu incarnes la persona {name}."

    def _parse_file(self, path: Path) -> Persona:
        """Parse un fichier Markdown ou JSON et l'enregistre dans le moteur de versioning.
                PARAMS: - path - PATH: chemin vers le fichier de la persona
                RETURN: instance Persona instanciée et versionnée"""
        with open(path, "r", encoding="utf-8") as f:
            raw_content = f.read()

        ver_obj = self.versioning_engine.save_version(
            persona_name=path.stem,
            content=raw_content,
            author="system",
            message="Auto-synchronisation à la lecture",
        )
        active_version = ver_obj.version

        if path.suffix.lower() == ".json":
            try:
                data = json.loads(raw_content)
            except json.JSONDecodeError as err:
                raise ValueError(f"Fichier de persona JSON invalide ({path.name}) : {err}") from err

            name = str(data.get("name") or path.stem)
            role = str(data.get("role") or "")
            tone = str(data.get("tone") or "")
            scope = str(data.get("scope") or "")
            description = str(data.get("description") or "")
            prompt = str(data.get("system_prompt") or "")

            if not prompt:
                prompt = self._build_system_prompt_from_meta(name, role, tone, scope, "")

            return Persona(
                name=name,
                description=description,
                role=role,
                tone=tone,
                scope=scope,
                system_prompt=prompt,
                active_version=active_version,
                file_path=path,
            )

        metadata, body = self._parse_frontmatter(raw_content)
        name = metadata.get("name") or path.stem
        role = metadata.get("role") or ""
        tone = metadata.get("tone") or ""
        scope = metadata.get("scope") or ""
        description = metadata.get("description") or ""

        prompt = self._build_system_prompt_from_meta(name, role, tone, scope, body)
        return Persona(
            name=name,
            description=description,
            role=role,
            tone=tone,
            scope=scope,
            system_prompt=prompt,
            active_version=active_version,
            file_path=path,
        )

    def _resolve_persona_path(self, name_or_filename: str) -> Path | None:
        """Localise le fichier d'une persona par son nom, son nom de fichier ou son chemin.
                PARAMS: - name_or_filename - STR: identifiant, nom ou chemin de la persona
                RETURN: objet Path pointant vers le fichier ou None si introuvable"""
        target = Path(name_or_filename)
        if target.is_file():
            return target

        direct = self.personas_dir / name_or_filename
        if direct.is_file():
            return direct

        clean = target.stem.lower().strip()
        for ext in (".md", ".json", ".txt"):
            candidate = self.personas_dir / f"{clean}{ext}"
            if candidate.is_file():
                return candidate

        for f in self.personas_dir.iterdir():
            if f.is_file() and f.stem.lower() == clean:
                return f

        return None

    def load_persona(self, name_or_filename: str) -> Persona:
        """Charge dynamiquement une persona depuis le répertoire dédié sans redémarrage.
                PARAMS: - name_or_filename - STR: nom ou identifiant de la persona à charger
                RETURN: instance Persona chargée"""
        path = self._resolve_persona_path(name_or_filename)
        if path is None or not path.is_file():
            available = self.list_personas()
            raise FileNotFoundError(
                f"Persona '{name_or_filename}' introuvable dans '{self.personas_dir}'. "
                f"Profils disponibles : {', '.join(available) if available else 'aucun'}"
            )
        return self._parse_file(path)

    def list_personas(self) -> list[str]:
        """Scanne le dossier et liste tous les identifiants de personas disponibles.
                PARAMS: Aucun
                RETURN: liste triée des noms de personas trouvées"""
        valid_extensions = {".md", ".json", ".txt"}
        found: set[str] = set()
        for f in self.personas_dir.iterdir():
            if f.is_file() and f.suffix.lower() in valid_extensions:
                found.add(f.stem)
        return sorted(found)
