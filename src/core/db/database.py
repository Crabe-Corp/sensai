import sqlite3
from pathlib import Path
from typing import Any, Dict
from src.core.db.init_db import init_database

DB_PATH = Path("kingdoms.db")

def get_kingdom_stats(kingdom_name: str) -> Dict[str, Any]:
    """Retrieves the current resources and status of a specific kingdom."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, gold, military_power, status FROM kingdoms WHERE name = ?",
            (kingdom_name,)
        )
        row = cursor.fetchone()
        
        if row:
            return dict(row)
        return {"error": f"Kingdom '{kingdom_name}' not found.", "code": 404}

def get_active_diplomacy(kingdom_name: str) -> Dict[str, Any]:
    """Fetches only the currently active diplomatic relations for a kingdom."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        query = """
            SELECT k2.name, d.relation_status 
            FROM diplomacy d
            JOIN kingdoms k1 ON d.kingdom_id_1 = k1.id
            JOIN kingdoms k2 ON d.kingdom_id_2 = k2.id
            WHERE k1.name = ? AND d.is_active = 1
            UNION
            SELECT k1.name, d.relation_status 
            FROM diplomacy d
            JOIN kingdoms k2 ON d.kingdom_id_2 = k2.id
            JOIN kingdoms k1 ON d.kingdom_id_1 = k1.id
            WHERE k2.name = ? AND d.is_active = 1
        """
        cursor.execute(query, (kingdom_name, kingdom_name))
        relations = cursor.fetchall()
        
        if not relations:
            cursor.execute("SELECT id FROM kingdoms WHERE name = ?", (kingdom_name,))
            if not cursor.fetchone():
                return {"error": f"Kingdom '{kingdom_name}' not found.", "code": 404}
            return {"kingdom": kingdom_name, "relations": []}
            
        return {
            "kingdom": kingdom_name,
            "relations": [{"with_kingdom": r[0], "status": r[1]} for r in relations]
        }
