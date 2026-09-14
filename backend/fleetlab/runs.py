"""Durable experiment records and the public scenario contract."""

from copy import deepcopy
from .models import Experiment

SCENARIO_CATALOG = [
    {
        "id": "baseline",
        "title": "01 · Baseline delivery",
        "group": "workload",
        "question": "Can we follow every request across services?",
        "expected": "Three-service traces, gateway logs, and counters arrive.",
        "seconds": "5–20",
    },
    {
        "id": "label-growth",
        "title": "02 · Cardinality growth",
        "group": "workload",
        "question": "What does a request_id metric label cost?",
        "expected": "Three new counter series per request; histogram cost is additional.",
        "seconds": "5–20",
    },
    {
        "id": "contract-gate",
        "title": "03 · Instrumentation gate",
        "group": "workload",
        "question": "Can bad metric labels be stopped before emission?",
        "expected": "Every request is rejected before emitting work signals.",
        "seconds": "3–10",
    },
    {
        "id": "slow-worker",
        "title": "04 · Find the slow service",
        "group": "workload",
        "question": "Does the introduced delay appear in the right span?",
        "expected": "Each worker span includes the injected 180 ms delay.",
        "seconds": "5–20",
    },
    {
        "id": "backend-outage",
        "title": "05 · Backend outage",
        "group": "workload",
        "question": "Does a short export outage drain without missing evidence?",
        "expected": "Actual 503 responses, nonempty queue, then complete delivery.",
        "seconds": "12–30",
    },
    {
        "id": "durable-crash",
        "title": "06 · Crash with a persistent queue",
        "group": "isolated",
        "question": "Will data already in the WAL survive SIGKILL?",
        "expected": "All accepted probe traces and logs reappear after restart.",
        "seconds": "8–25",
    },
    {
        "id": "volatile-crash",
        "title": "07 · Crash with an in-memory queue",
        "group": "isolated",
        "question": "What happens when the same backlog has no persistence?",
        "expected": "Original probe data is lost; a new canary proves recovery.",
        "seconds": "8–25",
    },
    {
        "id": "retry-exhaustion",
        "title": "08 · Exhaust the retry budget",
        "group": "isolated",
        "question": "Does persistence protect data after retries expire?",
        "expected": "Finite retries expire, terminal export failures are measured, originals do not arrive.",
        "seconds": "8–25",
    },
    {
        "id": "queue-saturation",
        "title": "09 · Fill the sending queue",
        "group": "isolated",
        "question": "Where does the pipeline reject excess data?",
        "expected": "The tiny queue refuses excess ingress; accepted probes recover.",
        "seconds": "8–25",
    },
]
SCENARIOS_BY_ID = {item["id"]: item for item in SCENARIO_CATALOG}
TERMINAL = {"passed", "incomplete", "failed", "cancelled", "interrupted"}


def validate_run(name, count):
    if name not in SCENARIOS_BY_ID:
        raise ValueError("Unknown experiment")
    if not 1 <= count <= 40:
        raise ValueError("Request count must be between 1 and 40")
    if SCENARIOS_BY_ID[name]["group"] == "isolated" and count < 8:
        raise ValueError("Isolated reliability experiments require 8–40 probes")


def save_run(factory, result, phase=None):
    if phase:
        result["phase"] = phase
    with factory.begin() as db:
        item = db.get(Experiment, result["id"])
        if item is None:
            item = Experiment(
                id=result["id"],
                name=result["name"],
                state=result.get("state", "running"),
                results={},
            )
            db.add(item)
        item.state = result.get("state", "running")
        item.results = deepcopy(result)


def run_record(item):
    return {
        "id": item.id,
        "name": item.name,
        "state": item.state,
        "created_at": item.created_at.isoformat(),
        "results": item.results,
    }
