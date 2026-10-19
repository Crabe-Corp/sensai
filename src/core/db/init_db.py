import sqlite3
from pathlib import Path

DB_PATH = Path("kingdoms.db")

def init_database() -> None:
    """Initialise la base de données SQLite des royaumes avec le schéma et les données initiales.
            PARAMS: Aucun
            RETURN: None"""

    DB_PATH.touch(exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS kingdoms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                gold INTEGER NOT NULL,
                military_power INTEGER NOT NULL,
                status TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS diplomacy (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kingdom_id_1 INTEGER NOT NULL,
                kingdom_id_2 INTEGER NOT NULL,
                relation_status TEXT NOT NULL,
                is_active BOOLEAN NOT NULL CHECK (is_active IN (0, 1)),
                FOREIGN KEY (kingdom_id_1) REFERENCES kingdoms (id),
                FOREIGN KEY (kingdom_id_2) REFERENCES kingdoms (id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS military_units (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kingdom_id INTEGER NOT NULL,
                unit_name TEXT NOT NULL,
                attack INTEGER NOT NULL,
                defense INTEGER NOT NULL,
                FOREIGN KEY (kingdom_id) REFERENCES kingdoms (id)
            )
        """)
        cursor.execute("DELETE FROM military_units")
        cursor.execute("DELETE FROM diplomacy")
        cursor.execute("DELETE FROM kingdoms")

        kingdoms_data = [
            ("Qin", 8500, 95000, "Active"),
            ("Chu", 7000, 85000, "Active"),
            ("Qi", 9000, 60000, "Active"),
            ("Zhao", 5500, 75000, "Active"),
            ("Wei", 6000, 65000, "Active"),
            ("Han", 3000, 40000, "Active"),
            ("Yan", 4500, 50000, "Active")
        ]
        
        cursor.executemany("""
            INSERT INTO kingdoms (name, gold, military_power, status)
            VALUES (?, ?, ?, ?)
        """, kingdoms_data)
        cursor.execute("SELECT id, name FROM kingdoms")
        kingdom_ids = {name: k_id for k_id, name in cursor.fetchall()}
        units_data = [
            (kingdom_ids["Qin"], "Crossbowmen", 8, 4),
            (kingdom_ids["Qin"], "Heavy Infantry", 7, 7),
            (kingdom_ids["Zhao"], "Light Cavalry", 9, 3),
            (kingdom_ids["Wei"], "Armored Halberdiers", 6, 8),
            (kingdom_ids["Chu"], "Chariots", 7, 5),
            (kingdom_ids["Qi"], "Mercenary Swordsmen", 6, 5)
        ]

        cursor.executemany("""
            INSERT INTO military_units (kingdom_id, unit_name, attack, defense)
            VALUES (?, ?, ?, ?)
        """, units_data)

        conn.commit()

if __name__ == "__main__":
    init_database()
    print(f"Database initialized successfully at {DB_PATH.absolute()}")
