from datetime import timedelta
import pytest
import yaml
from pydantic import ValidationError
from sqlalchemy import select, func
from fleetlab.catalog import Batch, Record, ingest, snapshot, impact, backstage_export
from fleetlab.fixtures import fixture_records, scenario, record
from fleetlab.models import Entity, Audit, utcnow


def test_baseline_has_one_record_per_physical_identity(factory):
    with factory() as db:
        data = snapshot(db)
        assert len(data["entities"]) == 27
        assert len([e for e in data["entities"] if e["kind"] == "node"]) == 12
        assert sum(e.get("gpus", 0) for e in data["entities"]) == 96
        assert not any(e["issues"] for e in data["entities"])


def test_same_batch_replay_is_idempotent(factory):
    batch = Batch(
        batch_id="same", observed_at=utcnow(), records=fixture_records()["redfish-bmc"]
    )
    with factory.begin() as db:
        assert ingest(db, "redfish-bmc", batch)["status"] == "imported"
        history = db.scalar(select(func.count()).select_from(Audit))
        assert ingest(db, "redfish-bmc", batch)["status"] == "duplicate"
        assert db.scalar(select(func.count()).select_from(Audit)) == history
        assert db.scalar(select(func.count()).select_from(Entity)) == 27


def test_source_alias_change_does_not_claim_entity_disappeared(factory):
    records = fixture_records()["redfish-bmc"]
    for item in records:
        if item["entity_id"] == "node:FTL-A11":
            item["external_id"] = "new-bmc-system-id"
    with factory.begin() as db:
        ingest(
            db,
            "redfish-bmc",
            Batch(batch_id="alias-changed", observed_at=utcnow(), records=records),
        )
        data = snapshot(db)
        nodes = [e for e in data["entities"] if e["id"] == "node:FTL-A11"]
        assert len(nodes) == 1
        assert not any(i["code"] == "source_absent" for i in nodes[0]["issues"])


def test_reused_batch_id_with_different_payload_rejected(factory):
    now = utcnow()
    with factory.begin() as db:
        ingest(db, "redfish-bmc", Batch(batch_id="reuse", observed_at=now, records=[]))
    with pytest.raises(ValueError, match="different content"), factory.begin() as db:
        ingest(
            db,
            "redfish-bmc",
            Batch(
                batch_id="reuse",
                observed_at=now,
                records=fixture_records()["redfish-bmc"],
            ),
        )


def test_older_snapshot_cannot_roll_back_newer_data(factory):
    with factory.begin() as db:
        result = ingest(
            db,
            "kubernetes",
            Batch(batch_id="old", observed_at=utcnow() - timedelta(days=1), records=[]),
        )
        assert result["status"] == "out_of_order"
        assert len(snapshot(db)["entities"]) == 27


def test_owner_authority_preserves_conflicting_evidence(factory):
    with factory.begin() as db:
        scenario(db, "ownership-conflict")
        worker = next(
            e for e in snapshot(db)["entities"] if e["id"] == "service:worker"
        )
        assert worker["owner"] == "team:inference"
        assert worker["provenance"]["owner"]["source"] == "service-catalog"
        assert next(i for i in worker["issues"] if i["code"] == "owner_conflict")[
            "evidence"
        ]


def test_stale_source_is_unknown_not_hardware_failure(factory):
    with factory.begin() as db:
        scenario(db, "stale-source")
        node = next(e for e in snapshot(db)["entities"] if e["id"] == "node:FTL-A11")
        assert node["health"] == "healthy"
        assert any(i["code"] == "stale_source" for i in node["issues"])


def test_source_disappearance_retains_entity(factory):
    with factory.begin() as db:
        scenario(db, "missing-node")
        node = next(e for e in snapshot(db)["entities"] if e["id"] == "node:FTL-A11")
        assert any(i["code"] == "source_absent" for i in node["issues"])


def test_absent_from_all_snapshots_retains_lifecycle_history(factory):
    with factory.begin() as db:
        for source in ["kubernetes", "redfish-bmc"]:
            ingest(
                db, source, Batch(batch_id="empty", observed_at=utcnow(), records=[])
            )
        node = next(e for e in snapshot(db)["entities"] if e["id"] == "node:FTL-A11")
        assert any(i["code"] == "unobserved" for i in node["issues"])


def test_transitive_impact_finds_services_and_teams(factory):
    with factory() as db:
        data = impact(snapshot(db), "node:FTL-A11")
        assert {s["id"] for s in data["services"]} == {
            "service:gateway",
            "service:scheduler",
            "service:worker",
            "service:embeddings",
        }
        assert data["owners"] == ["team:inference", "team:platform"]
        assert data["paths"]["service:gateway"][0] == "node:FTL-A11"


def test_dependency_cycles_terminate(factory):
    with factory() as db:
        data = snapshot(db)
        data["edges"].append(
            {
                "source": "service:worker",
                "target": "service:gateway",
                "type": "dependsOn",
            }
        )
        result = impact(data, "node:FTL-A11")
        assert len(result["services"]) == 4


def test_unknown_impact_target_is_error(factory):
    with factory() as db:
        with pytest.raises(KeyError):
            impact(snapshot(db), "node:missing")


def test_change_creates_audit_entry(factory):
    with factory.begin() as db:
        scenario(db, "node-degraded")
        changes = list(
            db.scalars(
                select(Audit).where(
                    Audit.entity_id == "node:FTL-A11", Audit.action == "entity.updated"
                )
            )
        )
        assert changes[-1].detail["health"]["after"] == "degraded"


def test_backstage_export_contains_valid_owners_and_dependencies(factory):
    with factory() as db:
        docs = list(yaml.safe_load_all(backstage_export(snapshot(db))))
        assert len(docs) == 27
        names = {d["metadata"]["name"] for d in docs}
        for doc in docs:
            assert doc["apiVersion"] == "backstage.io/v1alpha1"
            if "owner" in doc["spec"]:
                assert doc["spec"]["owner"].split("/")[-1] in names
        gateway = next(d for d in docs if d["metadata"]["name"] == "service-gateway")
        assert "component:default/service-scheduler" in gateway["spec"]["dependsOn"]


def test_missing_owner_is_visible(factory):
    with factory.begin() as db:
        ingest(
            db,
            "service-catalog",
            Batch(
                batch_id="orphan",
                observed_at=utcnow(),
                full_snapshot=False,
                records=[record("service:orphan", "service", name="Orphan")],
            ),
        )
        e = next(e for e in snapshot(db)["entities"] if e["id"] == "service:orphan")
        assert any(i["code"] == "missing_owner" for i in e["issues"])


def test_dangling_dependency_is_visible(factory):
    with factory.begin() as db:
        ingest(
            db,
            "service-catalog",
            Batch(
                batch_id="dangling",
                observed_at=utcnow(),
                full_snapshot=False,
                records=[
                    record(
                        "service:new",
                        "service",
                        name="New",
                        owner="team:platform",
                        dependsOn=["service:unknown"],
                    )
                ],
            ),
        )
        e = next(e for e in snapshot(db)["entities"] if e["id"] == "service:new")
        assert any(i["code"] == "dangling_reference" for i in e["issues"])


def test_duplicate_external_ids_roll_back(factory):
    r = fixture_records()["redfish-bmc"][0]
    with pytest.raises(ValueError, match="Duplicate external"), factory.begin() as db:
        ingest(
            db,
            "redfish-bmc",
            Batch(batch_id="bad", observed_at=utcnow(), records=[r, r]),
        )
    with factory() as db:
        assert len(snapshot(db)["entities"]) == 27


def test_external_identity_cannot_silently_change(factory):
    r = fixture_records()["redfish-bmc"][0]
    r["entity_id"] = "node:replacement"
    with pytest.raises(ValueError, match="physical identity"), factory.begin() as db:
        ingest(
            db,
            "redfish-bmc",
            Batch(batch_id="swapped", observed_at=utcnow(), records=[r]),
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("script", "x"),
        ("runbook", "javascript:alert(1)"),
        ("repository", "http://insecure.example"),
        ("gpus", -1),
        ("dependsOn", "service:one"),
        ("name", "x" * 2001),
    ],
)
def test_invalid_fields_are_rejected(field, value):
    with pytest.raises(ValidationError):
        Record(external_id="x", entity_id="node:x", kind="node", fields={field: value})


def test_future_observations_rejected():
    with pytest.raises(ValidationError):
        Batch(batch_id="future", observed_at=utcnow() + timedelta(hours=1), records=[])


def test_naive_observation_timestamp_rejected():
    with pytest.raises(ValidationError):
        Batch(batch_id="naive", observed_at=utcnow().replace(tzinfo=None), records=[])


def test_unknown_source_rejected(factory):
    with factory() as db:
        with pytest.raises(KeyError):
            ingest(
                db,
                "unknown",
                Batch(batch_id="unknown", observed_at=utcnow(), records=[]),
            )
