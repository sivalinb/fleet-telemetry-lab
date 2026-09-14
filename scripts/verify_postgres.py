"""Verify run persistence against a disposable PostgreSQL database."""

import os

from fastapi.testclient import TestClient
from fleetlab.api import create_app
from fleetlab.runs import save_run


def main():
    url = os.environ["DATABASE_URL"]
    assert url.startswith("postgresql")
    run = {
        "id": "postgres-persistence",
        "name": "baseline",
        "state": "passed",
        "assertions": {"stored": True},
    }
    with TestClient(create_app(url)) as client:
        assert client.get("/health").json()["database"] == "postgresql"
        save_run(client.app.state.factory, run)
        assert client.get("/api/catalog").status_code == 404
    with TestClient(create_app(url)) as client:
        result = client.get("/api/runs/postgres-persistence").json()
        assert result["results"]["assertions"] == {"stored": True}
    print("PostgreSQL run storage and restart persistence: passed")


if __name__ == "__main__":
    main()
