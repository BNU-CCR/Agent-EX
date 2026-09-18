"""Approved-artifact loader and immutable manifest for real cloud calibration."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime
import hashlib
from pathlib import Path, PurePosixPath
import re
import shutil
from typing import Mapping

from ..artifacts import ArtifactEnvelope
from ..domain import (
    _freeze,
    _json_ready,
    _require_int,
    _require_json_transport,
    _require_payload_hash,
    _require_sha256,
    canonical_payload_hash,
)
from .bundle import ProbeBundle
from .contracts import (
    CloudProbeRuntimePolicy,
    ProbeAttempt,
    ProbeCase,
    ProbeRequest,
    ProbeRunProjection,
)
from .environment import (
    EnvironmentLock,
    EnvironmentObservation,
    verify_current_environment,
)
from .review import SemanticReviewPolicy
from .response_contract import RESPONSE_CONTRACT_VERSION, response_contract_hash
from .runner import ProbeRunCrash, resume_probe_run
from .specification import expand_probe_cases, load_probe_specification
from .store import ProbeRunStore, review_evidence_hash
from .vllm_adapter import VllmProbeAdapter, VllmTransportEvidence


_GROUP_NAMES = frozenset(
    {
        "probe_specification",
        "runtime_policy",
        "semantic_review_policy",
        "candidate_manifest",
        "credential_boundary",
        "archive_declaration",
    }
)
_EXPECTED_COUNTS = {"continuity": 576, "identity": 96, "topic_quality": 144}
_REVISION = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_KEYS = frozenset(
    {
        "polarization",
        "homogenization",
        "treatment_effect",
        "primary_contrast",
        "p_value",
        "network_outcome",
    }
)


class AmbiguousCloudDispatchError(RuntimeError):
    """A request may have reached vLLM but has no durable terminal evidence."""


def _store_evidence_root(store: ProbeRunStore) -> Path:
    if store._sealed:  # noqa: SLF001 - same-package validated store state
        return store.root / "sealed" / "evidence"
    return store.root / "staging"


def _append_review_once(store: ProbeRunStore, payload: Mapping[str, object]) -> None:
    digest = payload.get("record_hash")
    if not isinstance(digest, str):
        raise ValueError("dispatch journal record must contain record_hash")
    records = store._load_records(store.root / "staging" / "reviews", "review")  # noqa: SLF001
    if digest in records:
        if records[digest] != payload:
            raise ValueError("dispatch journal hash collision")
        return
    store.append_review(payload)


def _dispatch_intent_record(
    *, store: ProbeRunStore, request: ProbeRequest, request_body: bytes
) -> Mapping[str, object]:
    if not isinstance(request, ProbeRequest):
        raise TypeError("dispatch intent requires ProbeRequest")
    content: dict[str, object] = {
        "schema_version": "paper1.calibration.cloud-dispatch-intent.v1",
        "manifest_hash": store.manifest_hash,
        "request_id": request.request_id,
        "request_hash": request.record_hash,
        "probe_case_id": request.probe_case_id,
        "attempt_index": request.attempt_index,
        "request_body_sha256": hashlib.sha256(request_body).hexdigest(),
        "request_body_bytes": len(request_body),
        "calibration_only": True,
        "formal_parameter_authority": False,
    }
    return {**content, "record_hash": canonical_payload_hash(content)}


def _bind_dispatch_journal(adapter: VllmProbeAdapter, store: ProbeRunStore) -> None:
    def before_dispatch(request: ProbeRequest, request_body: bytes) -> None:
        _append_review_once(
            store,
            _dispatch_intent_record(store=store, request=request, request_body=request_body),
        )

    adapter.bind_dispatch_journal(before_dispatch)


def _reconcile_dispatch_journal(store: ProbeRunStore, *, reject_unresolved: bool) -> None:
    """Resolve journaled sends from durable attempts; fail closed on ambiguity."""
    evidence_root = _store_evidence_root(store)
    reviews = store._load_records(evidence_root / "reviews", "review")  # noqa: SLF001
    attempts = store._load_records(evidence_root / "attempts", "attempt")  # noqa: SLF001
    intents: dict[str, Mapping[str, object]] = {}
    resolutions: dict[str, Mapping[str, object]] = {}
    for record in reviews.values():
        schema = record.get("schema_version")
        if schema == "paper1.calibration.cloud-dispatch-intent.v1":
            _exact(
                record,
                {
                    "schema_version",
                    "manifest_hash",
                    "request_id",
                    "request_hash",
                    "probe_case_id",
                    "attempt_index",
                    "request_body_sha256",
                    "request_body_bytes",
                    "calibration_only",
                    "formal_parameter_authority",
                    "record_hash",
                },
                "cloud dispatch intent",
            )
            _validated_record(record, name="cloud dispatch intent")
            request_id = record["request_id"]
            if (
                not isinstance(request_id, str)
                or record["manifest_hash"] != store.manifest_hash
                or record["calibration_only"] is not True
                or record["formal_parameter_authority"] is not False
            ):
                raise ValueError("cloud dispatch intent authorization drift")
            if request_id in intents:
                raise ValueError("duplicate cloud dispatch intent")
            intents[request_id] = record
        elif schema == "paper1.calibration.cloud-dispatch-resolution.v1":
            _exact(
                record,
                {
                    "schema_version",
                    "manifest_hash",
                    "request_id",
                    "dispatch_intent_hash",
                    "attempt_record_hash",
                    "transport_evidence_hash",
                    "calibration_only",
                    "formal_parameter_authority",
                    "record_hash",
                },
                "cloud dispatch resolution",
            )
            _validated_record(record, name="cloud dispatch resolution")
            request_id = record["request_id"]
            if (
                not isinstance(request_id, str)
                or request_id in resolutions
                or record["manifest_hash"] != store.manifest_hash
                or record["calibration_only"] is not True
                or record["formal_parameter_authority"] is not False
            ):
                raise ValueError("duplicate or invalid cloud dispatch resolution")
            resolutions[request_id] = record

    durable: dict[str, tuple[str, Mapping[str, object]]] = {}
    for attempt_hash, wrapper in attempts.items():
        nested = wrapper.get("probe_attempt")
        transport = wrapper.get("transport_evidence")
        if type(nested) is not dict or type(transport) is not dict:
            raise ValueError("durable cloud attempt lacks nested evidence")
        request = nested.get("request")
        if type(request) is not dict or not isinstance(request.get("request_id"), str):
            raise ValueError("durable cloud attempt lacks request identity")
        request_id = request["request_id"]
        if request_id in durable:
            raise ValueError("duplicate durable request identity")
        durable[request_id] = (attempt_hash, transport)

    for request_id, (attempt_hash, transport) in durable.items():
        intent = intents.get(request_id)
        if intent is None:
            raise ValueError("durable cloud attempt lacks pre-dispatch intent")
        nested = attempts[attempt_hash]["probe_attempt"]
        request = nested["request"]  # type: ignore[index]
        if (
            intent["request_hash"] != request.get("record_hash")
            or intent["probe_case_id"] != request.get("probe_case_id")
            or intent["attempt_index"] != request.get("attempt_index")
            or intent["request_body_sha256"] != transport.get("request_body_sha256")
            or intent["request_body_bytes"] != transport.get("request_body_bytes")
        ):
            raise ValueError("cloud dispatch intent differs from durable request evidence")
        transport_hash = transport.get("record_hash")
        _require_sha256("transport_evidence_hash", transport_hash)
        content: dict[str, object] = {
            "schema_version": "paper1.calibration.cloud-dispatch-resolution.v1",
            "manifest_hash": store.manifest_hash,
            "request_id": request_id,
            "dispatch_intent_hash": intent["record_hash"],
            "attempt_record_hash": attempt_hash,
            "transport_evidence_hash": transport_hash,
            "calibration_only": True,
            "formal_parameter_authority": False,
        }
        expected = {**content, "record_hash": canonical_payload_hash(content)}
        existing = resolutions.get(request_id)
        if existing is None:
            if store._sealed:  # noqa: SLF001
                raise ValueError("sealed evidence lacks cloud dispatch resolution")
            _append_review_once(store, expected)
        elif existing != expected:
            raise ValueError("cloud dispatch resolution differs from durable attempt")

    unresolved = sorted(set(intents) - set(durable))
    if unresolved and reject_unresolved:
        raise AmbiguousCloudDispatchError(
            "indeterminate cloud dispatch has no durable response; automatic retry is forbidden"
        )
    if set(resolutions) - set(durable):
        raise ValueError("cloud dispatch resolution lacks a durable attempt")


_SECRET_VALUE = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)"
    r"(?:\s*(?:=|:)\s*|\s+)\S+|hf_[A-Za-z0-9]{8,}|BEGIN [A-Z ]*PRIVATE KEY"
)


def _exact(payload: Mapping[str, object], expected: set[str], name: str) -> None:
    if type(payload) is not dict or set(payload) != expected:
        raise ValueError(f"{name} payload must contain exact fields")
    _require_json_transport(payload, f"{name} payload")


def _walk(value: object, *, path: str = "payload") -> None:
    if isinstance(value, str):
        if "UNRESOLVED[" in value:
            raise ValueError(f"{path} contains UNRESOLVED executable content")
        if _SECRET_VALUE.search(value):
            raise ValueError(f"{path} contains a credential or secret")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key.casefold() in _FORBIDDEN_KEYS:
                raise ValueError(f"{path} contains forbidden formal/network-outcome field {key}")
            _walk(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _walk(item, path=f"{path}[{index}]")


def _validated_record(
    payload: object, *, expected: set[str] | None = None, name: str
) -> Mapping[str, object]:
    if not isinstance(payload, Mapping) or type(payload) is not dict:
        raise TypeError(f"{name} must be a strict JSON object")
    if expected is not None:
        _exact(payload, expected, name)
    else:
        _require_json_transport(payload, name)
    if "record_hash" not in payload:
        raise ValueError(f"{name} requires record_hash")
    _require_sha256(f"{name} record_hash", payload["record_hash"])
    content = {key: value for key, value in payload.items() if key != "record_hash"}
    _require_payload_hash(f"{name} record_hash", payload["record_hash"], content)  # type: ignore[arg-type]
    return payload


def _require_metadata(payload: object, *, research_status: bool = False) -> None:
    expected = {"calibration_only", "formal_parameter_authority"}
    if research_status:
        expected.add("research_parameter_status")
    if type(payload) is not dict or set(payload) != expected:
        raise ValueError("artifact metadata must contain exact fields")
    if payload["calibration_only"] is not True:
        raise ValueError("artifact must remain calibration-only")
    if payload["formal_parameter_authority"] is not False:
        raise ValueError("artifact must not grant formal parameter authority")
    if research_status and payload["research_parameter_status"] != "not_frozen":
        raise ValueError("research_parameter_status must be not_frozen")


@dataclass(frozen=True, slots=True)
class CloudRunArtifacts:
    """Strictly validated six-group approval packet."""

    artifact_groups: Mapping[str, Mapping[str, object]]
    approved_group_hashes: Mapping[str, str]
    specification: ArtifactEnvelope
    cases: tuple[ProbeCase, ...]
    runtime_policy: CloudProbeRuntimePolicy
    semantic_review_policy: SemanticReviewPolicy
    record_hash: str

    def __post_init__(self) -> None:
        if set(self.artifact_groups) != _GROUP_NAMES:
            raise ValueError("cloud run requires exactly six artifact groups")
        if set(self.approved_group_hashes) != _GROUP_NAMES:
            raise ValueError("approved_group_hashes must bind all six artifact groups")
        _require_sha256("approved artifacts record_hash", self.record_hash)
        if not isinstance(self.specification, ArtifactEnvelope):
            raise TypeError("specification must be an ArtifactEnvelope")
        if type(self.cases) is not tuple or any(type(item) is not ProbeCase for item in self.cases):
            raise TypeError("cases must be exact ProbeCase records")
        if not isinstance(self.runtime_policy, CloudProbeRuntimePolicy):
            raise TypeError("runtime_policy must be CloudProbeRuntimePolicy")
        if not isinstance(self.semantic_review_policy, SemanticReviewPolicy):
            raise TypeError("semantic_review_policy must be SemanticReviewPolicy")
        object.__setattr__(self, "artifact_groups", _freeze(self.artifact_groups))
        object.__setattr__(self, "approved_group_hashes", _freeze(self.approved_group_hashes))

    @property
    def archive_uri(self) -> str:
        return self.artifact_groups["archive_declaration"]["archive_uri"]  # type: ignore[return-value]

    @property
    def candidate_manifest(self) -> Mapping[str, object]:
        return self.artifact_groups["candidate_manifest"]

    def to_payload(self) -> dict[str, object]:
        content: dict[str, object] = {
            "schema_version": "paper1.calibration.approved-cloud-artifacts.v1",
            "calibration_only": True,
            "formal_parameter_authority": False,
            "research_parameter_status": "not_frozen",
            "artifact_groups": self.artifact_groups,
            "approved_group_hashes": self.approved_group_hashes,
        }
        return _json_ready({**content, "record_hash": self.record_hash})


def load_cloud_run_artifacts(payload: Mapping[str, object]) -> CloudRunArtifacts:
    """Load a fully resolved, hash-bound six-group authorization packet."""
    _exact(
        payload,
        {
            "schema_version",
            "calibration_only",
            "formal_parameter_authority",
            "research_parameter_status",
            "artifact_groups",
            "approved_group_hashes",
            "record_hash",
        },
        "approved cloud artifacts",
    )
    if payload["schema_version"] != "paper1.calibration.approved-cloud-artifacts.v1":
        raise ValueError("approved cloud artifacts schema_version is not supported")
    if (
        payload["calibration_only"] is not True
        or payload["formal_parameter_authority"] is not False
    ):
        raise ValueError(
            "approved cloud artifacts must remain calibration-only and non-authoritative"
        )
    if payload["research_parameter_status"] != "not_frozen":
        raise ValueError("approved cloud artifacts research parameters must remain not_frozen")
    groups = payload["artifact_groups"]
    hashes = payload["approved_group_hashes"]
    if type(groups) is not dict or set(groups) != _GROUP_NAMES:
        raise ValueError("cloud run requires exactly six artifact groups")
    if type(hashes) is not dict or set(hashes) != _GROUP_NAMES:
        raise ValueError("approved_group_hashes must bind all six artifact groups")
    _walk(payload)
    checked_groups: dict[str, Mapping[str, object]] = {}
    for name in sorted(_GROUP_NAMES):
        checked = _validated_record(groups[name], name=f"{name} group")
        if hashes[name] != checked["record_hash"]:
            raise ValueError("approved_group_hashes do not match the six artifact groups")
        checked_groups[name] = checked
    _require_sha256("approved cloud artifacts record_hash", payload["record_hash"])
    content = {key: value for key, value in payload.items() if key != "record_hash"}
    _require_payload_hash(
        "approved cloud artifacts record_hash",
        payload["record_hash"],
        content,  # type: ignore[arg-type]
    )

    specification_group = checked_groups["probe_specification"]
    _exact(
        specification_group,
        {
            "schema_version",
            "specification",
            "gate_algorithm",
            "response_contract_version",
            "response_contract_hash",
            "case_inventory_hash",
            "record_hash",
        },
        "probe specification group",
    )
    if specification_group["schema_version"] != "paper1.calibration.approved-specification.v2":
        raise ValueError("probe specification group schema is not supported")
    envelope_payload = specification_group["specification"]
    if type(envelope_payload) is not dict or type(envelope_payload.get("payload")) is not dict:
        raise TypeError("probe specification must contain a strict artifact envelope")
    specification = load_probe_specification(envelope_payload["payload"])
    if specification.to_payload() != envelope_payload:
        raise ValueError("probe specification envelope hash drift")
    if specification_group["response_contract_version"] != RESPONSE_CONTRACT_VERSION:
        raise ValueError("response contract version differs from the approved probe group")
    if specification_group["response_contract_hash"] != response_contract_hash():
        raise ValueError("response contract wording differs from the approved probe group")
    cases = expand_probe_cases(specification)
    case_inventory_hash = canonical_payload_hash(
        [case.to_payload() for case in sorted(cases, key=lambda item: item.probe_case_id)]
    )
    if specification_group["case_inventory_hash"] != case_inventory_hash:
        raise ValueError("expanded case inventory differs from the approved probe group")
    gate_payload = specification_group["gate_algorithm"]
    if type(gate_payload) is not dict:
        raise TypeError("gate_algorithm must be a strict JSON object")
    if (
        canonical_payload_hash(gate_payload)
        != specification.payload["policy_hashes"]["gate_algorithm"]
    ):
        raise ValueError("gate_algorithm hash is not bound by the specification")

    runtime = CloudProbeRuntimePolicy.from_payload(checked_groups["runtime_policy"])
    semantic = SemanticReviewPolicy.from_payload(checked_groups["semantic_review_policy"])
    policy_hashes = specification.payload["policy_hashes"]
    if policy_hashes["runtime_policy"] != runtime.record_hash:
        raise ValueError("runtime policy is not bound by the specification")
    if policy_hashes["semantic_review_policy"] != semantic.record_hash:
        raise ValueError("semantic review policy is not bound by the specification")

    candidate = checked_groups["candidate_manifest"]
    _exact(
        candidate,
        {
            "schema_version",
            "metadata",
            "model_repository",
            "model_revision",
            "tokenizer_repository",
            "tokenizer_revision",
            "vllm_version",
            "endpoint",
            "served_model_name",
            "chat_template_hash",
            "rendered_non_thinking_hash",
            "model_artifacts_hash",
            "tokenizer_artifacts_hash",
            "vllm_wheel_hash",
            "image_repository",
            "image_digest",
            "serve_arguments",
            "generation_settings",
            "record_hash",
        },
        "candidate manifest",
    )
    if candidate["schema_version"] != "paper1.calibration.candidate-manifest.v1":
        raise ValueError("candidate manifest schema is not supported")
    _require_metadata(candidate["metadata"], research_status=True)
    for name in ("model_revision", "tokenizer_revision"):
        value = candidate[name]
        if not isinstance(value, str) or _REVISION.fullmatch(value) is None:
            raise ValueError(f"candidate {name} must be an exact revision")
    if candidate["endpoint"] != "http://127.0.0.1:8000/v1/chat/completions":
        raise ValueError("candidate endpoint must be the approved loopback endpoint")
    if type(candidate["generation_settings"]) is not dict or set(
        candidate["generation_settings"]
    ) != {"temperature", "top_p", "max_tokens", "request_seed"}:
        raise ValueError("candidate generation_settings must contain exact fields")
    if candidate["generation_settings"]["request_seed"] != "probe_case.requested_seed":
        raise ValueError("candidate request_seed must bind each probe case requested seed")
    specification_generation = specification.payload["generation_settings"]
    candidate_generation = candidate["generation_settings"]
    if any(
        specification_generation[name] != candidate_generation[name]
        for name in ("temperature", "top_p", "max_tokens", "request_seed")
    ):
        raise ValueError("candidate generation settings differ from the probe specification")
    for name in (
        "chat_template_hash",
        "rendered_non_thinking_hash",
        "model_artifacts_hash",
        "tokenizer_artifacts_hash",
        "vllm_wheel_hash",
    ):
        _require_sha256(f"candidate {name}", candidate[name])
    if type(candidate["serve_arguments"]) is not list or not candidate["serve_arguments"]:
        raise TypeError("candidate serve_arguments must be a nonempty JSON array")

    credential = checked_groups["credential_boundary"]
    _exact(
        credential,
        {
            "schema_version",
            "metadata",
            "injection_channel",
            "credential_values_archived",
            "record_hash",
        },
        "credential boundary",
    )
    if credential["schema_version"] != "paper1.calibration.credential-boundary.v1":
        raise ValueError("credential boundary schema is not supported")
    _require_metadata(credential["metadata"])
    if credential["credential_values_archived"] is not False:
        raise ValueError("credential values must not be archived")

    archive = checked_groups["archive_declaration"]
    _exact(
        archive,
        {
            "schema_version",
            "metadata",
            "archive_uri",
            "raw_artifacts_in_git",
            "record_hash",
        },
        "archive declaration",
    )
    if archive["schema_version"] != "paper1.calibration.archive-declaration.v1":
        raise ValueError("archive declaration schema is not supported")
    _require_metadata(archive["metadata"])
    uri = archive["archive_uri"]
    if not isinstance(uri, str) or not PurePosixPath(uri).is_absolute():
        raise ValueError("archive_uri must be an absolute POSIX path")
    if archive["raw_artifacts_in_git"] is not False:
        raise ValueError("raw artifacts must remain outside Git")

    counts: dict[str, int] = {}
    for case in cases:
        counts[case.case_family] = counts.get(case.case_family, 0) + 1
    if len(cases) != 816 or counts != _EXPECTED_COUNTS:
        raise ValueError("cloud run requires the exact 816-case family inventory")
    if runtime.max_total_cases != len(cases):
        raise ValueError("cloud runtime case budget differs from the exact inventory")
    return CloudRunArtifacts(
        artifact_groups=checked_groups,
        approved_group_hashes=dict(sorted(hashes.items())),
        specification=specification,
        cases=cases,
        runtime_policy=runtime,
        semantic_review_policy=semantic,
        record_hash=payload["record_hash"],  # type: ignore[arg-type]
    )


@dataclass(frozen=True, slots=True)
class CloudRunManifest:
    schema_version: str
    calibration_only: bool
    formal_parameter_authority: bool
    research_parameter_status: str
    approved_artifacts_hash: str
    approved_group_hashes: Mapping[str, str]
    environment_lock_hash: str
    environment_inspection_algorithm: str
    case_inventory_hash: str
    case_count: int
    case_family_counts: Mapping[str, int]
    archive_uri: str
    record_hash: str

    _SCHEMA = "paper1.calibration.cloud-run-manifest.v1"

    def __post_init__(self) -> None:
        if self.schema_version != self._SCHEMA:
            raise ValueError("cloud run manifest schema is not supported")
        if self.calibration_only is not True or self.formal_parameter_authority is not False:
            raise ValueError(
                "cloud run manifest must remain calibration-only and non-authoritative"
            )
        if self.research_parameter_status != "not_frozen":
            raise ValueError("cloud run manifest research parameters must remain not_frozen")
        for name in ("approved_artifacts_hash", "environment_lock_hash", "case_inventory_hash"):
            _require_sha256(name, getattr(self, name))
        if (
            type(self.approved_group_hashes) is not dict
            or set(self.approved_group_hashes) != _GROUP_NAMES
        ):
            raise ValueError("cloud run manifest must bind all six group hashes")
        for digest in self.approved_group_hashes.values():
            _require_sha256("approved group hash", digest)
        if self.environment_inspection_algorithm != "agent-ex.environment-inspection.v1":
            raise ValueError("environment inspection algorithm is not supported")
        _require_int("case_count", self.case_count, minimum=1)
        if self.case_count != 816 or dict(self.case_family_counts) != _EXPECTED_COUNTS:
            raise ValueError("cloud run manifest requires exact 816-case family counts")
        if type(self.case_family_counts) is not dict:
            raise TypeError("case_family_counts must be a strict mapping")
        if (
            not isinstance(self.archive_uri, str)
            or not PurePosixPath(self.archive_uri).is_absolute()
        ):
            raise ValueError("archive_uri must be an absolute POSIX path")
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())
        object.__setattr__(self, "approved_group_hashes", _freeze(self.approved_group_hashes))
        object.__setattr__(self, "case_family_counts", _freeze(self.case_family_counts))

    def content_payload(self) -> dict[str, object]:
        return {
            name: getattr(self, name)
            for name in (field.name for field in fields(self))
            if name != "record_hash"
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> CloudRunManifest:
        _exact(payload, {field.name for field in fields(cls)}, "cloud run manifest")
        return cls(**payload)  # type: ignore[arg-type]


def build_cloud_run_manifest(
    artifacts: CloudRunArtifacts, *, environment_lock: EnvironmentLock | None
) -> CloudRunManifest:
    if not isinstance(artifacts, CloudRunArtifacts):
        raise TypeError("cloud run manifest requires CloudRunArtifacts")
    if environment_lock is None or not isinstance(environment_lock, EnvironmentLock):
        raise ValueError("cloud run manifest requires an environment lock")
    if environment_lock.authorization_hash != artifacts.record_hash:
        raise ValueError("environment lock must be created after six-group approval")
    candidate = artifacts.candidate_manifest
    environment_bindings = {
        "model_repository": environment_lock.model_repository,
        "model_revision": environment_lock.model_revision,
        "tokenizer_repository": environment_lock.tokenizer_repository,
        "tokenizer_revision": environment_lock.tokenizer_revision,
        "chat_template_hash": environment_lock.chat_template_hash,
        "rendered_non_thinking_hash": environment_lock.rendered_non_thinking_hash,
        "model_artifacts_hash": environment_lock.model_artifacts_hash,
        "tokenizer_artifacts_hash": environment_lock.tokenizer_artifacts_hash,
        "vllm_version": environment_lock.vllm_identity.version,
        "vllm_wheel_hash": environment_lock.vllm_identity.wheel_hash,
        "image_repository": environment_lock.image_identity.repository,
        "image_digest": environment_lock.image_identity.digest,
        "serve_arguments": environment_lock.serve_arguments,
    }
    for name, observed in environment_bindings.items():
        if candidate[name] != observed:
            raise ValueError(f"environment lock {name} differs from candidate manifest")
    ordered = tuple(sorted(artifacts.cases, key=lambda case: case.probe_case_id))
    counts = dict(sorted(_EXPECTED_COUNTS.items()))
    content: dict[str, object] = {
        "schema_version": CloudRunManifest._SCHEMA,
        "calibration_only": True,
        "formal_parameter_authority": False,
        "research_parameter_status": "not_frozen",
        "approved_artifacts_hash": artifacts.record_hash,
        "approved_group_hashes": dict(sorted(artifacts.approved_group_hashes.items())),
        "environment_lock_hash": environment_lock.record_hash,
        "environment_inspection_algorithm": environment_lock.inspection_algorithm,
        "case_inventory_hash": canonical_payload_hash(tuple(case.to_payload() for case in ordered)),
        "case_count": len(ordered),
        "case_family_counts": counts,
        "archive_uri": artifacts.archive_uri,
    }
    return CloudRunManifest(**content, record_hash=canonical_payload_hash(content))  # type: ignore[arg-type]


def _execution_inputs(artifacts: CloudRunArtifacts) -> dict[str, object]:
    candidate = artifacts.candidate_manifest
    settings = dict(candidate["generation_settings"])  # type: ignore[arg-type]
    settings.pop("request_seed")
    return {
        "specification_hash": artifacts.specification.output_hash,
        "cases": artifacts.cases,
        "runtime_policy": artifacts.runtime_policy,
        "generation_settings": settings,
        "runtime_identity": {
            "provider": "vllm-openai-loopback",
            "runtime_version": candidate["vllm_version"],
        },
        "model_identity": {
            "model": candidate["served_model_name"],
            "revision": candidate["model_revision"],
        },
        "tokenizer_identity": {
            "tokenizer": candidate["tokenizer_repository"],
            "revision": candidate["tokenizer_revision"],
        },
        "chat_template_hash": candidate["chat_template_hash"],
    }


def reconstruct_cloud_projection(
    store: ProbeRunStore,
    *,
    run_artifacts: CloudRunArtifacts,
    manifest: CloudRunManifest,
) -> ProbeRunProjection:
    """Rebuild the last validated projection only from durable append-only attempts."""
    if not isinstance(store, ProbeRunStore):
        raise TypeError("projection reconstruction requires ProbeRunStore")
    if not isinstance(run_artifacts, CloudRunArtifacts):
        raise TypeError("projection reconstruction requires CloudRunArtifacts")
    if not isinstance(manifest, CloudRunManifest):
        raise TypeError("projection reconstruction requires CloudRunManifest")
    if (
        store.manifest_hash != manifest.record_hash
        or manifest.approved_artifacts_hash != run_artifacts.record_hash
    ):
        raise ValueError("durable projection inputs do not bind the same authorization")
    _reconcile_dispatch_journal(store, reject_unresolved=True)
    evidence_root = _store_evidence_root(store)
    records = store._load_records(evidence_root / "attempts", "attempt")  # noqa: SLF001
    attempts: list[ProbeAttempt] = []
    for digest in store.attempt_hashes:
        record = records[digest]
        _exact(
            record,
            {
                "schema_version",
                "probe_case_id",
                "attempt_index",
                "probe_attempt",
                "transport_evidence",
                "calibration_only",
                "formal_parameter_authority",
                "record_hash",
            },
            "durable cloud attempt",
        )
        _validated_record(record, name="durable cloud attempt")
        if (
            record["schema_version"] != "paper1.calibration.cloud-attempt.v1"
            or record["calibration_only"] is not True
            or record["formal_parameter_authority"] is not False
            or type(record["probe_attempt"]) is not dict
            or type(record["transport_evidence"]) is not dict
        ):
            raise ValueError("durable cloud attempt metadata or nested payload is invalid")
        attempt = ProbeAttempt.from_payload(record["probe_attempt"])
        transport = VllmTransportEvidence.from_payload(record["transport_evidence"])
        if (
            record["probe_case_id"] != attempt.probe_case_id
            or record["attempt_index"] != attempt.attempt_index
            or transport.request_id != attempt.request.request_id
            or transport.request_hash != attempt.request.record_hash
            or transport.endpoint != run_artifacts.candidate_manifest["endpoint"]
            or transport.outcome != attempt.response.outcome
            or transport.error_code != attempt.response.error_code
            or transport.provider_request_id != attempt.response.provider_request_id
        ):
            raise ValueError("durable transport evidence is not bound to its probe attempt")
        attempts.append(attempt)
    inputs = _execution_inputs(run_artifacts)
    return ProbeRunProjection.create(
        run_instance_id="cloud-probe-" + run_artifacts.record_hash[:16],
        specification_hash=inputs["specification_hash"],  # type: ignore[arg-type]
        case_inventory_hash=manifest.case_inventory_hash,
        runtime_policy=run_artifacts.runtime_policy,
        generation_settings=inputs["generation_settings"],  # type: ignore[arg-type]
        runtime_identity=inputs["runtime_identity"],  # type: ignore[arg-type]
        model_identity=inputs["model_identity"],  # type: ignore[arg-type]
        tokenizer_identity=inputs["tokenizer_identity"],  # type: ignore[arg-type]
        chat_template_hash=inputs["chat_template_hash"],  # type: ignore[arg-type]
        case_ids=tuple(item.probe_case_id for item in run_artifacts.cases),
        attempts=tuple(attempts),
    )


def _validate_execution(
    *,
    run_artifacts: CloudRunArtifacts,
    adapter: object,
    environment_lock: EnvironmentLock | None,
    current_environment: EnvironmentObservation | None,
    manifest: CloudRunManifest | None,
    store: ProbeRunStore | None,
) -> tuple[VllmProbeAdapter, EnvironmentLock, CloudRunManifest, ProbeRunStore]:
    if not isinstance(run_artifacts, CloudRunArtifacts):
        raise TypeError("run_artifacts must be CloudRunArtifacts")
    if not isinstance(adapter, VllmProbeAdapter):
        raise TypeError("cloud execution requires VllmProbeAdapter, not a formal engine adapter")
    if not isinstance(environment_lock, EnvironmentLock):
        raise ValueError("cloud execution requires environment lock")
    if not isinstance(current_environment, EnvironmentObservation):
        raise ValueError("cloud execution requires a fresh current environment observation")
    verify_current_environment(environment_lock, current_environment)
    if not isinstance(manifest, CloudRunManifest):
        raise ValueError("cloud execution requires CloudRunManifest")
    expected_manifest = build_cloud_run_manifest(run_artifacts, environment_lock=environment_lock)
    if manifest != expected_manifest:
        raise ValueError("cloud run manifest differs from approved artifacts and environment")
    if not isinstance(store, ProbeRunStore) or store.manifest_hash != manifest.record_hash:
        raise ValueError("cloud run store does not bind the run manifest")
    return adapter, environment_lock, manifest, store


def _persist_projection(
    store: ProbeRunStore,
    projection: ProbeRunProjection,
    adapter: VllmProbeAdapter,
) -> None:
    if len(store.attempt_hashes) > len(projection.attempts):
        raise ValueError("stored attempts exceed the validated projection")
    records = store._load_records(store.root / "staging" / "attempts", "attempt")  # noqa: SLF001
    for index, digest in enumerate(store.attempt_hashes):
        record = records[digest]
        if (
            record.get("schema_version") != "paper1.calibration.cloud-attempt.v1"
            or record.get("probe_attempt") != projection.attempts[index].to_payload()
        ):
            raise ValueError("stored attempts are not a prefix of the validated projection")
    for attempt in projection.attempts[len(store.attempt_hashes) :]:
        transport = adapter.evidence_for(attempt.request.request_id)
        content: dict[str, object] = {
            "schema_version": "paper1.calibration.cloud-attempt.v1",
            "probe_case_id": attempt.probe_case_id,
            "attempt_index": attempt.attempt_index,
            "probe_attempt": attempt.to_payload(),
            "transport_evidence": transport.to_payload(),
            "calibration_only": True,
            "formal_parameter_authority": False,
        }
        store.append_attempt({**content, "record_hash": canonical_payload_hash(content)})
    _reconcile_dispatch_journal(store, reject_unresolved=True)


def _continue_cloud_probe(
    *,
    run_artifacts: CloudRunArtifacts,
    adapter: VllmProbeAdapter,
    store: ProbeRunStore,
    projection: ProbeRunProjection,
    stop_after_attempts: int | None,
) -> ProbeRunProjection:
    if stop_after_attempts is not None:
        _require_int("stop_after_attempts", stop_after_attempts, minimum=1)
    inputs = _execution_inputs(run_artifacts)
    added = 0
    current = projection
    while True:
        if _cloud_budget_failure_reason(run_artifacts, current, store) is not None:
            return current
        prior_count = len(current.attempts)
        try:
            current = resume_probe_run(
                projection=current,
                adapter=adapter,
                stop_after_attempts=1,
                **inputs,  # type: ignore[arg-type]
            )
        except ProbeRunCrash as error:
            _persist_projection(store, error.snapshot, adapter)
            raise
        _persist_projection(store, current, adapter)
        delta = len(current.attempts) - prior_count
        added += delta
        if "runtime_failed" in current.case_statuses.values():
            return current
        if current.status == "complete" or delta == 0:
            return current
        if stop_after_attempts is not None and added >= stop_after_attempts:
            return current


def _attempt_elapsed_seconds(attempt: ProbeAttempt) -> float:
    started = datetime.fromisoformat(attempt.response.started_at.replace("Z", "+00:00"))
    ended = datetime.fromisoformat(attempt.response.ended_at.replace("Z", "+00:00"))
    return (ended - started).total_seconds() + (attempt.retry_delay_seconds or 0.0)


def _cloud_budget_failure_reason(
    run_artifacts: CloudRunArtifacts,
    projection: ProbeRunProjection,
    store: ProbeRunStore,
) -> str | None:
    policy = run_artifacts.runtime_policy
    if projection.status == "complete":
        return None
    if len(projection.attempts) >= policy.max_total_transport_attempts:
        return "total_transport_attempt_budget_exhausted"
    if (
        sum(item.response.input_tokens for item in projection.attempts)
        >= policy.dispatch_stop_input_tokens
    ):
        return "input_token_budget_exhausted"
    if (
        sum(item.response.output_tokens for item in projection.attempts)
        >= policy.dispatch_stop_output_tokens
    ):
        return "output_token_budget_exhausted"
    if (
        sum(_attempt_elapsed_seconds(item) for item in projection.attempts)
        >= policy.dispatch_stop_cumulative_attempt_seconds
    ):
        return "cumulative_attempt_time_budget_exhausted"
    if shutil.disk_usage(store.root).free < policy.minimum_free_disk_bytes:
        return "archive_disk_safety_threshold_reached"
    return None


def _terminal_runtime_reason(
    run_artifacts: CloudRunArtifacts,
    projection: ProbeRunProjection,
    store: ProbeRunStore,
) -> str | None:
    if "runtime_failed" in projection.case_statuses.values():
        last_error = projection.attempts[-1].response.error_code
        if last_error == "provider_unreachable":
            if run_artifacts.runtime_policy.server_crash_action != (
                "retry_then_terminal_incomplete"
            ):
                raise ValueError("unsupported hash-bound server crash action")
            return "server_crash_retry_exhausted"
        if last_error == "provider_identity_mismatch":
            if run_artifacts.runtime_policy.model_identity_drift_action != ("terminal_incomplete"):
                raise ValueError("unsupported hash-bound model identity drift action")
            return "model_identity_drift"
        if last_error == "provider_missing_request_id":
            return "provider_request_identity_missing"
        if last_error == "oom":
            if run_artifacts.runtime_policy.oom_action != "terminal_incomplete":
                raise ValueError("unsupported hash-bound OOM action")
            return "oom"
        return "runtime_policy_exhausted"
    return _cloud_budget_failure_reason(run_artifacts, projection, store)


def execute_cloud_probe(
    *,
    run_artifacts: CloudRunArtifacts,
    adapter: object,
    environment_lock: EnvironmentLock | None = None,
    current_environment: EnvironmentObservation | None = None,
    manifest: CloudRunManifest | None = None,
    store: ProbeRunStore | None = None,
    stop_after_attempts: int | None = None,
) -> ProbeRunProjection:
    """Start a real cloud probe while durably appending each validated attempt."""
    checked_adapter, _, _, checked_store = _validate_execution(
        run_artifacts=run_artifacts,
        adapter=adapter,
        environment_lock=environment_lock,
        current_environment=current_environment,
        manifest=manifest,
        store=store,
    )
    terminal = _existing_terminal_record(checked_store)
    if terminal is not None:
        return reconstruct_cloud_projection(
            checked_store,
            run_artifacts=run_artifacts,
            manifest=manifest,
        )
    if checked_store.attempt_hashes:
        raise ValueError("new cloud execution requires an empty run store")
    _reconcile_dispatch_journal(checked_store, reject_unresolved=True)
    _bind_dispatch_journal(checked_adapter, checked_store)
    projection = reconstruct_cloud_projection(
        checked_store,
        run_artifacts=run_artifacts,
        manifest=manifest,
    )
    projection = _continue_cloud_probe(
        run_artifacts=run_artifacts,
        adapter=checked_adapter,
        store=checked_store,
        projection=projection,
        stop_after_attempts=stop_after_attempts,
    )
    terminal_reason = _terminal_runtime_reason(run_artifacts, projection, checked_store)
    if terminal_reason is not None:
        mark_cloud_probe_terminal(
            checked_store,
            manifest=manifest,
            status="incomplete",
            selected_candidate=None,
            reason=terminal_reason,
        )
    return projection


def resume_cloud_probe(
    *,
    manifest: CloudRunManifest,
    run_artifacts: CloudRunArtifacts,
    environment_lock: EnvironmentLock,
    current_environment: EnvironmentObservation,
    projection: ProbeRunProjection | None = None,
    adapter: object | None = None,
    store: ProbeRunStore | None = None,
    stop_after_attempts: int | None = None,
) -> ProbeRunProjection:
    """Resume only after fresh environment verification and exact prefix binding."""
    if not isinstance(run_artifacts, CloudRunArtifacts):
        raise TypeError("run_artifacts must be CloudRunArtifacts")
    if not isinstance(environment_lock, EnvironmentLock):
        raise ValueError("cloud resume requires environment lock")
    if not isinstance(current_environment, EnvironmentObservation):
        raise ValueError("cloud resume requires a fresh current environment observation")
    verify_current_environment(environment_lock, current_environment)
    checked_adapter, _, _, checked_store = _validate_execution(
        run_artifacts=run_artifacts,
        adapter=adapter,
        environment_lock=environment_lock,
        current_environment=current_environment,
        manifest=manifest,
        store=store,
    )
    terminal = _existing_terminal_record(checked_store)
    if terminal is not None:
        if projection is not None:
            raise ValueError("terminal cloud resume must reconstruct its immutable projection")
        return reconstruct_cloud_projection(
            checked_store,
            run_artifacts=run_artifacts,
            manifest=manifest,
        )
    _reconcile_dispatch_journal(checked_store, reject_unresolved=True)
    _bind_dispatch_journal(checked_adapter, checked_store)
    if projection is None:
        projection = reconstruct_cloud_projection(
            checked_store,
            run_artifacts=run_artifacts,
            manifest=manifest,
        )
    elif not isinstance(projection, ProbeRunProjection):
        raise ValueError("cloud resume projection has the wrong type")
    _persist_projection(checked_store, projection, checked_adapter)
    resumed = _continue_cloud_probe(
        run_artifacts=run_artifacts,
        adapter=checked_adapter,
        store=checked_store,
        projection=projection,
        stop_after_attempts=stop_after_attempts,
    )
    terminal_reason = _terminal_runtime_reason(run_artifacts, resumed, checked_store)
    if terminal_reason is not None:
        mark_cloud_probe_terminal(
            checked_store,
            manifest=manifest,
            status="incomplete",
            selected_candidate=None,
            reason=terminal_reason,
        )
    return resumed


@dataclass(frozen=True, slots=True)
class CloudProbeAuditReport:
    status: str
    selected_candidate: str | None
    manifest_hash: str
    terminal_record_hash: str
    attempt_hashes: tuple[str, ...]
    record_hash: str

    def __post_init__(self) -> None:
        if self.status not in {"complete", "incomplete"}:
            raise ValueError("cloud probe audit status must be terminal")
        if self.status == "incomplete" and self.selected_candidate is not None:
            raise ValueError("incomplete cloud probe cannot select a candidate")
        if self.selected_candidate is not None and (
            not isinstance(self.selected_candidate, str) or not self.selected_candidate.strip()
        ):
            raise ValueError("selected candidate must be a nonempty string or null")
        for name in ("manifest_hash", "terminal_record_hash", "record_hash"):
            _require_sha256(name, getattr(self, name))
        if type(self.attempt_hashes) is not tuple:
            raise TypeError("attempt_hashes must be a tuple")
        for digest in self.attempt_hashes:
            _require_sha256("attempt hash", digest)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": "paper1.calibration.cloud-probe-audit-report.v1",
            "status": self.status,
            "selected_candidate": self.selected_candidate,
            "manifest_hash": self.manifest_hash,
            "terminal_record_hash": self.terminal_record_hash,
            "attempt_hashes": self.attempt_hashes,
            "calibration_only": True,
            "formal_parameter_authority": False,
        }

    def to_payload(self) -> dict[str, object]:
        return _json_ready({**self.content_payload(), "record_hash": self.record_hash})


def mark_cloud_probe_terminal(
    store: ProbeRunStore,
    *,
    manifest: CloudRunManifest,
    status: str,
    selected_candidate: str | None,
    reason: str,
) -> Mapping[str, object]:
    if not isinstance(store, ProbeRunStore) or not isinstance(manifest, CloudRunManifest):
        raise TypeError("terminal marker requires store and CloudRunManifest")
    if store.manifest_hash != manifest.record_hash:
        raise ValueError("terminal marker manifest drift")
    if status not in {"complete", "incomplete"}:
        raise ValueError("terminal marker status is invalid")
    if status == "incomplete" and selected_candidate is not None:
        raise ValueError("terminal incomplete cannot select a candidate")
    if selected_candidate is not None and (
        not isinstance(selected_candidate, str) or not selected_candidate.strip()
    ):
        raise ValueError("terminal selected candidate must be a nonempty string or null")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("terminal marker requires a reason")
    _reconcile_dispatch_journal(store, reject_unresolved=True)
    content: dict[str, object] = {
        "schema_version": "paper1.calibration.cloud-terminal.v1",
        "status": status,
        "selected_candidate": selected_candidate,
        "reason": reason,
        "manifest_hash": manifest.record_hash,
        "calibration_only": True,
        "formal_parameter_authority": False,
    }
    record = {**content, "record_hash": canonical_payload_hash(content)}
    existing = _existing_terminal_record(store)
    if existing is not None:
        if existing == record:
            return existing
        raise ValueError("cloud terminal marker is irreversible")
    store.append_review(record)
    return record


def _existing_terminal_record(store: ProbeRunStore) -> Mapping[str, object] | None:
    if store._sealed:  # noqa: SLF001 - same-package validated store state
        raise RuntimeError("sealed cloud store report must be loaded from its bundle")
    records = store._load_records(  # noqa: SLF001
        store.root / "staging" / "reviews", "review"
    )
    terminal = [
        value
        for value in records.values()
        if value.get("schema_version") == "paper1.calibration.cloud-terminal.v1"
    ]
    if len(terminal) > 1:
        raise ValueError("cloud store must contain at most one terminal marker")
    if not terminal:
        return None
    record = terminal[0]
    _exact(
        record,
        {
            "schema_version",
            "status",
            "selected_candidate",
            "reason",
            "manifest_hash",
            "calibration_only",
            "formal_parameter_authority",
            "record_hash",
        },
        "cloud terminal marker",
    )
    _validated_record(record, name="cloud terminal marker")
    if record["manifest_hash"] != store.manifest_hash:
        raise ValueError("cloud terminal marker manifest drift")
    return record


def _terminal_record(store: ProbeRunStore) -> Mapping[str, object]:
    if not isinstance(store, ProbeRunStore):
        raise TypeError("cloud report requires ProbeRunStore")
    if store._sealed:  # noqa: SLF001 - same-package validated store state
        raise RuntimeError("sealed cloud store report must be loaded from its bundle")
    record = _existing_terminal_record(store)
    if record is None:
        raise RuntimeError("recoverable staging store cannot build or seal a terminal report")
    return record


def build_cloud_probe_report(store: ProbeRunStore) -> CloudProbeAuditReport:
    """Build a small terminal audit status; candidate scoring remains in ProbeReport."""
    if not isinstance(store, ProbeRunStore):
        raise TypeError("cloud report requires ProbeRunStore")
    _reconcile_dispatch_journal(store, reject_unresolved=True)
    terminal = _terminal_record(store)
    content: dict[str, object] = {
        "schema_version": "paper1.calibration.cloud-probe-audit-report.v1",
        "status": terminal["status"],
        "selected_candidate": terminal["selected_candidate"],
        "manifest_hash": store.manifest_hash,
        "terminal_record_hash": terminal["record_hash"],
        "attempt_hashes": store.attempt_hashes,
        "calibration_only": True,
        "formal_parameter_authority": False,
    }
    return CloudProbeAuditReport(
        status=terminal["status"],  # type: ignore[arg-type]
        selected_candidate=terminal["selected_candidate"],  # type: ignore[arg-type]
        manifest_hash=store.manifest_hash,
        terminal_record_hash=terminal["record_hash"],  # type: ignore[arg-type]
        attempt_hashes=store.attempt_hashes,
        record_hash=canonical_payload_hash(content),
    )


def seal_cloud_probe_report(
    store: ProbeRunStore,
    *,
    bundle: ProbeBundle | None,
    run_artifacts: CloudRunArtifacts,
    manifest: CloudRunManifest,
) -> None:
    """Seal only a bundle rebuilt from this store's exact durable evidence."""
    if not isinstance(store, ProbeRunStore):
        raise TypeError("cloud sealing requires ProbeRunStore")
    if not isinstance(run_artifacts, CloudRunArtifacts) or not isinstance(
        manifest, CloudRunManifest
    ):
        raise TypeError("cloud sealing requires authorized artifacts and manifest")
    if (
        store.manifest_hash != manifest.record_hash
        or manifest.approved_artifacts_hash != run_artifacts.record_hash
    ):
        raise ValueError("cloud seal authorization drift")
    _reconcile_dispatch_journal(store, reject_unresolved=True)
    if not isinstance(bundle, ProbeBundle):
        raise TypeError("terminal cloud probe sealing requires ProbeBundle")
    projection = reconstruct_cloud_projection(
        store,
        run_artifacts=run_artifacts,
        manifest=manifest,
    )
    source = bundle.report.source
    if source.projection.to_payload() != projection.to_payload():
        raise ValueError("probe bundle projection differs from durable cloud attempts")
    if source.specification.to_payload() != run_artifacts.specification.to_payload() or tuple(
        case.to_payload() for case in source.cases
    ) != tuple(case.to_payload() for case in run_artifacts.cases):
        raise ValueError("probe bundle source differs from authorized cloud artifacts")
    manifest_payload = bundle.to_payloads()["manifest.json"]
    if (
        not isinstance(manifest_payload, Mapping)
        or manifest_payload.get("external_archive_locator") != manifest.archive_uri
    ):
        raise ValueError("probe bundle archive locator differs from cloud manifest")
    review_records = store._load_records(  # noqa: SLF001
        store.root / "staging" / "reviews", "review"
    )
    for payload in (
        source.semantic_review.review_export.to_payload(),
        source.semantic_review.to_payload(),
    ):
        digest = review_evidence_hash(payload)
        if review_records.get(digest) != payload:
            raise ValueError("probe bundle semantic review is not durable run evidence")
    expected_status = "incomplete" if bundle.report.status == "incomplete" else "complete"
    expected_candidate = bundle.report.topic_selection.primary
    try:
        audit = build_cloud_probe_report(store)
    except RuntimeError as error:
        if "recoverable staging" not in str(error):
            raise
        mark_cloud_probe_terminal(
            store,
            manifest=manifest,
            status=expected_status,
            selected_candidate=expected_candidate,
            reason="bundle_rebuilt_from_exact_durable_cloud_evidence",
        )
        audit = build_cloud_probe_report(store)
    if audit.status != expected_status or audit.selected_candidate != expected_candidate:
        raise ValueError("terminal audit marker differs from the durable probe bundle")
    store.seal(bundle=bundle)


__all__ = [
    "AmbiguousCloudDispatchError",
    "CloudRunArtifacts",
    "CloudRunManifest",
    "CloudProbeAuditReport",
    "build_cloud_probe_report",
    "build_cloud_run_manifest",
    "execute_cloud_probe",
    "load_cloud_run_artifacts",
    "mark_cloud_probe_terminal",
    "reconstruct_cloud_projection",
    "resume_cloud_probe",
    "seal_cloud_probe_report",
]
