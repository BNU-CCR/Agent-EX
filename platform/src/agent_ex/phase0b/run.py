"""Preliminary Phase 0B diagnostic runner staging.

This module is intentionally smaller than the formal SQLite/recovery path. It
only provides an append-only, sanitized staging slice for the N=20/T=2 fast
track while the authoritative v6 diagnostic storage migration remains pending.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping

from ..domain import canonical_payload_hash
from ..mock_matrix import CANONICAL_CELL_IDS
from ..topic import TopicPackage
from .contracts import (
    DiagnosticAdapterBinding,
    DiagnosticAttemptPolicy,
    DiagnosticRunAuthorization,
    DiagnosticTerminalReport,
)
from .matrix import DiagnosticMatrixCandidate
from .pipeline import (
    DiagnosticEventState,
    apply_diagnostic_vllm_response,
    prepare_diagnostic_event,
)
from .vllm_event_adapter import (
    Phase0BDispatchJournal,
    Phase0BVllmEventRequest,
    Phase0BVllmEventResponse,
)


@dataclass(frozen=True, slots=True)
class DiagnosticRunPreflight:
    """Sanitized proof that a diagnostic launch matches its immutable authority."""

    authorization_hash: str
    matrix_hash: str
    adapter_binding_hash: str
    attempt_policy_hash: str
    expected_event_count: int
    max_transport_count: int
    unresolved_dispatch_count: int
    record_hash: str


@dataclass(frozen=True, slots=True)
class DiagnosticFakeSliceResult:
    """Terminal evidence for a local fake execution slice."""

    preflight: DiagnosticRunPreflight
    terminal_report: DiagnosticTerminalReport
    final_projection_hash: str
    committed_event_count: int
    transport_count: int


@dataclass(frozen=True, slots=True)
class DiagnosticMatrixRunResult:
    """Terminal evidence for a full 12-cell preliminary diagnostic staging run."""

    preflight: DiagnosticRunPreflight
    terminal_report: DiagnosticTerminalReport
    final_projection_hash: str
    committed_event_count: int
    transport_count: int


@dataclass(frozen=True, slots=True)
class DiagnosticApprovalPacket:
    """Sanitized source/authority packet for the cloud launch approval gate."""

    schema_version: str
    calibration_only: bool
    formal_parameter_authority: bool
    research_parameter_status: str
    source_commit: str
    source_dirty: bool
    source_diff_hash: str | None
    authorization_hash: str
    matrix_hash: str
    adapter_binding_hash: str
    attempt_policy_hash: str
    expected_event_count: int
    max_transport_count: int
    archive_uri: str
    endpoint: str
    served_model_name: str
    model_repository: str
    labels: tuple[str, ...]
    record_hash: str

    def content_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "calibration_only": self.calibration_only,
            "formal_parameter_authority": self.formal_parameter_authority,
            "research_parameter_status": self.research_parameter_status,
            "source_commit": self.source_commit,
            "source_dirty": self.source_dirty,
            "source_diff_hash": self.source_diff_hash,
            "authorization_hash": self.authorization_hash,
            "matrix_hash": self.matrix_hash,
            "adapter_binding_hash": self.adapter_binding_hash,
            "attempt_policy_hash": self.attempt_policy_hash,
            "expected_event_count": self.expected_event_count,
            "max_transport_count": self.max_transport_count,
            "archive_uri": self.archive_uri,
            "endpoint": self.endpoint,
            "served_model_name": self.served_model_name,
            "model_repository": self.model_repository,
            "labels": self.labels,
        }

    def to_payload(self) -> dict[str, object]:
        return {**self.content_payload(), "record_hash": self.record_hash}


class Phase0BJsonlStagingStore:
    """Append-only JSONL staging for preliminary runner evidence.

    The store never writes raw prompts or raw model responses. It keeps only
    hashes and transport summaries that are safe to commit as diagnostic proof.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def append_jsonl(self, name: str, payload: Mapping[str, object]) -> None:
        if "/" in name or "\\" in name:
            raise ValueError("staging JSONL name must be local to the staging root")
        self.root.mkdir(parents=True, exist_ok=True)
        content = dict(payload)
        record = {**content, "record_hash": canonical_payload_hash(content)}
        with (self.root / name).open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")

    def write_json(self, name: str, payload: Mapping[str, object]) -> str:
        if "/" in name or "\\" in name:
            raise ValueError("staging JSON name must be local to the staging root")
        self.root.mkdir(parents=True, exist_ok=True)
        content = {key: value for key, value in payload.items() if key != "record_hash"}
        record_hash = canonical_payload_hash(content)
        record = {**content, "record_hash": record_hash}
        (self.root / name).write_text(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        return record_hash

    def read_jsonl(self, name: str) -> list[dict[str, object]]:
        path = self.root / name
        if not path.exists():
            return []
        records: list[dict[str, object]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                payload = json.loads(line)
                if type(payload) is not dict:
                    raise ValueError("staging record must be an object")
                record_hash = payload.get("record_hash")
                content = {key: value for key, value in payload.items() if key != "record_hash"}
                if record_hash != canonical_payload_hash(content):
                    raise ValueError(f"staging record hash drift at line {line_number}")
                records.append(payload)
        return records

    def read_json(self, name: str) -> dict[str, object]:
        path = self.root / name
        if not path.exists():
            raise FileNotFoundError(f"missing staging JSON: {name}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if type(payload) is not dict:
            raise ValueError("staging JSON record must be an object")
        record_hash = payload.get("record_hash")
        content = {key: value for key, value in payload.items() if key != "record_hash"}
        if record_hash != canonical_payload_hash(content):
            raise ValueError("staging JSON record hash drift")
        return payload


def preflight_diagnostic_run(
    *,
    authorization: DiagnosticRunAuthorization,
    matrix_candidate: DiagnosticMatrixCandidate,
    adapter_binding: DiagnosticAdapterBinding,
    attempt_policy: DiagnosticAttemptPolicy,
    run_root: str | Path,
) -> DiagnosticRunPreflight:
    """Validate the minimum evidence chain before launching a diagnostic run."""

    if not isinstance(authorization, DiagnosticRunAuthorization):
        raise TypeError("authorization must be a DiagnosticRunAuthorization")
    if not isinstance(matrix_candidate, DiagnosticMatrixCandidate):
        raise TypeError("matrix_candidate must be a DiagnosticMatrixCandidate")
    if not isinstance(adapter_binding, DiagnosticAdapterBinding):
        raise TypeError("adapter_binding must be a DiagnosticAdapterBinding")
    if not isinstance(attempt_policy, DiagnosticAttemptPolicy):
        raise TypeError("attempt_policy must be a DiagnosticAttemptPolicy")

    root = Path(run_root)
    if root.exists() and any(root.iterdir()):
        raise RuntimeError("run root already exists or contains unresolved dispatch evidence")
    if authorization.adapter_binding_hash != adapter_binding.record_hash:
        raise ValueError("adapter binding hash does not match authorization")
    if authorization.attempt_policy_hash != attempt_policy.record_hash:
        raise ValueError("attempt policy hash does not match authorization")
    if authorization.artifact_hashes != matrix_candidate.authorization_artifact_hashes:
        raise ValueError("authorization artifact hashes drifted from matrix candidate")
    if authorization.cell_ids != matrix_candidate.cell_ids:
        raise ValueError("authorization cells drifted from matrix candidate")
    if authorization.expected_event_count != matrix_candidate.expected_event_count:
        raise ValueError("authorization event count drifted from matrix candidate")
    if authorization.max_transport_count != matrix_candidate.max_transport_count:
        raise ValueError("authorization transport ceiling drifted from matrix candidate")
    if matrix_candidate.expected_event_count != 480 or matrix_candidate.max_transport_count != 960:
        raise ValueError("diagnostic preflight requires exactly 480 events and 960 transports")

    dispatch_path = root / "dispatch.jsonl"
    unresolved = 0
    if dispatch_path.exists():
        unresolved = len(Phase0BDispatchJournal(dispatch_path).unresolved_request_ids())
    if unresolved:
        raise RuntimeError("unresolved dispatch evidence prevents diagnostic launch")

    content = {
        "authorization_hash": authorization.record_hash,
        "matrix_hash": matrix_candidate.matrix_hash,
        "adapter_binding_hash": adapter_binding.record_hash,
        "attempt_policy_hash": attempt_policy.record_hash,
        "expected_event_count": matrix_candidate.expected_event_count,
        "max_transport_count": matrix_candidate.max_transport_count,
        "unresolved_dispatch_count": unresolved,
    }
    return DiagnosticRunPreflight(**content, record_hash=canonical_payload_hash(content))


def run_fake_diagnostic_slice(
    *,
    authorization: DiagnosticRunAuthorization,
    matrix_candidate: DiagnosticMatrixCandidate,
    adapter_binding: DiagnosticAdapterBinding,
    attempt_policy: DiagnosticAttemptPolicy,
    adapter: object,
    run_root: str | Path,
    event_count: int,
) -> DiagnosticFakeSliceResult:
    """Run a tiny fake local slice through the Phase 0B request/journal contracts."""

    if type(event_count) is not int or not 1 <= event_count <= 39:
        raise ValueError("fake diagnostic slice must run between 1 and 39 events in one cell")
    root = Path(run_root)
    if root.exists():
        raise FileExistsError("diagnostic launch root already exists")

    preflight = preflight_diagnostic_run(
        authorization=authorization,
        matrix_candidate=matrix_candidate,
        adapter_binding=adapter_binding,
        attempt_policy=attempt_policy,
        run_root=root,
    )
    staging = Phase0BJsonlStagingStore(root / "staging")
    journal = Phase0BDispatchJournal(root / "dispatch.jsonl")

    if not hasattr(adapter, "bind_dispatch_journal") or not hasattr(adapter, "generate"):
        raise TypeError("adapter must expose bind_dispatch_journal and generate")
    adapter.bind_dispatch_journal(journal.record_before_dispatch)

    request_hashes: list[str] = []
    response_hashes: list[str] = []
    for offset in range(event_count):
        request = _fake_request_for_event(
            authorization=authorization,
            adapter_binding=adapter_binding,
            offset=offset,
        )
        response = adapter.generate(
            request,
            timeout_seconds=attempt_policy.total_timeout_seconds,
            connect_timeout_seconds=attempt_policy.connect_timeout_seconds,
            read_timeout_seconds=attempt_policy.read_timeout_seconds,
        )
        if not isinstance(response, Phase0BVllmEventResponse):
            raise TypeError("adapter returned an unsupported response type")
        journal.record_resolution(response)
        _append_sanitized_attempt(staging, request, response)
        request_hashes.append(request.record_hash)
        response_hashes.append(response.record_hash)

    unresolved_dispatch_count = len(journal.unresolved_request_ids())
    projection_hash = staging.write_json(
        "projection.json",
        {
            "schema_version": "paper1.phase0b.fake-slice-projection.v1",
            "authorization_hash": authorization.record_hash,
            "matrix_hash": matrix_candidate.matrix_hash,
            "committed_event_count": event_count,
            "transport_count": len(response_hashes),
            "unresolved_dispatch_count": unresolved_dispatch_count,
            "request_hashes": tuple(request_hashes),
            "response_hashes": tuple(response_hashes),
        },
    )
    terminal_report = DiagnosticTerminalReport.create(
        authorization_hash=authorization.record_hash,
        terminal_status="terminal_incomplete",
        completed_cell_ids=(),
        committed_event_count=event_count,
        transport_count=len(response_hashes),
        unresolved_dispatch_count=unresolved_dispatch_count,
        final_projection_hash=projection_hash,
    )
    staging.write_json("terminal-report.json", terminal_report.to_payload())
    return DiagnosticFakeSliceResult(
        preflight=preflight,
        terminal_report=terminal_report,
        final_projection_hash=projection_hash,
        committed_event_count=event_count,
        transport_count=len(response_hashes),
    )


def run_fake_diagnostic_matrix(
    *,
    authorization: DiagnosticRunAuthorization,
    matrix_candidate: DiagnosticMatrixCandidate,
    adapter_binding: DiagnosticAdapterBinding,
    attempt_policy: DiagnosticAttemptPolicy,
    adapter: object,
    run_root: str | Path,
) -> DiagnosticMatrixRunResult:
    """Run all 12 diagnostic cells through the safe fake transport contract.

    This is a local staging runner for the fast-track path.  It proves the
    12-cell/480-event orchestration, terminal accounting, dispatch journal, and
    sanitized export shape without contacting a real model.
    """

    root = Path(run_root)
    if root.exists():
        raise FileExistsError("diagnostic launch root already exists")

    preflight = preflight_diagnostic_run(
        authorization=authorization,
        matrix_candidate=matrix_candidate,
        adapter_binding=adapter_binding,
        attempt_policy=attempt_policy,
        run_root=root,
    )
    staging = Phase0BJsonlStagingStore(root / "staging")
    journal = Phase0BDispatchJournal(root / "dispatch.jsonl")

    if not hasattr(adapter, "bind_dispatch_journal") or not hasattr(adapter, "generate"):
        raise TypeError("adapter must expose bind_dispatch_journal and generate")
    adapter.bind_dispatch_journal(journal.record_before_dispatch)

    request_hashes: list[str] = []
    response_hashes: list[str] = []
    cell_summaries: list[dict[str, object]] = []
    for cell_index, cell_id in enumerate(CANONICAL_CELL_IDS):
        cell_request_hashes: list[str] = []
        cell_response_hashes: list[str] = []
        for event_offset in range(40):
            global_offset = cell_index * 40 + event_offset
            request = _fake_request_for_event(
                authorization=authorization,
                adapter_binding=adapter_binding,
                offset=global_offset,
                cell_id=cell_id,
            )
            response = adapter.generate(
                request,
                timeout_seconds=attempt_policy.total_timeout_seconds,
                connect_timeout_seconds=attempt_policy.connect_timeout_seconds,
                read_timeout_seconds=attempt_policy.read_timeout_seconds,
            )
            if not isinstance(response, Phase0BVllmEventResponse):
                raise TypeError("adapter returned an unsupported response type")
            journal.record_resolution(response)
            _append_sanitized_attempt(staging, request, response, cell_id=cell_id)
            request_hashes.append(request.record_hash)
            response_hashes.append(response.record_hash)
            cell_request_hashes.append(request.record_hash)
            cell_response_hashes.append(response.record_hash)
        cell_summaries.append(
            {
                "cell_id": cell_id,
                "committed_event_count": len(cell_request_hashes),
                "transport_count": len(cell_response_hashes),
                "request_hashes_hash": canonical_payload_hash(tuple(cell_request_hashes)),
                "response_hashes_hash": canonical_payload_hash(tuple(cell_response_hashes)),
            }
        )

    unresolved_dispatch_count = len(journal.unresolved_request_ids())
    projection_hash = staging.write_json(
        "projection.json",
        {
            "schema_version": "paper1.phase0b.fake-matrix-projection.v1",
            "authorization_hash": authorization.record_hash,
            "matrix_hash": matrix_candidate.matrix_hash,
            "committed_event_count": len(request_hashes),
            "transport_count": len(response_hashes),
            "unresolved_dispatch_count": unresolved_dispatch_count,
            "completed_cell_ids": CANONICAL_CELL_IDS,
            "cell_summaries": tuple(cell_summaries),
            "request_hashes_hash": canonical_payload_hash(tuple(request_hashes)),
            "response_hashes_hash": canonical_payload_hash(tuple(response_hashes)),
        },
    )
    terminal_report = DiagnosticTerminalReport.create(
        authorization_hash=authorization.record_hash,
        terminal_status="complete",
        completed_cell_ids=CANONICAL_CELL_IDS,
        committed_event_count=len(request_hashes),
        transport_count=len(response_hashes),
        unresolved_dispatch_count=unresolved_dispatch_count,
        final_projection_hash=projection_hash,
    )
    staging.write_json("terminal-report.json", terminal_report.to_payload())
    return DiagnosticMatrixRunResult(
        preflight=preflight,
        terminal_report=terminal_report,
        final_projection_hash=projection_hash,
        committed_event_count=len(request_hashes),
        transport_count=len(response_hashes),
    )


def run_real_adapter_diagnostic_matrix(
    *,
    authorization: DiagnosticRunAuthorization,
    matrix_candidate: DiagnosticMatrixCandidate,
    adapter_binding: DiagnosticAdapterBinding,
    attempt_policy: DiagnosticAttemptPolicy,
    adapter: object,
    topic_package: TopicPackage,
    run_root: str | Path,
) -> DiagnosticMatrixRunResult:
    """Run the 12-cell staging matrix through a real-adapter-shaped event loop.

    The adapter may be a fake in tests, but it must expose the same
    bind-before-dispatch and generate interface as Phase0BVllmEventAdapter.
    """

    if not isinstance(topic_package, TopicPackage):
        raise TypeError("topic_package must be a TopicPackage")
    root = Path(run_root)
    if root.exists():
        raise FileExistsError("diagnostic launch root already exists")

    preflight = preflight_diagnostic_run(
        authorization=authorization,
        matrix_candidate=matrix_candidate,
        adapter_binding=adapter_binding,
        attempt_policy=attempt_policy,
        run_root=root,
    )
    staging = Phase0BJsonlStagingStore(root / "staging")
    journal = Phase0BDispatchJournal(root / "dispatch.jsonl")

    if not hasattr(adapter, "bind_dispatch_journal") or not hasattr(adapter, "generate"):
        raise TypeError("adapter must expose bind_dispatch_journal and generate")
    adapter.bind_dispatch_journal(journal.record_before_dispatch)

    request_hashes: list[str] = []
    response_hashes: list[str] = []
    evidence_hashes: list[str] = []
    cell_summaries: list[dict[str, object]] = []
    for cell_id in CANONICAL_CELL_IDS:
        state = DiagnosticEventState.initial(
            topic_package=topic_package,
            matched_seed=authorization.matched_seed,
            agent_id=f"{cell_id}-agent-0000",
            stance_label="label-4",
            reason="phase0b-diagnostic-round-zero",
        )
        cell_request_hashes: list[str] = []
        cell_response_hashes: list[str] = []
        cell_evidence_hashes: list[str] = []
        for event_offset in range(40):
            prepared = prepare_diagnostic_event(
                state=state,
                authorization=authorization,
                adapter_binding=adapter_binding,
                publish_flag=True,
            )
            response = adapter.generate(
                prepared.request,
                timeout_seconds=attempt_policy.total_timeout_seconds,
                connect_timeout_seconds=attempt_policy.connect_timeout_seconds,
                read_timeout_seconds=attempt_policy.read_timeout_seconds,
            )
            if not isinstance(response, Phase0BVllmEventResponse):
                raise TypeError("adapter returned an unsupported response type")
            journal.record_resolution(response)
            result = apply_diagnostic_vllm_response(
                state=state,
                prepared=prepared,
                response=response,
                topic_package=topic_package,
            )
            _append_sanitized_attempt(
                staging,
                prepared.request,
                response,
                cell_id=cell_id,
                schema_version="paper1.phase0b.real-adapter-attempt.v1",
                pipeline_evidence_hash=result.evidence.record_hash,
                committed_state_hash=result.state.record_hash if result.committed else None,
            )
            request_hashes.append(prepared.request.record_hash)
            response_hashes.append(response.record_hash)
            evidence_hashes.append(result.evidence.record_hash)
            cell_request_hashes.append(prepared.request.record_hash)
            cell_response_hashes.append(response.record_hash)
            cell_evidence_hashes.append(result.evidence.record_hash)
            if not result.committed:
                raise RuntimeError("diagnostic real-adapter matrix stopped before terminal commit")
            state = result.state
            if state.next_event_ordinal != event_offset + 1:
                raise RuntimeError("diagnostic event prefix advanced unexpectedly")
        cell_summaries.append(
            {
                "cell_id": cell_id,
                "committed_event_count": len(cell_request_hashes),
                "transport_count": len(cell_response_hashes),
                "request_hashes_hash": canonical_payload_hash(tuple(cell_request_hashes)),
                "response_hashes_hash": canonical_payload_hash(tuple(cell_response_hashes)),
                "pipeline_evidence_hashes_hash": canonical_payload_hash(
                    tuple(cell_evidence_hashes)
                ),
                "final_state_hash": state.record_hash,
            }
        )

    unresolved_dispatch_count = len(journal.unresolved_request_ids())
    projection_hash = staging.write_json(
        "projection.json",
        {
            "schema_version": "paper1.phase0b.real-adapter-matrix-projection.v1",
            "authorization_hash": authorization.record_hash,
            "matrix_hash": matrix_candidate.matrix_hash,
            "committed_event_count": len(request_hashes),
            "transport_count": len(response_hashes),
            "unresolved_dispatch_count": unresolved_dispatch_count,
            "completed_cell_ids": CANONICAL_CELL_IDS,
            "cell_summaries": tuple(cell_summaries),
            "request_hashes_hash": canonical_payload_hash(tuple(request_hashes)),
            "response_hashes_hash": canonical_payload_hash(tuple(response_hashes)),
            "pipeline_evidence_hashes_hash": canonical_payload_hash(tuple(evidence_hashes)),
        },
    )
    terminal_report = DiagnosticTerminalReport.create(
        authorization_hash=authorization.record_hash,
        terminal_status="complete",
        completed_cell_ids=CANONICAL_CELL_IDS,
        committed_event_count=len(request_hashes),
        transport_count=len(response_hashes),
        unresolved_dispatch_count=unresolved_dispatch_count,
        final_projection_hash=projection_hash,
    )
    staging.write_json("terminal-report.json", terminal_report.to_payload())
    return DiagnosticMatrixRunResult(
        preflight=preflight,
        terminal_report=terminal_report,
        final_projection_hash=projection_hash,
        committed_event_count=len(request_hashes),
        transport_count=len(response_hashes),
    )


def materialize_diagnostic_approval_packet(
    *,
    authorization: DiagnosticRunAuthorization,
    matrix_candidate: DiagnosticMatrixCandidate,
    adapter_binding: DiagnosticAdapterBinding,
    attempt_policy: DiagnosticAttemptPolicy,
) -> DiagnosticApprovalPacket:
    """Create the sanitized approval gate packet without launching cloud work."""

    if authorization.adapter_binding_hash != adapter_binding.record_hash:
        raise ValueError("adapter binding hash does not match authorization")
    if authorization.attempt_policy_hash != attempt_policy.record_hash:
        raise ValueError("attempt policy hash does not match authorization")
    if authorization.artifact_hashes != matrix_candidate.authorization_artifact_hashes:
        raise ValueError("authorization artifact hashes drifted from matrix candidate")
    content = {
        "schema_version": "paper1.phase0b.diagnostic-approval-packet.v1",
        "calibration_only": True,
        "formal_parameter_authority": False,
        "research_parameter_status": "not_frozen",
        "source_commit": authorization.source_commit,
        "source_dirty": authorization.source_dirty,
        "source_diff_hash": authorization.source_diff_hash,
        "authorization_hash": authorization.record_hash,
        "matrix_hash": matrix_candidate.matrix_hash,
        "adapter_binding_hash": adapter_binding.record_hash,
        "attempt_policy_hash": attempt_policy.record_hash,
        "expected_event_count": matrix_candidate.expected_event_count,
        "max_transport_count": matrix_candidate.max_transport_count,
        "archive_uri": authorization.archive_uri,
        "endpoint": adapter_binding.endpoint,
        "served_model_name": adapter_binding.served_model_name,
        "model_repository": adapter_binding.model_repository,
        "labels": ("preliminary", "diagnostic", "not_frozen"),
    }
    return DiagnosticApprovalPacket(
        **content,
        record_hash=canonical_payload_hash(content),
    )


def verify_diagnostic_matrix_run(
    *,
    run_root: str | Path,
    authorization: DiagnosticRunAuthorization,
    matrix_candidate: DiagnosticMatrixCandidate,
) -> DiagnosticTerminalReport:
    """Verify a terminal Phase 0B staging run without contacting any model."""

    root = Path(run_root)
    staging = Phase0BJsonlStagingStore(root / "staging")
    projection = staging.read_json("projection.json")
    terminal = DiagnosticTerminalReport.from_payload(staging.read_json("terminal-report.json"))
    attempts = staging.read_jsonl("attempts.jsonl")
    unresolved = len(Phase0BDispatchJournal(root / "dispatch.jsonl").unresolved_request_ids())

    if projection["authorization_hash"] != authorization.record_hash:
        raise ValueError("projection authorization hash drift")
    if projection["matrix_hash"] != matrix_candidate.matrix_hash:
        raise ValueError("projection matrix hash drift")
    if terminal.authorization_hash != authorization.record_hash:
        raise ValueError("terminal report authorization hash drift")
    if terminal.final_projection_hash != projection["record_hash"]:
        raise ValueError("terminal report projection hash drift")
    if terminal.terminal_status != "complete":
        raise ValueError("terminal report is not complete")
    if terminal.completed_cell_ids != CANONICAL_CELL_IDS:
        raise ValueError("terminal report does not cover all canonical cells")
    if terminal.committed_event_count != 480 or len(attempts) != 480:
        raise ValueError("terminal report must bind exactly 480 committed events")
    if terminal.transport_count != 480:
        raise ValueError("terminal report must bind exactly 480 transports")
    if terminal.unresolved_dispatch_count != 0 or unresolved != 0:
        raise ValueError("terminal report must have no unresolved dispatches")

    counts_by_cell = {cell_id: 0 for cell_id in CANONICAL_CELL_IDS}
    for record in attempts:
        cell_id = record.get("cell_id")
        if cell_id not in counts_by_cell:
            raise ValueError("attempt record contains an unknown cell")
        counts_by_cell[cell_id] += 1  # type: ignore[index]
        serialized = json.dumps(record, sort_keys=True)
        if "raw_body" in serialized or "rendered_messages" in serialized:
            raise ValueError("attempt staging contains unsanitized raw content")
    if any(count != 40 for count in counts_by_cell.values()):
        raise ValueError("terminal report must bind exactly 40 attempts per cell")
    return terminal


def _fake_request_for_event(
    *,
    authorization: DiagnosticRunAuthorization,
    adapter_binding: DiagnosticAdapterBinding,
    offset: int,
    cell_id: str | None = None,
) -> Phase0BVllmEventRequest:
    cell_id = cell_id or CANONICAL_CELL_IDS[0]
    if cell_id not in CANONICAL_CELL_IDS:
        raise ValueError("cell_id must be canonical")
    event_id = f"phase0b-event-{cell_id}-{offset + 1:04d}"
    rendered_messages = (
        {"role": "system", "content": "Return a compact diagnostic JSON object."},
        {"role": "user", "content": f"preliminary diagnostic event {offset + 1}"},
    )
    prompt_hash = canonical_payload_hash(
        {
            "cell_id": cell_id,
            "event_offset": offset,
            "authorization_hash": authorization.record_hash,
        }
    )
    seed_hash = canonical_payload_hash(
        {
            "matched_seed": authorization.matched_seed,
            "cell_id": cell_id,
            "event_id": event_id,
            "rule": authorization.model_seed_pairing_rule,
        }
    )
    model_seed = int(seed_hash[:15], 16)
    return Phase0BVllmEventRequest.create(
        event_id=event_id,
        attempt_index=1,
        prompt_hash=prompt_hash,
        rendered_messages=rendered_messages,
        generation_settings={
            "temperature": authorization.temperature,
            "top_p": authorization.top_p,
            "max_tokens": authorization.max_tokens,
        },
        model_seed=model_seed,
        adapter_binding_hash=adapter_binding.record_hash,
    )


def _append_sanitized_attempt(
    store: Phase0BJsonlStagingStore,
    request: Phase0BVllmEventRequest,
    response: Phase0BVllmEventResponse,
    *,
    cell_id: str | None = None,
    schema_version: str = "paper1.phase0b.fake-slice-attempt.v1",
    pipeline_evidence_hash: str | None = None,
    committed_state_hash: str | None = None,
) -> None:
    store.append_jsonl(
        "attempts.jsonl",
        {
            "schema_version": schema_version,
            "cell_id": cell_id or CANONICAL_CELL_IDS[0],
            "event_id": request.event_id,
            "attempt_id": request.attempt_id,
            "request_id": request.request_id,
            "request_hash": request.record_hash,
            "response_hash": response.record_hash,
            "transport_evidence_hash": response.transport_evidence.record_hash,
            "pipeline_evidence_hash": pipeline_evidence_hash,
            "committed_state_hash": committed_state_hash,
            "outcome": response.outcome,
            "error_code": response.error_code,
            "provider_request_id": response.provider_request_id,
            "usage": dict(response.usage),
            "finish_reason": response.finish_reason,
        },
    )
