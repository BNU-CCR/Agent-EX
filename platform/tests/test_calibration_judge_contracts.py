from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from agent_ex.calibration.judge_contracts import (
    DIMENSIONS,
    VISIBLE_FIELDS,
    JudgeAuthorization,
    JudgeExecutionManifest,
    JudgePreflightEvidence,
    JudgePreManifestAbortEvidence,
    JudgeRunCompletion,
    JudgeServiceEvidence,
    JudgeRequestRenderer,
    RenderedJudgeRequest,
    derive_judge_seed,
)
from agent_ex.calibration.environment import EnvironmentLock
from agent_ex.calibration.review import BlindReviewItem, SemanticReviewPolicy
from agent_ex.domain import canonical_payload_hash
from test_calibration_environment import valid_observation


PLATFORM_ROOT = Path(__file__).parents[1]
POLICY_PATH = (
    PLATFORM_ROOT
    / "configs"
    / "paper1"
    / "phase0a1-approval-proposal-v2"
    / "semantic_review_policy.json"
)
GOLDEN_FIXTURE = (
    Path(__file__).parent / "fixtures" / "paper1" / "phase0a1_judge_rendered_request.golden.json"
)
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
SHA_F = "f" * 64
SOURCE_COMMIT = "1" * 40


def manifest_values_from_authorization(
    authorization: JudgeAuthorization,
) -> dict[str, object]:
    return {
        "review_bundle_hash": authorization.review_bundle_hash,
        "export_hash": authorization.export_hash,
        "judge_pack_hash": authorization.judge_pack_hash,
        "judge_pack_index_hash": authorization.judge_pack_index_hash,
        "judge_coder_contract_hash": authorization.coder_contract_hash,
        "old_judge_prompt_hash": authorization.old_judge_prompt_hash,
        "renderer_hash": authorization.renderer_hash,
        "ordering_policy_hash": authorization.ordering_policy_hash,
        "classifier_contract_hash": authorization.classifier_contract_hash,
        "model_id": authorization.model_id,
        "model_revision": authorization.model_revision,
        "model_artifacts_hash": authorization.model_artifacts_hash,
        "tokenizer_id": authorization.tokenizer_id,
        "tokenizer_revision": authorization.tokenizer_revision,
        "tokenizer_hash": authorization.tokenizer_hash,
        "tokenizer_artifacts_hash": authorization.tokenizer_artifacts_hash,
        "chat_template_hash": authorization.chat_template_hash,
        "runtime_version": authorization.runtime_version,
        "non_thinking": authorization.non_thinking,
        "generation_settings": authorization.generation_settings,
        "connect_timeout_seconds": authorization.connect_timeout_seconds,
        "read_timeout_seconds": authorization.read_timeout_seconds,
        "total_timeout_seconds": authorization.total_timeout_seconds,
        "retryable_codes": authorization.retryable_codes,
        "retry_backoff_seconds": authorization.retry_backoff_seconds,
        "max_attempts_per_item": authorization.max_attempts_per_item,
        "one_item_per_request": authorization.one_item_per_request,
        "strict_approved_order": authorization.strict_approved_order,
        "archive_uri": authorization.archive_uri,
        "source_commit": authorization.source_commit,
    }


@pytest.fixture
def policy() -> SemanticReviewPolicy:
    return SemanticReviewPolicy.from_payload(json.loads(POLICY_PATH.read_text(encoding="utf-8")))


@pytest.fixture
def item(policy: SemanticReviewPolicy) -> BlindReviewItem:
    return BlindReviewItem.create(
        item_id="blind-item-golden-001",
        policy_hash=policy.record_hash,
        visible_payload={
            "topic_text": "延迟退休是否合适？\n请只判断同一构念。",
            "history_text": "",
            "identity_text": '职业：教师；备注含引号 \\"与反斜杠 \\\\ ',
            "response_text": "我倾向支持，但会根据新证据调整。\tEND",
        },
    )


def golden_fixture_content(item: BlindReviewItem) -> dict[str, object]:
    return {
        "schema_version": "paper1.calibration.judge-rendered-request-golden-input.v1",
        "item": item.to_payload(),
        "attempt_index": 1,
        "repair": False,
    }


def ordered_json_identity(value: object) -> object:
    if isinstance(value, dict):
        return [["mapping-entry", key, ordered_json_identity(item)] for key, item in value.items()]
    if isinstance(value, list):
        return [["sequence-item", ordered_json_identity(item)] for item in value]
    return ["scalar", type(value).__name__, value]


def rehash_rendered_request_v3(payload: dict[str, object]) -> None:
    payload["response_schema_order_hash"] = canonical_payload_hash(
        ordered_json_identity(payload["response_schema"])
    )
    identity_hash = canonical_payload_hash(
        {
            "renderer_hash": payload["renderer_hash"],
            "item_id": payload["item_id"],
            "item_hash": payload["item_hash"],
            "visible_payload_hash": payload["visible_payload_hash"],
            "attempt_index": payload["attempt_index"],
            "repair": payload["repair"],
            "visible_fields_hash": canonical_payload_hash(payload["visible_fields"]),
            "messages_hash": canonical_payload_hash(payload["messages"]),
            "response_schema_order_hash": payload["response_schema_order_hash"],
            "generation_settings_hash": canonical_payload_hash(payload["generation_settings"]),
            "response_byte_ceiling": payload["response_byte_ceiling"],
        }
    )
    payload["request_id"] = "judge-request-" + identity_hash
    payload["idempotency_key"] = "judge-idempotency-" + identity_hash
    payload["record_hash"] = canonical_payload_hash(
        {name: value for name, value in payload.items() if name != "record_hash"}
    )


def rehash_record(payload: dict[str, object]) -> None:
    payload["record_hash"] = canonical_payload_hash(
        {name: value for name, value in payload.items() if name != "record_hash"}
    )


def reorder_response_schema(payload: dict[str, object], mutation: str) -> None:
    schema = payload["response_schema"]
    if mutation == "top_level":
        payload["response_schema"] = {name: schema[name] for name in reversed(tuple(schema))}
    elif mutation == "properties":
        properties = schema["properties"]
        schema["properties"] = {name: properties[name] for name in reversed(tuple(properties))}
    else:
        schema["required"] = list(reversed(schema["required"]))


@pytest.fixture
def renderer(policy: SemanticReviewPolicy, item: BlindReviewItem) -> JudgeRequestRenderer:
    return JudgeRequestRenderer.create(
        policy,
        chat_template_hash=SHA_A,
        response_byte_ceiling=16_384,
        generation_settings={
            "temperature": 0.0,
            "top_p": 1.0,
            "max_tokens": 512,
        },
        golden_fixture_content=golden_fixture_content(item),
    )


def authorization_payload(renderer: JudgeRequestRenderer) -> dict[str, object]:
    content = {
        "schema_version": "paper1.calibration.judge-authorization.v1",
        "authorization_id": "judge-authorization-test-001",
        "export_hash": SHA_A,
        "review_bundle_hash": SHA_B,
        "judge_pack_hash": SHA_C,
        "judge_pack_index_hash": SHA_D,
        "old_judge_prompt_hash": SHA_E,
        "renderer_hash": renderer.record_hash,
        "coder_contract_hash": SHA_F,
        "ordering_policy_hash": SHA_A,
        "classifier_contract_hash": SHA_B,
        "old_environment_lock_hash": SHA_C,
        "model_id": "qwen3-8b-paper1",
        "model_revision": "b968826d9c46dd6066d109eabc6255188de91218",
        "tokenizer_id": "qwen3-8b-paper1-tokenizer",
        "tokenizer_revision": "b968826d9c46dd6066d109eabc6255188de91218",
        "tokenizer_hash": SHA_D,
        "model_artifacts_hash": SHA_E,
        "tokenizer_artifacts_hash": SHA_F,
        "chat_template_hash": SHA_A,
        "runtime_provider": "vllm-loopback",
        "runtime_version": "0.23.0-cu129",
        "endpoint_url": "http://127.0.0.1:8000/v1/chat/completions",
        "non_thinking": True,
        "connect_timeout_seconds": 10.0,
        "read_timeout_seconds": 120.0,
        "total_timeout_seconds": 150.0,
        "max_attempts_per_item": 3,
        "retryable_codes": ["timeout", "http_429", "invalid_json"],
        "retry_backoff_seconds": [1.0, 2.0],
        "request_identity_derivation": "judge-request-ordered-rendered-contract-v3",
        "idempotency_key_derivation": "judge-idempotency-ordered-rendered-contract-v3",
        "one_item_per_request": True,
        "strict_approved_order": True,
        "generation_settings": {
            "temperature": 0.0,
            "top_p": 1.0,
            "max_tokens": 512,
        },
        "archive_uri": "/root/autodl-tmp/agent-ex-phase0a1-judge-test",
        "source_commit": SOURCE_COMMIT,
        "metadata": {
            "calibration_only": True,
            "formal_parameter_authority": False,
            "research_parameter_status": "not_frozen",
        },
    }
    return {**content, "record_hash": canonical_payload_hash(content)}


@pytest.fixture
def valid_lifecycle(renderer: JudgeRequestRenderer) -> dict[str, object]:
    observation = valid_observation()
    payload = authorization_payload(renderer)
    payload["chat_template_hash"] = observation.chat_template_hash
    payload["runtime_version"] = observation.vllm_identity.version
    payload["model_id"] = observation.model_repository
    payload["tokenizer_id"] = observation.tokenizer_repository
    payload["model_artifacts_hash"] = EnvironmentLock.create(
        observation, authorization_hash=SHA_A
    ).model_artifacts_hash
    payload["tokenizer_artifacts_hash"] = EnvironmentLock.create(
        observation, authorization_hash=SHA_A
    ).tokenizer_artifacts_hash
    payload["record_hash"] = canonical_payload_hash(
        {name: value for name, value in payload.items() if name != "record_hash"}
    )
    authorization = JudgeAuthorization.from_payload(payload)
    environment_lock = EnvironmentLock.create(
        observation,
        authorization_hash=authorization.record_hash,
    )
    return {
        "run_id": "judge-run-test-001",
        "authorization": authorization,
        "environment_lock": environment_lock,
        "preflight_hash": SHA_A,
        "service_start_identity_hash": SHA_B,
        "runner_view_hash": SHA_C,
        **manifest_values_from_authorization(authorization),
    }


def distinct_valid_value(field: str, value: object) -> object:
    if field in {
        "review_bundle_hash",
        "export_hash",
        "judge_pack_hash",
        "judge_pack_index_hash",
        "judge_coder_contract_hash",
        "old_judge_prompt_hash",
        "renderer_hash",
        "ordering_policy_hash",
        "classifier_contract_hash",
        "model_artifacts_hash",
        "tokenizer_hash",
        "tokenizer_artifacts_hash",
        "chat_template_hash",
    }:
        return SHA_F if value != SHA_F else SHA_E
    if field == "source_commit":
        return "2" * 40
    if field in {"non_thinking", "one_item_per_request", "strict_approved_order"}:
        return not value
    if field == "generation_settings":
        return {"temperature": 0.1, "top_p": 1.0, "max_tokens": 512}
    if field == "retryable_codes":
        return (*value, "http_503")
    if field == "retry_backoff_seconds":
        return (3.0, 4.0)
    if field == "max_attempts_per_item":
        return int(value) + 1
    if field in {
        "connect_timeout_seconds",
        "read_timeout_seconds",
        "total_timeout_seconds",
    }:
        return float(value) + 1.0
    if field == "archive_uri":
        return "/root/autodl-tmp/agent-ex-phase0a1-judge-drift"
    return f"{value}-drift"


def test_renderer_golden_binds_roles_schema_labels_and_seed(
    renderer: JudgeRequestRenderer, item: BlindReviewItem
) -> None:
    rendered = renderer.render(item, attempt_index=1, repair=False)
    assert tuple(message["role"] for message in rendered.messages) == ("system", "user")
    assert tuple(rendered.response_schema["properties"]) == DIMENSIONS
    assert tuple(renderer.dimension_labels) == DIMENSIONS
    assert renderer.visible_fields == VISIBLE_FIELDS
    assert renderer.canonical_json_version == "agent-ex-renderer-json-utf8-declared-order-v1"
    assert rendered.seed == derive_judge_seed(renderer.record_hash, item.item_id, 1)
    assert rendered.record_hash == canonical_payload_hash(rendered.content_payload())
    fixture = json.loads(GOLDEN_FIXTURE.read_text(encoding="utf-8"))
    assert set(fixture) == {
        "fixture_content",
        "fixture_content_hash",
        "rendered_request",
        "record_hash",
    }
    assert fixture["fixture_content"] == golden_fixture_content(item)
    assert "renderer_hash" not in fixture["fixture_content"]
    assert "rendered_request" not in fixture["fixture_content"]
    assert fixture["fixture_content_hash"] == canonical_payload_hash(fixture["fixture_content"])
    assert renderer.golden_fixture_hash == fixture["fixture_content_hash"]
    assert dict(renderer.golden_fixture_content) == fixture["fixture_content"]
    assert rendered.to_payload() == fixture["rendered_request"]
    assert rendered.record_hash == fixture["record_hash"]
    renderer.verify_fixture(item, fixture)


@pytest.mark.parametrize("missing", ["golden_fixture_content", "golden_fixture_hash"])
def test_renderer_payload_rejects_missing_golden_fixture_binding(
    renderer: JudgeRequestRenderer, missing: str
) -> None:
    payload = renderer.to_payload()
    del payload[missing]
    with pytest.raises(ValueError, match="exact fields"):
        JudgeRequestRenderer.from_payload(payload)


@pytest.mark.parametrize("mutation", ["hash", "content"])
def test_renderer_payload_rejects_rehashed_golden_fixture_drift(
    renderer: JudgeRequestRenderer, mutation: str
) -> None:
    payload = renderer.to_payload()
    if mutation == "hash":
        payload["golden_fixture_hash"] = SHA_F
    else:
        payload["golden_fixture_content"]["attempt_index"] = 2
    payload["record_hash"] = canonical_payload_hash(
        {name: value for name, value in payload.items() if name != "record_hash"}
    )
    with pytest.raises(ValueError, match="golden_fixture_hash|golden fixture"):
        JudgeRequestRenderer.from_payload(payload)


@pytest.mark.parametrize("mutation", ["missing", "hash_drift"])
def test_checked_in_fixture_rejects_missing_or_drifted_content_hash(
    renderer: JudgeRequestRenderer, item: BlindReviewItem, mutation: str
) -> None:
    fixture = json.loads(GOLDEN_FIXTURE.read_text(encoding="utf-8"))
    if mutation == "missing":
        del fixture["fixture_content_hash"]
    else:
        fixture["fixture_content_hash"] = SHA_F
    with pytest.raises(ValueError, match="fixture|hash|exact fields"):
        renderer.verify_fixture(item, fixture)


def test_renderer_round_trip_is_strict_and_immutable(
    renderer: JudgeRequestRenderer, item: BlindReviewItem
) -> None:
    round_trip = JudgeRequestRenderer.from_payload(renderer.to_payload())
    rendered = RenderedJudgeRequest.from_payload(renderer.render(item, 2, repair=True).to_payload())
    assert round_trip == renderer
    assert rendered == renderer.render(item, 2, repair=True)
    with pytest.raises(TypeError):
        round_trip.generation_settings["temperature"] = 0.7  # type: ignore[index]
    with pytest.raises(TypeError):
        rendered.messages[0]["role"] = "user"  # type: ignore[index]


@pytest.mark.parametrize("numeric_false", [0, 0.0])
def test_renderer_from_payload_rejects_bool_numeric_schema_normalization_attack(
    renderer: JudgeRequestRenderer, numeric_false: object
) -> None:
    payload = renderer.to_payload()
    payload["response_schema"]["additionalProperties"] = numeric_false
    with pytest.raises(ValueError, match="record_hash|record hash|response schema"):
        JudgeRequestRenderer.from_payload(payload)


@pytest.mark.parametrize("mutation", ["top_level", "properties", "required"])
def test_renderer_from_payload_rejects_response_schema_order_tamper(
    renderer: JudgeRequestRenderer, mutation: str
) -> None:
    payload = renderer.to_payload()
    reorder_response_schema(payload, mutation)
    payload["record_hash"] = canonical_payload_hash(
        {name: value for name, value in payload.items() if name != "record_hash"}
    )
    with pytest.raises(ValueError, match="response schema|order"):
        JudgeRequestRenderer.from_payload(payload)


@pytest.mark.parametrize("mutation", ["top_level", "properties", "required"])
def test_rendered_request_from_payload_rejects_response_schema_order_tamper(
    renderer: JudgeRequestRenderer,
    item: BlindReviewItem,
    mutation: str,
) -> None:
    payload = renderer.render(item, 1, repair=False).to_payload()
    reorder_response_schema(payload, mutation)
    rehash_rendered_request_v3(payload)
    with pytest.raises(ValueError, match="response schema|order"):
        RenderedJudgeRequest.from_payload(payload)


def test_seed_request_and_idempotency_are_deterministic_per_item_attempt(
    renderer: JudgeRequestRenderer, item: BlindReviewItem
) -> None:
    first = renderer.render(item, 1, repair=False)
    repeated = renderer.render(item, 1, repair=False)
    next_attempt = renderer.render(item, 2, repair=False)
    repair = renderer.render(item, 1, repair=True)
    assert first == repeated
    assert len({first.request_id, next_attempt.request_id, repair.request_id}) == 3
    assert len({first.idempotency_key, next_attempt.idempotency_key, repair.idempotency_key}) == 3
    assert first.seed != next_attempt.seed


def test_judge_seed_is_always_vllm_signed_int64_safe(
    renderer: JudgeRequestRenderer, item: BlindReviewItem
) -> None:
    assert renderer.seed_derivation == "sha256-canonical-renderer-item-attempt-signed63-v2"
    seeds = (
        derive_judge_seed(renderer.record_hash, item.item_id, attempt_index)
        for attempt_index in range(1, 257)
    )
    assert all(0 <= seed <= 2**63 - 1 for seed in seeds)


def test_request_identity_binds_item_hash_visible_hash_and_rendered_contract(
    renderer: JudgeRequestRenderer,
    item: BlindReviewItem,
) -> None:
    changed_visible = dict(item.visible_payload)
    changed_visible["response_text"] += " changed"
    changed_item = BlindReviewItem.create(
        item_id=item.item_id,
        policy_hash=item.policy_hash,
        visible_payload=changed_visible,
    )
    original = renderer.render(item, 1, repair=False)
    changed = renderer.render(changed_item, 1, repair=False)
    assert original.item_hash != changed.item_hash
    assert original.visible_payload_hash != changed.visible_payload_hash
    assert original.messages != changed.messages
    assert original.request_id != changed.request_id
    assert original.idempotency_key != changed.idempotency_key


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("seed", 123456789),
        ("request_id", "judge-request-" + "1" * 64),
        ("idempotency_key", "judge-idempotency-" + "2" * 64),
    ],
)
def test_rendered_request_rejects_rehashed_derived_identity_tamper(
    renderer: JudgeRequestRenderer,
    item: BlindReviewItem,
    field: str,
    value: object,
) -> None:
    payload = renderer.render(item, 1, repair=False).to_payload()
    payload[field] = value
    payload["record_hash"] = canonical_payload_hash(
        {name: field_value for name, field_value in payload.items() if name != "record_hash"}
    )
    with pytest.raises(ValueError, match=field):
        RenderedJudgeRequest.from_payload(payload)


@pytest.mark.parametrize(
    "field",
    ["item_hash", "visible_payload_hash", "messages", "response_schema"],
)
def test_rendered_request_identity_rejects_rehashed_bound_input_tamper(
    renderer: JudgeRequestRenderer,
    item: BlindReviewItem,
    field: str,
) -> None:
    payload = renderer.render(item, 1, repair=False).to_payload()
    if field in {"item_hash", "visible_payload_hash"}:
        payload[field] = SHA_F
    elif field == "messages":
        payload[field][1]["content"] += " tampered"
    else:
        payload[field]["properties"]["refusal"]["enum"][0] = "tampered"
    payload["record_hash"] = canonical_payload_hash(
        {name: value for name, value in payload.items() if name != "record_hash"}
    )
    with pytest.raises(ValueError, match="request_id|response_schema_order_hash"):
        RenderedJudgeRequest.from_payload(payload)


@pytest.mark.parametrize("attempt_index", [0, -1, True, 1.0])
def test_seed_rejects_invalid_attempt_index(attempt_index: object) -> None:
    with pytest.raises((TypeError, ValueError), match="attempt_index"):
        derive_judge_seed(SHA_A, "item-1", attempt_index)  # type: ignore[arg-type]


@pytest.mark.parametrize("mutation", ["role", "label", "field_order", "escape"])
def test_golden_verification_rejects_role_label_order_or_escape_tamper(
    renderer: JudgeRequestRenderer, item: BlindReviewItem, mutation: str
) -> None:
    fixture = json.loads(GOLDEN_FIXTURE.read_text(encoding="utf-8"))
    tampered = deepcopy(fixture)
    request = tampered["rendered_request"]
    if mutation == "role":
        request["messages"][0]["role"] = "user"
    elif mutation == "label":
        request["response_schema"]["properties"]["refusal"]["enum"][0] = "other"
    elif mutation == "field_order":
        request["visible_fields"][0], request["visible_fields"][1] = (
            request["visible_fields"][1],
            request["visible_fields"][0],
        )
    else:
        request["messages"][1]["content"] = request["messages"][1]["content"].replace("\\\\", "\\")
    with pytest.raises(ValueError, match="fixture|rendered request|hash|order|request_id"):
        renderer.verify_fixture(item, tampered)


def test_repair_template_is_distinct_but_keeps_single_item_contract(
    renderer: JudgeRequestRenderer, item: BlindReviewItem
) -> None:
    normal = renderer.render(item, 1, repair=False)
    repair = renderer.render(item, 2, repair=True)
    assert normal.messages[0] == repair.messages[0]
    assert normal.messages[1]["content"] != repair.messages[1]["content"]
    assert repair.item_id == item.item_id
    assert repair.visible_payload_hash == item.visible_payload_hash
    assert len(repair.messages) == 2


def test_authorization_round_trip_binds_every_static_hash(
    renderer: JudgeRequestRenderer,
) -> None:
    payload = authorization_payload(renderer)
    authorization = JudgeAuthorization.from_payload(payload)
    assert authorization.to_payload() == payload
    assert authorization.record_hash == canonical_payload_hash(authorization.content_payload())
    with pytest.raises(TypeError):
        authorization.generation_settings["temperature"] = 1.0  # type: ignore[index]
    for field in (
        "export_hash",
        "review_bundle_hash",
        "judge_pack_hash",
        "judge_pack_index_hash",
        "old_judge_prompt_hash",
        "renderer_hash",
        "coder_contract_hash",
        "ordering_policy_hash",
        "classifier_contract_hash",
        "old_environment_lock_hash",
        "tokenizer_hash",
        "chat_template_hash",
    ):
        tampered = deepcopy(payload)
        tampered[field] = "not-a-hash"
        with pytest.raises(ValueError, match=field):
            JudgeAuthorization.from_payload(tampered)


def test_authorization_is_hashed_only_after_supporting_material_matches(
    renderer: JudgeRequestRenderer,
) -> None:
    payload = authorization_payload(renderer)
    proposal = {name: value for name, value in payload.items() if name != "record_hash"}
    supporting = {
        "judge_prompt_hash": proposal["old_judge_prompt_hash"],
        "ordering_policy_hash": proposal["ordering_policy_hash"],
        "classifier_contract_hash": proposal["classifier_contract_hash"],
    }

    authorization = JudgeAuthorization.create_from_approved_payload(
        proposal, supporting_material=supporting
    )

    assert authorization.to_payload() == payload
    with pytest.raises(ValueError, match="supporting material.*judge prompt"):
        JudgeAuthorization.create_from_approved_payload(
            proposal,
            supporting_material={**supporting, "judge_prompt_hash": SHA_F},
        )


@pytest.mark.parametrize(
    "field",
    [
        "renderer_hash",
        "old_environment_lock_hash",
        "max_attempts_per_item",
        "generation_settings",
        "metadata",
    ],
)
def test_authorization_rejects_missing_field(renderer: JudgeRequestRenderer, field: str) -> None:
    payload = authorization_payload(renderer)
    del payload[field]
    with pytest.raises(ValueError, match="exact fields"):
        JudgeAuthorization.from_payload(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("connect_timeout_seconds", 0.0),
        ("read_timeout_seconds", -1.0),
        ("total_timeout_seconds", 9.0),
        ("max_attempts_per_item", 0),
        ("max_attempts_per_item", True),
        ("retry_backoff_seconds", []),
        ("non_thinking", False),
        ("one_item_per_request", False),
        ("strict_approved_order", False),
        ("runtime_provider", "remote-vllm"),
        ("endpoint_url", "http://0.0.0.0:8000/v1/chat/completions"),
        ("runtime_version", ""),
        ("generation_settings", {}),
    ],
)
def test_authorization_rejects_invalid_timeout_budget_loopback_or_runtime_flag(
    renderer: JudgeRequestRenderer, field: str, value: object
) -> None:
    payload = authorization_payload(renderer)
    payload[field] = value
    with pytest.raises(
        (TypeError, ValueError),
        match="timeout|attempt|backoff|non.thinking|item|order|loopback|runtime|generation",
    ):
        JudgeAuthorization.from_payload(payload)


def test_manifest_binds_authorization_fresh_lock_preflight_and_start(
    valid_lifecycle: dict[str, object],
) -> None:
    manifest = JudgeExecutionManifest.create(**valid_lifecycle)
    authorization = valid_lifecycle["authorization"]
    environment_lock = valid_lifecycle["environment_lock"]
    assert isinstance(authorization, JudgeAuthorization)
    assert isinstance(environment_lock, EnvironmentLock)
    assert manifest.authorization_hash == authorization.record_hash
    assert manifest.environment_lock_hash == environment_lock.record_hash
    assert manifest.preflight_hash == valid_lifecycle["preflight_hash"]
    assert manifest.service_start_identity_hash == valid_lifecycle["service_start_identity_hash"]
    assert JudgeExecutionManifest.from_payload(manifest.to_payload()) == manifest


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("total_timeout_seconds", 119.0),
        ("total_timeout_seconds", True),
        ("connect_timeout_seconds", True),
        ("retryable_codes", ["timeout", "timeout"]),
        ("retryable_codes", ["timeout", True]),
        ("retry_backoff_seconds", [1.0]),
        ("retry_backoff_seconds", [1.0, -1.0]),
        ("retry_backoff_seconds", [1.0, True]),
        ("max_attempts_per_item", True),
        ("generation_settings", {"stop": ("END",)}),
        ("expected_item_count", True),
    ],
)
def test_standalone_manifest_rejects_rehashed_invalid_execution_contract(
    valid_lifecycle: dict[str, object], field: str, value: object
) -> None:
    payload = JudgeExecutionManifest.create(**valid_lifecycle).to_payload()
    payload[field] = value
    rehash_record(payload)

    with pytest.raises((TypeError, ValueError)):
        JudgeExecutionManifest.from_payload(payload)


def test_standalone_manifest_rejects_nonfinite_retry_backoff_transport(
    valid_lifecycle: dict[str, object],
) -> None:
    payload = JudgeExecutionManifest.create(**valid_lifecycle).to_payload()
    payload["retry_backoff_seconds"] = [1.0, float("inf")]

    with pytest.raises(ValueError, match="finite"):
        JudgeExecutionManifest.from_payload(payload)


def test_manifest_rejects_environment_drift(
    valid_lifecycle: dict[str, object],
) -> None:
    environment_lock = valid_lifecycle["environment_lock"]
    assert isinstance(environment_lock, EnvironmentLock)
    valid_lifecycle["environment_lock"] = replace(
        environment_lock,
        authorization_hash=SHA_F,
        record_hash=canonical_payload_hash(
            {
                **environment_lock.payload_without_record_hash(),
                "authorization_hash": SHA_F,
            }
        ),
    )
    with pytest.raises(ValueError, match="authorization|environment"):
        JudgeExecutionManifest.create(**valid_lifecycle)


@pytest.mark.parametrize(
    "field",
    (
        "model_repository",
        "tokenizer_repository",
        "model_artifacts_hash",
        "tokenizer_artifacts_hash",
    ),
)
def test_manifest_rejects_fresh_repository_or_artifact_drift(
    valid_lifecycle: dict[str, object], field: str
) -> None:
    authorization = valid_lifecycle["authorization"]
    environment_lock = valid_lifecycle["environment_lock"]
    assert isinstance(authorization, JudgeAuthorization)
    assert isinstance(environment_lock, EnvironmentLock)
    observation = environment_lock._observation()  # noqa: SLF001 - construct drift fixture
    if field == "model_repository":
        observation = replace(observation, model_repository="Qwen/other-model")
    elif field == "tokenizer_repository":
        observation = replace(observation, tokenizer_repository="Qwen/other-tokenizer")
    elif field == "model_artifacts_hash":
        changed = replace(observation.model_artifacts[0], sha256=SHA_F)
        observation = replace(
            observation, model_artifacts=(changed, *observation.model_artifacts[1:])
        )
    else:
        changed = replace(observation.tokenizer_artifacts[0], sha256=SHA_F)
        observation = replace(observation, tokenizer_artifacts=(changed,))
    valid_lifecycle["environment_lock"] = EnvironmentLock.create(
        observation,
        authorization_hash=authorization.record_hash,
    )
    with pytest.raises(ValueError, match="environment|drift"):
        JudgeExecutionManifest.create(**valid_lifecycle)


@pytest.mark.parametrize(
    "field",
    (
        "review_bundle_hash",
        "export_hash",
        "judge_pack_hash",
        "judge_pack_index_hash",
        "judge_coder_contract_hash",
        "old_judge_prompt_hash",
        "renderer_hash",
        "ordering_policy_hash",
        "classifier_contract_hash",
        "model_id",
        "model_revision",
        "model_artifacts_hash",
        "tokenizer_id",
        "tokenizer_revision",
        "tokenizer_hash",
        "tokenizer_artifacts_hash",
        "chat_template_hash",
        "runtime_version",
        "non_thinking",
        "generation_settings",
        "connect_timeout_seconds",
        "read_timeout_seconds",
        "total_timeout_seconds",
        "retryable_codes",
        "retry_backoff_seconds",
        "max_attempts_per_item",
        "one_item_per_request",
        "strict_approved_order",
        "archive_uri",
        "source_commit",
    ),
)
def test_manifest_rejects_every_authorization_field_drift(
    valid_lifecycle: dict[str, object], field: str
) -> None:
    valid_lifecycle[field] = distinct_valid_value(field, valid_lifecycle[field])
    with pytest.raises(ValueError, match="authorization|drift"):
        JudgeExecutionManifest.create(**valid_lifecycle)


def test_pre_manifest_abort_binds_authorization_start_and_optional_lock(
    valid_lifecycle: dict[str, object],
) -> None:
    authorization = valid_lifecycle["authorization"]
    assert isinstance(authorization, JudgeAuthorization)
    abort = JudgePreManifestAbortEvidence.create(
        authorization_hash=authorization.record_hash,
        service_start_identity_hash=valid_lifecycle["service_start_identity_hash"],
        environment_lock_hash=None,
        process_exit_observed=True,
        loopback_listener_absent=True,
        gpu_idle_observation_hash=SHA_A,
    )
    assert abort.environment_lock_hash is None
    assert JudgePreManifestAbortEvidence.from_payload(abort.to_payload()) == abort
    with pytest.raises(ValueError, match="abort|completion"):
        JudgeRunCompletion.create_from_abort(abort)


def test_judge_preflight_and_service_wrappers_preserve_two_stage_order(
    valid_lifecycle: dict[str, object],
) -> None:
    authorization = valid_lifecycle["authorization"]
    assert isinstance(authorization, JudgeAuthorization)
    preflight = JudgePreflightEvidence.create(
        authorization=authorization,
        supporting_material_hash=SHA_D,
        old_judge_prompt_hash=authorization.old_judge_prompt_hash,
        preliminary_inspection_hash=SHA_E,
    )
    assert JudgePreflightEvidence.from_payload(preflight.to_payload()) == preflight
    start = JudgeServiceEvidence.create(
        phase="start",
        authorization_hash=authorization.record_hash,
        evidence_hash=SHA_B,
        service_start_identity_hash=SHA_B,
    )
    live = JudgeServiceEvidence.create(
        phase="live-observation",
        authorization_hash=authorization.record_hash,
        evidence_hash=SHA_C,
        service_start_identity_hash=start.evidence_hash,
        environment_lock_hash=SHA_C,
    )
    assert JudgeServiceEvidence.from_payload(start.to_payload()) == start
    assert JudgeServiceEvidence.from_payload(live.to_payload()) == live
    with pytest.raises(ValueError, match="old judge prompt"):
        JudgePreflightEvidence.create(
            authorization=authorization,
            supporting_material_hash=SHA_D,
            old_judge_prompt_hash=SHA_F,
            preliminary_inspection_hash=SHA_E,
        )


@pytest.mark.parametrize("field", ["environment_lock_hash", "manifest_hash"])
def test_start_service_evidence_rejects_later_lifecycle_hashes(field: str) -> None:
    values = {
        "phase": "start",
        "authorization_hash": SHA_A,
        "evidence_hash": SHA_B,
        "service_start_identity_hash": SHA_B,
        "environment_lock_hash": None,
        "manifest_hash": None,
    }
    values[field] = SHA_C

    with pytest.raises(ValueError, match="start.*later lifecycle"):
        JudgeServiceEvidence.create(**values)

    valid = JudgeServiceEvidence.create(
        phase="start",
        authorization_hash=SHA_A,
        evidence_hash=SHA_B,
        service_start_identity_hash=SHA_B,
    ).to_payload()
    valid[field] = SHA_C
    rehash_record(valid)
    with pytest.raises(ValueError, match="start.*later lifecycle"):
        JudgeServiceEvidence.from_payload(valid)


def test_judge_run_completion_round_trip_requires_post_manifest_stop() -> None:
    completion = JudgeRunCompletion.create(
        manifest_hash=SHA_A,
        projection_hash=SHA_B,
        service_index_hash=SHA_C,
        stop_evidence_hash=SHA_D,
        service_start_identity_hash=SHA_E,
        environment_lock_hash=SHA_F,
        gpu_idle_observation_hash=SHA_A,
    )
    assert JudgeRunCompletion.from_payload(completion.to_payload()) == completion


def test_authorization_rejects_wrong_container_types_and_hash_tamper(
    renderer: JudgeRequestRenderer,
) -> None:
    for field, value in (
        ("retryable_codes", ("timeout",)),
        ("retry_backoff_seconds", (1.0, 2.0)),
        ("generation_settings", []),
    ):
        payload = authorization_payload(renderer)
        payload[field] = value
        with pytest.raises((TypeError, ValueError)):
            JudgeAuthorization.from_payload(payload)
    payload = authorization_payload(renderer)
    payload["record_hash"] = SHA_F
    with pytest.raises(ValueError, match="record_hash|record hash"):
        JudgeAuthorization.from_payload(payload)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("calibration_only", False),
        ("formal_parameter_authority", True),
        ("research_parameter_status", "frozen"),
    ],
)
def test_authorization_rejects_formal_authority_metadata(
    renderer: JudgeRequestRenderer, key: str, value: object
) -> None:
    payload = authorization_payload(renderer)
    payload["metadata"][key] = value  # type: ignore[index]
    with pytest.raises(ValueError, match="metadata|calibration|formal"):
        JudgeAuthorization.from_payload(payload)
