import agent
import db
import tempfile
from pathlib import Path

tmp = tempfile.TemporaryDirectory()
agent.DATA_DIR = Path(tmp.name)
agent.ensure_data_files()

inq = agent.add_inquiry(parent_name="Parent Wang", raw_message="Eric needs math.")
print(f"inq: {inq}")
teacher = agent.add_teacher("Ms. Chen", subjects="math")
match = agent.create_match(inq["id"], teacher["id"])
print(f"match: {match}")
leaves = agent.add_leave_request(
    raw_message="Eric needs to take leave this Friday because of travel.",
    current_user={"role": "parent", "profile_id": inq["id"]}
)
print(f"leaves: {leaves}")
