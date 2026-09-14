import asyncio
import json
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from fleetlab.api import create_app
from fleetlab.jobs import ExperimentManager, BusyError
from fleetlab.models import make_database
from fleetlab.runs import save_run, validate_run
from fleetlab.isolation import isolated_config, run_isolated, allocate_ports
from fleetlab.reports import html_report, public_result, queue_svg, ROOT
from fleetlab.telemetry import query_prom


@pytest.fixture
def database(tmp_path):
    engine, factory = make_database("sqlite:///" + str(tmp_path / "runs.db"))
    yield factory
    engine.dispose()


@pytest.mark.parametrize(
    "name,count",
    [("unknown", 12), ("baseline", 0), ("baseline", 41), ("durable-crash", 7)],
)
def test_invalid_run_has_no_side_effects(name, count):
    with pytest.raises(ValueError):
        validate_run(name, count)


def test_job_serialization_cancellation_and_reuse(database):
    async def check():
        manager = ExperimentManager(database)

        async def blocked(*args):
            await asyncio.sleep(3600)

        manager.dispatch = blocked
        first = await manager.start("baseline", 8)
        with pytest.raises(BusyError):
            await manager.start("baseline", 8)
        cancelled = await manager.cancel(first["id"])
        assert cancelled["state"] == "cancelled"
        second = await manager.start("baseline", 8)
        await manager.close()
        assert manager.get(second["id"])["state"] == "cancelled"
        assert not manager.tasks and not manager.lock.locked()

    asyncio.run(check())


def test_uncaught_job_failure_is_persisted_and_unlocks(database):
    async def check():
        manager = ExperimentManager(database)

        async def broken(*args):
            raise RuntimeError("secret detail must not leak")

        manager.dispatch = broken
        record = await manager.start("baseline", 8)
        await asyncio.gather(*manager.tasks.values(), return_exceptions=True)
        record = manager.get(record["id"])
        assert record["state"] == "failed"
        assert "secret" not in str(record)
        assert not manager.lock.locked()

    asyncio.run(check())


def test_restart_marks_unfinished_runs_interrupted(database):
    save_run(database, {"id": "a", "name": "baseline", "state": "running"})
    save_run(database, {"id": "b", "name": "baseline", "state": "passed"})
    manager = ExperimentManager(database)
    assert manager.get("a")["state"] == "interrupted"
    assert manager.get("b")["state"] == "passed"


def test_missing_collector_fails_without_claiming_recovery(database, monkeypatch):
    monkeypatch.setenv("LAB_COLLECTOR_BINARY", "/nonexistent/collector")
    result = asyncio.run(run_isolated(database, "durable-crash", 8))
    assert result["state"] == "failed" and not result["passed"]
    assert "Collector binary missing" in result["errors"][0]
    assert result["cleanup"] == {"owned_processes": 0, "all_exited": True}


@pytest.mark.parametrize(
    "name,persistent",
    [
        ("durable-crash", True),
        ("volatile-crash", False),
        ("retry-exhaustion", True),
        ("queue-saturation", True),
    ],
)
def test_isolated_config_loss_boundaries(tmp_path, name, persistent):
    config = isolated_config(tmp_path, [14318, 14133, 14888, 14200], name, 12)
    assert ("file_storage" in config["extensions"]) == persistent
    assert "processors" not in config
    for exporter in config["exporters"].values():
        queue = exporter["sending_queue"]
        assert ("storage" in queue) == persistent
        assert queue["queue_size"] == (4 if name == "queue-saturation" else 100)
        assert exporter["retry_on_failure"]["max_elapsed_time"] == (
            "1s" if name == "retry-exhaustion" else "30s"
        )


def test_ports_are_distinct():
    assert len(set(allocate_ports(4))) == 4


@pytest.mark.parametrize("value", ["NaN", "+Inf", "-Inf"])
def test_nonfinite_prometheus_value_is_unavailable(value):
    async def check():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(
                    200,
                    json={
                        "status": "success",
                        "data": {"result": [{"value": [0, value]}]},
                    },
                )
            )
        ) as client:
            assert await query_prom(client, "example") is None

    asyncio.run(check())


def test_report_escapes_content_and_preserves_zero_queue():
    result = {
        "id": "a" * 32,
        "name": "volatile-crash",
        "state": "passed",
        "phase": "<script>alert(1)</script>",
        "scope": "<img src=x onerror=alert(1)>",
        "samples": [{"elapsed_s": 2, "collector": {"queued_batches": 0}}],
        "assertions": {"safe": True},
    }
    report = html_report(result)
    assert "<script>" not in report and "<img src=x" not in report
    assert "&lt;img" in report and "expected loss" in report
    assert "Queue peak: 0" in queue_svg(result)
    assert "No queue samples" in queue_svg({})
    assert (
        public_result({"path": str(ROOT / "observability/collector.yaml")})["path"]
        == "observability/collector.yaml"
    )


def test_async_run_api_reports_busy_cancel_and_validation(tmp_path):
    app = create_app("sqlite:///" + str(tmp_path / "api.db"))

    async def blocked(*args):
        await asyncio.sleep(3600)

    app.state.experiments.dispatch = blocked
    with TestClient(app) as client:
        assert len(client.get("/api/scenarios").json()) == 9
        assert (
            client.post(
                "/api/runs", json={"name": "durable-crash", "count": 2}
            ).status_code
            == 422
        )
        first = client.post("/api/runs", json={"name": "baseline", "count": 8})
        assert first.status_code == 202
        path = "/api/runs/" + first.json()["id"]
        assert client.get(path).json()["state"] == "queued"
        assert client.post("/api/runs", json={"name": "baseline"}).status_code == 409
        assert client.post(path + "/cancel").json()["state"] == "cancelled"
        for extension in ["html", "json"]:
            report = client.get(path + "/report", params={"format": extension})
            assert (
                report.status_code == 200
                and "attachment" in report.headers["content-disposition"]
            )
        assert client.get(path + "/report?format=exe").status_code == 422
        assert client.get("/api/runs/missing").status_code == 404
        assert client.post("/api/runs/missing/cancel").status_code == 404


def test_gradio_renders_real_evidence_and_expected_loss(monkeypatch, tmp_path):
    from fleetlab import demo

    monkeypatch.setattr(demo, "REPORTS", tmp_path)
    result = {
        "id": "f" * 32,
        "name": "volatile-crash",
        "state": "passed",
        "requested": 8,
        "completed": 8,
        "trace_ids": [],
        "event_ids": [],
        "assertions": {"loss_observed": True},
        "delivery": {
            "traces_received": 0,
            "traces_sent": 8,
            "unique_logs_received": 0,
            "logs_sent": 8,
            "missing_trace_ids": [],
            "missing_event_ids": [],
        },
    }
    rendered = demo.render_result(result)
    assert "Expected loss" in rendered[0] and "Hypothesis verified" in rendered[0]
    assert len(rendered[-1]) == 2
    assert (
        json.loads(Path(rendered[-1][1]).read_text())["delivery"]["traces_received"]
        == 0
    )
    assert rendered[2].data[1].y == (0, 0)


def test_gradio_build_and_offline_status(monkeypatch):
    from fleetlab import demo

    app = demo.build_demo()
    assert len([c for c in app.config["components"] if c["type"] == "tabitem"]) == 4

    async def offline(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(demo, "api", offline)
    assert "API unavailable" in asyncio.run(demo.health_view())
