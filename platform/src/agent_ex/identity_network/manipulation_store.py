"""Dedicated append-only SQLite evidence for independent manipulation trials."""

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys

from ..domain import _json_ready, canonical_payload_hash
from ..phase0b.vllm_event_adapter import Phase0BVllmEventAdapter, Phase0BVllmEventRequest
from .dispatch import _strict_json
from .manipulation_evidence import bind_response, response_payload, terminal_evidence
from .manipulation_lock import ManipulationRunLock
from .manipulation_requests import validate_manipulation_request_plan

SCHEMA = "paper1.identity-network.manipulation-store.v1"
TRANSITION = "paper1.identity-network.manipulation-transition.v1"
DDL = (
    "CREATE TABLE metadata (id INTEGER PRIMARY KEY CHECK(id=1), schema_version TEXT NOT NULL, plan_json TEXT NOT NULL, plan_hash TEXT NOT NULL)",
    "CREATE TABLE trials (ordinal INTEGER PRIMARY KEY, trial_id TEXT NOT NULL UNIQUE, request_id TEXT NOT NULL UNIQUE, entry_json TEXT NOT NULL)",
    "CREATE TABLE transitions (seq INTEGER PRIMARY KEY, ordinal INTEGER NOT NULL REFERENCES trials, kind TEXT NOT NULL CHECK(kind IN ('INTENT','RESPONSE_STORED','VALID','INVALID')), record_json TEXT NOT NULL, UNIQUE(ordinal,kind))",
)


def encode(payload):
    return json.dumps(
        _json_ready(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
        sort_keys=True,
    )


def file_signature(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("database must be a regular, non-symlink single-link file")
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


class ManipulationStore:
    @classmethod
    def create(cls, root, *, plan, checked_at, lease):
        return cls._connect(root, plan=plan, checked_at=checked_at, lease=lease, fresh=True)

    @classmethod
    def open(cls, root, *, plan, checked_at, lease):
        return cls._connect(root, plan=plan, checked_at=checked_at, lease=lease, fresh=False)

    @classmethod
    def verify(cls, root, *, plan, checked_at):
        with cls._connect(
            root, plan=plan, checked_at=checked_at, lease=None, fresh=False, readonly=True
        ) as store:
            return store.summary()

    @classmethod
    def _connect(cls, root, *, plan, checked_at, lease, fresh, readonly=False):
        root = Path(root).absolute()
        if root.is_symlink() or not root.is_dir():
            raise ValueError("trusted existing archive directory required")
        if not readonly:
            if type(lease) is not ManipulationRunLock:
                raise TypeError("concrete writer lease required")
            lease.assert_held(root)
        requests = validate_manipulation_request_plan(plan, checked_at=checked_at)
        path = root / "manipulation.sqlite3"
        if fresh:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
            os.close(fd)
            if sys.platform == "linux":
                directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        initial = file_signature(path)
        conn = None
        try:
            conn = sqlite3.connect(
                path.as_uri() + ("?mode=ro" if readonly else "?mode=rw"),
                uri=True,
                isolation_level=None,
            )
            conn.execute("PRAGMA foreign_keys=ON")
            if readonly:
                conn.execute("PRAGMA query_only=ON")
            else:
                conn.execute("PRAGMA journal_mode=DELETE")
                conn.execute("PRAGMA synchronous=FULL")
            if file_signature(path)[:2] != initial[:2]:
                raise ValueError("database identity changed during open")
            self = cls()
            self._root, self._path, self._conn = root, path, conn
            self._plan, self._checked_at, self._lease = plan, checked_at, lease
            self._requests = requests
            self._entries = _json_ready(plan.payload)["entries"]
            self._adapter = _json_ready(plan.payload)["adapter_binding"]
            encoder = Phase0BVllmEventAdapter(
                self._adapter["endpoint"], served_model_name=self._adapter["served_model_name"]
            )
            self._wires = tuple(encoder._request_body(r) for r in requests)
            if fresh:
                conn.execute("BEGIN IMMEDIATE")
                for ddl in DDL:
                    conn.execute(ddl)
                conn.execute(
                    "INSERT INTO metadata VALUES (1,?,?,?)",
                    (SCHEMA, encode(plan.to_payload()), plan.output_hash),
                )
                conn.executemany(
                    "INSERT INTO trials VALUES (?,?,?,?)",
                    [
                        (i, e["trial_id"], requests[i].request_id, encode(e))
                        for i, e in enumerate(self._entries)
                    ],
                )
                conn.execute("COMMIT")
            self._cold_replay()
            return self
        except BaseException:
            if conn is not None:
                conn.close()
            raise

    @property
    def requests(self):
        return self._requests

    def _cache_guard(self):
        self._guard = (
            self._conn.execute("PRAGMA data_version").fetchone()[0],
            self._conn.total_changes,
            file_signature(self._path),
        )

    def _refresh(self):
        if self._conn is None:
            raise RuntimeError("store is closed")
        signature = file_signature(self._path)
        if signature[:2] != self._guard[2][:2]:
            raise ValueError("database identity changed")
        guard = (
            self._conn.execute("PRAGMA data_version").fetchone()[0],
            self._conn.total_changes,
            signature,
        )
        if guard != self._guard:
            validate_manipulation_request_plan(self._plan, checked_at=self._checked_at)
            self._cold_replay()

    def _cold_replay(self):
        conn = self._conn
        owns_transaction = not conn.in_transaction
        if owns_transaction:
            conn.execute("BEGIN")
        try:
            self._replay()
            # Capture the verified database generation while its read lock is held.
            self._cache_guard()
            if owns_transaction:
                conn.execute("COMMIT")
        except BaseException:
            if owns_transaction:
                conn.execute("ROLLBACK")
            raise

    def _replay(self):
        conn = self._conn
        schema = conn.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        expected_schema = sorted((ddl.split()[2], ddl) for ddl in DDL)
        if schema != expected_schema:
            raise ValueError("database schema differs")
        indexes = conn.execute(
            "SELECT name,tbl_name,sql FROM sqlite_master WHERE type!='table' ORDER BY name"
        ).fetchall()
        if indexes != [
            ("sqlite_autoindex_transitions_1", "transitions", None),
            ("sqlite_autoindex_trials_1", "trials", None),
            ("sqlite_autoindex_trials_2", "trials", None),
        ]:
            raise ValueError("unexpected database indexes/views/triggers")
        if conn.execute("SELECT * FROM metadata").fetchall() != [
            (1, SCHEMA, encode(self._plan.to_payload()), self._plan.output_hash)
        ]:
            raise ValueError("database metadata differs")
        expected = [
            (i, e["trial_id"], self.requests[i].request_id, encode(e))
            for i, e in enumerate(self._entries)
        ]
        if conn.execute("SELECT * FROM trials ORDER BY ordinal").fetchall() != expected:
            raise ValueError("ordered trial inventory differs")
        ordinal, phase, tail, saved = 0, "READY", None, None
        rows = conn.execute("SELECT * FROM transitions ORDER BY seq").fetchall()
        for seq, row in enumerate(rows, 1):
            sql_seq, sql_ordinal, kind, raw = row
            if ordinal >= len(self.requests) or sql_seq != seq or sql_ordinal != ordinal:
                raise ValueError("transition sequence/order differs")
            request = self.requests[ordinal]
            record = _strict_json(raw)
            evidence = record.get("evidence")
            content = {
                "schema_version": TRANSITION,
                "plan_hash": self._plan.output_hash,
                "seq": seq,
                "ordinal": ordinal,
                "trial_id": self._entries[ordinal]["trial_id"],
                "request_id": request.request_id,
                "kind": kind,
                "evidence": evidence,
                "previous_record_hash": tail,
            }
            if record != {**content, "record_hash": canonical_payload_hash(content)}:
                raise ValueError("transition hash/content differs")
            if kind == "INTENT" and phase == "READY":
                if evidence != self._intent(ordinal):
                    raise ValueError("intent binding differs")
                phase = kind
            elif kind == "RESPONSE_STORED" and phase == "INTENT":
                saved = bind_response(
                    evidence,
                    request=request,
                    wire=self._wires[ordinal],
                    adapter_binding=self._adapter,
                )
                phase = kind
            elif kind in {"VALID", "INVALID"} and phase == "RESPONSE_STORED":
                expected_kind, parsed = terminal_evidence(self._plan, saved)
                if kind != expected_kind or evidence != parsed:
                    raise ValueError("terminal parse evidence differs")
                phase = kind
                if kind == "VALID":
                    ordinal, phase, saved = ordinal + 1, "READY", None
            else:
                raise ValueError("illegal transition prefix")
            tail = record["record_hash"]
        self._ordinal, self._phase, self._tail, self._saved, self._seq = (
            ordinal,
            phase,
            tail,
            saved,
            len(rows),
        )

    def _intent(self, ordinal):
        return {
            "request_hash": self.requests[ordinal].record_hash,
            "wire_sha256": hashlib.sha256(self._wires[ordinal]).hexdigest(),
        }

    def _epoch(self):
        return self._seq, self._tail, self._ordinal, self._phase

    def _append(self, kind, evidence, *, expected_phase, expected_epoch):
        if self._lease is None:
            raise RuntimeError("readonly store")
        self._lease.assert_held(self._root)
        self._refresh()
        snapshot = self._epoch()
        if snapshot != expected_epoch:
            raise ValueError("stale caller evidence after prefix advancement")
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            self._lease.assert_held(self._root)
            self._refresh()
            if (self._seq, self._tail, self._ordinal, self._phase) != snapshot:
                raise ValueError("stale current phase after transaction acquisition")
            last = conn.execute(
                "SELECT seq,record_json FROM transitions ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            current = (last[0], _strict_json(last[1])["record_hash"]) if last else (0, None)
            if (
                current != snapshot[:2]
                or self._phase != expected_phase
                or self._ordinal >= len(self.requests)
            ):
                raise ValueError("stale or illegal current phase")
            ordinal = self._ordinal
            content = {
                "schema_version": TRANSITION,
                "plan_hash": self._plan.output_hash,
                "seq": self._seq + 1,
                "ordinal": ordinal,
                "trial_id": self._entries[ordinal]["trial_id"],
                "request_id": self.requests[ordinal].request_id,
                "kind": kind,
                "evidence": evidence,
                "previous_record_hash": self._tail,
            }
            record = {**content, "record_hash": canonical_payload_hash(content)}
            conn.execute(
                "INSERT INTO transitions VALUES (?,?,?,?)",
                (self._seq + 1, ordinal, kind, encode(record)),
            )
            verified_data_version = self._guard[0]
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        self._seq += 1
        self._tail, self._phase = record["record_hash"], kind
        if kind == "RESPONSE_STORED":
            self._saved = bind_response(
                evidence,
                request=self.requests[ordinal],
                wire=self._wires[ordinal],
                adapter_binding=self._adapter,
            )
        elif kind == "VALID":
            self._ordinal += 1
            self._phase, self._saved = "READY", None
        self._post_commit_guard(verified_data_version)

    def _post_commit_guard(self, verified_data_version):
        """Accept own writes, never stamp an unchecked external generation as trusted."""
        conn = self._conn
        conn.execute("BEGIN")
        try:
            # Establish a read lock before observing generation and file metadata.
            conn.execute("SELECT id FROM metadata").fetchall()
            signature = file_signature(self._path)
            if signature[:2] != self._guard[2][:2]:
                raise ValueError("database identity changed after commit")
            if conn.execute("PRAGMA data_version").fetchone()[0] != verified_data_version:
                validate_manipulation_request_plan(self._plan, checked_at=self._checked_at)
                self._cold_replay()
            else:
                self._cache_guard()
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise

    def record_before_dispatch(self, request, exactbody):
        self._refresh()
        if (
            type(request) is not Phase0BVllmEventRequest
            or self._ordinal >= len(self.requests)
            or request != self.requests[self._ordinal]
            or type(exactbody) is not bytes
            or exactbody != self._wires[self._ordinal]
        ):
            raise ValueError("dispatch request/wire/order differs")
        self._append(
            "INTENT",
            self._intent(self._ordinal),
            expected_phase="READY",
            expected_epoch=self._epoch(),
        )

    def store_response(self, response):
        self._refresh()
        if self._phase != "INTENT":
            raise ValueError("response requires current intent")
        payload = response_payload(response)
        bind_response(
            payload,
            request=self.requests[self._ordinal],
            wire=self._wires[self._ordinal],
            adapter_binding=self._adapter,
        )
        self._append(
            "RESPONSE_STORED", payload, expected_phase="INTENT", expected_epoch=self._epoch()
        )

    def terminalize_saved_response(self):
        self._refresh()
        if self._phase != "RESPONSE_STORED":
            raise ValueError("terminalization requires saved response")
        kind, evidence = terminal_evidence(self._plan, self._saved)
        self._append(kind, evidence, expected_phase="RESPONSE_STORED", expected_epoch=self._epoch())

    def summary(self):
        self._refresh()
        return {
            "plan_hash": self._plan.output_hash,
            "tail_hash": self._tail,
            "trial_count": len(self.requests),
            "valid_count": self._ordinal,
            "invalid_count": int(self._phase == "INVALID"),
            "transition_count": self._seq,
            "phase": "COMPLETE" if self._ordinal == len(self.requests) else self._phase,
            "execution_complete": self._ordinal == len(self.requests),
            "status": "preliminary",
            "research_parameter_status": "not_frozen",
            "formal_parameter_authority": False,
            "inventory_contract": self._plan.payload["inventory_contract"],
            "cloud_launch_eligible": self._plan.payload["cloud_launch_eligible"],
        }

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        if self._conn is None:
            raise RuntimeError("store is closed")
        return self

    def __exit__(self, *exc):
        self.close()
