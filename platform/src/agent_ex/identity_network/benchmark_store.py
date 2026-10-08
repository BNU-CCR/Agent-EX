"""Dedicated SQLite v2: durable intent/response/resolution, incremental hot path.

Cold source derivation belongs to the CLI before opening this packet-bound store.
Raw evidence stays in the archive, not summaries/reports. Cooperating Linux writers
must hold the existing kernel lease. No HTTP takes place inside a transaction.
"""

import os
import sqlite3
import sys
from pathlib import Path

from ..domain import canonical_payload_hash
from .benchmark_adapter import BenchmarkVllmAdapter, reconstruct_request
from .benchmark_response import classify_benchmark_response
from .benchmark_retry import _record, replay_retry_journal
from .dispatch import _strict_json
from .manipulation_evidence import bind_response, reconstruct_response, response_payload
from .manipulation_lock import ManipulationRunLock
from .manipulation_store import encode, file_signature

DDL = (
    "CREATE TABLE metadata (id INTEGER PRIMARY KEY CHECK(id=1), packet_hash TEXT NOT NULL, packet_json TEXT NOT NULL, receipt_json TEXT)",
    "CREATE TABLE journal (seq INTEGER PRIMARY KEY, record_json TEXT NOT NULL)",
    "CREATE TABLE responses (attempt_id TEXT PRIMARY KEY, ordinal INTEGER NOT NULL, attempt_index INTEGER NOT NULL, response_hash TEXT NOT NULL, response_json TEXT NOT NULL)",
    "CREATE TABLE approvals (seq INTEGER PRIMARY KEY, receipt_hash TEXT NOT NULL UNIQUE, receipt_json TEXT NOT NULL)",
)


class BenchmarkStore:
    @classmethod
    def create(cls, root, *, pack, lease, receipt=None):
        return cls(root, pack=pack, lease=lease, fresh=True, receipt=receipt)

    @classmethod
    def open(cls, root, *, pack, lease, receipt=None):
        return cls(root, pack=pack, lease=lease, receipt=receipt)

    @classmethod
    def verify(cls, root, *, pack):
        with cls(root, pack=pack) as store:
            return {
                **store.summary(),
                "outcomes": store._outcomes,
                "execution_receipt": store._receipt,
            }

    def __init__(self, root, *, pack, lease=None, fresh=False, receipt=None):
        self._conn = None
        self.root = Path(root).absolute()
        if self.root.is_symlink() or not self.root.is_dir():
            raise ValueError("existing trusted nonsymlink root required")
        if lease is not None:
            if type(lease) is not ManipulationRunLock:
                raise ValueError("concrete Linux writer lease required")
            lease.assert_held(self.root)
        elif fresh:
            raise ValueError("writer lease required")
        self.pack, self.lease = pack, lease
        self._expected_receipt = receipt
        entries = pack.payload["entries"]
        if pack.payload["mode"] not in {"stage-a", "preflight"} or len(entries) != (
            240 if pack.payload["mode"] == "stage-a" else 2
        ):
            raise ValueError("exact benchmark or technical preflight required")
        self.bindings = tuple((e["trial_id"], e["wire_hash"]) for e in entries)
        encoder = BenchmarkVllmAdapter(
            "http://127.0.0.1:8000/v1/chat/completions",
            served_model_name=pack.payload["served_model_name"],
        )
        for entry in entries:
            if len(entry["attempt_requests"]) != 3:
                raise ValueError("three bound attempts required")
            for i, request in enumerate(entry["attempt_requests"], 1):
                typed = reconstruct_request(request)
                if (
                    typed.attempt_index != i
                    or encoder._request_body(typed) != entry["wire_body"].encode()
                ):
                    raise ValueError("request/wire attempt binding differs")
        self.path = self.root / "benchmark.sqlite3"
        if fresh:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
            os.close(fd)
            if sys.platform == "linux":
                directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        initial = file_signature(self.path)
        try:
            self._conn = sqlite3.connect(
                self.path.as_uri() + ("?mode=rw" if lease else "?mode=ro"),
                uri=True,
                isolation_level=None,
            )
            if file_signature(self.path)[:2] != initial[:2]:
                raise ValueError("database identity changed during open")
            if lease:
                self._conn.execute("PRAGMA journal_mode=DELETE")
                self._conn.execute("PRAGMA synchronous=FULL")
            else:
                self._conn.execute("PRAGMA query_only=ON")
            if fresh:
                with self._transaction():
                    for ddl in DDL:
                        self._conn.execute(ddl)
                    self._conn.execute(
                        "INSERT INTO metadata VALUES (1,?,?,?)",
                        (
                            pack.output_hash,
                            encode(pack.to_payload()),
                            encode(receipt) if receipt is not None else None,
                        ),
                    )
                    if receipt is not None:
                        self._conn.execute(
                            "INSERT INTO approvals VALUES (1,?,?)",
                            (canonical_payload_hash(receipt), encode(receipt)),
                        )
            self._cold_replay()
            if (
                lease is not None
                and receipt is not None
                and encode(receipt) != encode(self._receipt)
            ):
                with self._transaction():
                    self._conn.execute(
                        "INSERT INTO approvals VALUES (?,?,?)",
                        (
                            self._approval_count + 1,
                            canonical_payload_hash(receipt),
                            encode(receipt),
                        ),
                    )
                self._cold_replay()
        except BaseException:
            self.close()
            raise

    def _transaction(self):
        from contextlib import contextmanager

        @contextmanager
        def transaction():
            if self.lease is None:
                raise RuntimeError("readonly benchmark store")
            self.lease.assert_held(self.root)
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield
                self.lease.assert_held(self.root)
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise

        return transaction()

    def _stamp(self):
        self._guard = (
            self._conn.execute("PRAGMA data_version").fetchone()[0],
            file_signature(self.path),
        )

    def _refresh(self):
        guard = (self._conn.execute("PRAGMA data_version").fetchone()[0], file_signature(self.path))
        if guard[1][:2] != self._guard[1][:2]:
            raise ValueError("database replaced")
        if guard != self._guard:
            self._cold_replay()

    def _cold_replay(self):
        owns = not self._conn.in_transaction
        if owns:
            self._conn.execute("BEGIN")
        try:
            actual = self._conn.execute(
                "SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            if actual != sorted((d.split()[2], d) for d in DDL):
                raise ValueError("database schema differs")
            if self._conn.execute(
                "SELECT name,type,sql FROM sqlite_master WHERE type!='table' ORDER BY name"
            ).fetchall() != [
                ("sqlite_autoindex_approvals_1", "index", None),
                ("sqlite_autoindex_responses_1", "index", None),
            ]:
                raise ValueError("unexpected index/trigger/view")
            metadata = self._conn.execute("SELECT * FROM metadata").fetchall()
            if len(metadata) != 1 or metadata[0][:3] != (
                1,
                self.pack.output_hash,
                encode(self.pack.to_payload()),
            ):
                raise ValueError("packet binding differs")
            self._receipt = _strict_json(metadata[0][3]) if metadata[0][3] is not None else None
            original = self._receipt
            approvals = self._conn.execute("SELECT * FROM approvals ORDER BY seq").fetchall()
            self._approval_count = len(approvals)
            core = (
                "schema_version",
                "packet_hash",
                "runtime_hash",
                "source_commit",
                "mode",
                "decision",
            )
            for index, (seq, record_hash, raw) in enumerate(approvals, 1):
                renewal = _strict_json(raw)
                if (
                    seq != index
                    or canonical_payload_hash(renewal) != record_hash
                    or original is None
                    or any(renewal.get(k) != original.get(k) for k in core)
                ):
                    raise ValueError("approval renewal binding differs")
                if index == 1 and encode(renewal) != encode(original):
                    raise ValueError("original approval changed")
                self._receipt = renewal
            if original is not None and not approvals:
                raise ValueError("missing original approval record")
            if self._expected_receipt is not None and (
                original is None
                or any(self._expected_receipt.get(k) != original.get(k) for k in core)
            ):
                raise ValueError("resume approval changed packet/runtime/source")
            rows = self._conn.execute("SELECT seq,record_json FROM journal ORDER BY seq").fetchall()
            records = [_strict_json(raw) for seq, raw in rows]
            if any(seq != i for i, (seq, _) in enumerate(rows, 1)):
                raise ValueError("SQL sequence differs")
            self._state = replay_retry_journal(
                self.bindings, records, plan_hash=self.pack.output_hash
            )
            responses = {r[0]: r for r in self._conn.execute("SELECT * FROM responses").fetchall()}
            intents, consumed, outcomes = {}, set(), []
            histogram = {str(i): 0 for i in range(1, 6)}
            for record in records:
                key = record["attempt_id"]
                if record["kind"] == "INTENT":
                    intents[key] = record
                else:
                    if key not in responses:
                        raise ValueError("result without durable response")
                    classified = self._checked_response(responses[key], intents[key])
                    if record["evidence"] != {
                        k: classified[k] for k in ("classification", "response_record_hash")
                    }:
                        raise ValueError("saved response/result classification differs")
                    consumed.add(key)
                    if classified["classification"] == "VALID":
                        histogram[str(classified["parsed"]["post_confidence"])] += 1
                        outcomes.append(
                            {
                                "trial_id": record["trial_id"],
                                "status": "VALID",
                                "post_stance": classified["parsed"]["post_stance"],
                            }
                        )
            self._pending = None
            for key, row in responses.items():
                if key not in intents:
                    raise ValueError("orphan saved response")
                classified = self._checked_response(row, intents[key])
                if key not in consumed:
                    if (
                        not records
                        or key != records[-1]["attempt_id"]
                        or self._state["phase"] != "INTENT"
                    ):
                        raise ValueError("noncurrent pending response")
                    self._pending = classified
            self._outcomes = outcomes
            self._confidence_histogram = histogram
            self._stamp()
            if owns:
                self._conn.execute("COMMIT")
        except BaseException:
            if owns:
                self._conn.execute("ROLLBACK")
            raise

    def _checked_response(self, row, intent):
        key, ordinal, index, record_hash, raw = row
        payload = _strict_json(raw)
        if (ordinal, index) != (
            intent["ordinal"],
            intent["attempt_index"],
        ) or canonical_payload_hash(payload) != record_hash:
            raise ValueError("response SQL/hash binding differs")
        classified = classify_benchmark_response(
            self.pack, ordinal, index, reconstruct_response(payload)
        )
        if classified["response_record_hash"] != record_hash:
            raise ValueError("response content hash differs")
        return classified

    def _post_write(self, before):
        # Never bless a different external generation after an own write.
        self._conn.execute("BEGIN")
        try:
            self._conn.execute("SELECT id FROM metadata").fetchall()
            if file_signature(self.path)[:2] != self._guard[1][:2]:
                raise ValueError("database replaced after commit")
            if self._conn.execute("PRAGMA data_version").fetchone()[0] != before:
                self._cold_replay()
            else:
                self._stamp()
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise

    def _append(self, kind, evidence=None):
        self._refresh()
        state = self._state
        record = _record(
            self.bindings,
            plan_hash=self.pack.output_hash,
            seq=state["transition_count"] + 1,
            tail=state["tail_hash"],
            ordinal=state["ordinal"],
            attempt=state["attempt_index"],
            phase=state["phase"],
            kind=kind,
            evidence=evidence,
        )
        before = self._guard[0]
        with self._transaction():
            self._refresh()
            if self._state != state:
                raise ValueError("stale transition")
            self._conn.execute("INSERT INTO journal VALUES (?,?)", (record["seq"], encode(record)))
        # O(1) incremental prefix; cold audit at entry/verify/external mutation.
        self._state = dict(state, transition_count=record["seq"], tail_hash=record["record_hash"])
        if kind == "INTENT":
            self._state.update(phase="INTENT", next_action="RECOVER_RESPONSE_OR_STOP")
        elif evidence["classification"] == "VALID":
            self._confidence_histogram[str(self._pending["parsed"]["post_confidence"])] += 1
            self._outcomes.append(
                {
                    "trial_id": record["trial_id"],
                    "status": "VALID",
                    "post_stance": self._pending["parsed"]["post_stance"],
                }
            )
            ordinal = state["ordinal"] + 1
            complete = ordinal == len(self.bindings)
            self._state.update(
                ordinal=ordinal,
                valid_count=ordinal,
                attempt_index=1,
                phase="COMPLETE" if complete else "READY",
                next_action="VERIFY_TRANSPORT" if complete else "DISPATCH",
            )
        elif evidence["classification"] in {"PARSE_INVALID", "HTTP_429_REJECTED"}:
            exhausted = state["attempt_index"] == 3
            self._state.update(
                phase="INCOMPLETE" if exhausted else "RETRY_READY",
                next_action="STOP" if exhausted else "DISPATCH",
                attempt_index=state["attempt_index"] if exhausted else state["attempt_index"] + 1,
            )
        else:
            self._state.update(phase="BLOCKED_AMBIGUOUS", next_action="STOP")
        if kind == "RESULT":
            self._pending = None
        self._post_write(before)

    def current_request(self):
        self._refresh()
        state = self._state
        if state["ordinal"] >= len(self.bindings):
            raise ValueError("run already complete")
        return reconstruct_request(
            self.pack.payload["entries"][state["ordinal"]]["attempt_requests"][
                state["attempt_index"] - 1
            ]
        )

    def record_before_dispatch(self, request, body):
        if (
            request != self.current_request()
            or body != self.pack.payload["entries"][self._state["ordinal"]]["wire_body"].encode()
        ):
            raise ValueError("current request/wire differs")
        self._append("INTENT")

    def save_response(self, response):
        self._refresh()
        state = self._state
        if state["phase"] != "INTENT" or self._pending is not None:
            raise ValueError("response needs unresolved current intent")
        payload = response_payload(response)
        entry = self.pack.payload["entries"][state["ordinal"]]
        bind_response(
            payload,
            request=self.current_request(),
            wire=entry["wire_body"].encode(),
            adapter_binding={
                "endpoint": "http://127.0.0.1:8000/v1/chat/completions",
                "served_model_name": self.pack.payload["served_model_name"],
            },
        )
        key = canonical_payload_hash(
            {
                "logical_request_id": canonical_payload_hash(
                    {
                        "plan_hash": self.pack.output_hash,
                        "trial_id": self.bindings[state["ordinal"]][0],
                        "wire_hash": self.bindings[state["ordinal"]][1],
                    }
                ),
                "attempt_index": state["attempt_index"],
            }
        )
        before = self._guard[0]
        with self._transaction():
            self._refresh()
            if self._state != state or self._pending is not None:
                raise ValueError("stale saved response")
            self._conn.execute(
                "INSERT INTO responses VALUES (?,?,?,?,?)",
                (
                    key,
                    state["ordinal"],
                    state["attempt_index"],
                    canonical_payload_hash(payload),
                    encode(payload),
                ),
            )
        try:
            self._pending = classify_benchmark_response(
                self.pack, state["ordinal"], state["attempt_index"], response
            )
            self._post_write(before)
        except BaseException:
            # A durable response exists: invalidate cache so retry entry cold-replays.
            self._guard = (self._guard[0], (*self._guard[1][:2], -1, -1))
            raise

    def resolve_saved_response(self):
        self._refresh()
        if self._pending is None:
            raise ValueError("no saved response; ambiguous dispatch must not resend")
        self._append(
            "RESULT",
            {key: self._pending[key] for key in ("classification", "response_record_hash")},
        )

    def summary(self):
        self._refresh()
        return {
            **self._state,
            "saved_response_pending": self._pending is not None,
            "packet_hash": self.pack.output_hash,
            "mode": self.pack.payload["mode"],
            "execution_approval_hash": canonical_payload_hash(self._receipt)
            if self._receipt is not None
            else None,
            "formal_parameter_authority": False,
            "post_confidence_histogram": dict(self._confidence_histogram),
        }

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
