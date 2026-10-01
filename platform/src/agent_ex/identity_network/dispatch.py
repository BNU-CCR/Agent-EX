"""Study-specific durable dispatch journal and local-only reconciliation."""

from dataclasses import replace
import hashlib
import json
import os

from ..domain import EventStatus, canonical_payload_hash
from ..phase0b.vllm_event_adapter import Phase0BDispatchJournal
from .storage import StudyRunStorage


def _strict_json(value):
    def pairs(entries):
        result = {}
        for key, item in entries:
            if key in result:
                raise ValueError("ambiguous dispatch wire/entry duplicate key")
            result[key] = item
        return result

    def constant(value):
        raise ValueError("nonfinite dispatch wire/entry constant")

    return json.loads(value, object_pairs_hook=pairs, parse_constant=constant)


class StudyDispatchJournal(Phase0BDispatchJournal):
    """Hash-only SIS ledger; callers must hold the corresponding SQLite lease.

    This does not authorize a model run or send HTTP. Uncertain dispatches
    remain unresolved. Reconciliation requires a response already in SQLite.
    """

    def __init__(self, path, *, storage):
        if not isinstance(storage, StudyRunStorage):
            raise TypeError("SIS dispatch requires StudyRunStorage")
        self.storage = storage
        self._binding = {
            "run_id": storage.binding.run_id,
            "study_binding_hash": storage.study_binding.record_hash,
            "baseline_manifest_hash": storage.execution_state().baseline_manifest_hash,
        }
        self._tail = None
        self._cached = None
        self._file_signature = None
        self._data_version = None
        self._needs_cover = True
        self._covered_transition_rowid = 0
        self._intent_attempt_ids = set()
        self._unresolved_ids = set()
        super().__init__(path)
        self._records()

    def _safe_path(self):
        if self.path.is_symlink() or (self.path.exists() and self.path.stat().st_nlink != 1):
            raise ValueError("dispatch journal must be a single-link regular file")

    def _records(self):
        self._safe_path()
        was_verified = self.storage._connection_state_is_verified()
        self.storage.verify_integrity()
        signature = self._stat_signature()
        data_version = self.storage._connection_signature()[0]
        # Shared storage marks only verified/trusted atomic writes as hot.
        # External DB edits or any changed journal identity force cold replay.
        if (
            self._cached is not None
            and was_verified
            and signature == self._file_signature
            and data_version == self._data_version
        ):
            self._validate_current_response(self._cached)
            return self._cached
        self._needs_cover = True
        records = {"intents": {}, "resolutions": {}}
        tail = None
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.endswith("\n"):
                        raise ValueError("dispatch journal has a partial entry")
                    payload = _strict_json(line)
                    if not isinstance(payload, dict):
                        raise ValueError("dispatch journal must contain objects")
                    kind = payload.get("kind")
                    if kind not in ("intent", "resolution"):
                        raise ValueError("unsupported dispatch entry")
                    fields = (
                        {"request_hash", "request_body_sha256"}
                        if kind == "intent"
                        else {"response_hash", "transport_evidence_hash"}
                    )
                    if set(payload) != fields | set(self._binding) | {
                        "schema_version",
                        "kind",
                        "request_id",
                        "attempt_id",
                        "created_at",
                        "previous_record_hash",
                        "record_hash",
                    }:
                        raise ValueError("dispatch entry fields differ from schema")
                    if (
                        any(payload[k] != v for k, v in self._binding.items())
                        or payload["schema_version"]
                        != f"paper1.identity-network.dispatch-{kind}.v1"
                        or payload["previous_record_hash"] != tail
                    ):
                        raise ValueError("dispatch journal binding/chain mismatch")
                    if payload["record_hash"] != canonical_payload_hash(
                        {k: v for k, v in payload.items() if k != "record_hash"}
                    ):
                        raise ValueError("dispatch journal hash mismatch")
                    evidence = self.storage.adapter_request_evidence(payload["attempt_id"])
                    if evidence is None or evidence.request_id != payload["request_id"]:
                        raise ValueError("dispatch entry lacks its durable request")
                    request_id = evidence.request_id
                    bucket = records["intents" if kind == "intent" else "resolutions"]
                    if request_id in bucket:
                        raise ValueError("duplicate dispatch journal entry")
                    if kind == "intent":
                        if payload["request_hash"] != evidence.request.record_hash:
                            raise ValueError("dispatch intent request mismatch")
                        transitions = self.storage.attempt_transitions(evidence.attempt_id)
                        if not any(t.status is EventStatus.IN_PROGRESS for t in transitions):
                            raise ValueError("dispatch intent lacks IN_PROGRESS prefix")
                    else:
                        intent = records["intents"].get(request_id)
                        invocation = self.storage.invocation_evidence(evidence.attempt_id)
                        if intent is None or invocation is None:
                            raise ValueError("resolution lacks intent/durable response")
                        self._match_response(intent, invocation.response, payload)
                    invocation = self.storage.invocation_evidence(evidence.attempt_id)
                    if kind == "intent" and invocation is not None:
                        self._match_response(payload, invocation.response)
                    bucket[request_id] = payload
                    tail = payload["record_hash"]
        self._tail = tail
        self._cached = records
        self._intent_attempt_ids = {entry["attempt_id"] for entry in records["intents"].values()}
        self._unresolved_ids = set(records["intents"]) - set(records["resolutions"])
        self._file_signature = signature
        self._data_version = data_version
        return records

    def _stat_signature(self):
        if not self.path.exists():
            return None
        stat = self.path.stat()
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns

    def _validate_current_response(self, records):
        current = self.storage.current_event_journal().latest_transition
        if current is None:
            return
        intent = records["intents"].get(current.request_id)
        invocation = self.storage.invocation_evidence(current.attempt_id)
        if intent is not None and invocation is not None:
            self._match_response(
                intent, invocation.response, records["resolutions"].get(current.request_id)
            )

    def _assert_historical_cover(self, records):
        watermark = 0 if self._needs_cover else self._covered_transition_rowid
        started = self.storage._connection.execute(
            "SELECT rowid, attempt_id FROM attempt_transitions WHERE rowid>? AND status=? ORDER BY rowid",
            (watermark, EventStatus.IN_PROGRESS.value),
        ).fetchall()
        if any(row[1] not in self._intent_attempt_ids for row in started):
            raise RuntimeError("durable dispatch intent history is incomplete")
        if started:
            self._covered_transition_rowid = started[-1][0]
        self._needs_cover = False

    def unresolved_request_ids(self):
        self._records()
        return tuple(sorted(self._unresolved_ids))

    @staticmethod
    def _match_response(intent, response, resolution=None):
        if (
            intent["request_hash"] != response.request_hash
            or intent["request_body_sha256"]
            != hashlib.sha256(response.transport_evidence.request_body).hexdigest()
        ):
            raise ValueError("dispatch intent differs from durable transport")
        if resolution is not None and (
            resolution["response_hash"] != response.record_hash
            or resolution["transport_evidence_hash"] != response.transport_evidence.record_hash
        ):
            raise ValueError("dispatch resolution differs from durable response")

    def _append(self, payload):
        self.storage.assert_run_lease_owned()
        self._records()
        evidence = self.storage.current_event_journal().latest_transition
        if evidence is None or evidence.request_id != payload["request_id"]:
            raise ValueError("dispatch entry is not the current attempt")
        content = {
            **{k: v for k, v in payload.items() if k != "record_hash"},
            **self._binding,
            "schema_version": f"paper1.identity-network.dispatch-{payload['kind']}.v1",
            "attempt_id": evidence.attempt_id,
            "previous_record_hash": self._tail,
        }
        entry = {**content, "record_hash": canonical_payload_hash(content)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._safe_path()
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.path, flags, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8", newline="\n") as handle:
            if os.fstat(handle.fileno()).st_nlink != 1:
                raise ValueError("dispatch journal must be single-link")
            handle.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        if os.name == "posix":
            directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        self._cached["intents" if entry["kind"] == "intent" else "resolutions"][
            entry["request_id"]
        ] = entry
        if entry["kind"] == "intent":
            self._intent_attempt_ids.add(entry["attempt_id"])
            self._unresolved_ids.add(entry["request_id"])
        else:
            self._unresolved_ids.discard(entry["request_id"])
        self._tail = entry["record_hash"]
        self._file_signature = self._stat_signature()

    def record_before_dispatch(self, request, body):
        self.storage.assert_run_lease_owned()
        self.assert_no_unresolved_dispatches()
        current = self.storage.current_event_journal().latest_transition
        evidence = self.storage.adapter_request_evidence(request.attempt_id)
        if (
            current is None
            or current.status is not EventStatus.IN_PROGRESS
            or current.attempt_id != request.attempt_id
            or evidence is None
            or evidence.request != request
        ):
            raise ValueError("dispatch requires exact durable IN_PROGRESS request")
        adapter = self.storage.adapter_execution_binding(request.attempt_id)
        expected = {
            "model": adapter.served_model_name,
            "messages": [dict(m) for m in request.rendered_messages],
            **dict(request.generation_settings),
            "seed": request.model_seed,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if type(body) is not bytes or canonical_payload_hash(
            _strict_json(body)
        ) != canonical_payload_hash(expected):
            raise ValueError("dispatch wire differs from durable request")
        super().record_before_dispatch(request, body)

    def record_resolution(self, response):
        self.storage.assert_run_lease_owned()
        records = self._records()
        invocation = self.storage.invocation_evidence(response.attempt_id)
        if invocation is None or invocation.response != response:
            raise ValueError("dispatch resolution requires exact durable response")
        if response.request_id in records["resolutions"]:
            return
        intent = records["intents"].get(response.request_id)
        if intent is None:
            raise ValueError("durable response has no dispatch intent")
        self._match_response(intent, response)
        super().record_resolution(response)


def reconcile_study_event(*, storage, journal):
    """Finish only saved evidence; never dispatch, reset, retry or invent a response."""
    if not isinstance(journal, StudyDispatchJournal) or journal.storage is not storage:
        raise ValueError("SIS reconciliation requires the same journal/store binding")
    storage.assert_run_lease_owned()
    records = journal._records()
    journal._assert_historical_cover(records)
    current = storage.current_event_journal()
    latest = current.latest_transition
    if latest is None:
        journal.assert_no_unresolved_dispatches()
        return "complete" if current.resume_state == "complete" else "new_event"
    if latest.status is EventStatus.PENDING:
        journal.assert_no_unresolved_dispatches()
        return "pending"
    invocation = storage.invocation_evidence(latest.attempt_id)
    if latest.request_id not in records["intents"]:
        raise RuntimeError("IN_PROGRESS/terminal recovery requires durable dispatch intent")
    if invocation is None:
        raise RuntimeError("unresolved dispatch intent; do not resend")
    if set(journal.unresolved_request_ids()) - {latest.request_id}:
        raise RuntimeError("another unresolved dispatch prevents recovery")
    result = storage._validate_study_invocation(invocation)
    journal.record_resolution(invocation.response)
    if latest.status is EventStatus.IN_PROGRESS:
        response, parsed = invocation.response, result.parse
        raw = response.raw_body.decode("utf-8", errors="replace")
        metadata = {"diagnostic_response_hash": response.record_hash}
        parsed_payload = (
            None
            if not parsed.success
            else {
                "topic_package_id": parsed.topic_package_id,
                "topic_package_hash": parsed.topic_package_hash,
                **dict(parsed.parsed_response),
            }
        )
        latest = replace(
            latest,
            status=EventStatus.SUCCEEDED if parsed.success else EventStatus.FAILED,
            provider_request_id=response.provider_request_id,
            provider_metadata=metadata,
            provider_metadata_hash=canonical_payload_hash(metadata),
            http_status=response.transport_evidence.http_status,
            raw_response=raw,
            raw_response_hash=canonical_payload_hash(raw),
            parsed_response=parsed_payload,
            parsed_response_hash=None
            if parsed_payload is None
            else canonical_payload_hash(parsed_payload),
            usage=dict(response.usage),
            usage_hash=canonical_payload_hash(response.usage),
            finish_reason=response.finish_reason,
            finished_at=response.transport_evidence.ended_at,
            error=None if parsed.success else {"code": parsed.error_code},
        )
        storage.record_diagnostic_finalized_attempt(latest, parsed)
    if latest.status is EventStatus.SUCCEEDED:
        storage.commit_study_success(latest.attempt_id)
        return "committed"
    # A failure is retained, not converted into another request or next event.
    if storage.terminal_failure_evidence() is None:
        policy = storage.attempt_policy_evidence(latest.event_id)
        storage.record_terminal_failure(
            event_id=latest.event_id,
            reason="diagnostic_response_failed",
            policy_evidence={
                "policy_id": "phase0b-diagnostic-attempt-policy-v1",
                "policy_hash": policy.record_hash,
            },
            recorded_at=invocation.response.transport_evidence.ended_at,
        )
    return "failed"
