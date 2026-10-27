import sqlite3
import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from src.core.db.init_db import init_database
from src.core.fs_tools import (
    ask_human_confirmation,
    clear_action_confirmations,
    register_action_confirmation,
    set_confirmation_callback,
)

DB_PATH = Path("kingdoms.db")

def get_kingdom_stats(kingdom_name: str) -> Dict[str, Any]:
    """Récupère les informations actuelles d'un royaume spécifique.
            PARAMS: - kingdom_name - STR: le nom du royaume à rechercher
            RETURN: dictionnaire contenant les informations du royaume ou une erreur 404"""

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, capital, status, annexed_year, ruler FROM kingdoms WHERE LOWER(name) = LOWER(?)",
            (kingdom_name,)
        )
        row = cursor.fetchone()

        if row:
            return dict(row)
        return {"error": f"Kingdom '{kingdom_name}' not found.", "code": 404}

def get_active_diplomacy(kingdom_name: str) -> Dict[str, Any]:
    """Récupère les alliances actives pour un royaume donné.
            PARAMS: - kingdom_name - STR: le nom du royaume concerné
            RETURN: dictionnaire avec la liste des relations actives ou une erreur 404"""

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name FROM kingdoms WHERE LOWER(name) = LOWER(?)",
            (kingdom_name,)
        )
        kingdom = cursor.fetchone()
        if not kingdom:
            return {"error": f"Kingdom '{kingdom_name}' not found.", "code": 404}

        k_id, k_name = kingdom
        cursor.execute(
            """
            SELECT kingdom_b, type FROM alliances
            WHERE active = 1 AND (LOWER(kingdom_a) = LOWER(?) OR LOWER(kingdom_a) = LOWER(?))
            UNION
            SELECT kingdom_a, type FROM alliances
            WHERE active = 1 AND (LOWER(kingdom_b) = LOWER(?) OR LOWER(kingdom_b) = LOWER(?))
            """,
            (k_id, k_name, k_id, k_name)
        )
        relations = cursor.fetchall()

        return {
            "kingdom": k_name,
            "relations": [{"with_kingdom": r[0], "status": r[1]} for r in relations]
        }

def query_db(sql_query: str) -> str:
    """Exécute une requête SELECT générée par l'agent.
            PARAMS: - sql_query - STR: requête SQL de lecture (SELECT uniquement)
            RETURN: chaîne JSON contenant les résultats ou l'erreur"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if not sql_query.strip().upper().startswith("SELECT"):
                return json.dumps({"error": "Seules les requêtes SELECT sont autorisées ici."}, ensure_ascii=False)
                
            cursor.execute(sql_query)
            rows = cursor.fetchall()
            
            results = [dict(row) for row in rows]
            return json.dumps({"status": "success", "data": results}, ensure_ascii=False)
            
    except sqlite3.Error as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

def execute_db_update(
    sql_statement: str,
    auto_confirm: Optional[bool] = None,
    callback: Optional[Callable[[str], bool]] = None,
    action_id: Optional[str] = None,
) -> str:
    """Exécute une requête INSERT, UPDATE ou DELETE générée par l'agent après confirmation humaine.
            PARAMS: - sql_statement - STR: requête SQL d'écriture
                    - auto_confirm - BOOL (optionnel): confirmation automatique sans invite
                    - callback - CALLABLE (optionnel): fonction de validation
                    - action_id - STR (optionnel): token/identifiant d'action pour HITL
            RETURN: chaîne JSON contenant le statut de l'opération"""
    try:
        if sql_statement.strip().upper().startswith("SELECT"):
            return json.dumps({"error": "Utilisez query_db pour les requêtes SELECT."}, ensure_ascii=False)

        summary = f"Exécuter la requête suivante en base de données :\n  > {sql_statement.strip()}"
        if not ask_human_confirmation(summary, auto_confirm=auto_confirm, callback=callback, action_id=action_id):
            return json.dumps({
                "status": "aborted", 
                "message": "L'utilisateur a refusé et annulé la modification de la base de données."
            }, ensure_ascii=False)

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(sql_statement)
            conn.commit()
            
            return json.dumps({
                "status": "success", 
                "rows_affected": cursor.rowcount
            }, ensure_ascii=False)
            
    except sqlite3.Error as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)
