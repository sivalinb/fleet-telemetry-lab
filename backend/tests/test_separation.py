from fastapi.testclient import TestClient
from fleetlab.api import create_app
from fleetlab.models import Base


def test_telemetry_has_only_run_storage_and_routes(tmp_path):
    with TestClient(create_app("sqlite:///" + str(tmp_path / "runs.db"))) as client:
        assert client.get("/api/catalog").status_code == 404
        assert client.post("/api/sources/kubernetes/sync", json={}).status_code == 404
        assert len(client.get("/api/scenarios").json()) == 9
        assert set(Base.metadata.tables) == {"experiments"}
