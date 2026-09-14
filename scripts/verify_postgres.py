"""Test the PostgreSQL path against an explicitly configured disposable CI database."""

import os
from fastapi.testclient import TestClient
from fleetlab.api import create_app


def main():
    url = os.environ["DATABASE_URL"]
    assert url.startswith("postgresql"), "This check requires PostgreSQL"
    with TestClient(create_app(url)) as client:
        assert client.get("/health").json()["database"] == "postgresql"
        assert len(client.get("/api/catalog").json()["entities"]) == 27
        assert (
            client.post("/api/catalog/scenarios/ownership-conflict").status_code == 200
        )
        assert any(
            i["code"] == "owner_conflict"
            for e in client.get("/api/catalog").json()["entities"]
            for i in e["issues"]
        )
        assert len(client.get("/api/impact/node:FTL-A11").json()["services"]) == 4
        assert client.post("/api/catalog/scenarios/refresh").status_code == 200
    with TestClient(create_app(url)) as client:
        assert not any(
            e["issues"] for e in client.get("/api/catalog").json()["entities"]
        )
        assert client.get("/api/audit").json()
    print(
        "PostgreSQL seed, reconciliation, conflict, dependency lookup, and restart persistence: passed"
    )


if __name__ == "__main__":
    main()
