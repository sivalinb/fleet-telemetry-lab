import pytest
from fastapi.testclient import TestClient
from fleetlab.api import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("LAB_API_TOKEN", raising=False)
    app = create_app("sqlite:///" + str(tmp_path / "api.db"))
    with TestClient(app) as c:
        yield c


def test_token_enforcement(client, monkeypatch):
    monkeypatch.setenv("LAB_API_TOKEN", "test-token")
    assert client.get("/api/scenarios").status_code == 401
    assert (
        client.get(
            "/api/scenarios", headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/api/scenarios", headers={"Authorization": "Bearer test-token"}
        ).status_code
        == 200
    )
    assert client.get("/health").status_code == 200


def test_request_size_limit(client):
    assert (
        client.post("/api/contract", content="x" * (4 * 1024 * 1024 + 1)).status_code
        == 413
    )


def test_invalid_scenario_and_experiment_are_rejected(client):
    assert (
        client.post(
            "/api/experiments", json={"name": "unknown", "count": 4}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/experiments", json={"name": "baseline", "count": 100}
        ).status_code
        == 422
    )


def test_instrumentation_contract_endpoint(client):
    r = client.post(
        "/api/contract", json={"resource": {}, "attributes": {"request_id": "x"}}
    )
    assert r.status_code == 200 and not r.json()["valid"]
