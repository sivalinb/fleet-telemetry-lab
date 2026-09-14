"""Deterministic fictional inventory; these are not records from a real employer."""

from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select
from .catalog import Batch, ingest
from .models import Source, Audit, utcnow


def record(identity, kind, **fields):
    return {
        "external_id": identity.replace(":", "/"),
        "entity_id": identity,
        "kind": kind,
        "fields": fields,
    }


def fixture_records():
    catalog = [
        record(
            "team:platform",
            "team",
            name="Platform Engineering",
            oncall="Platform primary",
            description="Fleet lifecycle, scheduling, and service foundations.",
        ),
        record(
            "team:inference",
            "team",
            name="Inference Systems",
            oncall="Inference primary",
            description="Serving performance and model delivery.",
        ),
        record(
            "team:reliability",
            "team",
            name="Site Reliability",
            oncall="SRE primary",
            description="Telemetry, incident response, and service health.",
        ),
    ]
    redfish, kube = [], []
    for cluster, label, zone in [
        ("alpine", "Alpine · on-prem lab", "zone-a"),
        ("coastal", "Coastal · cloud fixture", "zone-b"),
    ]:
        catalog.append(
            record(
                "cluster:" + cluster,
                "cluster",
                name=label,
                owner="team:platform",
                zone=zone,
                description="Fictional environment for interoperability testing.",
            )
        )
        for r in range(1, 3):
            rack = f"{cluster}-r{r:02}"
            catalog.append(
                record(
                    "rack:" + rack,
                    "rack",
                    name=rack.upper(),
                    cluster="cluster:" + cluster,
                    owner="team:platform",
                )
            )
            for n in range(1, 4):
                serial = f"FTL-{cluster[:1].upper()}{r}{n}"
                identity = "node:" + serial
                redfish.append(
                    record(
                        identity,
                        "node",
                        name=f"{cluster}-{r}{n}",
                        serial=serial,
                        model="GPU compute node (fixture)",
                        gpus=8,
                        rack="rack:" + rack,
                        cluster="cluster:" + cluster,
                        health="healthy",
                        lifecycle="active",
                    )
                )
                kube.append(
                    record(
                        identity,
                        "node",
                        name=f"{cluster}-{r}{n}",
                        serial=serial,
                        owner="team:platform",
                        cluster="cluster:" + cluster,
                        health="healthy",
                    )
                )
    services = [
        (
            "gateway",
            "Inference Gateway",
            "inference",
            ["node:FTL-A11", "node:FTL-C11"],
            ["service:scheduler"],
        ),
        (
            "scheduler",
            "Request Scheduler",
            "platform",
            ["node:FTL-A12", "node:FTL-C12"],
            ["service:worker"],
        ),
        (
            "worker",
            "Inference Worker",
            "inference",
            ["node:FTL-A11", "node:FTL-C11"],
            [],
        ),
        (
            "embeddings",
            "Embedding Service",
            "inference",
            ["node:FTL-A21", "node:FTL-C21"],
            ["service:worker"],
        ),
        (
            "telemetry",
            "Telemetry Gateway",
            "reliability",
            ["node:FTL-A22", "node:FTL-C22"],
            [],
        ),
        ("catalog", "Fleet Catalog", "platform", ["node:FTL-A23", "node:FTL-C23"], []),
    ]
    for slug, name, owner, nodes, dependencies in services:
        catalog.append(
            record(
                "service:" + slug,
                "service",
                name=name,
                owner="team:" + owner,
                lifecycle="experimental",
                dependsOn=dependencies,
                runbook="/docs-guide/field-guide.html#runbooks",
                repository="https://github.com/sivalinb/fleet-telemetry-lab",
                description="A fictional fleet service; gateway, scheduler, and worker also run as real Python HTTP services in the telemetry lab.",
            )
        )
        kube.append(
            record(
                "service:" + slug,
                "service",
                name=name,
                owner="team:" + owner,
                runsOn=nodes,
                health="healthy",
            )
        )
    return {"service-catalog": catalog, "redfish-bmc": redfish, "kubernetes": kube}


def seed(db):
    if db.scalar(select(Source.id).limit(1)):
        return False
    for id, name, kind, priority in [
        ("service-catalog", "Git service catalog", "catalog", 100),
        ("redfish-bmc", "Redfish hardware feed", "redfish", 80),
        ("kubernetes", "Kubernetes discovery", "kubernetes", 70),
    ]:
        db.add(Source(id=id, name=name, kind=kind, priority=priority, ttl_seconds=900))
    db.flush()
    now = utcnow()
    for source, records in fixture_records().items():
        ingest(
            db, source, Batch(batch_id="initial-seed", observed_at=now, records=records)
        )
    return True


def scenario(db, name):
    if name == "refresh":
        for source, records in fixture_records().items():
            ingest(
                db,
                source,
                Batch(
                    batch_id="refresh-" + uuid4().hex,
                    observed_at=utcnow(),
                    records=records,
                ),
            )
        db.add(
            Audit(
                entity_id="fleet",
                action="scenario.restored",
                detail={
                    "description": "Restored the original fictional source snapshots."
                },
            )
        )
    elif name == "stale-source":
        source = db.get(Source, "redfish-bmc")
        source.last_success = utcnow() - timedelta(hours=2)
        db.add(
            Audit(
                entity_id="source:redfish-bmc",
                action="scenario.stale_source",
                detail={
                    "description": "Fixture source heartbeat moved two hours into the past."
                },
            )
        )
    elif name in {"ownership-conflict", "node-degraded", "missing-node"}:
        source = "redfish-bmc" if name != "ownership-conflict" else "kubernetes"
        records = fixture_records()[source]
        if name == "ownership-conflict":
            for r in records:
                if r["entity_id"] == "service:worker":
                    r["fields"]["owner"] = "team:reliability"
        elif name == "node-degraded":
            for r in records:
                if r["entity_id"] == "node:FTL-A11":
                    r["fields"]["health"] = "degraded"
        else:
            records = [r for r in records if r["entity_id"] != "node:FTL-A11"]
        ingest(
            db,
            source,
            Batch(
                batch_id=name + "-" + uuid4().hex, observed_at=utcnow(), records=records
            ),
        )
        db.add(
            Audit(
                entity_id="fleet",
                action="scenario." + name,
                detail={"source": source, "data_origin": "injected fixture change"},
            )
        )
    else:
        raise KeyError("Unknown scenario")
    db.flush()
