import db
import agent

def test_init_db_creates_tables(isolated_db):
    """
    Test that the isolated database is initialized properly and empty.
    """
    db_path = agent.DATA_DIR / "tutor.db"
    assert db_path.exists()
    
    with db.get_db(db_path) as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row["name"] for row in cursor.fetchall()]
        
        # Verify the expected tables are present
        assert "teachers" in tables
        assert "inquiries" in tables
        assert "matches" in tables
        assert "users" in tables

def test_get_db_can_insert_and_retrieve(isolated_db):
    db_path = agent.DATA_DIR / "tutor.db"
    with db.get_db(db_path) as conn:
        conn.execute(
            "INSERT INTO teachers (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ("t1", "Alice", "2023-01-01", "2023-01-01")
        )
        conn.commit()
        
        cursor = conn.execute("SELECT * FROM teachers WHERE id = ?", ("t1",))
        teacher = cursor.fetchone()
        
        assert teacher is not None
        assert teacher["name"] == "Alice"
