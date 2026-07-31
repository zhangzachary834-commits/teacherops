import json
import sqlite3
from pathlib import Path
import db

def read_json(path: Path):
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

def migrate():
    db.init_db()
    conn = db.get_db()
    
    # Paths based on agent.py
    DATA_DIR = Path(__file__).resolve().parent / "data"
    TEACHERS_FILE = DATA_DIR / "teachers" / "teachers.json"
    INQUIRIES_FILE = DATA_DIR / "inquiries" / "inquiries.json"
    MATCHES_FILE = DATA_DIR / "matches" / "matches.json"
    LEAVE_REQUESTS_FILE = DATA_DIR / "operations" / "leave_requests.json"
    FAQS_FILE = DATA_DIR / "support" / "faqs.json"
    
    # 1. Migrate Teachers
    teachers = read_json(TEACHERS_FILE)
    for t in teachers:
        conn.execute("""
            INSERT OR REPLACE INTO teachers 
            (id, name, subjects, levels, availability, rate, capacity, active_matches, contact, notes, created_at, updated_at) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            t.get("id"), t.get("name"),
            db.to_json(t.get("subjects", [])),
            db.to_json(t.get("levels", [])),
            db.to_json(t.get("availability", [])),
            t.get("rate"), t.get("capacity"), t.get("active_matches"),
            t.get("contact"), t.get("notes"),
            t.get("created_at"), t.get("updated_at")
        ))
        
    # 2. Migrate Inquiries
    inquiries = read_json(INQUIRIES_FILE)
    for i in inquiries:
        conn.execute("""
            INSERT OR REPLACE INTO inquiries 
            (id, parent_name, student_name, subject, level, availability, frequency, raw_message, notes, status, next_action, last_contacted, created_at, updated_at) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            i.get("id"), i.get("parent_name"), i.get("student_name"),
            i.get("subject"), i.get("level"),
            db.to_json(i.get("availability", [])),
            i.get("frequency"), i.get("raw_message"), i.get("notes"),
            i.get("status"), i.get("next_action"), i.get("last_contacted"),
            i.get("created_at"), i.get("updated_at")
        ))
        
    # 3. Migrate Matches
    matches = read_json(MATCHES_FILE)
    for m in matches:
        conn.execute("""
            INSERT OR REPLACE INTO matches 
            (id, inquiry_id, teacher_id, parent_name, student_name, teacher_name, subject, status, next_action, last_contacted, payment_status, notes, created_at, updated_at) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            m.get("id"), m.get("inquiry_id"), m.get("teacher_id"),
            m.get("parent_name"), m.get("student_name"), m.get("teacher_name"),
            m.get("subject"), m.get("status"), m.get("next_action"),
            m.get("last_contacted"), m.get("payment_status"), m.get("notes"),
            m.get("created_at"), m.get("updated_at")
        ))
        
    # 4. Migrate Leave Requests
    leaves = read_json(LEAVE_REQUESTS_FILE)
    for l in leaves:
        conn.execute("""
            INSERT OR REPLACE INTO leave_requests 
            (id, parent_name, student_name, teacher_name, subject, class_date, reason, raw_message, notes, status, next_action, google_doc_updated, created_at, updated_at) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            l.get("id"), l.get("parent_name"), l.get("student_name"),
            l.get("teacher_name"), l.get("subject"), l.get("class_date"),
            l.get("reason"), l.get("raw_message"), l.get("notes"),
            l.get("status"), l.get("next_action"),
            1 if l.get("google_doc_updated") else 0,
            l.get("created_at"), l.get("updated_at")
        ))
        
    # 5. Migrate FAQs
    faqs = read_json(FAQS_FILE)
    for f in faqs:
        conn.execute("""
            INSERT OR REPLACE INTO faqs 
            (id, topic, keywords, answer, created_at, updated_at) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            f.get("id"), f.get("topic"),
            db.to_json(f.get("keywords", [])),
            f.get("answer"), f.get("created_at"), f.get("updated_at")
        ))
        
    conn.commit()
    print("Migration complete!")

if __name__ == "__main__":
    migrate()
