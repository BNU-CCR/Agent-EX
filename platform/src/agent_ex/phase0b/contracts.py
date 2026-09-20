"""Content-addressed contracts for the preliminary Phase 0B diagnostic."""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import PurePosixPath
import posixpath
import re
from typing import ClassVar, Mapping
from urllib.parse import urlparse

from ..domain import (
    _freeze,
    _json_ready,
    _require_int,
    _require_json_transport,
    _require_payload_hash,
    _require_sha256,
    _require_string,
    canonical_payload_hash,
)
from ..mock_matrix import CANONICAL_CELL_IDS


_GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_HOST_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_METADATA = {
    "calibration_only": True,
    "formal_parameter_authority": False,
    "research_parameter_status": "not_frozen",
}
_ARTIFACT_HASH_KEYS = frozenset(
    {
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
    }
)
_FORBIDDEN_CLAIMS = (
    "causal_estimate",
    "formal_experiment",
    "independent_agent_replicates",
    "inferential_statistics",
    "parameter_freeze",
    "primary_result",
)


def _exact_payload(payload: Mapping[str, object], *, expected: set[str], record_name: str) -> None:
    if type(payload) is not dict or set(payload) != expected:
        raise ValueError(f"{record_name} payload must contain exact fields including record_hash")
    _require_json_transport(payload, f"{record_name} payload")


def _require_metadata(
    *,
    schema_version: object,
    expected_schema: str,
    calibration_only: object,
    formal_parameter_authority: object,
    research_parameter_status: object,
) -> None:
    if schema_version != expected_schema:
        raise ValueError("schema_version is not supported")
    if calibration_only is not True or type(calibration_only) is not bool:
        raise ValueError("diagnostic contract must remain calibration_only=true")
    if formal_parameter_authority is not False or type(formal_parameter_authority) is not bool:
        raise ValueError("diagnostic contract must not grant formal parameter authority")
    if research_parameter_status != "not_frozen":
        raise ValueError("research_parameter_status must remain not_frozen")


def _require_resolved(value: object, field_name: str = "payload") -> None:
    if isinstance(value, str):
        if "UNRESOLVED[" in value:
            raise ValueError(f"{field_name} must not contain UNRESOLVED markers")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _require_resolved(item, f"{field_name}.{key}")
        return
    if isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            _require_resolved(item, f"{field_name}[{index}]")


def _require_positive_number(name: str, value: object) -> None:
    if type(value) not in {int, float} or value <= 0:
        raise ValueError(f"{name} must be a positive number")


def _content_payload(value: object) -> dict[str, object]:
    return {
        field.name: getattr(value, field.name)
        for field in fields(value)  # type: ignore[arg-type]
        if field.name != "record_hash"
    }


def _to_payload(value: object) -> dict[str, object]:
    content = _content_payload(value)
    return _json_ready({**content, "record_hash": getattr(value, "record_hash")})


@dataclass(frozen=True, slots=True)
class DiagnosticAttemptPolicy:
    """One explicitly bounded retry policy that cannot advance event identity."""

    schema_version: str
    calibration_only: bool
    formal_parameter_authority: bool
    research_parameter_status: str
    connect_timeout_seconds: float
    read_timeout_seconds: float
    total_timeout_seconds: float
    retryable_error_codes: tuple[str, ...]
    max_same_event_retries: int
    preserve_event_id: bool
    preserve_prompt_hash: bool
    preserve_model_seed: bool
    record_hash: str

    _SCHEMA: ClassVar[str] = "paper1.phase0b.diagnostic-attempt-policy.v1"

    def __post_init__(self) -> None:
        _require_metadata(
            schema_version=self.schema_version,
            expected_schema=self._SCHEMA,
            calibration_only=self.calibration_only,
            formal_parameter_authority=self.formal_parameter_authority,
            research_parameter_status=self.research_parameter_status,
        )
        _require_resolved(self.content_payload())
        for name in (
            "connect_timeout_seconds",
            "read_timeout_seconds",
            "total_timeout_seconds",
        ):
            _require_positive_number(name, getattr(self, name))
        if self.total_timeout_seconds < max(
            self.connect_timeout_seconds, self.read_timeout_seconds
        ):
            raise ValueError("total timeout must cover connect and read timeout budgets")
        if (
            type(self.retryable_error_codes) is not tuple
            or not self.retryable_error_codes
            or len(set(self.retryable_error_codes)) != len(self.retryable_error_codes)
        ):
            raise ValueError("retryable_error_codes must be an explicit unique tuple")
        for code in self.retryable_error_codes:
            _require_string("retryable error code", code)
        if type(self.max_same_event_retries) is not int:
            raise TypeError("max_same_event_retries must be a strict integer")
        if self.max_same_event_retries != 1:
            raise ValueError("the diagnostic permits exactly one same-event retry")
        if not all(
            flag is True and type(flag) is bool
            for flag in (
                self.preserve_event_id,
                self.preserve_prompt_hash,
                self.preserve_model_seed,
            )
        ):
            raise ValueError("same-event retry must preserve event, prompt, and model seed")
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    def content_payload(self) -> dict[str, object]:
        return _content_payload(self)

    def to_payload(self) -> dict[str, object]:
        return _to_payload(self)

    @classmethod
    def create(
        cls,
        *,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        total_timeout_seconds: float,
        retryable_error_codes: tuple[str, ...],
        max_same_event_retries: int,
    ) -> DiagnosticAttemptPolicy:
        content: dict[str, object] = {
            "schema_version": cls._SCHEMA,
            **_METADATA,
            "connect_timeout_seconds": connect_timeout_seconds,
            "read_timeout_seconds": read_timeout_seconds,
            "total_timeout_seconds": total_timeout_seconds,
            "retryable_error_codes": retryable_error_codes,
            "max_same_event_retries": max_same_event_retries,
            "preserve_event_id": True,
            "preserve_prompt_hash": True,
            "preserve_model_seed": True,
        }
        return cls(**content, record_hash=canonical_payload_hash(content))  # type: ignore[arg-type]

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> DiagnosticAttemptPolicy:
        _exact_payload(
            payload,
            expected={field.name for field in fields(cls)},
            record_name="diagnostic attempt policy",
        )
        if type(payload["retryable_error_codes"]) is not list:
            raise TypeError("retryable_error_codes must use a JSON array")
        values = dict(payload)
        values["retryable_error_codes"] = tuple(payload["retryable_error_codes"])  # type: ignore[arg-type]
        return cls(**values)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class DiagnosticAdapterBinding:
    """Pinned real-Qwen/vLLM execution identity for a diagnostic run."""

    schema_version: str
    calibration_only: bool
    formal_parameter_authority: bool
    research_parameter_status: str
    input_artifact_mode: str
    model_execution_mode: str
    model_repository: str
    model_revision: str
    tokenizer_revision: str
    chat_template_hash: str
    vllm_version: str
    package_lock_hash: str
    image_identity_hash: str
    environment_lock_hash: str
    service_start_identity_hash: str
    endpoint: str
    served_model_name: str
    record_hash: str

    _SCHEMA: ClassVar[str] = "paper1.phase0b.diagnostic-adapter-binding.v1"

    def __post_init__(self) -> None:
        _require_metadata(
            schema_version=self.schema_version,
            expected_schema=self._SCHEMA,
            calibration_only=self.calibration_only,
            formal_parameter_authority=self.formal_parameter_authority,
            research_parameter_status=self.research_parameter_status,
        )
        _require_resolved(self.content_payload())
        if self.input_artifact_mode != "synthetic_phase4b_candidate":
            raise ValueError("input artifacts must remain synthetic Phase 4B candidates")
        if self.model_execution_mode != "real_qwen_vllm":
            raise ValueError("model execution must declare real Qwen vLLM")
        for name in (
            "model_repository",
            "vllm_version",
            "served_model_name",
        ):
            _require_string(name, getattr(self, name))
        if self.model_repository != "Qwen/Qwen3-8B":
            raise ValueError("model_repository must be exactly Qwen/Qwen3-8B")
        for name in ("model_revision", "tokenizer_revision"):
            value = getattr(self, name)
            if type(value) is not str or _GIT_COMMIT.fullmatch(value) is None:
                raise ValueError(f"{name} must be a lowercase 40-character revision")
        for name in (
            "chat_template_hash",
            "package_lock_hash",
            "image_identity_hash",
            "environment_lock_hash",
            "service_start_identity_hash",
        ):
            _require_sha256(name, getattr(self, name))
        if self.endpoint != "http://127.0.0.1:8000/v1/chat/completions":
            raise ValueError("endpoint must be the exact loopback vLLM endpoint")
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    def content_payload(self) -> dict[str, object]:
        return _content_payload(self)

    def to_payload(self) -> dict[str, object]:
        return _to_payload(self)

    @classmethod
    def create(
        cls,
        *,
        model_repository: str,
        model_revision: str,
        tokenizer_revision: str,
        chat_template_hash: str,
        vllm_version: str,
        package_lock_hash: str,
        image_identity_hash: str,
        environment_lock_hash: str,
        service_start_identity_hash: str,
        endpoint: str,
        served_model_name: str,
    ) -> DiagnosticAdapterBinding:
        content: dict[str, object] = {
            "schema_version": cls._SCHEMA,
            **_METADATA,
            "input_artifact_mode": "synthetic_phase4b_candidate",
            "model_execution_mode": "real_qwen_vllm",
            "model_repository": model_repository,
            "model_revision": model_revision,
            "tokenizer_revision": tokenizer_revision,
            "chat_template_hash": chat_template_hash,
            "vllm_version": vllm_version,
            "package_lock_hash": package_lock_hash,
            "image_identity_hash": image_identity_hash,
            "environment_lock_hash": environment_lock_hash,
            "service_start_identity_hash": service_start_identity_hash,
            "endpoint": endpoint,
            "served_model_name": served_model_name,
        }
        return cls(**content, record_hash=canonical_payload_hash(content))  # type: ignore[arg-type]

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> DiagnosticAdapterBinding:
        _exact_payload(
            payload,
            expected={field.name for field in fields(cls)},
            record_name="diagnostic adapter binding",
        )
        return cls(**payload)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class DiagnosticRunAuthorization:
    """Immutable authority for one N=20/T=2 preliminary diagnostic only."""

    schema_version: str
    calibration_only: bool
    formal_parameter_authority: bool
    research_parameter_status: str
    scope: str
    input_artifact_mode: str
    model_execution_mode: str
    cell_ids: tuple[str, ...]
    matched_seed_count: int
    agent_count: int
    sweep_count: int
    expected_event_count: int
    max_transport_count: int
    artifact_hashes: Mapping[str, str]
    feed_capacity_candidate: int
    feed_capacity_research_qa_id: str
    memory_window_candidate: int
    memory_window_research_qa_id: str
    adapter_binding_hash: str
    attempt_policy_hash: str
    source_commit: str
    source_dirty: bool
    source_diff_hash: str | None
    temperature: float
    top_p: float
    max_tokens: int
    enable_thinking: bool
    matched_seed: int
    model_seed_pairing_rule: str
    disk_budget_bytes: int
    token_budget: int
    wall_clock_limit_seconds: int
    checkpoint_cadence: str
    archive_uri: str
    interpretation_label: str
    forbidden_claims: tuple[str, ...]
    record_hash: str

    _SCHEMA: ClassVar[str] = "paper1.phase0b.diagnostic-run-authorization.v1"

    def __post_init__(self) -> None:
        _require_metadata(
            schema_version=self.schema_version,
            expected_schema=self._SCHEMA,
            calibration_only=self.calibration_only,
            formal_parameter_authority=self.formal_parameter_authority,
            research_parameter_status=self.research_parameter_status,
        )
        _require_resolved(self.content_payload())
        if self.scope != "phase0b_preliminary_diagnostic_n20_t2":
            raise ValueError("scope must remain the approved preliminary diagnostic")
        if self.input_artifact_mode != "synthetic_phase4b_candidate":
            raise ValueError("input artifacts must remain synthetic Phase 4B candidates")
        if self.model_execution_mode != "real_qwen_vllm":
            raise ValueError("model execution must declare real Qwen vLLM")
        if self.cell_ids != CANONICAL_CELL_IDS:
            raise ValueError("cell_ids must contain the canonical 12 cells in canonical order")
        for name in ("matched_seed_count", "agent_count", "sweep_count"):
            if type(getattr(self, name)) is not int:
                raise TypeError(f"{name} must be a strict integer")
        if self.matched_seed_count != 1 or self.agent_count != 20 or self.sweep_count != 2:
            raise ValueError("diagnostic inventory must be one matched seed, N=20, T=2")
        if self.expected_event_count != 480:
            raise ValueError("expected_event_count must be exactly 480")
        if self.max_transport_count != 960:
            raise ValueError("max_transport_count must be exactly 960")
        if not isinstance(self.artifact_hashes, Mapping) or set(self.artifact_hashes) != (
            _ARTIFACT_HASH_KEYS
        ):
            raise ValueError("artifact hashes must contain the exact diagnostic artifact inventory")
        for name, value in self.artifact_hashes.items():
            _require_sha256(f"artifact hash {name}", value)
        if self.feed_capacity_candidate != 6:
            raise ValueError("feed capacity must use the approved B=6 diagnostic candidate")
        if self.feed_capacity_research_qa_id != "P1_MAX_NEIGHBORS":
            raise ValueError("feed capacity must bind research QA ID P1_MAX_NEIGHBORS")
        if self.memory_window_candidate != 3:
            raise ValueError("memory window must use the approved K=3 diagnostic candidate")
        if self.memory_window_research_qa_id != "P1_MEMORY_WINDOW":
            raise ValueError("memory window must bind research QA ID P1_MEMORY_WINDOW")
        for name in ("adapter_binding_hash", "attempt_policy_hash"):
            _require_sha256(name, getattr(self, name))
        if type(self.source_commit) is not str or _GIT_COMMIT.fullmatch(self.source_commit) is None:
            raise ValueError("source_commit must be a lowercase 40-character Git commit")
        if type(self.source_dirty) is not bool:
            raise TypeError("source_dirty must be a boolean")
        if self.source_dirty:
            if self.source_diff_hash is None:
                raise ValueError("dirty source requires a source_diff_hash")
            _require_sha256("source_diff_hash", self.source_diff_hash)
        elif self.source_diff_hash is not None:
            raise ValueError("clean source must not declare a source_diff_hash")
        if self.temperature != 0.7 or self.top_p != 0.8 or self.max_tokens != 128:
            raise ValueError("generation settings must use the approved diagnostic candidates")
        if self.enable_thinking is not False or type(self.enable_thinking) is not bool:
            raise ValueError("enable_thinking must be false")
        _require_int("matched_seed", self.matched_seed, minimum=0)
        _require_string("model_seed_pairing_rule", self.model_seed_pairing_rule)
        for name in (
            "disk_budget_bytes",
            "token_budget",
            "wall_clock_limit_seconds",
        ):
            _require_int(name, getattr(self, name), minimum=1)
        if self.checkpoint_cadence != "completed_sweep_and_cell":
            raise ValueError("checkpoint cadence must cover each completed sweep and cell")
        self._validate_external_archive()
        if self.interpretation_label != "preliminary_descriptive_feasibility_only":
            raise ValueError("interpretation must remain preliminary and descriptive")
        if self.forbidden_claims != _FORBIDDEN_CLAIMS:
            raise ValueError("forbidden_claims must contain the complete canonical prohibition set")
        object.__setattr__(self, "artifact_hashes", _freeze(self.artifact_hashes))
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    def _validate_external_archive(self) -> None:
        parsed = urlparse(self.archive_uri)
        if parsed.scheme:
            hostname = parsed.hostname
            hostname_is_valid = (
                hostname is not None
                and len(hostname) <= 253
                and all(_HOST_LABEL.fullmatch(label) is not None for label in hostname.split("."))
            )
            if (
                parsed.scheme not in {"s3", "gs", "az"}
                or not parsed.netloc
                or parsed.username is not None
                or parsed.password is not None
                or not hostname_is_valid
                or parsed.path in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("archive_uri must point to an approved external archive")
            return
        normalized = posixpath.normpath(self.archive_uri)
        path = PurePosixPath(normalized)
        archive_root = PurePosixPath("/root/autodl-tmp")
        if (
            normalized != self.archive_uri
            or not path.is_absolute()
            or path == archive_root
            or not path.is_relative_to(archive_root)
        ):
            raise ValueError("archive_uri must be outside Git under /root/autodl-tmp")

    def content_payload(self) -> dict[str, object]:
        return _content_payload(self)

    def to_payload(self) -> dict[str, object]:
        return _to_payload(self)

    @classmethod
    def create(
        cls,
        *,
        cell_ids: tuple[str, ...],
        artifact_hashes: Mapping[str, str],
        feed_capacity_candidate: int,
        feed_capacity_research_qa_id: str,
        memory_window_candidate: int,
        memory_window_research_qa_id: str,
        adapter_binding_hash: str,
        attempt_policy_hash: str,
        source_commit: str,
        source_dirty: bool,
        source_diff_hash: str | None,
        temperature: float,
        top_p: float,
        max_tokens: int,
        enable_thinking: bool,
        matched_seed: int,
        model_seed_pairing_rule: str,
        disk_budget_bytes: int,
        token_budget: int,
        wall_clock_limit_seconds: int,
        checkpoint_cadence: str,
        archive_uri: str,
        forbidden_claims: tuple[str, ...],
    ) -> DiagnosticRunAuthorization:
        content: dict[str, object] = {
            "schema_version": cls._SCHEMA,
            **_METADATA,
            "scope": "phase0b_preliminary_diagnostic_n20_t2",
            "input_artifact_mode": "synthetic_phase4b_candidate",
            "model_execution_mode": "real_qwen_vllm",
            "cell_ids": cell_ids,
            "matched_seed_count": 1,
            "agent_count": 20,
            "sweep_count": 2,
            "expected_event_count": 480,
            "max_transport_count": 960,
            "artifact_hashes": dict(artifact_hashes),
            "feed_capacity_candidate": feed_capacity_candidate,
            "feed_capacity_research_qa_id": feed_capacity_research_qa_id,
            "memory_window_candidate": memory_window_candidate,
            "memory_window_research_qa_id": memory_window_research_qa_id,
            "adapter_binding_hash": adapter_binding_hash,
            "attempt_policy_hash": attempt_policy_hash,
            "source_commit": source_commit,
            "source_dirty": source_dirty,
            "source_diff_hash": source_diff_hash,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "enable_thinking": enable_thinking,
            "matched_seed": matched_seed,
            "model_seed_pairing_rule": model_seed_pairing_rule,
            "disk_budget_bytes": disk_budget_bytes,
            "token_budget": token_budget,
            "wall_clock_limit_seconds": wall_clock_limit_seconds,
            "checkpoint_cadence": checkpoint_cadence,
            "archive_uri": archive_uri,
            "interpretation_label": "preliminary_descriptive_feasibility_only",
            "forbidden_claims": forbidden_claims,
        }
        return cls(**content, record_hash=canonical_payload_hash(content))  # type: ignore[arg-type]

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> DiagnosticRunAuthorization:
        _exact_payload(
            payload,
            expected={field.name for field in fields(cls)},
            record_name="diagnostic run authorization",
        )
        if type(payload["cell_ids"]) is not list:
            raise TypeError("cell_ids must use a JSON array")
        if type(payload["artifact_hashes"]) is not dict:
            raise TypeError("artifact_hashes must use a JSON object")
        if type(payload["forbidden_claims"]) is not list:
            raise TypeError("forbidden_claims must use a JSON array")
        values = dict(payload)
        values["cell_ids"] = tuple(payload["cell_ids"])  # type: ignore[arg-type]
        values["forbidden_claims"] = tuple(payload["forbidden_claims"])  # type: ignore[arg-type]
        return cls(**values)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class DiagnosticTerminalReport:
    """Sanitized terminal-count skeleton; it contains no prompt or response text."""

    schema_version: str
    calibration_only: bool
    formal_parameter_authority: bool
    research_parameter_status: str
    authorization_hash: str
    terminal_status: str
    completed_cell_ids: tuple[str, ...]
    committed_event_count: int
    transport_count: int
    unresolved_dispatch_count: int
    final_projection_hash: str
    record_hash: str

    _SCHEMA: ClassVar[str] = "paper1.phase0b.diagnostic-terminal-report.v1"

    def __post_init__(self) -> None:
        _require_metadata(
            schema_version=self.schema_version,
            expected_schema=self._SCHEMA,
            calibration_only=self.calibration_only,
            formal_parameter_authority=self.formal_parameter_authority,
            research_parameter_status=self.research_parameter_status,
        )
        _require_resolved(self.content_payload())
        _require_sha256("authorization_hash", self.authorization_hash)
        if self.terminal_status not in {"complete", "terminal_incomplete"}:
            raise ValueError("terminal_status is unsupported")
        if type(self.completed_cell_ids) is not tuple or not set(self.completed_cell_ids).issubset(
            CANONICAL_CELL_IDS
        ):
            raise ValueError("completed_cell_ids must be canonical and unique")
        if len(set(self.completed_cell_ids)) != len(self.completed_cell_ids):
            raise ValueError("completed_cell_ids must be canonical and unique")
        for name in (
            "committed_event_count",
            "transport_count",
            "unresolved_dispatch_count",
        ):
            _require_int(name, getattr(self, name), minimum=0)
        if self.unresolved_dispatch_count > 1:
            raise ValueError(
                "unresolved_dispatch_count cannot exceed the single strict-serial inflight request"
            )
        if self.terminal_status == "terminal_incomplete":
            completed_cell_count = len(self.completed_cell_ids)
            if completed_cell_count == len(CANONICAL_CELL_IDS):
                raise ValueError("terminal_incomplete cannot list all 12 completed cells")
            if self.completed_cell_ids != CANONICAL_CELL_IDS[:completed_cell_count]:
                raise ValueError("completed_cell_ids must be a strict canonical cell prefix")
            minimum_committed = completed_cell_count * 40
            maximum_committed = minimum_committed + 39
            if not minimum_committed <= self.committed_event_count <= maximum_committed:
                raise ValueError(
                    "terminal_incomplete must bind 40 events per completed cell plus at most "
                    "39 events in the current cell"
                )
        if self.transport_count > 960:
            raise ValueError("transport_count exceeds the diagnostic ceiling")
        if self.transport_count < self.committed_event_count:
            raise ValueError("transport_count cannot be lower than committed_event_count")
        if self.terminal_status == "complete" and (
            self.completed_cell_ids != CANONICAL_CELL_IDS
            or self.committed_event_count != 480
            or self.unresolved_dispatch_count != 0
        ):
            raise ValueError(
                "complete terminal report requires all 12 cells, 480 events, and no unresolved dispatch"
            )
        if self.committed_event_count > 480:
            raise ValueError("committed_event_count exceeds 480")
        _require_sha256("final_projection_hash", self.final_projection_hash)
        _require_sha256("record_hash", self.record_hash)
        _require_payload_hash("record_hash", self.record_hash, self.content_payload())

    def content_payload(self) -> dict[str, object]:
        return _content_payload(self)

    def to_payload(self) -> dict[str, object]:
        return _to_payload(self)

    @classmethod
    def create(
        cls,
        *,
        authorization_hash: str,
        terminal_status: str,
        completed_cell_ids: tuple[str, ...],
        committed_event_count: int,
        transport_count: int,
        unresolved_dispatch_count: int,
        final_projection_hash: str,
    ) -> DiagnosticTerminalReport:
        content: dict[str, object] = {
            "schema_version": cls._SCHEMA,
            **_METADATA,
            "authorization_hash": authorization_hash,
            "terminal_status": terminal_status,
            "completed_cell_ids": completed_cell_ids,
            "committed_event_count": committed_event_count,
            "transport_count": transport_count,
            "unresolved_dispatch_count": unresolved_dispatch_count,
            "final_projection_hash": final_projection_hash,
        }
        return cls(**content, record_hash=canonical_payload_hash(content))  # type: ignore[arg-type]

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> DiagnosticTerminalReport:
        _exact_payload(
            payload,
            expected={field.name for field in fields(cls)},
            record_name="diagnostic terminal report",
        )
        if type(payload["completed_cell_ids"]) is not list:
            raise TypeError("completed_cell_ids must use a JSON array")
        values = dict(payload)
        values["completed_cell_ids"] = tuple(payload["completed_cell_ids"])  # type: ignore[arg-type]
        return cls(**values)  # type: ignore[arg-type]
