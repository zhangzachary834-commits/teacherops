import argparse
import csv
import json
import os
import re
import sys
import threading
import datetime
import uuid
import ai
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from availability import availability_overlap, overlap_minutes


DATA_DIR = Path(__file__).resolve().parent / "data"
TEACHERS_FILE = DATA_DIR / "teachers" / "teachers.json"
INQUIRIES_FILE = DATA_DIR / "inquiries" / "inquiries.json"
MATCHES_FILE = DATA_DIR / "matches" / "matches.json"
LEAVE_REQUESTS_FILE = DATA_DIR / "operations" / "leave_requests.json"
FAQS_FILE = DATA_DIR / "support" / "faqs.json"

SUBJECT_KEYWORDS = {
    "math": ["math", "algebra", "geometry", "calculus", "precalculus"],
    "english": ["english", "writing", "reading", "essay", "literature"],
    "chinese": ["chinese", "mandarin"],
    "science": ["science", "biology", "chemistry", "physics"],
    "history": ["history", "social studies"],
    "test prep": ["sat", "act", "ssat", "test prep"],
}

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
STATUS_ORDER = [
    "new_inquiry",
    "need_teacher",
    "teacher_contacted",
    "trial_scheduled",
    "trial_completed",
    "converted",
    "not_converted",
    "payment_pending",
    "closed",
]

RECORD_TYPES = ("teachers", "inquiries", "matches", "leave_requests", "faqs")
CSV_LIST_FIELDS = {"subjects", "levels", "availability"}
DATA_LOCK = threading.RLock()
CLOSED_MATCH_STATUSES = {"not_converted", "closed"}

DEFAULT_FAQ_TEMPLATES = [
    {
        "topic": "pricing",
        "keywords": ["price", "pricing", "cost", "rate", "how much", "fee", "tuition"],
        "answer": (
            "Hi! The price depends on the student's level, subject, and teacher. "
            "If you send the student's grade, subject, and available times, I can help find a good teacher and confirm the rate."
        ),
    },
    {
        "topic": "trial_class",
        "keywords": ["trial", "try", "first class", "demo"],
        "answer": (
            "Yes, we can usually arrange a trial class. Please send the student's grade, subject, current needs, "
            "and available times, then I can check which teacher is a good fit."
        ),
    },
    {
        "topic": "teacher_matching",
        "keywords": ["teacher", "match", "recommend", "available", "find"],
        "answer": (
            "I match students based on subject, grade level, goals, schedule, and teacher availability. "
            "After I understand the student's needs, I can recommend a suitable teacher."
        ),
    },
    {
        "topic": "class_format",
        "keywords": ["online", "in person", "zoom", "format", "wechat", "class"],
        "answer": (
            "Classes are arranged based on the teacher and student's situation. "
            "Many classes can be online, and we can confirm the exact format when matching the teacher."
        ),
    },
    {
        "topic": "payment",
        "keywords": ["pay", "payment", "wechat pay", "zelle", "venmo"],
        "answer": (
            "Payment details can be confirmed after the teacher, schedule, and lesson plan are set. "
            "I will let you know the amount and payment method before classes begin."
        ),
    },
    {
        "topic": "cancellation_policy",
        "keywords": ["cancel", "leave", "miss", "absence", "reschedule", "makeup"],
        "answer": (
            "If the student needs to miss or reschedule a class, please let me know as early as possible so I can inform the teacher "
            "and update the class record."
        ),
    },
    {
        "topic": "available_subjects",
        "keywords": ["subject", "math", "english", "science", "chinese", "sat", "act"],
        "answer": (
            "We can help look for teachers in subjects such as math, English, Chinese, science, and test prep. "
            "Please send the student's grade and the subject they need."
        ),
    },
]


@dataclass
class MatchScore:
    """Holds one teacher's ranked fit for a specific inquiry."""

    teacher: dict
    score: int
    reasons: list[str]
    cautions: list[str]


def now_iso() -> str:
    """Return the current local timestamp in a compact ISO format."""

    return datetime.now().isoformat(timespec="seconds")


def ensure_data_files() -> None:
    """Create the data directory and empty JSON files if this is the first run."""

    DATA_DIR.mkdir(exist_ok=True)
    for path in [TEACHERS_FILE, INQUIRIES_FILE, MATCHES_FILE, LEAVE_REQUESTS_FILE]:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("[]\n", encoding="utf-8")
    FAQS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not FAQS_FILE.exists():
        FAQS_FILE.write_text(json.dumps(default_faq_records(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


import db
import sqlite3

def read_json(path: Path) -> list[dict]:
    """Read one of the agent's tables from SQLite and format it as a list of dicts."""
    with DATA_LOCK:
        db_path = DATA_DIR / "tutor.db"
        conn = db.get_db(db_path)
        table_name = path.stem
        try:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            
            # Auto-populate FAQs if empty (matches file behavior)
            if count == 0 and table_name == "faqs":
                write_json(path, default_faq_records())
            
            cursor.execute(f"SELECT * FROM {table_name}")
            rows = cursor.fetchall()
            
            result = []
            for row in rows:
                d = dict(row)
                # Deserialize JSON list fields depending on table
                if table_name == "teachers":
                    d["subjects"] = db.from_json(d["subjects"])
                    d["levels"] = db.from_json(d["levels"])
                    d["availability"] = db.from_json(d["availability"])
                    d["google_doc_updated"] = False # not used in teachers but good for schema matching
                elif table_name == "inquiries":
                    d["availability"] = db.from_json(d["availability"])
                elif table_name == "faqs":
                    d["keywords"] = db.from_json(d["keywords"])
                elif table_name == "leave_requests":
                    d["google_doc_updated"] = bool(d["google_doc_updated"])
                result.append(d)
            return result
        except sqlite3.OperationalError:
            db.init_db(db_path)
            if table_name == "faqs":
                write_json(path, default_faq_records())
            return read_json(path) # Retry once after init
        finally:
            conn.close()

def write_json(path: Path, data: list[dict]) -> None:
    """Write a list of dicts back to SQLite (replaces the table content)."""
    with DATA_LOCK:
        db_path = DATA_DIR / "tutor.db"
        conn = db.get_db(db_path)
        table_name = path.stem
        cursor = conn.cursor()
        
        try:
            # We delete all and re-insert (mimicking file write behavior for now)
            cursor.execute(f"DELETE FROM {table_name}")
        except sqlite3.OperationalError:
            db.init_db(db_path)
            cursor.execute(f"DELETE FROM {table_name}")
        
        for d in data:
            if table_name == "teachers":
                cursor.execute("""
                    INSERT INTO teachers 
                    (id, name, subjects, levels, availability, rate, capacity, active_matches, contact, notes, created_at, updated_at) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    d.get("id"), d.get("name"),
                    db.to_json(d.get("subjects", [])),
                    db.to_json(d.get("levels", [])),
                    db.to_json(d.get("availability", [])),
                    d.get("rate"), d.get("capacity"), d.get("active_matches"),
                    d.get("contact"), d.get("notes"),
                    d.get("created_at"), d.get("updated_at")
                ))
            elif table_name == "inquiries":
                cursor.execute("""
                    INSERT INTO inquiries 
                    (id, parent_name, student_name, subject, level, availability, frequency, raw_message, notes, status, next_action, last_contacted, created_at, updated_at) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    d.get("id"), d.get("parent_name"), d.get("student_name"),
                    d.get("subject"), d.get("level"),
                    db.to_json(d.get("availability", [])),
                    d.get("frequency"), d.get("raw_message"), d.get("notes"),
                    d.get("status"), d.get("next_action"), d.get("last_contacted"),
                    d.get("created_at"), d.get("updated_at")
                ))
            elif table_name == "matches":
                cursor.execute("""
                    INSERT INTO matches 
                    (id, inquiry_id, teacher_id, parent_name, student_name, teacher_name, subject, status, next_action, last_contacted, payment_status, notes, created_at, updated_at) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    d.get("id"), d.get("inquiry_id"), d.get("teacher_id"),
                    d.get("parent_name"), d.get("student_name"), d.get("teacher_name"),
                    d.get("subject"), d.get("status"), d.get("next_action"),
                    d.get("last_contacted"), d.get("payment_status"), d.get("notes"),
                    d.get("created_at"), d.get("updated_at")
                ))
            elif table_name == "leave_requests":
                cursor.execute("""
                    INSERT INTO leave_requests 
                    (id, parent_name, student_name, teacher_name, subject, class_date, reason, raw_message, notes, status, next_action, google_doc_updated, created_at, updated_at) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    d.get("id"), d.get("parent_name"), d.get("student_name"),
                    d.get("teacher_name"), d.get("subject"), d.get("class_date"),
                    d.get("reason"), d.get("raw_message"), d.get("notes"),
                    d.get("status"), d.get("next_action"),
                    1 if d.get("google_doc_updated") else 0,
                    d.get("created_at"), d.get("updated_at")
                ))
            elif table_name == "faqs":
                cursor.execute("""
                    INSERT INTO faqs 
                    (id, topic, keywords, answer, created_at, updated_at) 
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    d.get("id"), d.get("topic"),
                    db.to_json(d.get("keywords", [])),
                    d.get("answer"), d.get("created_at"), d.get("updated_at")
                ))
        conn.commit()
        conn.close()


def record_file(record_type: str) -> Path:
    """Return the JSON store for a supported record type."""

    if record_type == "teachers":
        return TEACHERS_FILE
    if record_type == "inquiries":
        return INQUIRIES_FILE
    if record_type == "matches":
        return MATCHES_FILE
    if record_type == "leave_requests":
        return LEAVE_REQUESTS_FILE
    if record_type == "faqs":
        return FAQS_FILE
    raise ValueError(f"Unknown record type '{record_type}'. Use one of: {', '.join(RECORD_TYPES)}.")


def normalize_list(value: str | list[str] | None) -> list[str]:
    """Turn comma/semicolon/slash-separated text into normalized lowercase items."""

    if value is None:
        return []
    if isinstance(value, list):
        parts = value
    else:
        parts = re.split(r"[,;/]", value)
    return [part.strip().lower() for part in parts if part.strip()]


def parse_int(value, default: int = 0) -> int:
    """Parse an integer field from CSV/JSON-ish input with a safe default."""

    try:
        if value in ("", None):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def csv_value(value) -> str:
    """Convert stored values into spreadsheet-friendly CSV cell text."""

    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return "" if value is None else str(value)


def make_id(prefix: str, rows: list[dict]) -> str:
    """Create the next stable record id for a collection, such as T0001."""

    max_seen = 0
    for row in rows:
        row_id = str(row.get("id", ""))
        if row_id.startswith(prefix):
            try:
                max_seen = max(max_seen, int(row_id[len(prefix):]))
            except ValueError:
                pass
    return f"{prefix}{max_seen + 1:04d}"


def match_counts_as_active(match: dict) -> bool:
    """Return whether a match should occupy one teacher capacity slot."""

    return match.get("status") not in CLOSED_MATCH_STATUSES


def sync_teacher_active_matches(teachers: list[dict], matches: list[dict]) -> None:
    """Recalculate each teacher's active match count from the match records."""

    active_by_teacher: dict[str, int] = {}
    for match in matches:
        teacher_id = match.get("teacher_id")
        if teacher_id and match_counts_as_active(match):
            active_by_teacher[teacher_id] = active_by_teacher.get(teacher_id, 0) + 1
    for teacher in teachers:
        teacher["active_matches"] = active_by_teacher.get(teacher.get("id"), 0)


def phrase_in_text(phrase: str, text: str) -> bool:
    """Return whether a phrase appears as words rather than inside another word."""

    normalized = phrase.strip().lower()
    if not normalized:
        return False
    pattern = rf"(?<!\w){re.escape(normalized)}(?!\w)"
    return re.search(pattern, text.lower()) is not None


def default_faq_records() -> list[dict]:
    """Create the default customer FAQ answer bank."""

    timestamp = now_iso()
    return [
        {
            "id": f"F{index:04d}",
            "topic": item["topic"],
            "keywords": item["keywords"],
            "answer": item["answer"],
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        for index, item in enumerate(DEFAULT_FAQ_TEMPLATES, start=1)
    ]


def add_teacher(
    name: str,
    subjects: str,
    levels: str = "",
    availability: str = "",
    rate: str = "",
    capacity: int = 1,
    contact: str = "",
    notes: str = "",
) -> dict:
    """Store a teacher profile or update an existing one if the name matches."""

    teachers = read_json(TEACHERS_FILE)
    existing_teacher = next((t for t in teachers if t.get("name", "").lower() == name.lower()), None)
    
    if existing_teacher:
        existing_teacher["subjects"] = normalize_list(subjects)
        existing_teacher["levels"] = normalize_list(levels)
        existing_teacher["availability"] = normalize_list(availability)
        existing_teacher["rate"] = rate
        existing_teacher["capacity"] = capacity
        if contact:
            existing_teacher["contact"] = contact
        if notes:
            existing_teacher["notes"] = notes
        existing_teacher["updated_at"] = now_iso()
        teacher = existing_teacher
    else:
        teacher = {
            "id": make_id("T", teachers),
            "name": name,
            "subjects": normalize_list(subjects),
            "levels": normalize_list(levels),
            "availability": normalize_list(availability),
            "rate": rate,
            "capacity": capacity,
            "active_matches": 0,
            "contact": contact,
            "notes": notes,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        teachers.append(teacher)
        
    write_json(TEACHERS_FILE, teachers)
    return teacher


def row_to_teacher(row: dict, existing: list[dict]) -> dict:
    """Convert one CSV row into a teacher record."""

    timestamp = now_iso()
    return {
        "id": row.get("id") or make_id("T", existing),
        "name": row.get("name", "").strip(),
        "subjects": normalize_list(row.get("subjects", "")),
        "levels": normalize_list(row.get("levels", "")),
        "availability": normalize_list(row.get("availability", "")),
        "rate": row.get("rate", ""),
        "capacity": parse_int(row.get("capacity"), 1),
        "active_matches": parse_int(row.get("active_matches"), 0),
        "contact": row.get("contact", ""),
        "notes": row.get("notes", ""),
        "created_at": row.get("created_at") or timestamp,
        "updated_at": row.get("updated_at") or timestamp,
    }


def infer_subject(message: str) -> str:
    """Guess the requested subject from a pasted parent message."""

    lower = message.lower()
    for subject, keywords in SUBJECT_KEYWORDS.items():
        if any(keyword in lower for keyword in keywords):
            return subject
    return ""


def infer_level(message: str) -> str:
    """Guess the student's school level from grade or level wording."""

    lower = message.lower()
    grade_match = re.search(r"\b(?:grade|gr\.?|g)\s*(\d{1,2})\b", lower)
    if grade_match:
        return f"grade {grade_match.group(1)}"
    year_match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)\s*grade\b", lower)
    if year_match:
        return f"grade {year_match.group(1)}"
    for level in ["elementary", "middle school", "high school", "college", "adult"]:
        if level in lower:
            return level
    return ""


def infer_frequency(message: str) -> str:
    """Guess how often the parent wants lessons each week."""

    lower = message.lower()
    if "twice" in lower or "2x" in lower or "two times" in lower:
        return "twice a week"
    if "once" in lower or "1x" in lower or "one time" in lower:
        return "once a week"
    match = re.search(r"\b(\d+)\s*(?:times|x)\s*(?:a|per)?\s*week\b", lower)
    if match:
        return f"{match.group(1)} times a week"
    return ""


def infer_availability(message: str) -> list[str]:
    """Extract rough day/time availability from a pasted parent message."""

    lower = message.lower()
    availability = []
    for day in DAYS:
        day_pattern = rf"\b{day[:3]}\w*\b"
        if not re.search(day_pattern, lower):
            continue
        time_match = re.search(
            day_pattern + r"[^,.]*?(after\s*\d+(?::\d{2})?\s*(?:am|pm)?|before\s*\d+(?::\d{2})?\s*(?:am|pm)?|\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
            lower,
        )
        if time_match:
            availability.append(f"{day} {time_match.group(1).strip()}")
        else:
            period_match = re.search(day_pattern + r"[^,.]*?\b(morning|afternoon|evening)\b", lower)
            availability.append(f"{day} {period_match.group(1)}" if period_match else day)
    if "weekend" in lower:
        availability.extend(["saturday", "sunday"])
    if "evening" in lower and not availability:
        availability.append("evening")
    if "afternoon" in lower and not availability:
        availability.append("afternoon")
    return sorted(set(availability))


def infer_date_reference(message: str) -> str:
    """Extract a simple date reference as ISO date or weekday text."""

    lower = message.lower()
    iso_match = re.search(r"\b(\d{4}-\d{1,2}-\d{1,2})\b", lower)
    if iso_match:
        try:
            return date.fromisoformat(iso_match.group(1)).isoformat()
        except ValueError:
            return iso_match.group(1)

    slash_match = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", lower)
    if slash_match:
        month = int(slash_match.group(1))
        day = int(slash_match.group(2))
        year_text = slash_match.group(3)
        year = date.today().year if not year_text else int(year_text)
        if year < 100:
            year += 2000
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return slash_match.group(0)

    if "tomorrow" in lower:
        return (date.today() + timedelta(days=1)).isoformat()
    if "today" in lower:
        return date.today().isoformat()

    for index, day_name in enumerate(DAYS):
        if day_name in lower or day_name[:3] in lower:
            days_ahead = (index - date.today().weekday()) % 7
            if days_ahead == 0 and "next" in lower:
                days_ahead = 7
            return (date.today() + timedelta(days=days_ahead)).isoformat()
    return ""


def infer_student_name(message: str) -> str:
    """Make a conservative guess at a student's first name from a leave message."""

    match = re.search(r"\b([A-Z][a-z]+)\s+(?:needs?|will|can't|cannot|wants?|has)\b", message)
    if match:
        return match.group(1)
    return ""


def infer_leave_reason(message: str) -> str:
    """Extract a short reason phrase from a leave message when one is present."""

    lower = message.lower()
    match = re.search(r"\b(?:because|due to|since)\s+(.+)$", lower)
    if match:
        return match.group(1).strip(" .")
    return ""


def extract_inquiry(message: str) -> dict:
    """Convert an unstructured parent message into the first structured inquiry fields using AI."""
    ai_result = ai.extract_inquiry_with_ai(message)
    return {
        "subject": ai_result.get("subject", infer_subject(message)),
        "level": ai_result.get("level", infer_level(message)),
        "frequency": ai_result.get("frequency", infer_frequency(message)),
        "availability": ai_result.get("availability", infer_availability(message)),
        "raw_message": message,
        "next_action": "find matching teacher",
    }


def extract_leave_request(message: str) -> dict:
    """Convert a leave/absence message into structured absence fields using AI."""
    ai_result = ai.extract_leave_with_ai(message)
    return {
        "student_name": ai_result.get("student_name", infer_student_name(message)),
        "class_date": ai_result.get("class_date", infer_date_reference(message)),
        "reason": ai_result.get("reason", infer_leave_reason(message)),
        "raw_message": message,
        "next_action": "notify teacher and update Google doc",
    }


def add_inquiry(
    parent_name: str,
    student_name: str = "",
    subject: str = "",
    level: str = "",
    availability: str = "",
    frequency: str = "",
    raw_message: str = "",
    notes: str = "",
) -> dict:
    """Create a student inquiry, using extracted message details when fields are blank."""

    inquiries = read_json(INQUIRIES_FILE)
    extracted = extract_inquiry(raw_message) if raw_message else {}
    inquiry = {
        "id": make_id("I", inquiries),
        "parent_name": parent_name,
        "student_name": student_name,
        "subject": (subject or extracted.get("subject", "")).lower(),
        "level": (level or extracted.get("level", "")).lower(),
        "availability": normalize_list(availability) or extracted.get("availability", []),
        "frequency": frequency or extracted.get("frequency", ""),
        "raw_message": raw_message,
        "notes": notes,
        "status": "need_teacher",
        "next_action": "find matching teacher",
        "last_contacted": "",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    inquiries.append(inquiry)
    write_json(INQUIRIES_FILE, inquiries)
    return inquiry


def row_to_inquiry(row: dict, existing: list[dict]) -> dict:
    """Convert one CSV row into an inquiry record, extracting blanks from message text."""

    timestamp = now_iso()
    raw_message = row.get("raw_message") or row.get("message", "")
    extracted = extract_inquiry(raw_message) if raw_message else {}
    availability = normalize_list(row.get("availability", "")) or extracted.get("availability", [])
    return {
        "id": row.get("id") or make_id("I", existing),
        "parent_name": row.get("parent_name") or row.get("parent", ""),
        "student_name": row.get("student_name") or row.get("student", ""),
        "subject": (row.get("subject") or extracted.get("subject", "")).lower(),
        "level": (row.get("level") or extracted.get("level", "")).lower(),
        "availability": availability,
        "frequency": row.get("frequency") or extracted.get("frequency", ""),
        "raw_message": raw_message,
        "notes": row.get("notes", ""),
        "status": row.get("status") or "need_teacher",
        "next_action": row.get("next_action") or "find matching teacher",
        "last_contacted": row.get("last_contacted", ""),
        "created_at": row.get("created_at") or timestamp,
        "updated_at": row.get("updated_at") or timestamp,
    }


def find_by_id(rows: list[dict], row_id: str) -> dict:
    """Find one record by id or raise a clear error for the CLI/user."""

    for row in rows:
        if row.get("id") == row_id:
            return row
    raise ValueError(f"No record found for id {row_id}.")


# def availability_overlap(wanted: list[str], offered: list[str]) -> list[str]:
#     """Find simple overlap between requested and teacher-offered availability."""
#
#     overlap = []
#     for want in wanted:
#         for offer in offered:
#             if want in offer or offer in want or want.split()[0] == offer.split()[0]:
#                 overlap.append(offer)
#     return sorted(set(overlap))


def score_teacher(teacher: dict, inquiry: dict) -> MatchScore:
    """Score one teacher against an inquiry using subject, level, schedule, and capacity."""

    score = 0
    reasons = []
    cautions = []
    
    # General / Specific mapping: check if inquiry explicitly names this teacher
    inquiry_text = (inquiry.get("raw_message", "") + " " + inquiry.get("notes", "")).lower()
    teacher_name_lower = teacher.get("name", "").lower()
    if phrase_in_text(teacher_name_lower, inquiry_text):
        score += 500
        reasons.append(f"specifically requested by name")

    if inquiry["subject"] and inquiry["subject"] in teacher["subjects"]:
        score += 50
        reasons.append(f"teaches {inquiry['subject']}")
    elif inquiry["subject"]:
        cautions.append(f"subject mismatch: needs {inquiry['subject']}")

    if inquiry["level"]:
        levels_text = " ".join(teacher.get("levels", []))
        if inquiry["level"] in levels_text or not teacher.get("levels"):
            score += 20
            reasons.append(f"level fit: {inquiry['level']}")
        else:
            cautions.append(f"level uncertain: {inquiry['level']}")

    wanted = inquiry.get("availability", [])
    offered = teacher.get("availability", [])
    overlap = availability_overlap(wanted, offered)
    shared_minutes = overlap_minutes(wanted, offered)
    if shared_minutes > 0:
        score += min(20, 10 + shared_minutes // 30)
        reasons.append(f"availability overlap: {', '.join(overlap)}")
    elif wanted and offered:
        cautions.append("availability needs confirmation")
    elif wanted and not offered:
        cautions.append("teacher availability not recorded")

    remaining = parse_int(teacher.get("capacity"), 0) - parse_int(teacher.get("active_matches"), 0)
    if remaining > 0:
        score += 10
        reasons.append(f"{remaining} open slot(s)")
    else:
        cautions.append("teacher may be at capacity")

    return MatchScore(teacher=teacher, score=score, reasons=reasons, cautions=cautions)


def find_teacher_matches(inquiry_id: str, limit: int = 5) -> list[dict]:
    """Rank teachers for an inquiry and return a compact explanation of each fit."""

    teachers = read_json(TEACHERS_FILE)
    inquiries = read_json(INQUIRIES_FILE)
    inquiry = find_by_id(inquiries, inquiry_id)
    scored = [score_teacher(teacher, inquiry) for teacher in teachers]
    
    # Check for specific request
    specific_teachers = [item for item in scored if item.score >= 500]
    if specific_teachers:
        scored = specific_teachers
    else:
        scored.sort(key=lambda item: item.score, reverse=True)
        scored = scored[:limit]
        
    return [
        {
            "teacher_id": item.teacher["id"],
            "teacher_name": item.teacher["name"],
            "score": item.score,
            "rate": item.teacher.get("rate", ""),
            "reasons": item.reasons,
            "cautions": item.cautions,
        }
        for item in scored
    ]


def create_match(inquiry_id: str, teacher_id: str, status: str = "teacher_contacted") -> dict:
    """Create the working record that ties one inquiry to one teacher."""

    with DATA_LOCK:
        inquiries = read_json(INQUIRIES_FILE)
        teachers = read_json(TEACHERS_FILE)
        matches = read_json(MATCHES_FILE)
        inquiry = find_by_id(inquiries, inquiry_id)
        teacher = find_by_id(teachers, teacher_id)
        match = {
            "id": make_id("M", matches),
            "inquiry_id": inquiry_id,
            "teacher_id": teacher_id,
            "parent_name": inquiry.get("parent_name", ""),
            "student_name": inquiry.get("student_name", ""),
            "teacher_name": teacher.get("name", ""),
            "subject": inquiry.get("subject", ""),
            "status": status,
            "next_action": "confirm teacher availability",
            "last_contacted": now_iso(),
            "payment_status": "not_started",
            "notes": "",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        matches.append(match)
        sync_teacher_active_matches(teachers, matches)
        write_json(MATCHES_FILE, matches)
        write_json(TEACHERS_FILE, teachers)
        return match


def row_to_match(row: dict, existing: list[dict]) -> dict:
    """Convert one CSV row into a match record without requiring lookup joins."""

    timestamp = now_iso()
    return {
        "id": row.get("id") or make_id("M", existing),
        "inquiry_id": row.get("inquiry_id", ""),
        "teacher_id": row.get("teacher_id", ""),
        "parent_name": row.get("parent_name", ""),
        "student_name": row.get("student_name", ""),
        "teacher_name": row.get("teacher_name", ""),
        "subject": row.get("subject", ""),
        "status": row.get("status") or "teacher_contacted",
        "next_action": row.get("next_action") or "confirm teacher availability",
        "last_contacted": row.get("last_contacted", ""),
        "payment_status": row.get("payment_status") or "not_started",
        "notes": row.get("notes", ""),
        "created_at": row.get("created_at") or timestamp,
        "updated_at": row.get("updated_at") or timestamp,
    }


def add_leave_request(
    raw_message: str,
    current_user: dict,
) -> list[dict]:
    """Create leave requests that tracks messages and Google doc update status."""
    
    leave_requests = read_json(LEAVE_REQUESTS_FILE)
    extracted = extract_leave_request(raw_message) if raw_message else {}
    timestamp = now_iso()
    
    role = current_user.get("role")
    profile_id = current_user.get("profile_id")
    
    # Get active matches
    matches = [m for m in read_json(MATCHES_FILE) if m.get("status") not in ["archived", "closed", "dropped"]]
    if role == "teacher":
        user_matches = [m for m in matches if m.get("teacher_id") == profile_id]
    elif role == "parent":
        # We don't explicitly store parent_id in match, but we know inquiry_id
        # Let's find inquiries for this parent
        inquiries = [i for i in read_json(INQUIRIES_FILE) if i.get("id") == profile_id]
        if inquiries:
            parent_name = inquiries[0].get("parent_name", "")
            user_matches = [m for m in matches if m.get("parent_name") == parent_name]
        else:
            user_matches = []
    else:
        user_matches = []
        
    extracted_student = extracted.get("student_name", "").lower()
    matched_records = []
    
    if extracted_student:
        for m in user_matches:
            if extracted_student in m.get("student_name", "").lower():
                matched_records.append(m)
    
    # If no specific student matched, but they have active matches, apply to all their active matches
    if not matched_records and user_matches:
        matched_records = user_matches
        
    new_requests = []
    
    if not matched_records:
        # Fallback if no matches found
        leave_request = {
            "id": make_id("L", leave_requests),
            "parent_name": "",
            "student_name": extracted.get("student_name", ""),
            "teacher_name": "",
            "subject": "",
            "class_date": extracted.get("class_date", ""),
            "reason": extracted.get("reason", ""),
            "raw_message": raw_message,
            "status": "leave_requested",
            "teacher_notified": False,
            "parent_confirmed": False,
            "google_doc_updated": False,
            "next_action": "notify teacher and update Google doc",
            "notes": "",
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        leave_requests.append(leave_request)
        new_requests.append(leave_request)
    else:
        for m in matched_records:
            leave_request = {
                "id": make_id("L", leave_requests),
                "parent_name": m.get("parent_name", ""),
                "student_name": m.get("student_name", ""),
                "teacher_name": m.get("teacher_name", ""),
                "subject": m.get("subject", "").lower(),
                "class_date": extracted.get("class_date", ""),
                "reason": extracted.get("reason", ""),
                "raw_message": raw_message,
                "status": "leave_requested",
                "teacher_notified": role == "teacher",
                "parent_confirmed": role == "parent",
                "google_doc_updated": False,
                "next_action": "notify teacher and update Google doc" if role == "parent" else "confirm with parent and update Google doc",
                "notes": "",
                "created_at": timestamp,
                "updated_at": timestamp,
            }
            leave_requests.append(leave_request)
            new_requests.append(leave_request)

    write_json(LEAVE_REQUESTS_FILE, leave_requests)
    return new_requests


def row_to_leave_request(row: dict, existing: list[dict]) -> dict:
    """Convert one CSV row into a leave request record."""

    timestamp = now_iso()
    return {
        "id": row.get("id") or make_id("L", existing),
        "parent_name": row.get("parent_name") or row.get("parent", ""),
        "student_name": row.get("student_name") or row.get("student", ""),
        "teacher_name": row.get("teacher_name") or row.get("teacher", ""),
        "subject": row.get("subject", "").lower(),
        "class_date": row.get("class_date") or row.get("date", ""),
        "reason": row.get("reason", ""),
        "raw_message": row.get("raw_message") or row.get("message", ""),
        "status": row.get("status") or "leave_requested",
        "teacher_notified": str(row.get("teacher_notified", "")).lower() == "true",
        "parent_confirmed": str(row.get("parent_confirmed", "")).lower() == "true",
        "google_doc_updated": str(row.get("google_doc_updated", "")).lower() == "true",
        "next_action": row.get("next_action") or "notify teacher and update Google doc",
        "notes": row.get("notes", ""),
        "created_at": row.get("created_at") or timestamp,
        "updated_at": row.get("updated_at") or timestamp,
    }


def list_leave_requests(status: str = "") -> list[dict]:
    """Return leave requests, optionally filtered by status."""

    leave_requests = read_json(LEAVE_REQUESTS_FILE)
    if not status:
        return leave_requests
    return [request for request in leave_requests if request.get("status") == status]


def refresh_leave_request_status(leave_request: dict) -> None:
    """Update a leave request's status and next action from its three checklist flags."""

    missing_actions = []
    if not leave_request.get("teacher_notified"):
        missing_actions.append("notify teacher")
    if not leave_request.get("google_doc_updated"):
        missing_actions.append("update Google doc")
    if not leave_request.get("parent_confirmed"):
        missing_actions.append("confirm with parent")

    if missing_actions:
        leave_request["status"] = "leave_requested"
        leave_request["next_action"] = " and ".join(missing_actions)
    else:
        leave_request["status"] = "closed"
        leave_request["next_action"] = "complete"


def draft_leave_message(kind: str, leave_id: str) -> str:
    """Draft a teacher, parent, or Google-doc note for a leave request."""

    leave_request = find_by_id(read_json(LEAVE_REQUESTS_FILE), leave_id)
    student = leave_request.get("student_name") or "the student"
    teacher = leave_request.get("teacher_name") or "teacher"
    parent = leave_request.get("parent_name") or "there"
    subject = leave_request.get("subject") or "class"
    class_date = leave_request.get("class_date") or "the requested class date"
    reason = leave_request.get("reason")
    reason_text = f" Reason: {reason}." if reason else ""

    if kind == "teacher":
        return (
            f"Hi {teacher}, {student} will take leave from {subject} class on {class_date}.{reason_text} "
            "Please note the schedule change. I will update the class record."
        )
    if kind == "parent":
        return (
            f"Hi {parent}, got it. I will let the teacher know that {student} will take leave on {class_date} "
            "and update the class record."
        )
    if kind == "doc_note":
        return f"{class_date} | {student} | {teacher} | {subject} | leave requested | {reason or ''}"
    raise ValueError("Unknown leave message kind. Use teacher, parent, or doc_note.")


def mark_doc_updated(leave_id: str) -> dict:
    """Mark a leave request's Google doc update as completed."""

    leave_requests = read_json(LEAVE_REQUESTS_FILE)
    leave_request = find_by_id(leave_requests, leave_id)
    leave_request["google_doc_updated"] = True
    refresh_leave_request_status(leave_request)
    leave_request["updated_at"] = now_iso()
    write_json(LEAVE_REQUESTS_FILE, leave_requests)
    return leave_request


def mark_teacher_notified(leave_id: str) -> dict:
    """Mark a leave request as teacher notified."""

    leave_requests = read_json(LEAVE_REQUESTS_FILE)
    leave_request = find_by_id(leave_requests, leave_id)
    leave_request["teacher_notified"] = True
    refresh_leave_request_status(leave_request)
    leave_request["updated_at"] = now_iso()
    write_json(LEAVE_REQUESTS_FILE, leave_requests)
    return leave_request


def mark_parent_confirmed(leave_id: str) -> dict:
    """Mark a leave request as parent confirmed."""

    leave_requests = read_json(LEAVE_REQUESTS_FILE)
    leave_request = find_by_id(leave_requests, leave_id)
    leave_request["parent_confirmed"] = True
    refresh_leave_request_status(leave_request)
    leave_request["updated_at"] = now_iso()
    write_json(LEAVE_REQUESTS_FILE, leave_requests)
    return leave_request


def row_to_faq(row: dict, existing: list[dict]) -> dict:
    """Convert one CSV row into an FAQ template."""

    timestamp = now_iso()
    return {
        "id": row.get("id") or make_id("F", existing),
        "topic": row.get("topic", "").strip(),
        "keywords": normalize_list(row.get("keywords", "")),
        "answer": row.get("answer", ""),
        "created_at": row.get("created_at") or timestamp,
        "updated_at": row.get("updated_at") or timestamp,
    }


def add_faq_template(topic: str, keywords: str, answer: str) -> dict:
    """Add a reusable answer template for repeated customer questions."""

    faqs = read_json(FAQS_FILE)
    timestamp = now_iso()
    faq = {
        "id": make_id("F", faqs),
        "topic": topic.strip(),
        "keywords": normalize_list(keywords),
        "answer": answer.strip(),
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    faqs.append(faq)
    write_json(FAQS_FILE, faqs)
    return faq


def list_faqs() -> list[dict]:
    """Return the current FAQ answer bank."""

    return read_json(FAQS_FILE)


def classify_faq_question(question: str) -> list[dict]:
    """Rank FAQ templates by keyword overlap with a customer question."""

    lower = question.lower()
    matches = []
    for faq in read_json(FAQS_FILE):
        keywords = faq.get("keywords", [])
        hits = [keyword for keyword in keywords if keyword and keyword in lower]
        if hits:
            matches.append({
                "faq_id": faq["id"],
                "topic": faq.get("topic", ""),
                "score": len(hits),
                "matched_keywords": hits,
            })
    matches.sort(key=lambda item: item["score"], reverse=True)
    return matches


def draft_faq_reply(question: str, topic: str = "") -> dict:
    """Draft a reply to a repeated customer question from the FAQ answer bank."""

    faqs = read_json(FAQS_FILE)
    selected = None
    if topic:
        selected = next((faq for faq in faqs if faq.get("topic") == topic or faq.get("id") == topic), None)
    matches = classify_faq_question(question)
    if selected is None and matches:
        selected = find_by_id(faqs, matches[0]["faq_id"])
    if selected is None:
        return {
            "topic": "",
            "matched": [],
            "reply": (
                "Hi! Thanks for reaching out. Could you please send the student's grade, subject, current needs, "
                "and available times? Then I can help check the best next step."
            ),
        }
    return {
        "topic": selected.get("topic", ""),
        "matched": matches,
        "reply": selected.get("answer", ""),
    }


def update_match(match_id: str, status: str | None = None, next_action: str | None = None, notes: str | None = None) -> dict:
    """Update a match's pipeline status, next action, or notes."""

    with DATA_LOCK:
        matches = read_json(MATCHES_FILE)
        match = find_by_id(matches, match_id)
        if status:
            if status not in STATUS_ORDER:
                raise ValueError(f"Unknown status '{status}'. Use one of: {', '.join(STATUS_ORDER)}.")
            match["status"] = status
        if next_action is not None:
            match["next_action"] = next_action
        if notes is not None:
            match["notes"] = notes
        match["updated_at"] = now_iso()
        teachers = read_json(TEACHERS_FILE)
        sync_teacher_active_matches(teachers, matches)
        write_json(MATCHES_FILE, matches)
        write_json(TEACHERS_FILE, teachers)
        return match


def needs_followup(row: dict, older_than_days: int) -> bool:
    """Decide whether an open inquiry or match has waited long enough for follow-up."""

    if row.get("status") in {"converted", "not_converted", "closed"}:
        return False
    last = row.get("last_contacted") or row.get("created_at")
    if not last:
        return True
    try:
        last_date = datetime.fromisoformat(last).date()
    except ValueError:
        return True
    return last_date <= date.today() - timedelta(days=older_than_days)


def list_followups(older_than_days: int = 2) -> list[dict]:
    """List open inquiries, matches, and leave requests that need attention."""

    inquiries = read_json(INQUIRIES_FILE)
    matches = read_json(MATCHES_FILE)
    leave_requests = read_json(LEAVE_REQUESTS_FILE)
    items = []
    for inquiry in inquiries:
        if needs_followup(inquiry, older_than_days):
            items.append({
                "type": "inquiry",
                "id": inquiry["id"],
                "name": inquiry.get("parent_name", ""),
                "status": inquiry.get("status", ""),
                "next_action": inquiry.get("next_action", ""),
            })
    for match in matches:
        if needs_followup(match, older_than_days):
            items.append({
                "type": "match",
                "id": match["id"],
                "name": f"{match.get('parent_name', '')} / {match.get('teacher_name', '')}",
                "status": match.get("status", ""),
                "next_action": match.get("next_action", ""),
            })
    for request in leave_requests:
        if request.get("status") == "closed":
            continue
        if request.get("teacher_notified") and request.get("parent_confirmed") and request.get("google_doc_updated"):
            continue
        items.append({
            "type": "leave",
            "id": request["id"],
            "name": f"{request.get('student_name', '')} / {request.get('teacher_name', '')}",
            "status": request.get("status", ""),
            "next_action": request.get("next_action", ""),
        })
    return items


def draft_message(kind: str, match_id: str = "", inquiry_id: str = "", teacher_id: str = "") -> str:
    """Draft a human-approved WeChat-style message for common coordination moments."""

    inquiries = read_json(INQUIRIES_FILE)
    teachers = read_json(TEACHERS_FILE)
    matches = read_json(MATCHES_FILE)

    match = find_by_id(matches, match_id) if match_id else {}
    inquiry = find_by_id(inquiries, inquiry_id or match.get("inquiry_id", "")) if (inquiry_id or match.get("inquiry_id")) else {}
    teacher = find_by_id(teachers, teacher_id or match.get("teacher_id", "")) if (teacher_id or match.get("teacher_id")) else {}

    parent = inquiry.get("parent_name", "there")
    student = inquiry.get("student_name") or "your student"
    teacher_name = teacher.get("name", "the teacher")
    subject = inquiry.get("subject", "the subject")
    availability = ", ".join(inquiry.get("availability", [])) or "the times you mentioned"

    if kind == "ask_teacher":
        return (
            f"Hi {teacher_name}, I have a possible {subject} student: {student}, "
            f"{inquiry.get('level', 'level not specified')}, hoping for {inquiry.get('frequency', 'regular lessons')} "
            f"around {availability}. Would you be available and interested?"
        )
    if kind == "parent_intro":
        return (
            f"Hi {parent}, I found a possible teacher, {teacher_name}, for {student}'s {subject}. "
            "I am checking the schedule fit now and will confirm the next step with you."
        )
    if kind == "followup":
        return (
            f"Hi {parent}, just following up on {student}'s {subject} tutoring. "
            "Would you still like me to keep looking/confirming the schedule?"
        )
    if kind == "trial_confirm":
        return (
            f"Hi {parent}, confirming the trial lesson for {student} with {teacher_name}. "
            "Please reply to confirm the time still works."
        )
    if kind == "payment_reminder":
        return (
            f"Hi {parent}, quick reminder that payment for {student}'s {subject} lessons is pending. "
            "Thank you!"
        )
    raise ValueError("Unknown message kind. Use ask_teacher, parent_intro, followup, trial_confirm, or payment_reminder.")


def weekly_report() -> dict:
    """Summarize the current tutoring hub workload and bottlenecks."""

    inquiries = read_json(INQUIRIES_FILE)
    matches = read_json(MATCHES_FILE)
    teachers = read_json(TEACHERS_FILE)
    leave_requests = read_json(LEAVE_REQUESTS_FILE)
    week_ago = date.today() - timedelta(days=7)

    def this_week(row: dict) -> bool:
        created = row.get("created_at", "")
        try:
            return datetime.fromisoformat(created).date() >= week_ago
        except ValueError:
            return False

    subject_counts = {}
    for inquiry in inquiries:
        subject = inquiry.get("subject") or "unknown"
        subject_counts[subject] = subject_counts.get(subject, 0) + 1

    return {
        "teachers_total": len(teachers),
        "new_inquiries_this_week": sum(1 for inquiry in inquiries if this_week(inquiry)),
        "matches_created_this_week": sum(1 for match in matches if this_week(match)),
        "trial_scheduled": sum(1 for match in matches if match.get("status") == "trial_scheduled"),
        "converted": sum(1 for match in matches if match.get("status") == "converted"),
        "payment_pending": sum(1 for match in matches if match.get("payment_status") == "pending"),
        "followups_needed": len(list_followups()),
        "open_leave_requests": sum(1 for request in leave_requests if request.get("status") != "closed"),
        "google_doc_updates_needed": sum(
            1
            for request in leave_requests
            if request.get("status") != "closed" and not request.get("google_doc_updated")
        ),
        "most_requested_subject": max(subject_counts, key=subject_counts.get) if subject_counts else "",
    }


def import_csv(record_type: str, path: str) -> dict:
    """Import teachers, inquiries, or matches from a CSV file."""

    store_path = record_file(record_type)
    rows = read_json(store_path)
    imported = []
    with Path(path).open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for csv_row in reader:
            if record_type == "teachers":
                record = row_to_teacher(csv_row, rows + imported)
            elif record_type == "inquiries":
                record = row_to_inquiry(csv_row, rows + imported)
            elif record_type == "matches":
                record = row_to_match(csv_row, rows + imported)
            elif record_type == "leave_requests":
                record = row_to_leave_request(csv_row, rows + imported)
            else:
                record = row_to_faq(csv_row, rows + imported)
            imported.append(record)
    rows.extend(imported)
    write_json(store_path, rows)
    return {"record_type": record_type, "imported": len(imported), "path": str(path)}


def export_csv(record_type: str, path: str) -> dict:
    """Export one JSON store into a CSV file for spreadsheet editing/sharing."""

    rows = read_json(record_file(record_type))
    fieldnames = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field, "")) for field in fieldnames})
    return {"record_type": record_type, "exported": len(rows), "path": str(path)}


def process_inbox_lines(lines: list[str], parent_name: str = "Unknown parent") -> list[dict]:
    """Turn pasted inbox lines into inquiry records, skipping blank lines."""

    created = []
    for line in lines:
        message = line.strip()
        if not message:
            continue
        created.append(add_inquiry(parent_name=parent_name, raw_message=message))
    return created


def read_inbox_lines(from_file: str = "") -> list[str]:
    """Read inbox messages from a file or standard input."""

    if from_file:
        return Path(from_file).read_text(encoding="utf-8").splitlines()
    if sys.stdin.isatty():
        print("Paste one parent/student message per line. Press Ctrl-D when finished.")
    return sys.stdin.read().splitlines()


def print_json(data) -> None:
    """Print structured command output in a readable JSON format."""

    print(json.dumps(data, indent=2, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface for the coordination tools."""

    parser = argparse.ArgumentParser(description="Tutoring coordination agent for inquiries, teachers, matches, and follow-ups.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create empty data files.")

    teacher = sub.add_parser("add-teacher", help="Add a teacher profile.")
    teacher.add_argument("--name", required=True)
    teacher.add_argument("--subjects", required=True)
    teacher.add_argument("--levels", default="")
    teacher.add_argument("--availability", default="")
    teacher.add_argument("--rate", default="")
    teacher.add_argument("--capacity", type=int, default=1)
    teacher.add_argument("--contact", default="")
    teacher.add_argument("--notes", default="")

    extract = sub.add_parser("extract-inquiry", help="Extract structured details from a pasted message.")
    extract.add_argument("--message", required=True)

    inquiry = sub.add_parser("add-inquiry", help="Add a student/parent inquiry.")
    inquiry.add_argument("--parent", required=True)
    inquiry.add_argument("--student", default="")
    inquiry.add_argument("--subject", default="")
    inquiry.add_argument("--level", default="")
    inquiry.add_argument("--availability", default="")
    inquiry.add_argument("--frequency", default="")
    inquiry.add_argument("--message", default="")
    inquiry.add_argument("--notes", default="")

    match = sub.add_parser("match", help="Rank teacher matches for an inquiry.")
    match.add_argument("inquiry_id")
    match.add_argument("--limit", type=int, default=5)

    create = sub.add_parser("create-match", help="Create a match between an inquiry and teacher.")
    create.add_argument("inquiry_id")
    create.add_argument("teacher_id")
    create.add_argument("--status", default="teacher_contacted")

    update = sub.add_parser("update-match", help="Update a match status or next action.")
    update.add_argument("match_id")
    update.add_argument("--status")
    update.add_argument("--next-action")
    update.add_argument("--notes")

    followups = sub.add_parser("followups", help="List items needing follow-up.")
    followups.add_argument("--older-than-days", type=int, default=2)

    leave = sub.add_parser("add-leave-request", help="Add a temporary leave or absence request.")
    leave.add_argument("--parent", default="")
    leave.add_argument("--student", default="")
    leave.add_argument("--teacher", default="")
    leave.add_argument("--subject", default="")
    leave.add_argument("--date", default="")
    leave.add_argument("--reason", default="")
    leave.add_argument("--message", default="")
    leave.add_argument("--notes", default="")

    list_leave = sub.add_parser("list-leave-requests", help="List temporary leave requests.")
    list_leave.add_argument("--status", default="")

    leave_draft = sub.add_parser("draft-leave-message", help="Draft a leave message for teacher, parent, or doc note.")
    leave_draft.add_argument("kind", choices=["teacher", "parent", "doc_note"])
    leave_draft.add_argument("leave_id")

    doc_updated = sub.add_parser("mark-doc-updated", help="Mark a leave request's Google doc update as complete.")
    doc_updated.add_argument("leave_id")

    faq_add = sub.add_parser("add-faq-template", help="Add a reusable customer FAQ answer.")
    faq_add.add_argument("--topic", required=True)
    faq_add.add_argument("--keywords", required=True)
    faq_add.add_argument("--answer", required=True)

    sub.add_parser("list-faqs", help="List reusable FAQ templates.")

    faq_draft = sub.add_parser("draft-faq-reply", help="Draft a reply to a repeated customer question.")
    faq_draft.add_argument("--question", required=True)
    faq_draft.add_argument("--topic", default="")

    import_cmd = sub.add_parser("import-csv", help="Import teachers, inquiries, matches, leave requests, or FAQs from CSV.")
    import_cmd.add_argument("record_type", choices=RECORD_TYPES)
    import_cmd.add_argument("path")

    export_cmd = sub.add_parser("export-csv", help="Export teachers, inquiries, matches, leave requests, or FAQs to CSV.")
    export_cmd.add_argument("record_type", choices=RECORD_TYPES)
    export_cmd.add_argument("path")

    inbox = sub.add_parser("inbox", help="Paste or load parent messages and save each line as an inquiry.")
    inbox.add_argument("--parent", default="Unknown parent")
    inbox.add_argument("--from-file", default="")

    draft = sub.add_parser("draft", help="Draft a WeChat-style coordination message.")
    draft.add_argument("kind", choices=["ask_teacher", "parent_intro", "followup", "trial_confirm", "payment_reminder"])
    draft.add_argument("--match-id", default="")
    draft.add_argument("--inquiry-id", default="")
    draft.add_argument("--teacher-id", default="")

    sub.add_parser("weekly-report", help="Summarize the current operations picture.")
    return parser


def main() -> None:
    """Route one CLI command to the matching coordination function."""

    args = build_parser().parse_args()
    if args.command == "init":
        ensure_data_files()
        print_json({"status": "ready", "data_dir": str(DATA_DIR)})
    elif args.command == "add-teacher":
        print_json(add_teacher(args.name, args.subjects, args.levels, args.availability, args.rate, args.capacity, args.contact, args.notes))
    elif args.command == "extract-inquiry":
        print_json(extract_inquiry(args.message))
    elif args.command == "add-inquiry":
        print_json(add_inquiry(args.parent, args.student, args.subject, args.level, args.availability, args.frequency, args.message, args.notes))
    elif args.command == "match":
        print_json(find_teacher_matches(args.inquiry_id, args.limit))
    elif args.command == "create-match":
        print_json(create_match(args.inquiry_id, args.teacher_id, args.status))
    elif args.command == "update-match":
        print_json(update_match(args.match_id, args.status, args.next_action, args.notes))
    elif args.command == "followups":
        print_json(list_followups(args.older_than_days))
    elif args.command == "add-leave-request":
        print_json(add_leave_request(args.parent, args.student, args.teacher, args.subject, args.date, args.reason, args.message, args.notes))
    elif args.command == "list-leave-requests":
        print_json(list_leave_requests(args.status))
    elif args.command == "draft-leave-message":
        print(draft_leave_message(args.kind, args.leave_id))
    elif args.command == "mark-doc-updated":
        print_json(mark_doc_updated(args.leave_id))
    elif args.command == "add-faq-template":
        print_json(add_faq_template(args.topic, args.keywords, args.answer))
    elif args.command == "list-faqs":
        print_json(list_faqs())
    elif args.command == "draft-faq-reply":
        print_json(draft_faq_reply(args.question, args.topic))
    elif args.command == "import-csv":
        print_json(import_csv(args.record_type, args.path))
    elif args.command == "export-csv":
        print_json(export_csv(args.record_type, args.path))
    elif args.command == "inbox":
        print_json(process_inbox_lines(read_inbox_lines(args.from_file), args.parent))
    elif args.command == "draft":
        print(draft_message(args.kind, args.match_id, args.inquiry_id, args.teacher_id))
    elif args.command == "weekly-report":
        print_json(weekly_report())


def archive_record(record_type: str, record_id: str) -> bool:
    """Set the status of a record to 'archived'."""
    filename = ""
    if record_type == "teacher":
        filename = TEACHERS_FILE
    elif record_type == "inquiry":
        filename = INQUIRIES_FILE
    elif record_type == "match":
        filename = MATCHES_FILE
    else:
        return False

    records = read_json(filename)
    for row in records:
        if row["id"] == record_id:
            row["status"] = "archived"
            write_json(filename, records)
            return True
    return False


if __name__ == "__main__":
    main()
