import os, sqlite3
from datetime import date

DB_PATH = os.getenv("REGISTRY_DB", os.path.join(os.path.dirname(__file__), "..", "data", "registry.db"))
SCHEMA = """
CREATE TABLE IF NOT EXISTS persons(
  doc_number TEXT PRIMARY KEY, surname TEXT, given_names TEXT, dob TEXT, sex TEXT,
  nationality TEXT, place_of_birth TEXT, issue_date TEXT, expiry_date TEXT,
  status TEXT, watchlist INTEGER, watchlist_note TEXT, face_seed INTEGER);
"""

def connect():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    c = sqlite3.connect(DB_PATH); c.row_factory = sqlite3.Row
    return c

def init():
    with connect() as c:
        c.executescript(SCHEMA)

def upsert(rec: dict):
    cols = ["doc_number", "surname", "given_names", "dob", "sex", "nationality", "place_of_birth",
            "issue_date", "expiry_date", "status", "watchlist", "watchlist_note", "face_seed"]
    vals = [rec[k].isoformat() if isinstance(rec[k], date) else rec[k] for k in cols]
    with connect() as c:
        c.execute(f"INSERT OR REPLACE INTO persons({','.join(cols)}) VALUES({','.join('?'*len(cols))})", vals)

def get(doc_number: str):
    with connect() as c:
        return c.execute("SELECT * FROM persons WHERE doc_number=?", (doc_number,)).fetchone()

def count() -> int:
    with connect() as c:
        return c.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
