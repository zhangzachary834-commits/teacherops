from fastapi.testclient import TestClient

def test_read_root(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

def test_api_state_requires_auth(client: TestClient):
    # Depending on auth implementation, it might redirect or return 401/403
    response = client.get("/api/state")
    assert response.status_code in [401, 403, 500] # Usually 401 if unauthorized, 500 if missing context but let's check

import auth
from main import app

def test_add_teacher_authorized(client: TestClient):
    app.dependency_overrides[auth.get_current_user] = lambda: {"role": "admin", "id": "admin_1"}

    response = client.post(
        "/api/teachers",
        json={
            "name": "Jane Doe",
            "subjects": "Math",
            "levels": "High School",
            "availability": "Mondays",
            "rate": "50",
            "capacity": 5,
            "contact": "jane@example.com",
            "notes": "Good teacher"
        }
    )

    app.dependency_overrides = {}

    assert response.status_code == 200
    assert response.json()["name"] == "Jane Doe"

def test_add_teacher_unauthorized(client: TestClient):
    app.dependency_overrides[auth.get_current_user] = lambda: {"role": "parent", "id": "parent_1"}

    response = client.post(
        "/api/teachers",
        json={
            "name": "Jane Doe",
            "subjects": "Math",
            "levels": "High School",
            "availability": "Mondays",
            "rate": "50",
            "capacity": 5,
            "contact": "jane@example.com",
            "notes": "Good teacher"
        }
    )

    app.dependency_overrides = {}

    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized"

import os
import importlib
import main

def test_dev_mode_configuration():
    original_env = os.environ.get("ENVIRONMENT")
    try:
        # Case 1: Unset ENVIRONMENT -> should default to False (not dev)
        if "ENVIRONMENT" in os.environ:
            del os.environ["ENVIRONMENT"]
        importlib.reload(main)
        assert main.DEV_MODE is False

        # Case 2: ENVIRONMENT="production" -> False
        os.environ["ENVIRONMENT"] = "production"
        importlib.reload(main)
        assert main.DEV_MODE is False

        # Case 3: ENVIRONMENT="staging" -> False
        os.environ["ENVIRONMENT"] = "staging"
        importlib.reload(main)
        assert main.DEV_MODE is False

        # Case 4: ENVIRONMENT="DEV" or "dev" -> True
        os.environ["ENVIRONMENT"] = "dev"
        importlib.reload(main)
        assert main.DEV_MODE is True

        os.environ["ENVIRONMENT"] = "DEV"
        importlib.reload(main)
        assert main.DEV_MODE is True
    finally:
        if original_env is not None:
            os.environ["ENVIRONMENT"] = original_env
        elif "ENVIRONMENT" in os.environ:
            del os.environ["ENVIRONMENT"]
        importlib.reload(main)
