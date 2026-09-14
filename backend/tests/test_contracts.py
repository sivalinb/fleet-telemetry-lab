import pytest
from fleetlab.contracts import resource_for, validate_telemetry
from fleetlab.telemetry import parse_collector_metrics


def test_standard_resource_and_bounded_labels_pass():
    assert validate_telemetry(
        resource_for("gateway"), {"profile": "bounded", "operation": "work"}
    )["valid"]


@pytest.mark.parametrize(
    "label", ["request_id", "user_id", "session_id", "email", "prompt"]
)
def test_unbounded_labels_fail(label):
    r = validate_telemetry(resource_for("gateway"), {label: "value"})
    assert not r["valid"] and r["errors"][0]["code"] == "unbounded_label"


@pytest.mark.parametrize(
    "field",
    [
        "service.name",
        "service.namespace",
        "deployment.environment.name",
        "k8s.cluster.name",
        "team.owner",
    ],
)
def test_required_resource_attributes(field):
    resource = resource_for("gateway")
    del resource[field]
    assert not validate_telemetry(resource, {})["valid"]


def test_label_budget():
    assert not validate_telemetry(
        resource_for("gateway"), {str(i): str(i) for i in range(13)}
    )["valid"]


def test_counter_parser_sums_signal_queues_and_ignores_comments():
    text = '# HELP ignored\notelcol_exporter_queue_size{exporter="logs"} 4\notelcol_exporter_queue_size{exporter="traces"} 2\notelcol_receiver_accepted_spans_total{receiver="otlp"} 36\n'
    assert parse_collector_metrics(text)["queued_batches"] == 6
    assert parse_collector_metrics(text)["accepted_spans"] == 36
    assert parse_collector_metrics("not a metric") is None
