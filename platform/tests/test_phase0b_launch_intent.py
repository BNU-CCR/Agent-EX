from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError

import pytest

from agent_ex.domain import canonical_payload_hash
from agent_ex.phase0b.launch_intent import Phase0BLaunchIntent


SHA = "a" * 64
ARTIFACT_KEYS = (
    "topic",
    "population",
    "persona",
    "network",
    "shadow",
    "mapping",
    "attention",
    "expression",
    "activation",
    "publish",
    "schedule",
)


def _intent(**overrides: object) -> Phase0BLaunchIntent:
    args: dict[str, object] = {
        "source_commit": "b" * 40,
        "source_bundle_hash": SHA,
        "candidate_config_hash": SHA,
        "artifact_hashes": {key: SHA for key in ARTIFACT_KEYS},
        "model_repository": "Qwen/Qwen3-8B",
        "model_revision": "c" * 40,
        "tokenizer_revision": "d" * 40,
        "environment_lock_hash": SHA,
        "service_config_hash": SHA,
        "preflight_archive_uri": "/root/autodl-tmp/agent-ex-phase0b-preflight-v1",
        "full_run_archive_uri": "/root/autodl-tmp/agent-ex-phase0b-full-v1",
    }
    args.update(overrides)
    return Phase0BLaunchIntent.create(**args)  # type: ignore[arg-type]


def _rehash(payload: dict[str, object]) -> dict[str, object]:
    payload["record_hash"] = canonical_payload_hash(
        {name: value for name, value in payload.items() if name != "record_hash"}
    )
    return payload


def test_launch_intent_roundtrip_and_pre_service_metadata() -> None:
    intent = _intent()
    payload = intent.to_payload()

    assert Phase0BLaunchIntent.from_payload(payload) == intent
    assert intent.record_hash == canonical_payload_hash(intent.content_payload())
    assert intent.service_manifest_hash == intent.record_hash
    assert intent.calibration_only is True
    assert intent.formal_parameter_authority is False
    assert intent.research_parameter_status == "not_frozen"
    assert "service_start_identity_hash" not in payload
    assert "final_authorization_hash" not in payload
    with pytest.raises(FrozenInstanceError):
        intent.source_commit = "e" * 40  # type: ignore[misc]


def test_launch_intent_rejects_tampered_hash_and_extra_identity_field() -> None:
    payload = _intent().to_payload()
    payload["source_bundle_hash"] = "e" * 64
    with pytest.raises(ValueError, match="record_hash"):
        Phase0BLaunchIntent.from_payload(payload)

    payload = _intent().to_payload()
    payload["service_start_identity_hash"] = SHA
    with pytest.raises(ValueError, match="exact fields"):
        Phase0BLaunchIntent.from_payload(payload)

    payload = _intent().to_payload()
    payload["final_authorization_hash"] = SHA
    with pytest.raises(ValueError, match="exact fields"):
        Phase0BLaunchIntent.from_payload(payload)


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("source_commit", "f" * 39),
        ("source_bundle_hash", "F" * 64),
        ("candidate_config_hash", "UNRESOLVED[P1_CONFIG]"),
        ("model_revision", "main"),
        ("tokenizer_revision", "UNRESOLVED[P1_TOKENIZER]"),
        ("environment_lock_hash", "0" * 63),
        ("service_config_hash", "pending"),
    ],
)
def test_launch_intent_rejects_unpinned_inputs(field: str, bad_value: str) -> None:
    with pytest.raises((TypeError, ValueError)):
        _intent(**{field: bad_value})


def test_launch_intent_rejects_incomplete_or_mutated_artifact_inventory() -> None:
    missing = {key: SHA for key in ARTIFACT_KEYS if key != "schedule"}
    with pytest.raises(ValueError, match="artifact"):
        _intent(artifact_hashes=missing)

    payload = _intent().to_payload()
    hashes = payload["artifact_hashes"]
    assert isinstance(hashes, dict)
    hashes["topic"] = "UNRESOLVED[P1_TOPIC]"
    with pytest.raises(ValueError, match="UNRESOLVED"):
        Phase0BLaunchIntent.from_payload(_rehash(payload))

    original = {key: SHA for key in ARTIFACT_KEYS}
    intent = _intent(artifact_hashes=original)
    original["topic"] = "e" * 64
    assert intent.artifact_hashes["topic"] == SHA
    with pytest.raises(TypeError):
        intent.artifact_hashes["topic"] = "e" * 64  # type: ignore[index]


@pytest.mark.parametrize(
    "preflight,full",
    [
        ("reports/preflight", "/root/autodl-tmp/full"),
        ("/root/autodl-tmp/../repo/preflight", "/root/autodl-tmp/full"),
        ("/root/autodl-tmp/shared", "/root/autodl-tmp/shared"),
        ("/root/autodl-tmp/shared", "/root/autodl-tmp/shared/full"),
        ("/root/autodl-tmp/preflight", "./full"),
        ("s3://bucket/phase0b", "s3://bucket/phase0b/full"),
        ("s3://user:pass@bucket/preflight", "s3://bucket/full"),
    ],
)
def test_launch_intent_requires_disjoint_external_archive_roots(preflight: str, full: str) -> None:
    with pytest.raises(ValueError, match="archive"):
        _intent(preflight_archive_uri=preflight, full_run_archive_uri=full)


def test_launch_intent_rejects_wrong_metadata_and_non_json_transport() -> None:
    payload = deepcopy(_intent().to_payload())
    payload["formal_parameter_authority"] = True
    with pytest.raises(ValueError, match="formal parameter authority"):
        Phase0BLaunchIntent.from_payload(_rehash(payload))

    payload = _intent().to_payload()
    payload["artifact_hashes"] = tuple(payload["artifact_hashes"].items())  # type: ignore[union-attr]
    with pytest.raises(TypeError, match="JSON"):
        Phase0BLaunchIntent.from_payload(payload)
