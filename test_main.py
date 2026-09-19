from fastapi.testclient import TestClient

def test_read_root(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

def test_api_state_requires_auth(client: TestClient):
    response = client.get("/api/state")
<<<<<<< HEAD
    assert response.status_code in [401, 403, 500]

def test_dev_impersonate_test_accounts(client: TestClient):
    # Test Admin impersonation
    res_admin = client.post("/api/dev/impersonate?account_id=admin")
    assert res_admin.status_code == 200
    admin_data = res_admin.json()
    assert admin_data["role"] == "admin"
    assert "access_token" in admin_data

    # Test Parent Carol impersonation (Parent Carol & Student George)
    res_parent = client.post("/api/dev/impersonate?account_id=parent_carol")
    assert res_parent.status_code == 200
    parent_data = res_parent.json()
    assert parent_data["role"] == "parent"
    assert parent_data["profile_id"] == "i1"

    # Verify Carol's state data returns her profile info for auto-filling
    carol_token = parent_data["access_token"]
    carol_state_res = client.get("/api/state", headers={"Authorization": f"Bearer {carol_token}"})
    assert carol_state_res.status_code == 200
    carol_state = carol_state_res.json()
    assert carol_state["user_profile"]["parent_name"] == "Carol"
    assert carol_state["user_profile"]["student_name"] == "George"

    # Test Student Eric impersonation
    res_student = client.post("/api/dev/impersonate?account_id=student_eric")
    assert res_student.status_code == 200
    student_data = res_student.json()
    assert student_data["role"] == "parent"
    assert student_data["profile_id"] == "i2"

    # Verify student state data
    token = student_data["access_token"]
    state_res = client.get("/api/state", headers={"Authorization": f"Bearer {token}"})
    assert state_res.status_code == 200
    state_data = state_res.json()
    assert state_data["role"] == "parent"
    assert state_data["profile_id"] == "i2"
    assert len(state_data["inquiries"]) == 1
    assert state_data["inquiries"][0]["student_name"] == "Eric"

def test_dev_restart_route(client: TestClient):
    res = client.post("/api/dev/restart")
    assert res.status_code == 200
    assert res.json()["status"] == "success"
=======
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
>>>>>>> 444cefd9659a1fb20934eb236c37232fec559141
