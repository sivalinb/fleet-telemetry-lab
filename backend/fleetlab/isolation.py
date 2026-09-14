"""Measure loss boundaries using a real Collector and owned, isolated subprocesses.

The main lab Collector is never stopped or reconfigured. No shell commands are
accepted from requests. A probe emits one span and one log per logical input.
"""

import asyncio
from contextlib import nullcontext
import os
from pathlib import Path
import socket
import sys
import tempfile
import time
from uuid import uuid4
import httpx
import yaml
from .contracts import resource_for
from .runs import save_run, validate_run
from .telemetry import parse_collector_metrics, endpoints, auth_headers

ROOT = Path(__file__).resolve().parents[2]
ISOLATED = {"durable-crash", "volatile-crash", "retry-exhaustion", "queue-saturation"}


def collector_binary():
    return Path(os.getenv("LAB_COLLECTOR_BINARY", str(ROOT / ".runtime/bin/collector")))


def allocate_ports(count):
    """Reserve distinct OS-selected ports while forming the set, then release them."""
    sockets = []
    try:
        for _ in range(count):
            sock = socket.socket()
            sock.bind(("127.0.0.1", 0))
            sockets.append(sock)
        return [sock.getsockname()[1] for sock in sockets]
    finally:
        for sock in sockets:
            sock.close()


def isolated_config(directory, ports, name, count):
    receiver, health, metrics, relay = ports
    persistent = name != "volatile-crash"
    capacity = 4 if name == "queue-saturation" else 100
    extensions = {"health_check": {"endpoint": f"127.0.0.1:{health}"}}
    if persistent:
        extensions["file_storage"] = {"directory": str(directory / "wal")}
    exporters = {}
    for signal in ["logs", "traces"]:
        queue = {
            "enabled": True,
            "queue_size": capacity,
            "sizer": "requests",
            "num_consumers": count if name == "retry-exhaustion" else 1,
        }
        if persistent:
            queue["storage"] = "file_storage"
        exporters["otlphttp/" + signal] = {
            "endpoint": f"http://127.0.0.1:{relay}",
            "sending_queue": queue,
            "retry_on_failure": {
                "initial_interval": "200ms",
                "max_interval": "500ms",
                "max_elapsed_time": "1s" if name == "retry-exhaustion" else "30s",
            },
        }
    return {
        "extensions": extensions,
        "receivers": {
            "otlp": {"protocols": {"http": {"endpoint": f"127.0.0.1:{receiver}"}}}
        },
        "exporters": exporters,
        "service": {
            "extensions": list(extensions),
            # Deliberately no batch processor: each HTTP acceptance is a queue enqueue.
            "pipelines": {
                s: {"receivers": ["otlp"], "exporters": ["otlphttp/" + s]}
                for s in ["logs", "traces"]
            },
            "telemetry": {
                "metrics": {
                    "level": "detailed",
                    "readers": [
                        {
                            "pull": {
                                "exporter": {
                                    "prometheus": {"host": "127.0.0.1", "port": metrics}
                                }
                            }
                        }
                    ],
                }
            },
        },
    }


def probe_payloads(run_id, trace_id, event_id):
    resource = {**resource_for("reliability-probe"), "service.instance.id": run_id}
    attrs = [{"key": k, "value": {"stringValue": v}} for k, v in resource.items()]
    now = time.time_ns()
    common = {"traceId": trace_id, "spanId": uuid4().hex[:16]}
    extra = [
        {"key": "experiment.id", "value": {"stringValue": run_id}},
        {"key": "event.id", "value": {"stringValue": event_id}},
    ]
    span = {
        **common,
        "name": "reliability.probe",
        "kind": 1,
        "startTimeUnixNano": str(now),
        "endTimeUnixNano": str(now + 1000000),
        "attributes": extra,
    }
    log = {
        **common,
        "timeUnixNano": str(now),
        "severityNumber": 9,
        "body": {"stringValue": event_id},
        "attributes": extra,
    }
    return {
        "traces": {
            "resourceSpans": [
                {"resource": {"attributes": attrs}, "scopeSpans": [{"spans": [span]}]}
            ]
        },
        "logs": {
            "resourceLogs": [
                {
                    "resource": {"attributes": attrs},
                    "scopeLogs": [{"logRecords": [log]}],
                }
            ]
        },
    }


async def backend_evidence(client, trace_ids, run_id):
    async def trace_found(trace_id):
        r = await client.get(endpoints()["jaeger"] + "/api/traces/" + trace_id)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return trace_id if r.json().get("data") else None

    found = []
    for offset in range(0, len(trace_ids), 8):
        found.extend(
            await asyncio.gather(
                *(trace_found(t) for t in trace_ids[offset : offset + 8])
            )
        )
    response = await client.get(
        endpoints()["loki"] + "/loki/api/v1/query_range",
        params={
            "query": '{service_name="reliability-probe"} | experiment_id="'
            + run_id
            + '"',
            "since": "1h",
            "limit": 1000,
        },
    )
    response.raise_for_status()
    records = [
        v[1] for stream in response.json()["data"]["result"] for v in stream["values"]
    ]
    return set(t for t in found if t), set(records), len(records)


async def run_isolated(factory, name, count=12, run_id=None):
    validate_run(name, count)
    if name not in ISOLATED:
        raise ValueError("Not an isolated scenario")
    run_id = run_id or uuid4().hex
    start = time.monotonic()
    result = {
        "id": run_id,
        "name": name,
        "state": "running",
        "requested": count,
        "completed": 0,
        "blocked": 0,
        "samples": [],
        "errors": [],
        "assertions": {},
        "origin": "Real isolated Collector and Python OTLP probes; no GPU workload",
        "trace_ids": [uuid4().hex for _ in range(count)],
        "event_ids": [f"{run_id}:{i}" for i in range(count)],
        "expected_spans_per_request": 1,
        "scope": "Direct OTLP ingress into exporter queues; no upstream SDK or batch processor buffer in this experiment.",
    }
    save_run(factory, result, "Preparing isolated Collector")
    processes = []
    workspace = tempfile.TemporaryDirectory(prefix="fleetlab-isolated-")
    try:
        if not collector_binary().is_file():
            raise RuntimeError(
                "Collector binary missing: run python scripts/install_tools.py"
            )
        with nullcontext(workspace.name) as temp:
            directory = Path(temp)
            (directory / "wal").mkdir()
            ports = allocate_ports(4)
            receiver, health_port, metrics_port, relay_port = ports
            ingress = f"http://127.0.0.1:{receiver}"
            relay = f"http://127.0.0.1:{relay_port}"
            metrics_url = f"http://127.0.0.1:{metrics_port}/metrics"
            config = isolated_config(directory, ports, name, count)
            result["configuration"] = {
                "persistent": name != "volatile-crash",
                "queue_capacity_per_signal": 4 if name == "queue-saturation" else 100,
                "retry_budget_seconds": 1 if name == "retry-exhaustion" else 30,
                "batch_processor": False,
            }
            config_path = directory / "collector.yaml"
            config_path.write_text(yaml.safe_dump(config))
            with (directory / "processes.log").open("w+") as log:

                async def launch(*command):
                    process = await asyncio.create_subprocess_exec(
                        *command,
                        stdout=log,
                        stderr=log,
                        env={**os.environ, "PYTHONPATH": str(ROOT / "backend")},
                    )
                    processes.append(process)
                    return process

                async with httpx.AsyncClient(timeout=4) as client:

                    async def ready(url, process):
                        for _ in range(100):
                            if process.returncode is not None:
                                raise RuntimeError(
                                    "An isolated process exited before becoming ready"
                                )
                            try:
                                r = await client.get(url)
                                if r.is_success:
                                    return
                            except httpx.HTTPError:
                                pass
                            await asyncio.sleep(0.1)
                        raise RuntimeError("An isolated service did not become ready")

                    async def sample(phase):
                        response = await client.get(metrics_url)
                        response.raise_for_status()
                        counters = parse_collector_metrics(response.text)
                        result["samples"].append(
                            {
                                "elapsed_s": round(time.monotonic() - start, 2),
                                "phase": phase,
                                "collector": counters,
                            }
                        )
                        save_run(factory, result, phase)
                        return counters or {}

                    async def send(trace_id, event_id):
                        accepted = {}
                        for signal, payload in probe_payloads(
                            run_id, trace_id, event_id
                        ).items():
                            r = await client.post(
                                ingress + "/v1/" + signal, json=payload
                            )
                            rejected = (
                                r.json().get("partialSuccess", {})
                                if r.is_success and r.content
                                else {}
                            )
                            accepted[signal] = r.is_success and not any(
                                int(v)
                                for k, v in rejected.items()
                                if k.startswith("rejected")
                            )
                        return accepted

                    # A live backend must exist before a controlled loss is meaningful.
                    for url in [
                        endpoints()["jaeger"] + "/api/services",
                        endpoints()["loki"] + "/ready",
                    ]:
                        (await client.get(url)).raise_for_status()
                    relay_process = await launch(
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "fleetlab.relay:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(relay_port),
                    )
                    collector_command = [
                        str(collector_binary()),
                        "--config=" + str(config_path),
                    ]
                    collector = await launch(*collector_command)
                    await ready(relay + "/health", relay_process)
                    await ready(f"http://127.0.0.1:{health_port}/", collector)
                    (
                        await client.post(
                            relay + "/control",
                            json={"seconds": 45},
                            headers=auth_headers(),
                        )
                    ).raise_for_status()
                    accepted_traces, accepted_logs = [], []
                    for trace_id, event_id in zip(
                        result["trace_ids"], result["event_ids"]
                    ):
                        accepted = await send(trace_id, event_id)
                        if accepted["traces"]:
                            accepted_traces.append(trace_id)
                        if accepted["logs"]:
                            accepted_logs.append(event_id)
                        result["completed"] += 1
                        if result["completed"] % 4 == 0:
                            await sample("Export blocked; sending probes")
                    result["ingress"] = {
                        "accepted_traces": len(accepted_traces),
                        "accepted_logs": len(accepted_logs),
                        "rejected_traces": count - len(accepted_traces),
                        "rejected_logs": count - len(accepted_logs),
                    }
                    before = await sample("Backlog established")
                    result["before_crash_or_recovery"] = before
                    result["relay_blocked"] = (
                        await client.get(relay + "/health")
                    ).json()["rejected"] > 0
                    if name in {"durable-crash", "volatile-crash"}:
                        if before.get("queued_batches", 0) <= 0:
                            raise RuntimeError(
                                "No backlog was established before the crash"
                            )
                        save_run(
                            factory,
                            result,
                            "SIGKILL Collector; restart same queue directory",
                        )
                        collector.kill()
                        await collector.wait()
                        result["wal_bytes"] = sum(
                            p.stat().st_size
                            for p in (directory / "wal").iterdir()
                            if p.is_file()
                        )
                        collector = await launch(*collector_command)
                        await ready(f"http://127.0.0.1:{health_port}/", collector)
                    if name == "retry-exhaustion":
                        for _ in range(40):
                            before = await sample(
                                "Waiting for terminal export failures"
                            )
                            if before.get("failed_exports", 0) >= count * 2:
                                break
                            await asyncio.sleep(0.2)
                        result["terminal_failures"] = before.get("failed_exports")
                    await sample("Restoring backend exports")
                    (
                        await client.post(
                            relay + "/control",
                            json={"seconds": 0},
                            headers=auth_headers(),
                        )
                    ).raise_for_status()
                    for _ in range(50):
                        draining = await sample("Draining accepted backlog")
                        if draining.get("queued_batches") == 0:
                            break
                        await asyncio.sleep(0.2)
                    # Canary distinguishes intentional loss from a broken verification backend.
                    canary_trace, canary_event = uuid4().hex, run_id + ":canary"
                    canary_accepted = await send(canary_trace, canary_event)
                    original_traces, original_logs = set(), set()
                    expected_traces = (
                        set()
                        if name in {"volatile-crash", "retry-exhaustion"}
                        else set(accepted_traces)
                    )
                    expected_logs = (
                        set()
                        if name in {"volatile-crash", "retry-exhaustion"}
                        else set(accepted_logs)
                    )
                    restored_at = time.monotonic()
                    canary_ok = False
                    for _ in range(40):
                        found, bodies, log_count = await backend_evidence(
                            client, result["trace_ids"] + [canary_trace], run_id
                        )
                        original_traces = found & set(result["trace_ids"])
                        original_logs = bodies & set(result["event_ids"])
                        canary_ok = canary_trace in found and canary_event in bodies
                        after = await sample("Verifying delivery after recovery")
                        if (
                            canary_ok
                            and expected_traces.issubset(found)
                            and expected_logs.issubset(bodies)
                            and time.monotonic() - restored_at >= 2
                            and after.get("queued_batches") == 0
                        ):
                            break
                        await asyncio.sleep(0.5)
                    result["delivery"] = {
                        "traces_sent": count,
                        "traces_received": len(original_traces),
                        "logs_sent": count,
                        "unique_logs_received": len(original_logs),
                        "log_records_including_canary": log_count,
                        "missing_trace_ids": sorted(
                            set(result["trace_ids"]) - original_traces
                        ),
                        "missing_event_ids": sorted(
                            set(result["event_ids"]) - original_logs
                        ),
                        "canary_verified": canary_ok,
                    }
                    result["recovery_seconds"] = round(
                        time.monotonic() - restored_at, 2
                    )
                    checks = result["assertions"]
                    checks.update(
                        backend_exports_were_rejected=result["relay_blocked"],
                        recovery_canary_accepted=all(canary_accepted.values()),
                        recovery_canary_arrived=canary_ok,
                        queue_drained=after.get("queued_batches") == 0,
                    )
                    if name == "queue-saturation":
                        checks.update(
                            excess_ingress_rejected=len(accepted_traces) < count
                            and len(accepted_logs) < count,
                            queue_capacity_observed=max(
                                (s["collector"] or {}).get("queued_batches", 0)
                                for s in result["samples"]
                            )
                            <= 8,
                            all_accepted_traces_recovered=set(accepted_traces).issubset(
                                original_traces
                            ),
                            all_accepted_logs_recovered=set(accepted_logs).issubset(
                                original_logs
                            ),
                            backpressure_counter_recorded=(
                                result["before_crash_or_recovery"].get(
                                    "enqueue_failures"
                                )
                                or 0
                            )
                            > 0,
                        )
                    else:
                        checks["all_original_inputs_accepted"] = (
                            len(accepted_traces) == count
                            and len(accepted_logs) == count
                        )
                        if name == "durable-crash":
                            checks.update(
                                wal_written=result["wal_bytes"] > 0,
                                all_original_traces_recovered=len(original_traces)
                                == count,
                                all_original_logs_recovered=len(original_logs) == count,
                            )
                        else:
                            checks.update(
                                original_traces_lost_as_expected=not original_traces,
                                original_logs_lost_as_expected=not original_logs,
                            )
                            if name == "retry-exhaustion":
                                checks["terminal_failures_recorded"] = (
                                    result["terminal_failures"] or 0
                                ) >= 2 * count
                    result["passed"] = all(checks.values())
                    result["state"] = "passed" if result["passed"] else "incomplete"
                # Gracefully stop while logs/temp directory are still open.
                for process in reversed(processes):
                    if process.returncode is None:
                        process.terminate()
                for process in processes:
                    try:
                        await asyncio.wait_for(process.wait(), 5)
                    except asyncio.TimeoutError:
                        process.kill()
                        await process.wait()
    except asyncio.CancelledError:
        result.update(state="cancelled", passed=False)
        result["errors"].append("Experiment cancelled; owned processes stopped.")
    except Exception as error:
        result.update(state="failed", passed=False)
        result["errors"].append(str(error).replace(str(ROOT), "<project>")[:500])
    finally:
        for process in reversed(processes):
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), 5)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
        result["duration_s"] = round(time.monotonic() - start, 2)
        result["cleanup"] = {
            "owned_processes": len(processes),
            "all_exited": all(p.returncode is not None for p in processes),
        }
        workspace.cleanup()
        save_run(factory, result, "Finished: " + result["state"])
    return result
