from fastapi.testclient import TestClient

def test_read_root(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

def test_api_state_requires_auth(client: TestClient):
    # Depending on auth implementation, it might redirect or return 401/403
    response = client.get("/api/state")
    assert response.status_code in [401, 403, 500] # Usually 401 if unauthorized, 500 if missing context but let's check
