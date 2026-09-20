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
from .contracts import (
    DiagnosticAdapterBinding,
    DiagnosticAttemptPolicy,
    DiagnosticRunAuthorization,
    DiagnosticTerminalReport,
)
from .matrix import DiagnosticMatrixCandidate
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
        content = dict(payload)
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


def _fake_request_for_event(
    *,
    authorization: DiagnosticRunAuthorization,
    adapter_binding: DiagnosticAdapterBinding,
    offset: int,
) -> Phase0BVllmEventRequest:
    cell_id = CANONICAL_CELL_IDS[0]
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
) -> None:
    store.append_jsonl(
        "attempts.jsonl",
        {
            "schema_version": "paper1.phase0b.fake-slice-attempt.v1",
            "event_id": request.event_id,
            "attempt_id": request.attempt_id,
            "request_id": request.request_id,
            "request_hash": request.record_hash,
            "response_hash": response.record_hash,
            "transport_evidence_hash": response.transport_evidence.record_hash,
            "outcome": response.outcome,
            "error_code": response.error_code,
            "provider_request_id": response.provider_request_id,
            "usage": dict(response.usage),
            "finish_reason": response.finish_reason,
        },
    )
