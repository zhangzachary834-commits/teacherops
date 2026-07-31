import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional

def get_db(db_path: Path):
    """Return a database connection with dictionary-like rows."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: Path):
    """Create all tables if they don't exist."""
    with get_db(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS teachers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                subjects TEXT,
                levels TEXT,
                availability TEXT,
                rate TEXT,
                capacity INTEGER,
                active_matches INTEGER,
                contact TEXT,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS inquiries (
                id TEXT PRIMARY KEY,
                parent_name TEXT,
                student_name TEXT,
                subject TEXT,
                level TEXT,
                availability TEXT,
                frequency TEXT,
                raw_message TEXT,
                notes TEXT,
                status TEXT,
                next_action TEXT,
                last_contacted TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                id TEXT PRIMARY KEY,
                inquiry_id TEXT,
                teacher_id TEXT,
                parent_name TEXT,
                student_name TEXT,
                teacher_name TEXT,
                subject TEXT,
                status TEXT,
                next_action TEXT,
                last_contacted TEXT,
                payment_status TEXT,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leave_requests (
                id TEXT PRIMARY KEY,
                parent_name TEXT,
                student_name TEXT,
                teacher_name TEXT,
                subject TEXT,
                class_date TEXT,
                reason TEXT,
                raw_message TEXT,
                notes TEXT,
                status TEXT,
                next_action TEXT,
                google_doc_updated BOOLEAN,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS faqs (
                id TEXT PRIMARY KEY,
                topic TEXT,
                keywords TEXT,
                answer TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                profile_id TEXT,
                created_at TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS admin_whitelist (
                email TEXT PRIMARY KEY
            )
        """)

# Utility functions to serialize/deserialize lists to JSON strings for SQLite
def to_json(lst: List[str]) -> str:
    return json.dumps(lst)

def from_json(s: str) -> List[str]:
    if not s:
        return []
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return []
