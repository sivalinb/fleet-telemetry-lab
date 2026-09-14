from fastapi.testclient import TestClient
from fleetlab import relay
import httpx


def test_fault_is_bounded_and_recovers(monkeypatch):
    monkeypatch.delenv("LAB_API_TOKEN", raising=False)
    clock = [100.0]
    monkeypatch.setattr(relay.time, "time", lambda: clock[0])
    with TestClient(relay.app) as c:
        assert c.post("/control", json={"seconds": 46}).status_code == 422
        assert c.post("/control", json={"seconds": 8}).json()["remaining_seconds"] == 8
        assert c.post("/v1/traces", content=b"fixture").status_code == 503
        clock[0] = 109
        assert c.get("/health").json()["remaining_seconds"] == 0
        assert c.post("/v1/unknown", content=b"fixture").status_code == 404


def test_control_token_and_size(monkeypatch):
    monkeypatch.setenv("LAB_API_TOKEN", "test-token")
    with TestClient(relay.app) as c:
        assert c.post("/control", json={"seconds": 0}).status_code == 401
        assert (
            c.post(
                "/control",
                json={"seconds": 0},
                headers={"Authorization": "Bearer test-token"},
            ).status_code
            == 200
        )
        assert (
            c.post("/v1/logs", content=b"x" * (4 * 1024 * 1024 + 1)).status_code == 413
        )


def test_relay_preserves_otlp_payload_and_backend_error(monkeypatch):
    original = httpx.AsyncClient
    received = []

    def backend(request):
        received.append(request)
        return httpx.Response(429, content=b"backend throttled")

    monkeypatch.setattr(
        relay.httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(backend), **kw),
    )
    monkeypatch.setitem(relay.state, "fail_until", 0)
    with TestClient(relay.app) as c:
        r = c.post(
            "/v1/logs",
            content=b"otlp-fixture",
            headers={"content-type": "application/x-protobuf"},
        )
        assert r.status_code == 429 and r.content == b"backend throttled"
        assert received[0].url.path == "/otlp/v1/logs"
        assert received[0].content == b"otlp-fixture"


def test_backend_network_failure_becomes_retryable_503(monkeypatch):
    original = httpx.AsyncClient

    def backend(request):
        raise httpx.ConnectError("backend down", request=request)

    monkeypatch.setattr(
        relay.httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(backend), **kw),
    )
    monkeypatch.setitem(relay.state, "fail_until", 0)
    with TestClient(relay.app) as c:
        assert c.post("/v1/traces", content=b"x").status_code == 503
