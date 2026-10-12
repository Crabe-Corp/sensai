import sqlite3
from pathlib import Path

DB_PATH = Path("kingdoms.db")

def init_database() -> None:
    DB_PATH.touch(exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        # Table des royaumes
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

        # Table des figures historiques
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS historical_figures (
                name TEXT PRIMARY KEY,
                allegiance TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL
            )
        """)

        # Table des alliances
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alliances (
                kingdom_a TEXT NOT NULL,
                kingdom_b TEXT NOT NULL,
                type TEXT NOT NULL,
                active BOOLEAN NOT NULL CHECK (active IN (0, 1))
            )
        """)

        # Table de progression pédagogique
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_progress (
                topic TEXT PRIMARY KEY,
                mastery_level INTEGER NOT NULL,
                last_reviewed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("DELETE FROM user_progress")
        cursor.execute("DELETE FROM alliances")
        cursor.execute("DELETE FROM historical_figures")
        cursor.execute("DELETE FROM kingdoms")

        kingdoms_data = [
            ("qin", "Qin", "Xianyang", "independent", None, "Ying Zheng"),
            ("chu", "Chu", "Shouchun", "independent", None, "King Kaolie"),
            ("qi", "Qi", "Linzi", "independent", None, "King Jian"),
            ("zhao", "Zhao", "Handan", "independent", None, "King Daoxiang"),
            ("wei", "Wei", "Daliang", "independent", None, "King Jingmin"),
            ("han", "Han", "Xinzheng", "independent", None, "King An"),
            ("yan", "Yan", "Ji", "independent", None, "King Xi")
        ]
        cursor.executemany("INSERT INTO kingdoms VALUES (?, ?, ?, ?, ?, ?)", kingdoms_data)

        figures_data = [
            ("Wang Jian", "Qin", "Général", "Actif"),
            ("Lian Po", "Zhao", "Général", "Exilé"),
            ("Li Si", "Qin", "Premier ministre", "Actif")
        ]
        cursor.executemany("INSERT INTO historical_figures VALUES (?, ?, ?, ?)", figures_data)

        conn.commit()

if __name__ == "__main__":
    init_database()
    print(f"Database initialized successfully at {DB_PATH.absolute()}")
