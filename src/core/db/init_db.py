import sqlite3
from pathlib import Path

DB_PATH = Path("kingdoms.db")


def init_database(force_reset: bool = False) -> None:
    """Initialise la base de données SQLite des royaumes avec le schéma et les données initiales.
            PARAMS: - force_reset - BOOL: réinitialise de force toutes les tables si True
            RETURN: None"""

    DB_PATH.touch(exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        if force_reset:
            cursor.execute("DROP TABLE IF EXISTS user_progress")
            cursor.execute("DROP TABLE IF EXISTS alliances")
            cursor.execute("DROP TABLE IF EXISTS historical_figures")
            cursor.execute("DROP TABLE IF EXISTS kingdoms")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS kingdoms (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                capital TEXT,
                status TEXT NOT NULL,
                annexed_year INTEGER,
                ruler TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS historical_figures (
                name TEXT PRIMARY KEY,
                allegiance TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alliances (
                kingdom_a TEXT NOT NULL,
                kingdom_b TEXT NOT NULL,
                type TEXT NOT NULL,
                active BOOLEAN NOT NULL CHECK (active IN (0, 1))
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_progress (
                topic TEXT PRIMARY KEY,
                mastery_level INTEGER NOT NULL,
                last_reviewed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("SELECT COUNT(*) FROM kingdoms")
        if cursor.fetchone()[0] == 0:
            kingdoms_data = [
                ("qin", "Qin", "Xianyang", "independent", None, "Ying Zheng"),
                ("chu", "Chu", "Shouchun", "independent", None, "King Kaolie"),
                ("qi", "Qi", "Linzi", "independent", None, "King Jian"),
                ("zhao", "Zhao", "Handan", "independent", None, "King Daoxiang"),
                ("wei", "Wei", "Daliang", "independent", None, "King Jingmin"),
                ("han", "Han", "Xinzheng", "independent", None, "King An"),
                ("yan", "Yan", "Ji", "independent", None, "King Xi"),
            ]
            cursor.executemany("INSERT INTO kingdoms VALUES (?, ?, ?, ?, ?, ?)", kingdoms_data)

        cursor.execute("SELECT COUNT(*) FROM historical_figures")
        if cursor.fetchone()[0] == 0:
            figures_data = [
                ("Wang Jian", "Qin", "Général", "Actif"),
                ("Lian Po", "Zhao", "Général", "Exilé"),
                ("Li Si", "Qin", "Premier ministre", "Actif"),
            ]
            cursor.executemany("INSERT INTO historical_figures VALUES (?, ?, ?, ?)", figures_data)

        conn.commit()

if __name__ == "__main__":
    init_database()
    print(f"Database initialized successfully at {DB_PATH.absolute()}")
