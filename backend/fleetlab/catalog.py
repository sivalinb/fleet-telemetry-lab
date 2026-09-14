"""Deterministic reconciliation with provenance, replay safety, and freshness."""

from collections import defaultdict
from datetime import datetime, timezone, timedelta
import hashlib
import json
import re
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from .models import Source, Observation, Entity, Audit, SyncRun, utcnow

KINDS = Literal["cluster", "rack", "node", "service", "team"]
ALLOWED_FIELDS = {
    "name",
    "owner",
    "cluster",
    "rack",
    "health",
    "lifecycle",
    "serial",
    "model",
    "gpus",
    "zone",
    "description",
    "runbook",
    "repository",
    "dependsOn",
    "runsOn",
    "oncall",
    "capacity",
}
LIST_FIELDS = {"dependsOn", "runsOn"}


class Record(BaseModel):
    external_id: str = Field(
        min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9_.:/-]+$"
    )
    entity_id: str = Field(
        min_length=3, max_length=160, pattern=r"^[a-z]+:[a-zA-Z0-9_.:/-]+$"
    )
    kind: KINDS
    fields: dict[str, Any]

    @field_validator("fields")
    @classmethod
    def check_fields(cls, fields):
        if set(fields) - ALLOWED_FIELDS:
            raise ValueError("Unsupported inventory fields")
        for k, v in fields.items():
            if k in LIST_FIELDS:
                if (
                    not isinstance(v, list)
                    or len(v) > 100
                    or any(not isinstance(x, str) or len(x) > 160 for x in v)
                ):
                    raise ValueError(
                        "Relationships must be bounded lists of entity identifiers"
                    )
            elif k in {"gpus", "capacity"}:
                if (
                    not isinstance(v, int)
                    or isinstance(v, bool)
                    or not 0 <= v <= 1000000
                ):
                    raise ValueError("Capacity must be a non-negative integer")
            elif not isinstance(v, str) or len(v) > 2000:
                raise ValueError("Inventory values must be bounded strings")
            if k in {"repository", "runbook"} and not (
                v.startswith("https://") or v.startswith("/docs-guide/")
            ):
                raise ValueError(
                    "Documentation links must use HTTPS or the local guide"
                )
        return fields


class Batch(BaseModel):
    batch_id: str = Field(min_length=1, max_length=90, pattern=r"^[a-zA-Z0-9_.-]+$")
    observed_at: datetime
    full_snapshot: bool = True
    records: list[Record] = Field(max_length=5000)

    @field_validator("observed_at")
    @classmethod
    def aware_time(cls, value):
        if value.tzinfo is None:
            raise ValueError("observed_at must include a timezone")
        if value > utcnow() + timedelta(minutes=5):
            raise ValueError("Observation time is too far in the future")
        return value


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def rank(source, field):
    if field == "owner":
        return {"catalog": 100, "kubernetes": 60, "redfish": 20}.get(
            source.kind, source.priority
        )
    if field in {"serial", "model", "gpus", "rack"}:
        return {"redfish": 100, "kubernetes": 70, "catalog": 40}.get(
            source.kind, source.priority
        )
    return source.priority


def reconcile(db, now=None):
    now = now or utcnow()
    sources = {s.id: s for s in db.scalars(select(Source))}
    groups = defaultdict(list)
    for obs in db.scalars(select(Observation)):
        groups[obs.entity_id].append(obs)
    for entity_id, observations in groups.items():
        active = [o for o in observations if o.present]
        candidates = active or observations
        kinds = {o.kind for o in candidates}
        if len(kinds) != 1:
            raise ValueError(f"Conflicting entity kinds for {entity_id}")
        resolved, provenance, issues = {}, {}, []
        for field in sorted({f for o in candidates for f in o.fields}):
            values = [o for o in candidates if field in o.fields]
            values.sort(
                key=lambda o: (
                    -rank(sources[o.source_id], field),
                    -aware(o.observed_at).timestamp(),
                    o.source_id,
                )
            )
            chosen = values[0]
            resolved[field] = chosen.fields[field]
            provenance[field] = {
                "source": chosen.source_id,
                "observed_at": aware(chosen.observed_at).isoformat(),
            }
            if field == "owner" and len({str(o.fields[field]) for o in values}) > 1:
                issues.append(
                    {
                        "code": "owner_conflict",
                        "severity": "warning",
                        "message": "Sources disagree about ownership. The catalog owner is retained.",
                        "evidence": [
                            {"source": o.source_id, "value": o.fields[field]}
                            for o in values
                        ],
                    }
                )
        absent_sources = {o.source_id for o in observations if not o.present} - {
            o.source_id for o in active
        }
        if not active:
            issues.append(
                {
                    "code": "unobserved",
                    "severity": "warning",
                    "message": "Absent from the latest source snapshots; retained for lifecycle history.",
                }
            )
        elif absent_sources:
            issues.append(
                {
                    "code": "source_absent",
                    "severity": "warning",
                    "message": "A source no longer reports this record. Other observations are retained.",
                    "sources": sorted(absent_sources),
                }
            )
        if candidates[0].kind != "team" and not resolved.get("owner"):
            issues.append(
                {
                    "code": "missing_owner",
                    "severity": "critical",
                    "message": "No accountable team is recorded.",
                }
            )
        entity = db.get(Entity, entity_id)
        if entity and entity.resolved != resolved:
            changes = {
                k: {"before": entity.resolved.get(k), "after": resolved.get(k)}
                for k in set(entity.resolved) | set(resolved)
                if entity.resolved.get(k) != resolved.get(k)
            }
            db.add(Audit(entity_id=entity_id, action="entity.updated", detail=changes))
        if not entity:
            entity = Entity(
                id=entity_id,
                kind=candidates[0].kind,
                resolved={},
                provenance={},
                issues=[],
                updated_at=now,
            )
            db.add(entity)
            db.add(
                Audit(
                    entity_id=entity_id,
                    action="entity.discovered",
                    detail={"sources": sorted({o.source_id for o in candidates})},
                )
            )
        entity.resolved, entity.provenance, entity.issues, entity.updated_at = (
            resolved,
            provenance,
            issues,
            now,
        )
    db.flush()


def ingest(db, source_id, batch: Batch):
    source = db.get(Source, source_id)
    if not source:
        raise KeyError("Unknown source")
    digest = hashlib.sha256(
        json.dumps(batch.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()
    run_id = f"{source_id}:{batch.batch_id}"
    old_run = db.get(SyncRun, run_id)
    if old_run:
        if old_run.digest != digest:
            raise ValueError("Batch identifier reused with different content")
        return {"status": "duplicate", "records": old_run.records}
    if source.last_success and aware(batch.observed_at) < aware(source.last_success):
        return {"status": "out_of_order", "records": 0}
    ids = [r.external_id for r in batch.records]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate external identifiers in one batch")
    for record in batch.records:
        if record.entity_id.split(":", 1)[0] != record.kind:
            raise ValueError("Entity kind must match its canonical identifier")
        existing = db.get(Entity, record.entity_id)
        if existing and existing.kind != record.kind:
            raise ValueError("Canonical identity cannot change kind")
    if batch.full_snapshot:
        for obs in db.scalars(
            select(Observation).where(Observation.source_id == source_id)
        ):
            obs.present = 0
    for record in batch.records:
        key = f"{source_id}:{record.external_id}"
        obs = db.get(Observation, key)
        if obs and obs.entity_id != record.entity_id:
            raise ValueError(
                "An external identifier cannot silently change physical identity"
            )
        if not obs:
            obs = Observation(
                id=key,
                source_id=source_id,
                external_id=record.external_id,
                entity_id=record.entity_id,
                kind=record.kind,
                fields={},
                observed_at=batch.observed_at,
            )
            db.add(obs)
        obs.fields = record.fields
        obs.observed_at = batch.observed_at
        obs.present = 1
    source.last_success = batch.observed_at
    db.add(
        SyncRun(
            id=run_id,
            source_id=source_id,
            digest=digest,
            records=len(batch.records),
            observed_at=batch.observed_at,
        )
    )
    db.flush()
    reconcile(db)
    return {"status": "imported", "records": len(batch.records)}


def snapshot(db, now=None):
    now = now or utcnow()
    sources = []
    source_map = {}
    for s in db.scalars(select(Source).order_by(Source.id)):
        age = (now - aware(s.last_success)).total_seconds() if s.last_success else None
        item = {
            "id": s.id,
            "name": s.name,
            "kind": s.kind,
            "ttl_seconds": s.ttl_seconds,
            "age_seconds": round(max(0, age)) if age is not None else None,
            "stale": age is None or age > s.ttl_seconds,
            "last_success": aware(s.last_success).isoformat()
            if s.last_success
            else None,
        }
        sources.append(item)
        source_map[s.id] = item
    entities = []
    known = set(db.scalars(select(Entity.id)))
    edges = []
    for e in db.scalars(select(Entity).order_by(Entity.kind, Entity.id)):
        issues = list(e.issues)
        stale = sorted(
            {
                p["source"]
                for p in e.provenance.values()
                if source_map[p["source"]]["stale"]
            }
        )
        if stale:
            issues.append(
                {
                    "code": "stale_source",
                    "severity": "warning",
                    "message": "Some fields come from a stale source; current state is unknown.",
                    "sources": stale,
                }
            )
        for field, relation in [
            ("owner", "ownedBy"),
            ("cluster", "inCluster"),
            ("rack", "inRack"),
            ("dependsOn", "dependsOn"),
            ("runsOn", "runsOn"),
        ]:
            refs = e.resolved.get(field, [])
            if isinstance(refs, str):
                refs = [refs]
            for target in refs:
                edges.append({"source": e.id, "target": target, "type": relation})
                if target not in known:
                    issues.append(
                        {
                            "code": "dangling_reference",
                            "severity": "warning",
                            "message": f"Unknown {relation} target: {target}",
                        }
                    )
        entities.append(
            {
                "id": e.id,
                "kind": e.kind,
                **e.resolved,
                "provenance": e.provenance,
                "issues": issues,
                "updated_at": aware(e.updated_at).isoformat(),
            }
        )
    return {
        "entities": entities,
        "sources": sources,
        "edges": edges,
        "generated_at": now.isoformat(),
        "data_origin": "fictional fixture fleet; real reconciliation and persistence",
    }


def impact(data, entity_id):
    if entity_id not in {e["id"] for e in data["entities"]}:
        raise KeyError("Unknown entity")
    visited = {entity_id}
    paths = {entity_id: [entity_id]}
    changed = True
    while changed:
        changed = False
        for edge in data["edges"]:
            if (
                edge["type"] in {"runsOn", "dependsOn", "inRack", "inCluster"}
                and edge["target"] in visited
                and edge["source"] not in visited
            ):
                visited.add(edge["source"])
                paths[edge["source"]] = paths[edge["target"]] + [edge["source"]]
                changed = True
    services = [
        e for e in data["entities"] if e["id"] in visited and e["kind"] == "service"
    ]
    return {
        "entity_id": entity_id,
        "services": services,
        "paths": paths,
        "owners": sorted({s.get("owner") for s in services if s.get("owner")}),
        "interpretation": "Dependency exposure, not a prediction that every listed service will fail.",
    }


def backstage_export(data):
    import yaml

    docs = []
    for e in data["entities"]:
        name = re.sub(r"[^a-z0-9-]", "-", e["id"].lower()).strip("-")
        is_team = e["kind"] == "team"
        owner = re.sub(r"[^a-z0-9-]", "-", e.get("owner", "team:unassigned").lower())
        spec = (
            {"type": "team", "children": []}
            if is_team
            else {"type": e["kind"], "owner": f"group:default/{owner}"}
        )
        if e["kind"] == "service":
            spec["lifecycle"] = e.get("lifecycle", "experimental")
        dependencies = []
        for target in e.get("dependsOn", []) + e.get("runsOn", []):
            target_name = re.sub(r"[^a-z0-9-]", "-", target.lower()).strip("-")
            dependencies.append(
                ("component" if target.startswith("service:") else "resource")
                + ":default/"
                + target_name
            )
        if dependencies:
            spec["dependsOn"] = dependencies
        docs.append(
            {
                "apiVersion": "backstage.io/v1alpha1",
                "kind": "Group"
                if is_team
                else ("Component" if e["kind"] == "service" else "Resource"),
                "metadata": {
                    "name": name,
                    "title": e.get("name", e["id"]),
                    "annotations": {"fleet-atlas/canonical-id": e["id"]},
                },
                "spec": spec,
            }
        )
    return yaml.safe_dump_all(docs, sort_keys=False)
