# Tutor Coordination Agent

A local operations assistant for an informal tutoring hub: teacher profiles, parent/student inquiries, teacher matching, follow-up tracking, WeChat-style message drafting, and weekly reporting.

This first version is intentionally human-in-the-loop. It does not send WeChat messages or pretend to replace mom's judgment. It organizes the logistics so she can spend less energy holding every loose thread in her head.

## Setup

```sh
cd ~/Documents/GitHub/teacherops
pip3 install fastapi uvicorn
python3 agent.py init
```

## Web Interface

Run the local API server:

```sh
cd ~/Documents/GitHub/teacherops
uvicorn main:app --host 127.0.0.1 --port 8765 --reload
```

Then open:

```text
http://127.0.0.1:8765/docs
```

The web interface can add teachers, add inquiries, process pasted inbox messages, find teacher matches, create match records, show follow-ups, and draft coordination messages.
It also includes temporary leave requests and repeated customer FAQ replies.

Data is stored locally in SQLite:

- `data/tutor.db`

## Example Flow

Add teachers:

```sh
python3 agent.py add-teacher \
  --name "Ms. Chen" \
  --subjects "math" \
  --levels "grade 6, grade 7, grade 8" \
  --availability "tuesday after 6, friday after 6" \
  --rate "$40/hr" \
  --capacity 2
```

Extract a pasted parent message:

```sh
python3 agent.py extract-inquiry \
  --message "My son is grade 8 and needs math twice a week, Tuesday and Friday after 6."
```

Save the inquiry:

```sh
python3 agent.py add-inquiry \
  --parent "Parent Wang" \
  --student "Eric" \
  --message "My son is grade 8 and needs math twice a week, Tuesday and Friday after 6."
```

Find matching teachers:

```sh
python3 agent.py match I0001
```

Create a match:

```sh
python3 agent.py create-match I0001 T0001
```

Draft a message:

```sh
python3 agent.py draft ask_teacher --match-id M0001
```

Handle a temporary leave request:

```sh
python3 agent.py add-leave-request \
  --parent "Parent Wang" \
  --student "Eric" \
  --teacher "Ms. Chen" \
  --subject "math" \
  --message "Eric needs to take leave this Friday because of travel."
```

Draft leave notices:

```sh
python3 agent.py draft-leave-message teacher L0001
python3 agent.py draft-leave-message parent L0001
python3 agent.py draft-leave-message doc_note L0001
```

Mark the Google doc update as done:

```sh
python3 agent.py mark-doc-updated L0001
```

Draft a repeated customer FAQ reply:

```sh
python3 agent.py draft-faq-reply \
  --question "How much is math tutoring and can we do a trial class?"
```

Check follow-ups:

```sh
python3 agent.py followups
```

Import teachers, inquiries, or matches from CSV:

```sh
python3 agent.py import-csv teachers teachers.csv
```

Export records back to CSV:

```sh
python3 agent.py export-csv inquiries inquiries.csv
```

Paste raw messages into the inbox, one per line:

```sh
python3 agent.py inbox --parent "Unknown parent"
```

Or load inbox messages from a text file:

```sh
python3 agent.py inbox --parent "Parent Wang" --from-file pasted_messages.txt
```

Generate a weekly report:

```sh
python3 agent.py weekly-report
```

## CSV Columns

Supported record types are `teachers`, `inquiries`, and `matches`.

Teacher CSVs can include:

```text
id,name,subjects,levels,availability,rate,capacity,active_matches,contact,notes,created_at,updated_at
```

Inquiry CSVs can include:

```text
id,parent_name,parent,student_name,student,subject,level,availability,frequency,raw_message,message,notes,status,next_action,last_contacted,created_at,updated_at
```

Match CSVs can include:

```text
id,inquiry_id,teacher_id,parent_name,student_name,teacher_name,subject,status,next_action,last_contacted,payment_status,notes,created_at,updated_at
```

Leave request CSVs can include:

```text
id,parent_name,parent,student_name,student,teacher_name,teacher,subject,class_date,date,reason,raw_message,message,status,teacher_notified,parent_confirmed,google_doc_updated,next_action,notes,created_at,updated_at
```

FAQ CSVs can include:

```text
id,topic,keywords,answer,created_at,updated_at
```

List-like fields such as `subjects`, `levels`, and `availability` may use commas, semicolons, or slashes inside a cell.

## Current Thesis

The core object is not a chatbot message. The core object is a tutoring match:

- parent/student need
- teacher fit
- schedule fit
- leave or absence requests
- repeated customer questions
- trial status
- follow-up status
- payment status
- next action

That makes the agent useful before it becomes fancy.

## Next Increments

- Add lesson package tracking: lessons purchased, lessons used, renewal warning.
- Add Chinese / bilingual FAQ and leave-message templates.
- Add actual Google Sheets API integration for class-record updates.
- Add an optional LLM layer that calls these deterministic tools rather than improvising over raw data.
