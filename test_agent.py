import json
import tempfile
import unittest
import csv
from pathlib import Path

import agent


class TutorCoordinationTests(unittest.TestCase):
    """Regression tests for the tutoring coordination workflow."""

    def setUp(self):
        """Redirect the agent's JSON stores into a temporary test directory."""

        self.tmp = tempfile.TemporaryDirectory()
        self.original_data_dir = agent.DATA_DIR
        self.original_teachers = agent.TEACHERS_FILE
        self.original_inquiries = agent.INQUIRIES_FILE
        self.original_matches = agent.MATCHES_FILE
        self.original_leave_requests = agent.LEAVE_REQUESTS_FILE
        self.original_faqs = agent.FAQS_FILE

        agent.DATA_DIR = Path(self.tmp.name)
        agent.TEACHERS_FILE = agent.DATA_DIR / "teachers.json"
        agent.INQUIRIES_FILE = agent.DATA_DIR / "inquiries.json"
        agent.MATCHES_FILE = agent.DATA_DIR / "matches.json"
        agent.LEAVE_REQUESTS_FILE = agent.DATA_DIR / "leave_requests.json"
        agent.FAQS_FILE = agent.DATA_DIR / "faqs.json"
        agent.ensure_data_files()

    def tearDown(self):
        """Restore the real data paths after each test."""

        agent.DATA_DIR = self.original_data_dir
        agent.TEACHERS_FILE = self.original_teachers
        agent.INQUIRIES_FILE = self.original_inquiries
        agent.MATCHES_FILE = self.original_matches
        agent.LEAVE_REQUESTS_FILE = self.original_leave_requests
        agent.FAQS_FILE = self.original_faqs
        self.tmp.cleanup()

    def test_extract_inquiry_from_parent_message(self):
        """A pasted parent message should become structured inquiry fields."""

        extracted = agent.extract_inquiry(
            "My son is grade 8 and needs math twice a week, Tuesday and Friday after 6."
        )

        self.assertEqual(extracted["subject"], "math")
        self.assertEqual(extracted["level"], "grade 8")
        self.assertEqual(extracted["frequency"], "twice a week")
        self.assertIn("tuesday", " ".join(extracted["availability"]))

    def test_teacher_matching_ranks_best_fit_first(self):
        """Teacher matching should rank the strongest subject/schedule fit first."""

        strong = agent.add_teacher(
            "Ms. Chen",
            subjects="math",
            levels="grade 6, grade 7, grade 8",
            availability="tuesday after 6, friday after 6",
            rate="$40/hr",
            capacity=2,
        )
        agent.add_teacher(
            "Mr. Li",
            subjects="english",
            levels="grade 8",
            availability="saturday",
            rate="$35/hr",
            capacity=2,
        )
        inquiry = agent.add_inquiry(
            parent_name="Parent Wang",
            student_name="Eric",
            raw_message="Grade 8 math twice a week Tuesday and Friday after 6.",
        )

        matches = agent.find_teacher_matches(inquiry["id"])

        self.assertEqual(matches[0]["teacher_id"], strong["id"])
        self.assertGreater(matches[0]["score"], matches[1]["score"])

    def test_create_match_draft_and_followups(self):
        """Created matches should support message drafting and follow-up detection."""

        teacher = agent.add_teacher("Ms. Chen", subjects="math", levels="grade 8", availability="tuesday", capacity=1)
        inquiry = agent.add_inquiry(parent_name="Parent Wang", student_name="Eric", subject="math", level="grade 8")
        match = agent.create_match(inquiry["id"], teacher["id"])

        draft = agent.draft_message("ask_teacher", match_id=match["id"])
        self.assertIn("Ms. Chen", draft)
        self.assertIn("Eric", draft)

        followups = agent.list_followups(older_than_days=0)
        self.assertTrue(any(item["id"] == match["id"] for item in followups))

    def test_weekly_report_counts_current_records(self):
        """The weekly report should count current operational records."""

        teacher = agent.add_teacher("Ms. Chen", subjects="math")
        inquiry = agent.add_inquiry(parent_name="Parent Wang", subject="math")
        agent.create_match(inquiry["id"], teacher["id"], status="trial_scheduled")

        report = agent.weekly_report()

        self.assertEqual(report["teachers_total"], 1)
        self.assertEqual(report["new_inquiries_this_week"], 1)
        self.assertEqual(report["trial_scheduled"], 1)
        self.assertEqual(report["most_requested_subject"], "math")

    def test_csv_import_and_export_teachers(self):
        """Teacher CSV files should import into JSON and export back to spreadsheets."""

        csv_path = Path(self.tmp.name) / "teachers.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=["name", "subjects", "levels", "availability", "rate", "capacity"])
            writer.writeheader()
            writer.writerow({
                "name": "Ms. Chen",
                "subjects": "math; algebra",
                "levels": "grade 8",
                "availability": "tuesday after 6",
                "rate": "$40/hr",
                "capacity": "2",
            })

        summary = agent.import_csv("teachers", str(csv_path))
        teachers = agent.read_json(agent.TEACHERS_FILE)
        export_path = Path(self.tmp.name) / "exported_teachers.csv"
        export_summary = agent.export_csv("teachers", str(export_path))

        self.assertEqual(summary["imported"], 1)
        self.assertEqual(teachers[0]["subjects"], ["math", "algebra"])
        self.assertEqual(teachers[0]["capacity"], 2)
        self.assertEqual(export_summary["exported"], 1)
        self.assertIn("Ms. Chen", export_path.read_text(encoding="utf-8"))

    def test_inbox_lines_create_extracted_inquiries(self):
        """Inbox lines should become normal inquiry records with extracted fields."""

        created = agent.process_inbox_lines([
            "Grade 8 math Tuesday after 6",
            "",
            "Need SAT test prep on weekends",
        ], parent_name="Inbox Parent")

        inquiries = agent.read_json(agent.INQUIRIES_FILE)

        self.assertEqual(len(created), 2)
        self.assertEqual(len(inquiries), 2)
        self.assertEqual(inquiries[0]["parent_name"], "Inbox Parent")
        self.assertEqual(inquiries[0]["subject"], "math")
        self.assertEqual(inquiries[1]["subject"], "test prep")

    def test_leave_request_tracks_doc_update_and_drafts_messages(self):
        """Leave requests should extract date info, draft messages, and track doc updates."""

        leave = agent.add_leave_request(
            parent_name="Parent Wang",
            student_name="Eric",
            teacher_name="Ms. Chen",
            subject="math",
            raw_message="Eric needs to take leave this Friday because of travel.",
        )
        teacher_message = agent.draft_leave_message("teacher", leave["id"])
        doc_note = agent.draft_leave_message("doc_note", leave["id"])
        updated = agent.mark_doc_updated(leave["id"])

        self.assertEqual(leave["student_name"], "Eric")
        self.assertIn("Ms. Chen", teacher_message)
        self.assertIn("Eric", doc_note)
        self.assertTrue(updated["google_doc_updated"])

    def test_faq_reply_uses_matching_template(self):
        """Repeated customer questions should match FAQ templates and return reusable replies."""

        reply = agent.draft_faq_reply("How much does math tutoring cost and can we do a trial?")

        self.assertIn(reply["topic"], {"pricing", "trial_class"})
        self.assertTrue(reply["matched"])
        self.assertTrue(reply["reply"])

    def test_init_creates_json_lists(self):
        """Initial data files should be empty JSON lists."""

        for path in [agent.TEACHERS_FILE, agent.INQUIRIES_FILE, agent.MATCHES_FILE, agent.LEAVE_REQUESTS_FILE]:
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), [])
        self.assertGreater(len(json.loads(agent.FAQS_FILE.read_text(encoding="utf-8"))), 0)


if __name__ == "__main__":
    unittest.main()
