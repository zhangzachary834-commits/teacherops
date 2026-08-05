import sqlite3
import sys
from pathlib import Path

def whitelist_email(email: str):
    db_path = Path("data/tutor.db")
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return
        
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS admin_whitelist (email TEXT PRIMARY KEY)"
        )
        conn.execute(
            "INSERT OR IGNORE INTO admin_whitelist (email) VALUES (?)",
            (email,)
        )
        conn.commit()
        print(f"Successfully whitelisted '{email}' for admin/developer roles!")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 whitelist_admin.py <email>")
        sys.exit(1)
    
    whitelist_email(sys.argv[1])
