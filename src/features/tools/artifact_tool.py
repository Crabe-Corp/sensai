from typing import Literal

from src.features.memory.artifact_manager import ArtifactDocument, ArtifactManager
from src.features.tools.registry import tool

_active_artifact: ArtifactDocument | None = None
_active_session_id: str | None = None
_active_manager: ArtifactManager | None = None

ARTIFACT_SYSTEM_INSTRUCTION = (
    "You have access to tools including a live deliverable document ('update_artifact') and a PDF generator ('generate_pdf_document'). "
    "Keep the deliverable up to date by calling the 'update_artifact' tool when recording key facts. "
    "When the user asks to create, produce, or export a PDF, invoke the 'generate_pdf_document' tool with an appropriate filename, title, and formatted content. "
    "Do not rewrite the entire deliverable at once: apply targeted section modifications. "
    "Always respond in English."
)


def set_active_artifact(
    document: ArtifactDocument | None,
    session_id: str | None = None,
    manager: ArtifactManager | None = None,
) -> None:
    """Définit le document d'état actif, son identifiant de session et son gestionnaire.
            PARAMS: - document - ARTIFACTDOCUMENT | NONE: instance de l'artefact actif
                    - session_id - STR | NONE: identifiant de la session courante
                    - manager - ARTIFACTMANAGER | NONE: gestionnaire d'artefacts associé
            RETURN: None"""
    global _active_artifact, _active_session_id, _active_manager
    _active_artifact = document
    _active_session_id = session_id
    _active_manager = manager


def get_active_artifact() -> ArtifactDocument:
    """Récupère l'artefact actif en cours ou en instancie un nouveau par défaut.
            PARAMS: Aucun
            RETURN: instance active du document d'artefact"""
    global _active_artifact
    if _active_artifact is None:
        _active_artifact = ArtifactDocument(title="Document d'État & Livrable")
    return _active_artifact


def reset_active_artifact() -> None:
    """Réinitialise l'artefact actif et ses références globales de session à None.
            PARAMS: Aucun
            RETURN: None"""
    set_active_artifact(None, None, None)


@tool
def update_artifact(
    action: Literal["update", "append", "delete"],
    section: str,
    content: str = "",
) -> str:
    """Met à jour le document vivant d'état et livrable (artefact) de manière incrémentale.
            PARAMS: - action - LITERAL: type de modification ('update', 'append', 'delete')
                    - section - STR: nom de la section ciblée dans le document
                    - content - STR: contenu textuel à écrire ou ajouter dans la section
            RETURN: message confirmant ou détaillant l'issue de l'opération"""
    doc = get_active_artifact()
    sec_name = section.strip()
    if not sec_name:
        return "Erreur : le nom de la section ne peut pas être vide."

    clean_action = str(action).strip().lower()

    if clean_action == "update":
        doc.set_section(sec_name, content)
        msg = f"Section '{sec_name}' mise à jour."
    elif clean_action == "append":
        doc.append_to_section(sec_name, content)
        msg = f"Contenu ajouté à la section '{sec_name}'."
    elif clean_action == "delete":
        if doc.delete_section(sec_name):
            msg = f"Section '{sec_name}' supprimée."
        else:
            msg = f"Section '{sec_name}' introuvable dans l'artefact."
    else:
        return f"Erreur : action '{action}' inconnue. Utilisez 'update', 'append' ou 'delete'."

    if _active_manager and _active_session_id:
        try:
            _active_manager.save_artifact(_active_session_id, doc)
        except Exception:
            pass

    return msg
