# Changelog: Program Audit and Patch

Date: 2026-08-04

## Overview
A comprehensive audit of the codebase was performed following a partial migration from a JSON-based file storage system to a SQLite database. Several critical issues were identified and patched across the FastAPI backend, the core agent logic, and the unit test suite.

## Fixes and Improvements

### 1. Fixed Broken State Endpoints (`main.py`)
- **Issue**: The application state endpoint (`/api/state`) was failing because it was still referencing outdated JSON file constants (e.g., `agent.TEACHERS_FILE`) and the obsolete `agent.read_json` method.
- **Fix**: Updated `main.py` to correctly query the new SQLite tables using the refactored `agent.read_records(agent.TEACHERS_TABLE)` and related table constants.

### 2. Fixed Database Crashing Bugs (`agent.py`)
- **Issue**: The SQLite migration introduced `NameError` bugs inside the database access functions (`write_records` and `read_records`) due to undefined `table` and `path` variables. Any attempt to add an inquiry, teacher, match, or leave request would crash the application.
- **Fix**: Corrected the function signatures and variable references within `read_records` and `write_records` to properly accept and use the `table` string variable for all queries.

### 3. Fixed Student Name Extraction Fallback (`agent.py`)
- **Issue**: When the AI extraction failed or a student name wasn't explicitly provided, the fallback regex function (`infer_student_name`) successfully parsed the name, but `add_inquiry` was inadvertently discarding this fallback data.
- **Fix**: Patched `add_inquiry` and `extract_inquiry` to ensure that the student name correctly falls back to the regex-inferred name and is successfully saved to the database.

### 4. Repaired Unit Test Suite (`test_agent.py`)
- **Issue**: The entire unit test suite was broken because it attempted to mock nonexistent JSON files and called a function (`add_leave_request`) using an outdated signature.
- **Fix**: Refactored the test suite to natively use a temporary SQLite test database (`tempfile.TemporaryDirectory()`). Updated the `add_leave_request` test to properly seed prerequisite data (inquiry, teacher, match) and call the function with the new `current_user` dictionary signature.
- **Result**: All 9 unit tests now pass successfully.
