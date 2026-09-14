from fleetlab.reports import public_result


def test_public_evidence_omits_machine_metadata_without_changing_delivery():
    original = {
        "delivery": {"traces_received": 0, "traces_sent": 12},
        "logs": [
            {
                "metadata": {
                    "code_file_path": "/local/workload.py",
                    "host_name": "workstation",
                    "service_name": "worker",
                }
            }
        ],
        "tags": [
            {"key": "host.name", "value": "workstation"},
            {"key": "service.name", "value": "worker"},
        ],
        "assertions": {"loss_observed": True},
    }
    result = public_result(original)
    assert result["delivery"] == original["delivery"]
    assert result["assertions"] == original["assertions"]
    assert result["logs"] == [{"metadata": {"service_name": "worker"}}]
    assert result["tags"] == [{"key": "service.name", "value": "worker"}]
    assert original["logs"][0]["metadata"]["host_name"] == "workstation"
