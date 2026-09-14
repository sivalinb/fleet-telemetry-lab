"""Observe real backends and save bounded, repeatable experiment evidence."""

import asyncio
import math
import os
import re
import statistics
import time
from uuid import uuid4
import httpx
from .models import Experiment


def endpoints():
    return {
        "prometheus": os.getenv("PROMETHEUS_URL", "http://127.0.0.1:9090"),
        "loki": os.getenv("LOKI_URL", "http://127.0.0.1:3100"),
        "jaeger": os.getenv("JAEGER_URL", "http://127.0.0.1:16686"),
        "collector": os.getenv("COLLECTOR_HEALTH_URL", "http://127.0.0.1:13133"),
        "relay": os.getenv("RELAY_URL", "http://127.0.0.1:8200"),
        "gateway": os.getenv("GATEWAY_URL", "http://127.0.0.1:8101"),
    }


def auth_headers():
    token = os.getenv("LAB_API_TOKEN", "")
    return {"Authorization": "Bearer " + token} if token else {}


async def query_prom(client, query):
    try:
        response = await client.get(
            endpoints()["prometheus"] + "/api/v1/query", params={"query": query}
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "success":
            return None
        values = [float(r["value"][1]) for r in payload["data"]["result"]]
        return sum(v for v in values if math.isfinite(v)) if values else None
    except (httpx.HTTPError, ValueError, KeyError):
        return None


def parse_collector_metrics(text):
    totals = {
        "queued_batches": 0,
        "failed_exports": 0,
        "accepted_spans": 0,
        "accepted_logs": 0,
    }
    prefixes = {
        "otelcol_exporter_queue_size": "queued_batches",
        "otelcol_exporter_send_failed_spans": "failed_exports",
        "otelcol_exporter_send_failed_log_records": "failed_exports",
        "otelcol_receiver_accepted_spans": "accepted_spans",
        "otelcol_receiver_accepted_log_records": "accepted_logs",
    }
    found = False
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        for prefix, name in prefixes.items():
            metric = line.split("{", 1)[0].split(" ", 1)[0]
            if metric in {prefix, prefix + "_total"}:
                try:
                    totals[name] += float(line.rsplit(" ", 1)[1])
                    found = True
                except ValueError:
                    pass
    return totals if found else None


async def collector_counters(client):
    try:
        r = await client.get(
            os.getenv("COLLECTOR_METRICS_URL", "http://127.0.0.1:8888/metrics")
        )
        r.raise_for_status()
        return parse_collector_metrics(r.text)
    except httpx.HTTPError:
        return None


async def pipeline_status():
    paths = {
        "prometheus": "/-/ready",
        "loki": "/ready",
        "jaeger": "/api/services",
        "collector": "/",
        "relay": "/health",
        "gateway": "/health",
    }
    async with httpx.AsyncClient(timeout=3) as client:

        async def check(name):
            try:
                r = await client.get(endpoints()[name] + paths[name])
                r.raise_for_status()
                return {"name": name, "status": "ready"}
            except httpx.HTTPError:
                return {"name": name, "status": "unavailable"}

        async def instance(name, default):
            try:
                r = await client.get(
                    os.getenv(name.upper() + "_URL", default) + "/health"
                )
                r.raise_for_status()
                value = r.json().get("instance_id", "")
                return value if re.fullmatch(r"[a-f0-9]{32}", value) else None
            except (httpx.HTTPError, ValueError):
                return None

        health, ids, counters = await asyncio.gather(
            asyncio.gather(*(check(n) for n in paths)),
            asyncio.gather(
                *(
                    instance(n, "http://127.0.0.1:" + str(p))
                    for n, p in [
                        ("gateway", 8101),
                        ("scheduler", 8102),
                        ("worker", 8103),
                    ]
                )
            ),
            collector_counters(client),
        )
        bounded = unbounded = requests = None
        if all(ids):
            # Old instance series may still exist after a restart. Compare only current processes.
            selector = 'service_instance_id=~"' + "|".join(ids) + '"'
            bounded, unbounded, requests = await asyncio.gather(
                query_prom(
                    client,
                    'count(fleetlab_requests_total{profile="bounded",'
                    + selector
                    + "}) or vector(0)",
                ),
                query_prom(
                    client,
                    'count(fleetlab_requests_total{profile="unbounded",'
                    + selector
                    + "}) or vector(0)",
                ),
                query_prom(
                    client,
                    "sum(fleetlab_requests_total{" + selector + "}) or vector(0)",
                ),
            )
    return {
        "services": health,
        "metrics": {
            "bounded_series": bounded,
            "unbounded_series": unbounded,
            "completed_service_requests": requests,
        },
        "active_workload_instances": ids,
        "collector": counters,
        "origin": "live HTTP queries; metrics scoped to current workload instances",
        "observed_at": time.time(),
    }


async def log_evidence(client, experiment_id):
    try:
        query = '{service_name="gateway"} | experiment_id="' + experiment_id + '"'
        r = await client.get(
            endpoints()["loki"] + "/loki/api/v1/query_range",
            params={"query": query, "limit": 1000, "since": "1h"},
        )
        r.raise_for_status()
        records = []
        for stream in r.json()["data"]["result"]:
            for value in stream["values"]:
                records.append(
                    {
                        "timestamp": value[0],
                        "body": value[1],
                        "metadata": {
                            **stream.get("stream", {}),
                            **(value[2] if len(value) > 2 else {}),
                        },
                    }
                )
        return {"available": True, "count": len(records), "records": records[:100]}
    except (httpx.HTTPError, KeyError, ValueError):
        return {"available": False, "count": None, "records": []}


async def trace_evidence(client, trace_id):
    try:
        r = await client.get(endpoints()["jaeger"] + "/api/traces/" + trace_id)
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            return {"trace_id": trace_id, "found": False}
        services = sorted(
            {p["serviceName"] for t in data for p in t.get("processes", {}).values()}
        )
        spans = [
            {
                "operation": s["operationName"],
                "duration_us": s["duration"],
                "start_us": s["startTime"],
                "service": t["processes"][s["processID"]]["serviceName"],
            }
            for t in data
            for s in t["spans"]
        ]
        return {
            "trace_id": trace_id,
            "found": True,
            "services": services,
            "spans": spans,
            "complete_chain": {"gateway", "scheduler", "worker"}.issubset(services),
        }
    except (httpx.HTTPError, KeyError, ValueError):
        return {"trace_id": trace_id, "found": False}


SCENARIOS = {
    "baseline": {"profile": "bounded", "delay_ms": 0},
    "label-growth": {"profile": "unbounded", "delay_ms": 0},
    "contract-gate": {"profile": "guarded", "delay_ms": 0},
    "slow-worker": {"profile": "bounded", "delay_ms": 180},
    "backend-outage": {"profile": "bounded", "delay_ms": 0},
}


async def run_experiment(factory, name, count=12):
    if name not in SCENARIOS:
        raise ValueError("Unknown experiment")
    if not 1 <= count <= 40:
        raise ValueError("Request count must be between 1 and 40")
    run_id = uuid4().hex
    start = time.time()
    with factory.begin() as db:
        db.add(
            Experiment(
                id=run_id,
                name=name,
                state="running",
                results={"requested": count, "origin": "real Python HTTP workload"},
            )
        )
    result = {
        "id": run_id,
        "name": name,
        "requested": count,
        "completed": 0,
        "blocked": 0,
        "errors": [],
        "trace_ids": [],
        "latencies_ms": [],
        "samples": [],
        "origin": "measured lab execution; no GPU workload",
        "expected_spans_per_request": 3,
    }
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            health = await client.get(endpoints()["gateway"] + "/health")
            health.raise_for_status()
            result["before"] = await pipeline_status()
            if name == "backend-outage":
                result["relay_before"] = (
                    await client.get(endpoints()["relay"] + "/health")
                ).json()
                response = await client.post(
                    endpoints()["relay"] + "/control",
                    json={"seconds": 8},
                    headers=auth_headers(),
                )
                response.raise_for_status()

            async def send(i):
                try:
                    r = await client.post(
                        endpoints()["gateway"] + "/work",
                        json={
                            **SCENARIOS[name],
                            "experiment_id": run_id,
                            "request_id": f"{run_id}-{i}",
                        },
                    )
                    if r.status_code == 422 and name == "contract-gate":
                        return {"blocked": True}
                    r.raise_for_status()
                    return r.json()
                except httpx.HTTPError as e:
                    return {"error": str(e)[:250]}

            for offset in range(0, count, 4):
                responses = await asyncio.gather(
                    *(send(i) for i in range(offset, min(offset + 4, count)))
                )
                for r in responses:
                    if r.get("error"):
                        result["errors"].append(r["error"])
                    elif r.get("blocked"):
                        result["blocked"] += 1
                    else:
                        result["completed"] += 1
                        result["trace_ids"].append(r["trace_id"])
                        result["latencies_ms"].append(r["duration_ms"])
                result["samples"].append(
                    {
                        "elapsed_s": round(time.time() - start, 2),
                        "collector": await collector_counters(client),
                    }
                )
                if name == "backend-outage":
                    await asyncio.sleep(0.5)
            if name == "backend-outage":
                for _ in range(5):
                    await asyncio.sleep(2)
                    result["samples"].append(
                        {
                            "elapsed_s": round(time.time() - start, 2),
                            "collector": await collector_counters(client),
                        }
                    )
            else:
                await asyncio.sleep(2)
            traces, logs = [], {"available": False, "count": None, "records": []}
            # Poll boundedly for asynchronous export, scraping, and log indexing.
            for _ in range(12):
                traces = await asyncio.gather(
                    *(trace_evidence(client, t) for t in result["trace_ids"])
                )
                logs = await log_evidence(client, run_id)
                if (not result["trace_ids"]) or (
                    all(t.get("complete_chain") for t in traces)
                    and (logs.get("count") or 0) >= result["completed"] * 2
                ):
                    break
                await asyncio.sleep(1)
            result["traces"] = traces
            result["logs"] = logs
            result["verified_chains"] = sum(
                bool(t.get("complete_chain")) for t in traces
            )
            result["after"] = await pipeline_status()
            # Wait for the metric export interval and the next Prometheus scrape.
            expected = (
                result["before"]["metrics"]["completed_service_requests"] or 0
            ) + result["completed"] * 3
            for _ in range(8):
                actual = result["after"]["metrics"]["completed_service_requests"]
                if actual is not None and actual >= expected:
                    break
                await asyncio.sleep(1)
                result["after"] = await pipeline_status()
            result["duration_s"] = round(time.time() - start, 2)
            result["latency_p50_ms"] = (
                round(statistics.median(result["latencies_ms"]), 2)
                if result["latencies_ms"]
                else None
            )
            latencies = sorted(result["latencies_ms"])
            result["latency_p95_ms"] = (
                latencies[max(0, math.ceil(len(latencies) * 0.95) - 1)]
                if latencies
                else None
            )
            before, after = result["before"]["metrics"], result["after"]["metrics"]
            result["assertions"] = {"no_request_errors": not result["errors"]}
            checks = result["assertions"]
            if name == "contract-gate":
                checks["all_requests_rejected_before_work"] = result["blocked"] == count
                checks["no_new_service_requests"] = (
                    after["completed_service_requests"]
                    == before["completed_service_requests"]
                    and after["completed_service_requests"] is not None
                )
                checks["no_gateway_logs"] = logs["available"] and logs["count"] == 0
            else:
                checks.update(
                    all_requests_completed=result["completed"] == count,
                    all_trace_chains_present=result["verified_chains"] == count,
                    gateway_logs_present=(logs.get("count") or 0) >= count * 2,
                    service_metrics_exported=after["completed_service_requests"]
                    is not None
                    and after["completed_service_requests"] >= expected,
                )
            if name == "label-growth":
                result["series_added"] = (after["unbounded_series"] or 0) - (
                    before["unbounded_series"] or 0
                )
                checks["three_new_series_per_request"] = (
                    result["series_added"] == count * 3
                )
            if name in {"baseline", "slow-worker"}:
                checks["bounded_series_do_not_grow_with_requests"] = after[
                    "bounded_series"
                ] == max(3, before["bounded_series"] or 0)
            if name == "slow-worker":
                worker_ms = [
                    s["duration_us"] / 1000
                    for t in traces
                    for s in t.get("spans", [])
                    if s["service"] == "worker"
                ]
                result["worker_p50_ms"] = (
                    statistics.median(worker_ms) if worker_ms else None
                )
                checks["delay_visible_in_worker_span"] = (
                    bool(worker_ms) and min(worker_ms) >= 180
                )
            if name == "backend-outage":
                result["relay_after"] = (
                    await client.get(endpoints()["relay"] + "/health")
                ).json()
                checks["backend_exports_were_rejected"] = (
                    result["relay_after"]["rejected"]
                    > result["relay_before"]["rejected"]
                )
                checks["queue_observed"] = any(
                    (s.get("collector") or {}).get("queued_batches", 0) > 0
                    for s in result["samples"]
                )
                checks["queue_drained"] = (
                    result["after"]["collector"] is not None
                    and result["after"]["collector"]["queued_batches"] == 0
                )
            result["passed"] = all(checks.values())
            result["state"] = "passed" if result["passed"] else "incomplete"
    except Exception as e:
        result.update(
            state="failed", passed=False, duration_s=round(time.time() - start, 2)
        )
        result["errors"].append(str(e)[:300])
    finally:
        if name == "backend-outage":
            try:
                async with httpx.AsyncClient(timeout=3) as client:
                    await client.post(
                        endpoints()["relay"] + "/control",
                        json={"seconds": 0},
                        headers=auth_headers(),
                    )
            except httpx.HTTPError:
                pass
        with factory.begin() as db:
            saved = db.get(Experiment, run_id)
            saved.state = result["state"]
            saved.results = result
    return result
