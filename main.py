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
    
    if role in ["admin", "developer"]:
        teachers = all_teachers
        inquiries = all_inquiries
        matches = all_matches
        leaves = all_leaves
    elif role == "teacher":
        teachers = [t for t in all_teachers if t["id"] == profile_id]
        inquiries = [i for i in all_inquiries if i["status"] == "need_teacher"]
        matches = [m for m in all_matches if m["teacher_id"] == profile_id]
        leaves = [l for l in all_leaves if l.get("teacher_id") == profile_id]
    elif role == "parent":
        teachers = []
        inquiries = [i for i in all_inquiries if i["id"] == profile_id]
        matches = [m for m in all_matches if m["inquiry_id"] == profile_id]
        leaves = [l for l in all_leaves if l.get("inquiry_id") == profile_id]
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
    @app.post("/api/dev/impersonate")
    def dev_impersonate(role: str):
        """Instantly get a JWT token for a specific role without a password."""
        if role not in ["admin", "teacher", "parent"]:
            raise HTTPException(400, "Invalid role")
            
        mock_id = f"dev_{role}_123"
        mock_email = f"dev_{role}@example.com"
        
        db_path = agent.DATA_DIR / "tutor.db"
        conn = db.get_db(db_path)
        cursor = conn.cursor()
        
        # Ensure user exists
        cursor.execute("SELECT id FROM users WHERE email = ?", (mock_email,))
        if not cursor.fetchone():
            hashed = auth.get_password_hash("password")
            cursor.execute(
                "INSERT INTO users (id, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
                (mock_id, mock_email, hashed, role, datetime.datetime.utcnow().isoformat())
            )
            conn.commit()
            
        conn.close()
        
        token = auth.create_access_token({"sub": mock_id, "role": role})
        return {"access_token": token, "token_type": "bearer", "role": role}

    @app.post("/api/dev/nuke-and-seed")
    def dev_nuke_and_seed():
        """Wipes the database and populates it with a rich test scenario."""
        db_path = agent.DATA_DIR / "tutor.db"
        conn = db.get_db(db_path)
        
        # Nuke
        tables = ["teachers", "inquiries", "matches", "leave_requests", "faqs", "users"]
        for table in tables:
            conn.execute(f"DELETE FROM {table}")
        
        # Seed Teachers
        conn.execute("INSERT INTO teachers (id, name, subjects, levels, availability, rate, capacity, active_matches) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("t1", "Alice Expert", db.to_json(["Math", "Physics"]), db.to_json(["High School"]), db.to_json(["monday 4pm", "tuesday 4pm"]), "$50/hr", 5, 0))
        conn.execute("INSERT INTO teachers (id, name, subjects, levels, availability, rate, capacity, active_matches) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("t2", "Bob Beginner", db.to_json(["English"]), db.to_json(["Middle School"]), db.to_json(["wednesday 5pm", "thursday 5pm"]), "$40/hr", 3, 0))
            
        # Seed Inquiries
        conn.execute("INSERT INTO inquiries (id, parent_name, student_name, subject, level, status) VALUES (?, ?, ?, ?, ?, ?)",
            ("i1", "Carol Parent", "Dave Student", "Math", "High School", "need_teacher"))
            
        # Seed Admin User
        admin_hash = auth.get_password_hash("password")
        conn.execute("INSERT INTO users (id, email, password_hash, role) VALUES (?, ?, ?, ?)",
            ("dev_admin_123", "dev_admin@example.com", admin_hash, "admin"))
            
        conn.commit()
        conn.close()
        return {"status": "success", "message": "Database nuked and seeded."}
