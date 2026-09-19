from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Any
import db
import agent
import auth
import os
import sqlite3
import uuid
import datetime
from pathlib import Path

app = FastAPI(title="Tutor Coordination Agent API")
db.init_db(agent.DATA_DIR / "tutor.db")

# DEV MODE FLAG - strictly disables dev tools in production
DEV_MODE = os.environ.get("ENVIRONMENT", "dev") != "production"

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")

@app.get("/")
def read_root():
    return RedirectResponse(url="/home.html")

@app.get("/{page}.html")
def read_page(page: str):
    file_path = os.path.join(WEB_DIR, f"{page}.html")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    raise HTTPException(status_code=404, detail="Page not found")

@app.get("/shared.js")
def read_js():
    with open(os.path.join(WEB_DIR, "shared.js"), "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), media_type="application/javascript")

@app.get("/shared.css")
def read_css():
    with open(os.path.join(WEB_DIR, "shared.css"), "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), media_type="text/css")

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    role: str # parent, teacher, admin, developer

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

@app.post("/api/register")
def register(req: RegisterRequest):
    conn = db.get_db(agent.DATA_DIR / "tutor.db")
    cursor = conn.cursor()
    
    # Check if admin/dev is allowed
    if req.role in ["admin", "developer"]:
        cursor.execute("SELECT email FROM admin_whitelist WHERE email = ?", (req.email,))
        if not cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=403, detail="Email not whitelisted for admin/developer role")
    
    # Check if user exists
    cursor.execute("SELECT id FROM users WHERE email = ?", (req.email,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Email already registered")
        
    user_id = str(uuid.uuid4())
    cursor.execute(
        "INSERT INTO users (id, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, req.email, auth.get_password_hash(req.password), req.role, datetime.datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()
    return {"message": "User registered successfully"}

@app.post("/api/login")
def login(req: LoginRequest):
    conn = db.get_db(agent.DATA_DIR / "tutor.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (req.email,))
    user = cursor.fetchone()
    conn.close()
    
    if not user or not auth.verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    
    token = auth.create_access_token(data={"sub": user["id"]})
    return {"access_token": token, "token_type": "bearer", "role": user["role"]}

@app.get("/api/me")
def get_me(current_user: dict = Depends(auth.get_current_user)):
    return {"id": current_user["id"], "email": current_user["email"], "role": current_user["role"], "profile_id": current_user["profile_id"]}

@app.get("/api/state")
def get_state(current_user: dict = Depends(auth.get_current_user)):
    role = current_user["role"]
    profile_id = current_user.get("profile_id")
    
    all_teachers = [t for t in agent.read_records(agent.TEACHERS_TABLE) if t.get("status") != "archived"]
    all_inquiries = [i for i in agent.read_records(agent.INQUIRIES_TABLE) if i.get("status") != "archived"]
    all_matches = [m for m in agent.read_records(agent.MATCHES_TABLE) if m.get("status") != "archived"]
    all_leaves = [l for l in agent.read_records(agent.LEAVE_REQUESTS_TABLE) if l.get("status") != "archived"]
    
    user_profile = {}
    if role == "parent":
        user_inquiries = [i for i in all_inquiries if i["id"] == profile_id] if profile_id else all_inquiries
        if user_inquiries:
            inq = user_inquiries[0]
            user_profile = {
                "parent_name": inq.get("parent_name", ""),
                "student_name": inq.get("student_name", ""),
                "subject": inq.get("subject", ""),
                "level": inq.get("level", ""),
                "availability": inq.get("availability", []),
                "frequency": inq.get("frequency", "")
            }
        teachers = []
        inquiries = [i for i in all_inquiries if i["id"] == profile_id] if profile_id else []
        matches = [m for m in all_matches if m["inquiry_id"] == profile_id] if profile_id else []
        leaves = [l for l in all_leaves if l.get("inquiry_id") == profile_id] if profile_id else []
    elif role == "teacher":
        user_teachers = [t for t in all_teachers if t["id"] == profile_id] if profile_id else all_teachers
        if user_teachers:
            tch = user_teachers[0]
            user_profile = {
                "name": tch.get("name", ""),
                "subjects": tch.get("subjects", []),
                "levels": tch.get("levels", []),
                "availability": tch.get("availability", []),
                "rate": tch.get("rate", ""),
                "capacity": tch.get("capacity", 1),
                "contact": tch.get("contact", "")
            }
        teachers = [t for t in all_teachers if t["id"] == profile_id] if profile_id else []
        inquiries = [i for i in all_inquiries if i["status"] == "need_teacher"]
        matches = [m for m in all_matches if m["teacher_id"] == profile_id] if profile_id else []
        leaves = [l for l in all_leaves if l.get("teacher_id") == profile_id] if profile_id else []
    elif role in ["admin", "developer"]:
        teachers = all_teachers
        inquiries = all_inquiries
        matches = all_matches
        leaves = all_leaves
    else:
        teachers, inquiries, matches, leaves = [], [], [], []

    return {
        "summary": agent.weekly_report() if role in ["admin", "developer"] else {},
        "followups": agent.list_followups() if role in ["admin", "developer"] else [],
        "teachers": teachers,
        "inquiries": inquiries,
        "matches": matches,
        "leave_requests": leaves,
        "faqs": agent.read_records(agent.FAQS_TABLE),
        "role": role,
        "profile_id": profile_id,
        "user_profile": user_profile,
        "user": {
            "id": current_user["id"],
            "email": current_user["email"],
            "role": current_user["role"],
            "profile_id": current_user.get("profile_id"),
        }
    }

@app.get("/api/matches")
def get_matches(inquiry_id: str):
    if not inquiry_id:
        raise HTTPException(status_code=400, detail="Missing inquiry_id.")
    return agent.find_teacher_matches(inquiry_id)

class TeacherCreate(BaseModel):
    name: str = ""
    subjects: str = ""
    levels: str = ""
    availability: str = ""
    rate: str = ""
    capacity: int = 1
    contact: str = ""
    notes: str = ""

@app.post("/api/teachers")
def add_teacher(t: TeacherCreate, current_user: dict = Depends(auth.get_current_user)):
    if current_user["role"] not in ["admin", "teacher"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    res = agent.add_teacher(
        t.name, t.subjects, t.levels, t.availability,
        t.rate, t.capacity, t.contact, t.notes
    )
    if current_user["role"] == "teacher" and not current_user.get("profile_id"):
        conn = db.get_db(agent.DATA_DIR / "tutor.db")
        conn.execute("UPDATE users SET profile_id = ? WHERE id = ?", (res["id"], current_user["id"]))
        conn.commit()
        conn.close()
    return res

class InquiryCreate(BaseModel):
    parent_name: str = ""
    student_name: str = ""
    subject: str = ""
    level: str = ""
    availability: str = ""
    frequency: str = ""
    raw_message: str = ""
    notes: str = ""

@app.post("/api/inquiries")
def add_inquiry(i: InquiryCreate, current_user: dict = Depends(auth.get_current_user)):
    res = agent.add_inquiry(
        i.parent_name, i.student_name, i.subject, i.level,
        i.availability, i.frequency, i.raw_message, i.notes
    )
    if current_user["role"] == "parent" and not current_user.get("profile_id"):
        conn = db.get_db(agent.DATA_DIR / "tutor.db")
        conn.execute("UPDATE users SET profile_id = ? WHERE id = ?", (res["id"], current_user["id"]))
        conn.commit()
        conn.close()
    return res

class InboxProcess(BaseModel):
    messages: str = ""
    parent_name: str = "Unknown parent"

@app.post("/api/inbox")
def process_inbox(i: InboxProcess):
    lines = i.messages.splitlines()
    return agent.process_inbox_lines(lines, i.parent_name)

class CreateMatch(BaseModel):
    inquiry_id: str = ""
    teacher_id: str = ""
    status: str = "teacher_contacted"

@app.post("/api/create-match")
def create_match(m: CreateMatch, current_user: dict = Depends(auth.get_current_user)):
    if current_user["role"] not in ["admin", "developer"]:
        raise HTTPException(status_code=403, detail="Not authorized to create matches")
    return agent.create_match(m.inquiry_id, m.teacher_id, m.status)

class UpdateMatch(BaseModel):
    match_id: str = ""
    status: Optional[str] = None
    next_action: Optional[str] = None
    notes: Optional[str] = None

@app.post("/api/update-match")
def update_match(m: UpdateMatch, current_user: dict = Depends(auth.get_current_user)):
    if current_user["role"] not in ["admin", "developer"]:
        raise HTTPException(status_code=403, detail="Not authorized to update matches")
    return agent.update_match(m.match_id, m.status, m.next_action, m.notes)

class DraftMessage(BaseModel):
    kind: str = ""
    match_id: str = ""
    inquiry_id: str = ""
    teacher_id: str = ""

@app.post("/api/draft")
def draft_message(d: DraftMessage, current_user: dict = Depends(auth.get_current_user)):
    if current_user["role"] not in ["admin", "developer"]:
        raise HTTPException(status_code=403, detail="Not authorized to draft messages")
    result = agent.draft_message(d.kind, d.match_id, d.inquiry_id, d.teacher_id)
    return {"message": result}

class LeaveRequestCreate(BaseModel):
    parent_name: str = ""
    student_name: str = ""
    teacher_name: str = ""
    subject: str = ""
    class_date: str = ""
    reason: str = ""
    raw_message: str = ""
    notes: str = ""

@app.post("/api/leave-requests")
def add_leave_request(l: LeaveRequestCreate, current_user: dict = Depends(auth.get_current_user)):
    return agent.add_leave_request(
        l.raw_message, current_user
    )

class DraftLeaveMessage(BaseModel):
    kind: str = ""
    leave_id: str = ""

@app.post("/api/draft-leave")
def draft_leave_message(d: DraftLeaveMessage):
    result = agent.draft_leave_message(d.kind, d.leave_id)
    return {"message": result}

class MarkLeaveAction(BaseModel):
    leave_id: str = ""

@app.post("/api/mark-doc-updated")
def mark_doc_updated(m: MarkLeaveAction):
    return agent.mark_doc_updated(m.leave_id)

@app.post("/api/mark-teacher-notified")
def mark_teacher_notified(m: MarkLeaveAction):
    return agent.mark_teacher_notified(m.leave_id)

@app.post("/api/mark-parent-confirmed")
def mark_parent_confirmed(m: MarkLeaveAction):
    return agent.mark_parent_confirmed(m.leave_id)

class DraftFaq(BaseModel):
    question: str = ""
    topic: str = ""

@app.post("/api/draft-faq")
def draft_faq_reply(f: DraftFaq):
    return agent.draft_faq_reply(f.question, f.topic)

class FaqCreate(BaseModel):
    topic: str = ""
    keywords: str = ""
    answer: str = ""

@app.post("/api/faqs")
def add_faq_template(f: FaqCreate, current_user: dict = Depends(auth.get_current_user)):
    if current_user["role"] not in ["admin", "developer"]:
        raise HTTPException(status_code=403, detail="Not authorized to add FAQs")
    return agent.add_faq_template(f.topic, f.keywords, f.answer)

class ArchiveRecord(BaseModel):
    record_type: str
    record_id: str

@app.post("/api/archive")
def archive_record(req: ArchiveRecord, current_user: dict = Depends(auth.get_current_user)):
    if current_user["role"] not in ["admin", "developer"]:
        raise HTTPException(status_code=403, detail="Not authorized to archive records")
    success = agent.archive_record(req.record_type, req.record_id)
    if not success:
        raise HTTPException(status_code=404, detail="Record not found or type invalid")
    return {"message": "Archived successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

# ---------------------------------------------------------
# DEV ROUTES (Only available in DEV_MODE)
# ---------------------------------------------------------
if DEV_MODE:
    TEST_ACCOUNTS = {
        # Admins
        "admin": {
            "id": "dev_admin_123",
            "email": "dev_admin@example.com",
            "role": "admin",
            "profile_id": None,
            "label": "Admin (Main)"
        },
        "admin2": {
            "id": "dev_admin2_123",
            "email": "dev_admin2@example.com",
            "role": "admin",
            "profile_id": None,
            "label": "Admin (Ops)"
        },
        # Parents
        "parent_carol": {
            "id": "dev_parent_carol_123",
            "email": "dev_parent_carol@example.com",
            "role": "parent",
            "profile_id": "i1",
            "label": "Carol (George's Mom)",
            "inquiry": {
                "id": "i1",
                "parent_name": "Carol",
                "student_name": "George",
                "subject": "Math",
                "level": "High School",
                "availability": ["monday 4pm", "tuesday 4pm"],
                "frequency": "twice a week",
                "status": "need_teacher"
            }
        },
        "parent_wang": {
            "id": "dev_parent_wang_123",
            "email": "dev_parent_wang@example.com",
            "role": "parent",
            "profile_id": "i2",
            "label": "Wang (Eric's Dad)",
            "inquiry": {
                "id": "i2",
                "parent_name": "Wang",
                "student_name": "Eric",
                "subject": "Math",
                "level": "Grade 8",
                "availability": ["tuesday after 6", "friday after 6"],
                "frequency": "twice a week",
                "status": "need_teacher"
            }
        },
        # Students
        "student_dave": {
            "id": "dev_student_dave_123",
            "email": "dev_student_dave@example.com",
            "role": "parent",
            "profile_id": "i1",
            "label": "George (High School Math)",
            "inquiry": {
                "id": "i1",
                "parent_name": "Carol",
                "student_name": "George",
                "subject": "Math",
                "level": "High School",
                "availability": ["monday 4pm", "tuesday 4pm"],
                "frequency": "twice a week",
                "status": "need_teacher"
            }
        },
        "student_eric": {
            "id": "dev_student_eric_123",
            "email": "dev_student_eric@example.com",
            "role": "parent",
            "profile_id": "i2",
            "label": "Eric (Grade 8 Math)",
            "inquiry": {
                "id": "i2",
                "parent_name": "Wang",
                "student_name": "Eric",
                "subject": "Math",
                "level": "Grade 8",
                "availability": ["tuesday after 6", "friday after 6"],
                "frequency": "twice a week",
                "status": "need_teacher"
            }
        },
        # Teachers
        "teacher_alice": {
            "id": "dev_teacher_alice_123",
            "email": "dev_teacher_alice@example.com",
            "role": "teacher",
            "profile_id": "t1",
            "label": "Alice Chen (Math/Physics)",
            "teacher": {
                "id": "t1",
                "name": "Alice Chen",
                "subjects": ["Math", "Physics"],
                "levels": ["High School", "AP"],
                "availability": ["monday 4pm", "tuesday 4pm"],
                "rate": "$50/hr",
                "capacity": 5
            }
        },
        "teacher_bob": {
            "id": "dev_teacher_bob_123",
            "email": "dev_teacher_bob@example.com",
            "role": "teacher",
            "profile_id": "t2",
            "label": "Bob Smith (English)",
            "teacher": {
                "id": "t2",
                "name": "Bob Smith",
                "subjects": ["English"],
                "levels": ["Middle School"],
                "availability": ["wednesday 5pm", "thursday 5pm"],
                "rate": "$40/hr",
                "capacity": 3
            }
        }
    }
    # Backward compatibility mappings
    TEST_ACCOUNTS["teacher"] = TEST_ACCOUNTS["teacher_alice"]
    TEST_ACCOUNTS["parent"] = TEST_ACCOUNTS["parent_carol"]

    @app.post("/api/dev/impersonate")
    def dev_impersonate(account_id: Optional[str] = None, role: Optional[str] = None):
        """Instantly get a JWT token for a specific developer test dummy account or role."""
        key = account_id or role or "admin"
        
        if key not in TEST_ACCOUNTS:
            if key in ["admin", "developer", "teacher", "parent"]:
                acc = {
                    "id": f"dev_{key}_123",
                    "email": f"dev_{key}@example.com",
                    "role": key,
                    "profile_id": None
                }
            else:
                raise HTTPException(400, f"Invalid test account or role: {key}")
        else:
            acc = TEST_ACCOUNTS[key]
            
        user_id = acc["id"]
        email = acc["email"]
        user_role = acc["role"]
        profile_id = acc.get("profile_id")
        
        db_path = agent.DATA_DIR / "tutor.db"
        conn = db.get_db(db_path)
        cursor = conn.cursor()
        
        # Whitelist if admin/developer
        if user_role in ["admin", "developer"]:
            cursor.execute("INSERT OR IGNORE INTO admin_whitelist (email) VALUES (?)", (email,))
            
        # Ensure linked inquiry exists in SQLite if specified
        if "inquiry" in acc:
            inq = acc["inquiry"]
            cursor.execute("SELECT id FROM inquiries WHERE id = ?", (inq["id"],))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO inquiries (id, parent_name, student_name, subject, level, availability, frequency, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        inq["id"], inq.get("parent_name"), inq.get("student_name"),
                        inq.get("subject"), inq.get("level"),
                        db.to_json(inq.get("availability", [])),
                        inq.get("frequency", ""), inq.get("status", "need_teacher"),
                        datetime.datetime.utcnow().isoformat(), datetime.datetime.utcnow().isoformat()
                    )
                )
            else:
                cursor.execute(
                    "UPDATE inquiries SET parent_name = ?, student_name = ? WHERE id = ?",
                    (inq.get("parent_name"), inq.get("student_name"), inq["id"])
                )

        # Ensure linked teacher exists in SQLite if specified
        if "teacher" in acc:
            tch = acc["teacher"]
            cursor.execute("SELECT id FROM teachers WHERE id = ?", (tch["id"],))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO teachers (id, name, subjects, levels, availability, rate, capacity, active_matches, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        tch["id"], tch.get("name"),
                        db.to_json(tch.get("subjects", [])),
                        db.to_json(tch.get("levels", [])),
                        db.to_json(tch.get("availability", [])),
                        tch.get("rate", ""), tch.get("capacity", 1), 0,
                        datetime.datetime.utcnow().isoformat(), datetime.datetime.utcnow().isoformat()
                    )
                )
        
        # Ensure user exists in users table
        cursor.execute("SELECT id FROM users WHERE id = ? OR email = ?", (user_id, email))
        if not cursor.fetchone():
            hashed = auth.get_password_hash("password")
            cursor.execute(
                "INSERT INTO users (id, email, password_hash, role, profile_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, email, hashed, user_role, profile_id, datetime.datetime.utcnow().isoformat())
            )
        else:
            cursor.execute("UPDATE users SET profile_id = ?, role = ? WHERE id = ? OR email = ?", (profile_id, user_role, user_id, email))
            
        conn.commit()
        conn.close()
        
        token = auth.create_access_token({"sub": user_id, "role": user_role})
        return {
            "access_token": token,
            "token_type": "bearer",
            "role": user_role,
            "email": email,
            "profile_id": profile_id,
            "account_id": key
        }

    @app.post("/api/dev/nuke-and-seed")
    def dev_nuke_and_seed():
        """Wipes the database and populates it with a rich test scenario and dummy accounts."""
        db_path = agent.DATA_DIR / "tutor.db"
        conn = db.get_db(db_path)
        
        # Nuke
        tables = ["teachers", "inquiries", "matches", "leave_requests", "faqs", "users", "admin_whitelist"]
        for table in tables:
            conn.execute(f"DELETE FROM {table}")
        
        # Whitelist Admins
        conn.execute("INSERT INTO admin_whitelist (email) VALUES (?)", ("dev_admin@example.com",))
        conn.execute("INSERT INTO admin_whitelist (email) VALUES (?)", ("dev_admin2@example.com",))
        
        # Seed Teachers
        conn.execute("INSERT INTO teachers (id, name, subjects, levels, availability, rate, capacity, active_matches, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("t1", "Alice Chen", db.to_json(["Math", "Physics"]), db.to_json(["High School", "AP"]), db.to_json(["monday 4pm", "tuesday 4pm"]), "$50/hr", 5, 0, datetime.datetime.utcnow().isoformat(), datetime.datetime.utcnow().isoformat()))
        conn.execute("INSERT INTO teachers (id, name, subjects, levels, availability, rate, capacity, active_matches, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("t2", "Bob Smith", db.to_json(["English"]), db.to_json(["Middle School"]), db.to_json(["wednesday 5pm", "thursday 5pm"]), "$40/hr", 3, 0, datetime.datetime.utcnow().isoformat(), datetime.datetime.utcnow().isoformat()))
            
        # Seed Inquiries (Carol / George, Wang / Eric)
        conn.execute("INSERT INTO inquiries (id, parent_name, student_name, subject, level, availability, frequency, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("i1", "Carol", "George", "Math", "High School", db.to_json(["monday 4pm", "tuesday 4pm"]), "twice a week", "need_teacher", datetime.datetime.utcnow().isoformat(), datetime.datetime.utcnow().isoformat()))
        conn.execute("INSERT INTO inquiries (id, parent_name, student_name, subject, level, availability, frequency, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("i2", "Wang", "Eric", "Math", "Grade 8", db.to_json(["tuesday after 6", "friday after 6"]), "twice a week", "need_teacher", datetime.datetime.utcnow().isoformat(), datetime.datetime.utcnow().isoformat()))
            
        # Seed Users
        admin_hash = auth.get_password_hash("password")
        seed_users = [
            ("dev_admin_123", "dev_admin@example.com", "admin", None),
            ("dev_admin2_123", "dev_admin2@example.com", "admin", None),
            ("dev_parent_carol_123", "dev_parent_carol@example.com", "parent", "i1"),
            ("dev_parent_wang_123", "dev_parent_wang@example.com", "parent", "i2"),
            ("dev_student_dave_123", "dev_student_dave@example.com", "parent", "i1"),
            ("dev_student_eric_123", "dev_student_eric@example.com", "parent", "i2"),
            ("dev_teacher_alice_123", "dev_teacher_alice@example.com", "teacher", "t1"),
            ("dev_teacher_bob_123", "dev_teacher_bob@example.com", "teacher", "t2"),
        ]
        for uid, email, role, prof_id in seed_users:
            conn.execute(
                "INSERT INTO users (id, email, password_hash, role, profile_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (uid, email, admin_hash, role, prof_id, datetime.datetime.utcnow().isoformat())
            )
            
        conn.commit()
        conn.close()
        return {"status": "success", "message": "Database nuked and seeded with developer test accounts."}

    @app.post("/api/dev/restart")
    def dev_restart():
        """Touches main.py to trigger uvicorn auto-reload."""
        main_file = Path(__file__).resolve()
        os.utime(main_file, None)
        return {"status": "success", "message": "Server reload triggered"}
