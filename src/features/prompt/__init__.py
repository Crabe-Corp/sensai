"""Module de gestion des personas dynamiques [A5] et du versioning de prompts [A4]."""

from src.features.prompt.persona_manager import Persona, PersonaManager
from src.features.prompt.prompt_versioning import (
    PromptVersion,
    PromptVersioningEngine,
    default_versioning_engine,
    get_diff,
    get_history,
    rollback,
    save_version,
)

__all__ = [
    "Persona",
    "PersonaManager",
    "PromptVersion",
    "PromptVersioningEngine",
    "default_versioning_engine",
    "get_diff",
    "get_history",
    "rollback",
    "save_version",
]
