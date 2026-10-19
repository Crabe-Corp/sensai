import os
from pathlib import Path

ALLOWED_DIR = Path("manuscrit_royaumes").resolve()
ALLOWED_DIR.mkdir(exist_ok=True)
(ALLOWED_DIR / "brouillons").mkdir(exist_ok=True)

def ask_human_confirmation(action_summary: str) -> bool:
    """
    [A3] Met l'agent en pause et force une validation manuelle.
    """
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

def is_path_safe(requested_path: str) -> bool:
    """
    [T4] Empêche les attaques par path traversal (ex: ../../etc/passwd).
    """
    try:
        target = (ALLOWED_DIR / requested_path).resolve()
        return ALLOWED_DIR in target.parents or target == ALLOWED_DIR
    except Exception:
        return False

def agent_read_file(filename: str) -> str:
    """Outil de lecture restreint au dossier autorisé."""
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

def agent_write_file(filename: str, content: str) -> str:
    """Outil d'écriture protégé par permissions [T4] et confirmation humaine [A3]."""
    if not is_path_safe(filename):
        return '{"error": "Accès refusé. Vous ne pouvez écrire que dans /manuscrit_royaumes ou ses sous-dossiers."}'
    
    target_path = (ALLOWED_DIR / filename).resolve()
    
    if target_path.exists():
        lines_count = len(target_path.read_text(encoding="utf-8").splitlines())
        summary = f"Écraser le fichier existant {filename} (perte potentielle de {lines_count} lignes)"
    else:
        summary = f"Créer un nouveau fichier {filename}"

    if not ask_human_confirmation(summary):
        return '{"status": "aborted", "message": "L\'utilisateur a refusé l\'opération."}'

    try:
        target_path.write_text(content, encoding="utf-8")
        return f'{{"status": "success", "message": "Fichier {filename} enregistré."}}'
    except Exception as e:
        return f'{{"error": "{str(e)}"}}'
