import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

ALLOWED_DIR = Path("manuscrit_royaumes").resolve()
ALLOWED_DIR.mkdir(exist_ok=True)
(ALLOWED_DIR / "brouillons").mkdir(exist_ok=True)

# Registre global de callbacks et confirmations par token / action_id pour contextes non-interactifs (Web, API, background)
_confirmation_callback: Optional[Callable[[str], bool]] = None
_action_confirmations: Dict[str, bool] = {}


def set_confirmation_callback(cb: Optional[Callable[[str], bool]]) -> None:
    """Injecte un callback global de confirmation humaine."""
    global _confirmation_callback
    _confirmation_callback = cb


def get_confirmation_callback() -> Optional[Callable[[str], bool]]:
    """Récupère le callback global de confirmation humaine actuellement configuré."""
    return _confirmation_callback


def register_action_confirmation(action_id: str, approved: bool) -> None:
    """Enregistre l'approbation ou le refus préalable d'une action via son token / action_id."""
    _action_confirmations[action_id] = approved


def clear_action_confirmations() -> None:
    """Vide le registre des confirmations par token."""
    _action_confirmations.clear()


def is_interactive_terminal() -> bool:
    """Vérifie si l'environnement d'exécution dispose d'un terminal interactif (TTY)."""
    try:
        return sys.stdin is not None and hasattr(sys.stdin, "isatty") and sys.stdin.isatty()
    except Exception:
        return False


def ask_human_confirmation(
    action_summary: str,
    auto_confirm: Optional[bool] = None,
    callback: Optional[Callable[[str], bool]] = None,
    action_id: Optional[str] = None,
) -> bool:
    """Vérifie l'approbation de l'utilisateur pour une action critique sans bloquer en mode serveur.

    Ordre d'évaluation :
      1. Paramètre explicite auto_confirm (True / False).
      2. Variable d'environnement SENSAI_AUTO_CONFIRM (1/true/0/false).
      3. Token / action_id enregistré préalablement.
      4. Callback direct injecté.
      5. Callback global injecté via set_confirmation_callback.
      6. Fallback interactif via input() uniquement si un TTY interactif est disponible.
      7. En environnement non interactif (FastAPI / serveur / CI) : refus sécurisé (False) sans blocage.
    """
    # 1. Validation explicite par paramètre
    if auto_confirm is not None:
        return bool(auto_confirm)

    # 2. Variable d'environnement
    env_auto = os.environ.get("SENSAI_AUTO_CONFIRM")
    if env_auto is not None:
        if env_auto.lower() in ("1", "true", "yes", "o", "oui"):
            return True
        elif env_auto.lower() in ("0", "false", "no", "n", "non"):
            return False

    # 3. Confirmation par token / action_id
    if action_id and action_id in _action_confirmations:
        return bool(_action_confirmations.pop(action_id))

    # 4. Callback injecté directement
    if callback is not None:
        try:
            return bool(callback(action_summary))
        except Exception:
            return False

    # 5. Callback global enregistré
    if _confirmation_callback is not None:
        try:
            return bool(_confirmation_callback(action_summary))
        except Exception:
            return False

    # 6. Fallback interactif TTY pour le CLI
    if is_interactive_terminal():
        print(f"\n[ATTENTION] Confirmez-vous cette action : {action_summary} ? (O/N)")
        while True:
            try:
                choice = input("Votre choix > ").strip().upper()
                if choice == 'O':
                    return True
                elif choice == 'N':
                    print("[Système] Action annulée par l'utilisateur.")
                    return False
            except (KeyboardInterrupt, EOFError):
                return False

    # 7. Contexte non interactif sans approbation fournie : refus par défaut sans bloquer stdin
    print(f"[Système] Action non confirmée en contexte non interactif : {action_summary}")
    return False


def is_path_safe(requested_path: str) -> bool:
    """Vérifie qu'un chemin de fichier reste strictement confiné dans le dossier autorisé.
            PARAMS: - requested_path - STR: chemin relatif demandé
            RETURN: booléen indiquant si le chemin est sécurisé"""

    try:
        target = (ALLOWED_DIR / requested_path).resolve()
        return ALLOWED_DIR in target.parents or target == ALLOWED_DIR
    except Exception:
        return False


def agent_read_file(filename: str) -> str:
    """Lit un fichier texte ou markdown restreint au répertoire autorisé des manuscrits.
            PARAMS: - filename - STR: nom du fichier à lire
            RETURN: chaîne JSON contenant le statut et le contenu ou un message d'erreur"""

    if not is_path_safe(filename):
        return '{"error": "Accès refusé. Vous ne pouvez lire que dans /manuscrit_royaumes."}'
    
    target_path = (ALLOWED_DIR / filename).resolve()
    
    if target_path.suffix not in ['.txt', '.md']:
         return '{"error": "Type de fichier non autorisé à la lecture."}'

    if not target_path.exists():
        return f'{{"error": "Le fichier {filename} n\'existe pas."}}'

    try:
        content = target_path.read_text(encoding="utf-8")
        return f'{{"status": "success", "content": "{content}"}}'
    except Exception as e:
        return f'{{"error": "{str(e)}"}}'


def agent_write_file(
    filename: str,
    content: str,
    auto_confirm: Optional[bool] = None,
    callback: Optional[Callable[[str], bool]] = None,
    action_id: Optional[str] = None,
) -> str:
    """Écrit du contenu dans un fichier avec vérification de sécurité et confirmation humaine.
            PARAMS: - filename - STR: nom du fichier cible
                    - content - STR: contenu textuel à enregistrer
                    - auto_confirm - BOOL (optionnel): validation automatique
                    - callback - CALLABLE (optionnel): validation par callback
                    - action_id - STR (optionnel): token/identifiant d'action pour HITL
            RETURN: chaîne JSON indiquant le résultat de l'écriture ou l'annulation"""

    if not is_path_safe(filename):
        return '{"error": "Accès refusé. Vous ne pouvez écrire que dans /manuscrit_royaumes ou ses sous-dossiers."}'
    
    target_path = (ALLOWED_DIR / filename).resolve()
    
    if target_path.exists():
        lines_count = len(target_path.read_text(encoding="utf-8").splitlines())
        summary = f"Écraser le fichier existant {filename} (perte potentielle de {lines_count} lignes)"
    else:
        summary = f"Créer un nouveau fichier {filename}"

    if not ask_human_confirmation(summary, auto_confirm=auto_confirm, callback=callback, action_id=action_id):
        return '{"status": "aborted", "message": "L\'utilisateur a refusé l\'opération."}'

    try:
        target_path.write_text(content, encoding="utf-8")
        return f'{{"status": "success", "message": "Fichier {filename} enregistré."}}'
    except Exception as e:
        return f'{{"error": "{str(e)}"}}'
