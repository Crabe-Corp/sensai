import sqlite3
import json
from pathlib import Path
from src.core.db.init_db import init_database
from src.core.fs_tools import ask_human_confirmation

DB_PATH = Path("kingdoms.db")

def query_db(sql_query: str) -> str:
    """
    Exécute une requête SELECT générée par l'agent.
    Renvoie les résultats au format JSON (string) pour l'orchestrateur.
    """
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

def execute_db_update(sql_statement: str) -> str:
    """
    Exécute une requête INSERT, UPDATE ou DELETE générée par l'agent.
    Renvoie le statut de l'opération au format JSON (string).
    """
    try:
        if sql_statement.strip().upper().startswith("SELECT"):
            return json.dumps({"error": "Utilisez query_db pour les requêtes SELECT."}, ensure_ascii=False)

        summary = f"Exécuter la requête suivante en base de données :\n  > {sql_statement.strip()}"
        if not ask_human_confirmation(summary):
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
