"""Crash an isolated real Collector with queued data; verify its WAL replays.

Only kills subprocesses created by this script. Existing application processes are untouched.
Uses a second Collector + relay on separate loopback ports and the running Loki/Jaeger.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import httpx
import yaml
from fleetlab.telemetry import parse_collector_metrics

ROOT = Path(__file__).resolve().parents[1]


def wait_ready(client, url):
    for _ in range(100):
        try:
            if client.get(url).is_success:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise RuntimeError("Service did not start: " + url)


def main():
    run_id = uuid4().hex
    traces = [uuid4().hex for _ in range(20)]
    token = os.getenv("LAB_API_TOKEN")
    auth = {"Authorization": "Bearer " + token} if token else {}
    processes = []
    with (
        tempfile.TemporaryDirectory(prefix="fleetlab-recovery-") as tmp,
        httpx.Client(timeout=5) as client,
    ):
        directory = Path(tmp)
        storage = directory / "wal"
        storage.mkdir()
        config = yaml.safe_load((ROOT / "observability/collector.yaml").read_text())
        config["extensions"]["health_check"]["endpoint"] = "127.0.0.1:23133"
        config["extensions"]["file_storage"]["directory"] = str(storage)
        config["receivers"]["otlp"]["protocols"]["http"]["endpoint"] = "127.0.0.1:14318"
        config["exporters"]["prometheus"]["endpoint"] = "127.0.0.1:18889"
        config["service"]["telemetry"]["metrics"]["readers"][0]["pull"]["exporter"][
            "prometheus"
        ].update(host="127.0.0.1", port=18888)
        for signal in ["traces", "logs"]:
            config["exporters"]["otlphttp/" + signal]["endpoint"] = (
                "http://127.0.0.1:18200"
            )
        file = directory / "collector.yaml"
        file.write_text(yaml.safe_dump(config))
        with (directory / "processes.log").open("w+") as log:

            def start(command):
                p = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
                processes.append(p)
                return p

            command = [str(ROOT / ".runtime/bin/collector"), "--config=" + str(file)]
            try:
                start(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "fleetlab.relay:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "18200",
                    ]
                )
                collector = start(command)
                wait_ready(client, "http://127.0.0.1:18200/health")
                wait_ready(client, "http://127.0.0.1:23133/")
                client.post(
                    "http://127.0.0.1:18200/control", json={"seconds": 45}, headers=auth
                ).raise_for_status()
                attrs = [
                    {"key": "service.name", "value": {"stringValue": "recovery-probe"}},
                    {
                        "key": "deployment.environment.name",
                        "value": {"stringValue": "lab"},
                    },
                ]
                for i, trace_id in enumerate(traces):
                    now = time.time_ns()
                    common = {"traceId": trace_id, "spanId": f"{i + 1:016x}"}
                    span = {
                        **common,
                        "name": "wal.probe",
                        "kind": 1,
                        "startTimeUnixNano": str(now),
                        "endTimeUnixNano": str(now + 1000000),
                    }
                    event = {
                        **common,
                        "timeUnixNano": str(now),
                        "severityNumber": 9,
                        "body": {"stringValue": run_id + ":" + str(i)},
                        "attributes": [
                            {"key": "experiment.id", "value": {"stringValue": run_id}}
                        ],
                    }
                    for signal, payload in [
                        (
                            "traces",
                            {
                                "resourceSpans": [
                                    {
                                        "resource": {"attributes": attrs},
                                        "scopeSpans": [{"spans": [span]}],
                                    }
                                ]
                            },
                        ),
                        (
                            "logs",
                            {
                                "resourceLogs": [
                                    {
                                        "resource": {"attributes": attrs},
                                        "scopeLogs": [{"logRecords": [event]}],
                                    }
                                ]
                            },
                        ),
                    ]:
                        client.post(
                            "http://127.0.0.1:14318/v1/" + signal, json=payload
                        ).raise_for_status()
                    time.sleep(0.06)
                # Wait for batch processor -> durable exporter queue, not merely receiver acceptance.
                for _ in range(50):
                    counters = parse_collector_metrics(
                        client.get("http://127.0.0.1:18888/metrics").text
                    )
                    if (
                        counters
                        and counters["accepted_spans"] >= 20
                        and counters["accepted_logs"] >= 20
                        and counters["queued_batches"] >= 4
                    ):
                        break
                    time.sleep(0.1)
                assert counters and counters["queued_batches"] >= 4, (
                    "Did not establish a persisted backlog"
                )
                time.sleep(0.5)
                collector.kill()
                collector.wait(timeout=5)  # Abrupt process loss, no graceful export.
                wal_bytes = sum(
                    p.stat().st_size for p in storage.iterdir() if p.is_file()
                )
                collector = start(command)
                wait_ready(client, "http://127.0.0.1:23133/")
                client.post(
                    "http://127.0.0.1:18200/control", json={"seconds": 0}, headers=auth
                ).raise_for_status()
                found = []
                bodies = set()
                for _ in range(40):
                    found = [
                        t
                        for t in traces
                        if client.get("http://127.0.0.1:16686/api/traces/" + t)
                        .json()
                        .get("data")
                    ]
                    data = (
                        client.get(
                            "http://127.0.0.1:3100/loki/api/v1/query_range",
                            params={
                                "query": '{service_name="recovery-probe"} |= "'
                                + run_id
                                + '"',
                                "since": "1h",
                                "limit": 1000,
                            },
                        )
                        .raise_for_status()
                        .json()
                    )
                    bodies = {v[1] for s in data["data"]["result"] for v in s["values"]}
                    if len(found) == 20 and len(bodies) == 20:
                        break
                    time.sleep(0.5)
                after = parse_collector_metrics(
                    client.get("http://127.0.0.1:18888/metrics").text
                )
                checks = {
                    "backlog_before_crash": counters["queued_batches"] >= 4,
                    "wal_written": wal_bytes > 0,
                    "all_traces_recovered": len(found) == 20,
                    "all_unique_logs_recovered": len(bodies) == 20,
                    "queue_drained": after["queued_batches"] == 0,
                }
                evidence = {
                    "experiment_id": run_id,
                    "mechanism": "SIGKILL isolated Collector; restart same file_storage directory; restore backend relay",
                    "requests": 20,
                    "trace_ids": traces,
                    "traces_recovered": len(found),
                    "unique_logs_recovered": len(bodies),
                    "queued_batches_before_crash": counters["queued_batches"],
                    "wal_bytes": wal_bytes,
                    "after": after,
                    "assertions": checks,
                    "passed": all(checks.values()),
                    "scope": "Only records that reached the persistent exporter queues; no exactly-once guarantee.",
                }
                (ROOT / "evidence").mkdir(exist_ok=True)
                (ROOT / "evidence/collector-recovery.json").write_text(
                    json.dumps(evidence, indent=2) + "\n"
                )
                print(json.dumps(evidence, indent=2))
                return 0 if evidence["passed"] else 1
            except Exception:
                log.flush()
                log.seek(0)
                print(log.read()[-7000:])
                raise
            finally:
                for p in reversed(processes):
                    if p.poll() is None:
                        p.terminate()
                for p in reversed(processes):
                    try:
                        p.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        p.kill()
                        p.wait()


if __name__ == "__main__":
    sys.exit(main())
