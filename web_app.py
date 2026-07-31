import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import agent


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
PAGE_FILES = {
    "/home": WEB_DIR / "home.html",
    "/home.html": WEB_DIR / "home.html",
    "/parents.html": WEB_DIR / "parents.html",
    "/teachers.html": WEB_DIR / "teachers.html",
    "/admin.html": WEB_DIR / "admin.html",
}
STATIC_FILES = {
    "/shared.css": WEB_DIR / "shared.css",
    "/shared.js": WEB_DIR / "shared.js",
}


def redirect(handler: BaseHTTPRequestHandler, location: str) -> None:
    """Send the browser to another page."""

    handler.send_response(302)
    handler.send_header("Location", location)
    handler.end_headers()


def normalize_path(path: str) -> str:
    """Make browser page routes tolerant of capitalization and trailing slashes."""

    normalized = path.lower()
    if normalized != "/" and normalized.endswith("/"):
        normalized = normalized.rstrip("/")
    return normalized


def serve_file(handler: BaseHTTPRequestHandler, file_path: Path, content_type: str) -> None:
    """Send a static file from the web directory."""

    body = file_path.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def json_response(handler: BaseHTTPRequestHandler, data, status: int = 200) -> None:
    """Send a JSON API response."""

    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def text_response(handler: BaseHTTPRequestHandler, text: str, content_type: str = "text/html; charset=utf-8", status: int = 200) -> None:
    """Send a text or HTML response."""

    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    """Read and parse the request JSON body, returning an empty dict for blank bodies."""

    length = int(handler.headers.get("Content-Length", "0"))
    if length == 0:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def app_state() -> dict:
    """Collect the current dashboard state from the coordination data stores."""

    return {
        "summary": agent.weekly_report(),
        "followups": agent.list_followups(),
        "teachers": agent.read_json(agent.TEACHERS_FILE),
        "inquiries": agent.read_json(agent.INQUIRIES_FILE),
        "matches": agent.read_json(agent.MATCHES_FILE),
        "leave_requests": agent.read_json(agent.LEAVE_REQUESTS_FILE),
        "faqs": agent.read_json(agent.FAQS_FILE),
    }


class TutorWebHandler(BaseHTTPRequestHandler):
    """Small HTTP API and static-file server for the local web interface."""

    def log_message(self, format, *args):
        """Keep the local server quiet unless Python raises an actual error."""

    def do_GET(self) -> None:
        """Route GET requests for the app shell and read-only API endpoints."""

        parsed = urlparse(self.path)
        path = normalize_path(parsed.path)
        if path in ("/", "/index.html"):
            redirect(self, "/home")
            return
        if path in PAGE_FILES:
            serve_file(self, PAGE_FILES[path], "text/html; charset=utf-8")
            return
        if path in STATIC_FILES:
            content_type = "text/css; charset=utf-8" if path.endswith(".css") else "application/javascript; charset=utf-8"
            serve_file(self, STATIC_FILES[path], content_type)
            return
        if path == "/api/state":
            json_response(self, app_state())
            return
        if path == "/api/matches":
            params = parse_qs(parsed.query)
            inquiry_id = params.get("inquiry_id", [""])[0]
            if not inquiry_id:
                json_response(self, {"error": "Missing inquiry_id."}, status=400)
                return
            json_response(self, agent.find_teacher_matches(inquiry_id))
            return
        text_response(self, "Not found", "text/plain; charset=utf-8", status=404)

    def do_POST(self) -> None:
        """Route POST requests that create records, draft messages, or update matches."""

        try:
            payload = read_json_body(self)
            if self.path == "/api/teachers":
                result = agent.add_teacher(
                    payload.get("name", ""),
                    payload.get("subjects", ""),
                    payload.get("levels", ""),
                    payload.get("availability", ""),
                    payload.get("rate", ""),
                    int(payload.get("capacity") or 1),
                    payload.get("contact", ""),
                    payload.get("notes", ""),
                )
                json_response(self, result)
                return
            if self.path == "/api/inquiries":
                result = agent.add_inquiry(
                    payload.get("parent_name", ""),
                    payload.get("student_name", ""),
                    payload.get("subject", ""),
                    payload.get("level", ""),
                    payload.get("availability", ""),
                    payload.get("frequency", ""),
                    payload.get("raw_message", ""),
                    payload.get("notes", ""),
                )
                json_response(self, result)
                return
            if self.path == "/api/inbox":
                lines = payload.get("messages", "").splitlines()
                result = agent.process_inbox_lines(lines, payload.get("parent_name", "Unknown parent"))
                json_response(self, result)
                return
            if self.path == "/api/create-match":
                result = agent.create_match(
                    payload.get("inquiry_id", ""),
                    payload.get("teacher_id", ""),
                    payload.get("status", "teacher_contacted"),
                )
                json_response(self, result)
                return
            if self.path == "/api/update-match":
                result = agent.update_match(
                    payload.get("match_id", ""),
                    payload.get("status") or None,
                    payload.get("next_action") if "next_action" in payload else None,
                    payload.get("notes") if "notes" in payload else None,
                )
                json_response(self, result)
                return
            if self.path == "/api/draft":
                result = agent.draft_message(
                    payload.get("kind", ""),
                    payload.get("match_id", ""),
                    payload.get("inquiry_id", ""),
                    payload.get("teacher_id", ""),
                )
                json_response(self, {"message": result})
                return
            if self.path == "/api/leave-requests":
                result = agent.add_leave_request(
                    payload.get("parent_name", ""),
                    payload.get("student_name", ""),
                    payload.get("teacher_name", ""),
                    payload.get("subject", ""),
                    payload.get("class_date", ""),
                    payload.get("reason", ""),
                    payload.get("raw_message", ""),
                    payload.get("notes", ""),
                )
                json_response(self, result)
                return
            if self.path == "/api/draft-leave":
                result = agent.draft_leave_message(payload.get("kind", ""), payload.get("leave_id", ""))
                json_response(self, {"message": result})
                return
            if self.path == "/api/mark-doc-updated":
                result = agent.mark_doc_updated(payload.get("leave_id", ""))
                json_response(self, result)
                return
            if self.path == "/api/mark-teacher-notified":
                result = agent.mark_teacher_notified(payload.get("leave_id", ""))
                json_response(self, result)
                return
            if self.path == "/api/mark-parent-confirmed":
                result = agent.mark_parent_confirmed(payload.get("leave_id", ""))
                json_response(self, result)
                return
            if self.path == "/api/draft-faq":
                result = agent.draft_faq_reply(payload.get("question", ""), payload.get("topic", ""))
                json_response(self, result)
                return
            if self.path == "/api/faqs":
                result = agent.add_faq_template(
                    payload.get("topic", ""),
                    payload.get("keywords", ""),
                    payload.get("answer", ""),
                )
                json_response(self, result)
                return
            json_response(self, {"error": "Not found."}, status=404)
        except Exception as error:
            json_response(self, {"error": str(error)}, status=400)


def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Start the local web interface server."""

    agent.ensure_data_files()
    server = ThreadingHTTPServer((host, port), TutorWebHandler)
    print(f"Tutor Coordination Agent web UI: http://{host}:{port}")
    server.serve_forever()


def main() -> None:
    """Parse server options and run the local web interface."""

    parser = argparse.ArgumentParser(description="Run the Tutor Coordination Agent web interface.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    run_server(args.host, args.port)


if __name__ == "__main__":
    main()
