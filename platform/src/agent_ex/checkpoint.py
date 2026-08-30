"""Canonical derived recovery checkpoints for a per-run SQLite store."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass, replace
from pathlib import Path
import tempfile
from types import MappingProxyType
from typing import Mapping

from .domain import (
    _require_id,
    _require_int,
    _require_sha256,
    _require_string,
    _require_timestamp,
    canonical_payload_hash,
    derive_attempt_id,
    derive_event_id,
    GenerationAttempt,
)
from .storage import ExternalResponseReference, RunStorage


_CHECKPOINT_VERSION = "paper1.checkpoint.v1"
_MAX_CHECKPOINT_BYTES = 16 * 1024 * 1024
_MAX_JSON_DEPTH = 32


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _freeze(value: object) -> object:
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(_plain(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _validate_depth(value: object, depth: int = 0) -> None:
    if depth > _MAX_JSON_DEPTH:
        raise ValueError("checkpoint JSON exceeds maximum nesting depth")
    if isinstance(value, Mapping):
        for item in value.values():
            _validate_depth(item, depth + 1)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _validate_depth(item, depth + 1)


def _preflight_json_depth(raw: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    for character in raw:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > _MAX_JSON_DEPTH:
                raise ValueError("checkpoint JSON exceeds maximum nesting depth")
        elif character in "]}":
            depth -= 1


def _validate_attempt_prefix(prefix: list[object], current_event_id: str | None) -> None:
    if prefix and current_event_id is None:
        raise ValueError("complete checkpoint cannot contain a current attempt prefix")
    allowed_lifecycles = {
        ("pending",),
        ("pending", "in_progress"),
        ("pending", "in_progress", "failed"),
        ("pending", "in_progress", "succeeded"),
    }
    for expected_index, attempt in enumerate(prefix, start=1):
        if type(attempt) is not dict or set(attempt) != {
            "attempt_id",
            "attempt_index",
            "transitions",
            "transition_entries",
        }:
            raise ValueError("checkpoint attempt prefix entry has unexpected fields")
        _require_int("checkpoint attempt index", attempt["attempt_index"])
        if attempt["attempt_index"] != expected_index:
            raise ValueError("checkpoint attempt prefix has an attempt-index gap")
        if attempt["attempt_id"] != derive_attempt_id(current_event_id, expected_index):
            raise ValueError("checkpoint attempt identity does not match current event")
        transitions = attempt["transitions"]
        entries = attempt["transition_entries"]
        if (
            type(transitions) is not list
            or not transitions
            or type(entries) is not list
            or len(entries) != len(transitions)
        ):
            raise ValueError("checkpoint attempt transition prefix is incomplete")
        statuses = tuple(
            transition.get("status") if type(transition) is dict else None
            for transition in transitions
        )
        if statuses not in allowed_lifecycles:
            raise ValueError("checkpoint attempt transition lifecycle is invalid")
        if expected_index < len(prefix) and statuses != ("pending", "in_progress", "failed"):
            raise ValueError("only a failed attempt may precede another attempt")
        for transition_index, (transition, entry) in enumerate(zip(transitions, entries), start=1):
            if type(transition) is not dict:
                raise TypeError("checkpoint attempt transition must be a plain mapping")
            if (
                transition.get("attempt_id") != attempt["attempt_id"]
                or transition.get("event_id") != current_event_id
                or transition.get("attempt_index") != expected_index
            ):
                raise ValueError("checkpoint attempt transition identity drifted")
            if type(entry) is not dict or set(entry) != {"transition", "row_envelope"}:
                raise ValueError("checkpoint attempt transition entry has unexpected fields")
            if entry["transition"] != transition:
                raise ValueError("checkpoint attempt transition copies do not match")
            envelope = entry["row_envelope"]
            if type(envelope) is not dict or set(envelope) != {
                "attempt_id",
                "event_id",
                "attempt_index",
                "transition_index",
                "status",
                "payload_hash",
                "checkpoint_payload_hash",
                "raw_response_uri",
                "raw_response_hash",
            }:
                raise ValueError("checkpoint attempt transition row envelope is invalid")
            if (
                envelope["attempt_id"] != attempt["attempt_id"]
                or envelope["event_id"] != current_event_id
                or envelope["attempt_index"] != expected_index
                or envelope["transition_index"] != transition_index
                or envelope["status"] != transition["status"]
            ):
                raise ValueError("checkpoint attempt transition row identity drifted")
            _require_sha256("checkpoint attempt transition payload hash", envelope["payload_hash"])
            _require_sha256(
                "checkpoint redacted transition payload hash",
                envelope["checkpoint_payload_hash"],
            )
            if canonical_payload_hash(transition) != envelope["checkpoint_payload_hash"]:
                raise ValueError("checkpoint transition canonical payload hash drifted")
            raw_uri = envelope["raw_response_uri"]
            raw_hash = envelope["raw_response_hash"]
            if (raw_uri is None) != (raw_hash is None):
                raise ValueError("checkpoint external response URI/hash binding is incomplete")
            if raw_uri is not None:
                ExternalResponseReference(uri=raw_uri, sha256=raw_hash)
                if transition.get("raw_response") is not None or (
                    transition.get("raw_response_hash") != raw_hash
                ):
                    raise ValueError("checkpoint external response body/hash binding drifted")
                _validate_redacted_attempt_transition(transition)
            else:
                replayed_transition = GenerationAttempt.from_payload(transition)
                if replayed_transition.to_payload() != transition:
                    raise ValueError("checkpoint attempt transition is not canonical")
                if canonical_payload_hash(transition) != envelope["payload_hash"]:
                    raise ValueError("checkpoint attempt transition payload hash drifted")
        immutable_fields = (
            "attempt_id",
            "event_id",
            "attempt_index",
            "request_id",
            "exposure_id",
            "rendered_messages",
            "rendered_prompt_hash",
            "request_parameters",
            "request_parameters_hash",
            "model_identity",
            "model_identity_hash",
            "model_seed",
        )
        if any(
            transition[field] != transitions[0][field]
            for transition in transitions[1:]
            for field in immutable_fields
        ):
            raise ValueError("checkpoint attempt immutable request evidence drifted")
        if len(transitions) == 3 and transitions[2]["started_at"] != transitions[1]["started_at"]:
            raise ValueError("checkpoint terminal transition start time drifted")
        for previous, current in zip(transitions, transitions[1:]):
            if previous["provider_request_id"] is not None and (
                current["provider_request_id"] != previous["provider_request_id"]
            ):
                raise ValueError("checkpoint provider request identity drifted")
            if any(
                key not in current["provider_metadata"]
                or current["provider_metadata"][key] != value
                for key, value in previous["provider_metadata"].items()
            ):
                raise ValueError("checkpoint provider metadata progression drifted")


def _validate_redacted_attempt_transition(payload: dict[str, object]) -> None:
    expected_fields = set(GenerationAttempt.__dataclass_fields__)
    if set(payload) != expected_fields:
        raise ValueError("redacted checkpoint attempt fields do not match the v2 contract")
    pending_shadow = dict(payload)
    pending_shadow.update(
        {
            "status": "pending",
            "provider_request_id": None,
            "provider_metadata": {},
            "provider_metadata_hash": canonical_payload_hash({}),
            "http_status": None,
            "raw_response": None,
            "raw_response_hash": None,
            "parsed_response": None,
            "parsed_response_hash": None,
            "usage": {},
            "usage_hash": canonical_payload_hash({}),
            "finish_reason": None,
            "error": None,
            "started_at": None,
            "finished_at": None,
        }
    )
    GenerationAttempt.from_payload(pending_shadow)
    if payload["status"] not in {"failed", "succeeded"}:
        raise ValueError("only terminal checkpoint attempts may redact an external response")
    provider_request_id = payload["provider_request_id"]
    if provider_request_id is not None:
        _require_id("provider_request_id", provider_request_id)
    for name in ("provider_metadata", "usage"):
        if type(payload[name]) is not dict:
            raise TypeError(f"redacted checkpoint attempt {name} must be a JSON object")
        if canonical_payload_hash(payload[name]) != payload[f"{name}_hash"]:
            raise ValueError(f"redacted checkpoint attempt {name} hash drifted")
    for name in ("parsed_response", "error"):
        if payload[name] is not None and type(payload[name]) is not dict:
            raise TypeError(f"redacted checkpoint attempt {name} must be an object or null")
    if (payload["parsed_response"] is None) != (payload["parsed_response_hash"] is None):
        raise ValueError("redacted checkpoint parsed response hash pairing drifted")
    if (
        payload["parsed_response"] is not None
        and canonical_payload_hash(payload["parsed_response"]) != payload["parsed_response_hash"]
    ):
        raise ValueError("redacted checkpoint parsed response hash drifted")
    _require_sha256("redacted raw response hash", payload["raw_response_hash"])
    started = _require_timestamp("started_at", payload["started_at"])
    finished = _require_timestamp("finished_at", payload["finished_at"])
    if finished < started:
        raise ValueError("redacted checkpoint finish time precedes start")
    if payload["http_status"] is not None:
        _require_int("http_status", payload["http_status"], minimum=100)
        if payload["http_status"] > 599:
            raise ValueError("redacted checkpoint HTTP status is outside range")
    _require_string("finish_reason", payload["finish_reason"], optional=True)
    if payload["usage"]:
        required_usage = {"prompt_tokens", "completion_tokens", "total_tokens"}
        if not required_usage.issubset(payload["usage"]):
            raise ValueError("redacted checkpoint attempt usage is incomplete")
        for key in required_usage:
            _require_int(f"usage[{key}]", payload["usage"][key])
        if payload["usage"]["total_tokens"] != (
            payload["usage"]["prompt_tokens"] + payload["usage"]["completion_tokens"]
        ):
            raise ValueError("redacted checkpoint usage total drifted")
    if payload["status"] == "succeeded":
        if (
            provider_request_id is None
            or not payload["provider_metadata"]
            or payload["parsed_response"] is None
            or not payload["usage"]
            or payload["finish_reason"] is None
            or payload["error"] is not None
            or type(payload["http_status"]) is not int
            or not 200 <= payload["http_status"] < 300
        ):
            raise ValueError("redacted succeeded checkpoint attempt is incomplete")
    elif not payload["error"] or payload["parsed_response"] is not None:
        raise ValueError("redacted failed checkpoint attempt is incomplete")


@dataclass(frozen=True, slots=True)
class Checkpoint:
    version: str
    storage_schema_version: str
    run_id: str
    run_spec_hash: str
    protocol_id: str
    protocol_version: str
    protocol_hash: str
    schedule_hash: str
    schedule_count: int
    artifact_hashes: Mapping[str, str]
    expected_agent_ids_hash: str
    expected_exposure_mode: str
    expected_exposure_graph_hash: str | None
    expected_exposure_graph_artifact_id: str | None
    expected_exposure_graph_artifact_type: str | None
    expected_source_ws_artifact_hash: str | None
    expected_source_ws_artifact_id: str | None
    expected_source_ws_artifact_type: str | None
    round0_root: str
    baseline_manifest_hash: str
    current_manifest_hash: str
    next_event_ordinal: int
    current_event_id: str | None
    private_state_root: str
    public_stock_root: str
    latest_public_pointer_root: str
    feed_cursor_root: str
    state_collection_root: str
    event_chain_head: str
    current_attempt_prefix: tuple[Mapping[str, object], ...]

    @property
    def resume_action(self) -> str:
        """Describe the evidence-preserving recovery action without choosing policy."""

        validated = Checkpoint.from_payload(self.to_payload())
        if validated.current_event_id is None:
            return "complete"
        if not validated.current_attempt_prefix:
            return "start_current_event"
        transitions = validated.current_attempt_prefix[-1].get("transitions")
        if not isinstance(transitions, (tuple, list)) or not transitions:
            raise ValueError("checkpoint attempt prefix is incomplete")
        last = transitions[-1]
        if not isinstance(last, Mapping):
            raise ValueError("checkpoint attempt transition is invalid")
        status = last.get("status")
        if status in {"pending", "in_progress"}:
            return "resume_same_attempt"
        if status == "failed":
            return "retry_same_event"
        if status == "succeeded":
            return "commit_landed_success"
        raise ValueError("checkpoint attempt transition status is invalid")

    @property
    def checkpoint_hash(self) -> str:
        return canonical_payload_hash(self._body_payload())

    def _body_payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "storage_schema_version": self.storage_schema_version,
            "run_id": self.run_id,
            "run_spec_hash": self.run_spec_hash,
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "protocol_hash": self.protocol_hash,
            "schedule_hash": self.schedule_hash,
            "schedule_count": self.schedule_count,
            "artifact_hashes": dict(self.artifact_hashes),
            "expected_agent_ids_hash": self.expected_agent_ids_hash,
            "expected_exposure_mode": self.expected_exposure_mode,
            "expected_exposure_graph_hash": self.expected_exposure_graph_hash,
            "expected_exposure_graph_artifact_id": self.expected_exposure_graph_artifact_id,
            "expected_exposure_graph_artifact_type": self.expected_exposure_graph_artifact_type,
            "expected_source_ws_artifact_hash": self.expected_source_ws_artifact_hash,
            "expected_source_ws_artifact_id": self.expected_source_ws_artifact_id,
            "expected_source_ws_artifact_type": self.expected_source_ws_artifact_type,
            "round0_root": self.round0_root,
            "baseline_manifest_hash": self.baseline_manifest_hash,
            "current_manifest_hash": self.current_manifest_hash,
            "next_event_ordinal": self.next_event_ordinal,
            "current_event_id": self.current_event_id,
            "private_state_root": self.private_state_root,
            "public_stock_root": self.public_stock_root,
            "latest_public_pointer_root": self.latest_public_pointer_root,
            "feed_cursor_root": self.feed_cursor_root,
            "state_collection_root": self.state_collection_root,
            "event_chain_head": self.event_chain_head,
            "current_attempt_prefix": _plain(self.current_attempt_prefix),
        }

    def to_payload(self) -> dict[str, object]:
        body = self._body_payload()
        return {"checkpoint": body, "checkpoint_hash": canonical_payload_hash(body)}

    @classmethod
    def from_payload(cls, payload: object) -> Checkpoint:
        if type(payload) is not dict or set(payload) != {"checkpoint", "checkpoint_hash"}:
            raise ValueError("checkpoint envelope has unexpected fields")
        body = payload["checkpoint"]
        if type(body) is not dict:
            raise TypeError("checkpoint body must be a plain mapping")
        expected_fields = {
            "version",
            "storage_schema_version",
            "run_id",
            "run_spec_hash",
            "protocol_id",
            "protocol_version",
            "protocol_hash",
            "schedule_hash",
            "schedule_count",
            "artifact_hashes",
            "expected_agent_ids_hash",
            "expected_exposure_mode",
            "expected_exposure_graph_hash",
            "expected_exposure_graph_artifact_id",
            "expected_exposure_graph_artifact_type",
            "expected_source_ws_artifact_hash",
            "expected_source_ws_artifact_id",
            "expected_source_ws_artifact_type",
            "round0_root",
            "baseline_manifest_hash",
            "current_manifest_hash",
            "next_event_ordinal",
            "current_event_id",
            "private_state_root",
            "public_stock_root",
            "latest_public_pointer_root",
            "feed_cursor_root",
            "state_collection_root",
            "event_chain_head",
            "current_attempt_prefix",
        }
        if set(body) != expected_fields:
            raise ValueError("checkpoint body has unexpected fields")
        _require_sha256("checkpoint_hash", payload["checkpoint_hash"])
        if canonical_payload_hash(body) != payload["checkpoint_hash"]:
            raise ValueError("checkpoint envelope hash does not match body")
        if body["version"] != _CHECKPOINT_VERSION:
            raise ValueError("checkpoint version is unsupported")
        _require_id("storage_schema_version", body["storage_schema_version"])
        _require_id("run_id", body["run_id"])
        _require_id("protocol_id", body["protocol_id"])
        _require_id("protocol_version", body["protocol_version"])
        _require_id("expected_exposure_mode", body["expected_exposure_mode"])
        for name in (
            "run_spec_hash",
            "protocol_hash",
            "schedule_hash",
            "expected_agent_ids_hash",
            "round0_root",
            "baseline_manifest_hash",
            "current_manifest_hash",
            "private_state_root",
            "public_stock_root",
            "latest_public_pointer_root",
            "feed_cursor_root",
            "state_collection_root",
            "event_chain_head",
        ):
            _require_sha256(name, body[name])
        _require_int("schedule_count", body["schedule_count"])
        _require_int("next_event_ordinal", body["next_event_ordinal"])
        if not 0 <= body["next_event_ordinal"] <= body["schedule_count"]:
            raise ValueError("checkpoint next event ordinal is outside schedule")
        expected_event_id = (
            derive_event_id(body["run_id"], body["next_event_ordinal"])
            if body["next_event_ordinal"] < body["schedule_count"]
            else None
        )
        if body["current_event_id"] != expected_event_id:
            raise ValueError("checkpoint current event identity does not match ordinal")
        artifacts = body["artifact_hashes"]
        if type(artifacts) is not dict or not artifacts:
            raise ValueError("checkpoint artifact hashes must be a non-empty plain mapping")
        for artifact_id, artifact_hash in artifacts.items():
            _require_id("checkpoint artifact ID", artifact_id)
            _require_sha256("checkpoint artifact hash", artifact_hash)
        for name in (
            "expected_exposure_graph_hash",
            "expected_source_ws_artifact_hash",
        ):
            if body[name] is not None:
                _require_sha256(name, body[name])
        for name in (
            "expected_exposure_graph_artifact_id",
            "expected_exposure_graph_artifact_type",
            "expected_source_ws_artifact_id",
            "expected_source_ws_artifact_type",
        ):
            if body[name] is not None:
                _require_id(name, body[name])
        prefix = body["current_attempt_prefix"]
        if type(prefix) is not list or any(type(item) is not dict for item in prefix):
            raise TypeError("checkpoint attempt prefix must be a list of plain mappings")
        _validate_attempt_prefix(prefix, body["current_event_id"])
        _validate_depth(payload)
        frozen_prefix = tuple(_freeze(item) for item in prefix)
        return cls(
            version=body["version"],
            storage_schema_version=body["storage_schema_version"],
            run_id=body["run_id"],
            run_spec_hash=body["run_spec_hash"],
            protocol_id=body["protocol_id"],
            protocol_version=body["protocol_version"],
            protocol_hash=body["protocol_hash"],
            schedule_hash=body["schedule_hash"],
            schedule_count=body["schedule_count"],
            artifact_hashes=MappingProxyType(dict(artifacts)),
            expected_agent_ids_hash=body["expected_agent_ids_hash"],
            expected_exposure_mode=body["expected_exposure_mode"],
            expected_exposure_graph_hash=body["expected_exposure_graph_hash"],
            expected_exposure_graph_artifact_id=body["expected_exposure_graph_artifact_id"],
            expected_exposure_graph_artifact_type=body["expected_exposure_graph_artifact_type"],
            expected_source_ws_artifact_hash=body["expected_source_ws_artifact_hash"],
            expected_source_ws_artifact_id=body["expected_source_ws_artifact_id"],
            expected_source_ws_artifact_type=body["expected_source_ws_artifact_type"],
            round0_root=body["round0_root"],
            baseline_manifest_hash=body["baseline_manifest_hash"],
            current_manifest_hash=body["current_manifest_hash"],
            next_event_ordinal=body["next_event_ordinal"],
            current_event_id=body["current_event_id"],
            private_state_root=body["private_state_root"],
            public_stock_root=body["public_stock_root"],
            latest_public_pointer_root=body["latest_public_pointer_root"],
            feed_cursor_root=body["feed_cursor_root"],
            state_collection_root=body["state_collection_root"],
            event_chain_head=body["event_chain_head"],
            current_attempt_prefix=frozen_prefix,  # type: ignore[arg-type]
        )


def _root(values: list[object]) -> str:
    return canonical_payload_hash(values)


def _path(value: str | Path, *, must_exist: bool) -> Path:
    if not isinstance(value, (str, Path)):
        raise TypeError("checkpoint path must be a string or Path")
    raw = str(value)
    if not raw or "\x00" in raw or "://" in raw:
        raise ValueError("checkpoint path must be a local filesystem path")
    path = Path(value)
    if path.is_symlink():
        raise ValueError("checkpoint path must not be a symbolic link")
    if must_exist:
        if not path.is_file():
            raise FileNotFoundError(f"checkpoint file does not exist: {path}")
    elif not path.parent.is_dir() or path.parent.is_symlink():
        raise ValueError("checkpoint parent must be an existing non-symlink directory")
    return path


def _fsync_parent_directory(path: Path) -> bool:
    """Persist a rename on POSIX; Windows has no portable directory-fsync API."""

    if os.name == "nt":
        return False
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path.parent, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return True


def _open_checkpoint_windows(path: Path) -> int:
    """Open one Windows handle without following a final reparse point."""

    import ctypes
    from ctypes import wintypes
    import msvcrt

    class FileAttributeTagInfo(ctypes.Structure):
        _fields_ = [
            ("file_attributes", wintypes.DWORD),
            ("reparse_tag", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    get_information = kernel32.GetFileInformationByHandleEx
    get_information.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    get_information.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    absolute = os.path.abspath(os.fspath(path))
    if absolute.startswith("\\\\"):
        api_path = "\\\\?\\UNC\\" + absolute[2:]
    else:
        api_path = "\\\\?\\" + absolute
    handle = create_file(
        api_path,
        0x80000000,  # GENERIC_READ
        0x00000001 | 0x00000002 | 0x00000004,  # FILE_SHARE_READ | WRITE | DELETE
        None,
        3,  # OPEN_EXISTING
        0x00200000 | 0x02000000,  # OPEN_REPARSE_POINT | BACKUP_SEMANTICS
        None,
    )
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    information = FileAttributeTagInfo()
    try:
        if not get_information(
            handle,
            9,  # FileAttributeTagInfo
            ctypes.byref(information),
            ctypes.sizeof(information),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if information.file_attributes & 0x00000400:  # FILE_ATTRIBUTE_REPARSE_POINT
            raise ValueError("checkpoint path must not be a Windows reparse point")
        descriptor = msvcrt.open_osfhandle(
            handle,
            os.O_RDONLY | getattr(os, "O_BINARY", 0),
        )
    except BaseException:
        close_handle(handle)
        raise
    return descriptor


def write_checkpoint_atomic(path: str | Path, checkpoint: Checkpoint) -> str:
    """Atomically replace a local checkpoint without damaging an older file."""

    if not isinstance(checkpoint, Checkpoint):
        raise TypeError("checkpoint must be a Checkpoint")
    checkpoint = Checkpoint.from_payload(checkpoint.to_payload())
    target = _path(path, must_exist=False)
    raw = _canonical_json(checkpoint.to_payload()).encode("utf-8")
    if len(raw) > _MAX_CHECKPOINT_BYTES:
        raise ValueError("checkpoint exceeds maximum byte size")
    descriptor: int | None = None
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        temporary = None
        _fsync_parent_directory(target)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return checkpoint.checkpoint_hash


def load_checkpoint(path: str | Path) -> Checkpoint:
    """Load a bounded canonical checkpoint from a local regular file."""

    source = _path(path, must_exist=True)
    if os.name == "nt":
        descriptor = _open_checkpoint_windows(source)
    else:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(source, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("checkpoint must be a regular file")
        if metadata.st_size > _MAX_CHECKPOINT_BYTES:
            raise ValueError("checkpoint exceeds maximum byte size")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            raw_bytes = stream.read(_MAX_CHECKPOINT_BYTES + 1)
        if len(raw_bytes) > _MAX_CHECKPOINT_BYTES:
            raise ValueError("checkpoint exceeds maximum byte size")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    try:
        raw = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("checkpoint is not valid UTF-8") from error
    _preflight_json_depth(raw)

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("checkpoint JSON contains a duplicate key")
            result[key] = value
        return result

    try:
        payload = json.loads(raw, object_pairs_hook=reject_duplicates)
    except (json.JSONDecodeError, RecursionError, ValueError) as error:
        raise ValueError("checkpoint JSON is invalid or contains a duplicate key") from error
    _validate_depth(payload)
    if raw != _canonical_json(payload):
        raise ValueError("checkpoint JSON bytes are not canonical")
    return Checkpoint.from_payload(payload)


def build_checkpoint(storage: RunStorage) -> Checkpoint:
    """Build a deterministic checkpoint from fully verified storage."""

    if not isinstance(storage, RunStorage):
        raise TypeError("storage must be a RunStorage")
    binding = storage.binding
    if binding.round0_root is None:
        raise ValueError("checkpoint requires sealed round-0 state")
    progress = storage.progress
    evidence = storage.recovery_evidence()
    private_root = _root(list(evidence["private_states"]))
    public_root = _root(list(evidence["public_stock"]))
    pointer_root = _root(list(evidence["latest_public_pointers"]))
    cursor_root = _root(list(evidence["feed_cursors"]))
    current_manifest_hash = canonical_payload_hash(
        {
            "baseline_manifest_hash": binding.manifest_hash,
            "next_event_ordinal": progress.next_event_ordinal,
            "succeeded_event_count": progress.succeeded_event_count,
            "event_chain_head": progress.event_chain_head,
        }
    )
    current_event_id = (
        derive_event_id(binding.run_id, progress.next_event_ordinal)
        if progress.next_event_ordinal < progress.expected_event_count
        else None
    )
    checkpoint = Checkpoint(
        version=_CHECKPOINT_VERSION,
        storage_schema_version=binding.schema_version,
        run_id=binding.run_id,
        run_spec_hash=binding.run_spec_hash,
        protocol_id=binding.protocol_id,
        protocol_version=binding.protocol_version,
        protocol_hash=binding.protocol_hash,
        schedule_hash=binding.schedule_hash,
        schedule_count=binding.schedule_count,
        artifact_hashes=MappingProxyType(dict(binding.artifact_hashes)),
        expected_agent_ids_hash=binding.expected_agent_ids_hash,
        expected_exposure_mode=binding.expected_exposure_mode,
        expected_exposure_graph_hash=binding.expected_exposure_graph_hash,
        expected_exposure_graph_artifact_id=binding.expected_exposure_graph_artifact_id,
        expected_exposure_graph_artifact_type=binding.expected_exposure_graph_artifact_type,
        expected_source_ws_artifact_hash=binding.expected_source_ws_artifact_hash,
        expected_source_ws_artifact_id=binding.expected_source_ws_artifact_id,
        expected_source_ws_artifact_type=binding.expected_source_ws_artifact_type,
        round0_root=binding.round0_root,
        baseline_manifest_hash=binding.manifest_hash,
        current_manifest_hash=current_manifest_hash,
        next_event_ordinal=progress.next_event_ordinal,
        current_event_id=current_event_id,
        private_state_root=private_root,
        public_stock_root=public_root,
        latest_public_pointer_root=pointer_root,
        feed_cursor_root=cursor_root,
        state_collection_root=canonical_payload_hash(
            {
                "private_state_root": private_root,
                "public_stock_root": public_root,
                "latest_public_pointer_root": pointer_root,
                "feed_cursor_root": cursor_root,
            }
        ),
        event_chain_head=evidence["event_chain_head"],  # type: ignore[arg-type]
        current_attempt_prefix=evidence["current_attempt_prefix"],  # type: ignore[arg-type]
    )
    return Checkpoint.from_payload(checkpoint.to_payload())


def validate_checkpoint(checkpoint: Checkpoint, storage: RunStorage) -> str:
    """Validate a checkpoint against storage and classify its freshness."""

    if not isinstance(checkpoint, Checkpoint):
        raise TypeError("checkpoint must be a Checkpoint")
    checkpoint = Checkpoint.from_payload(checkpoint.to_payload())
    if checkpoint.next_event_ordinal > storage.progress.next_event_ordinal:
        raise ValueError("checkpoint is ahead of SQLite storage")
    if checkpoint.next_event_ordinal < storage.progress.next_event_ordinal:
        evidence = storage.recovery_evidence(checkpoint.next_event_ordinal)
        expected = _build_checkpoint_from_evidence(storage, evidence)
        if not _is_attempt_prefix(
            checkpoint.current_attempt_prefix,
            evidence["current_attempt_prefix"],  # type: ignore[arg-type]
        ):
            raise ValueError("stale checkpoint attempt prefix conflicts with SQLite history")
        expected = replace(expected, current_attempt_prefix=checkpoint.current_attempt_prefix)
        if checkpoint != expected:
            raise ValueError("stale checkpoint conflicts with SQLite history")
        return "stale"
    current = build_checkpoint(storage)
    if checkpoint == current:
        return "current"
    if _is_attempt_prefix(
        checkpoint.current_attempt_prefix,
        current.current_attempt_prefix,
    ) and checkpoint == replace(
        current,
        current_attempt_prefix=checkpoint.current_attempt_prefix,
    ):
        return "stale"
    raise ValueError("checkpoint conflicts with SQLite storage")


def _is_attempt_prefix(
    candidate: tuple[Mapping[str, object], ...],
    stored: tuple[Mapping[str, object], ...],
) -> bool:
    if len(candidate) > len(stored):
        return False
    for candidate_attempt, stored_attempt in zip(candidate, stored):
        if candidate_attempt.get("attempt_id") != stored_attempt.get("attempt_id") or (
            candidate_attempt.get("attempt_index") != stored_attempt.get("attempt_index")
        ):
            return False
        for name in ("transitions", "transition_entries"):
            candidate_values = tuple(candidate_attempt.get(name, ()))
            stored_values = tuple(stored_attempt.get(name, ()))
            if len(candidate_values) > len(stored_values) or _plain(candidate_values) != _plain(
                stored_values[: len(candidate_values)]
            ):
                return False
    return True


def _build_checkpoint_from_evidence(
    storage: RunStorage, evidence: Mapping[str, object]
) -> Checkpoint:
    """Build a historical checkpoint projection for stale validation."""

    binding = storage.binding
    ordinal = evidence["next_event_ordinal"]
    assert type(ordinal) is int
    private_root = _root(list(evidence["private_states"]))
    public_root = _root(list(evidence["public_stock"]))
    pointer_root = _root(list(evidence["latest_public_pointers"]))
    cursor_root = _root(list(evidence["feed_cursors"]))
    chain_head = evidence["event_chain_head"]
    assert type(chain_head) is str
    current_manifest_hash = canonical_payload_hash(
        {
            "baseline_manifest_hash": binding.manifest_hash,
            "next_event_ordinal": ordinal,
            "succeeded_event_count": ordinal,
            "event_chain_head": chain_head,
        }
    )
    checkpoint = Checkpoint(
        version=_CHECKPOINT_VERSION,
        storage_schema_version=binding.schema_version,
        run_id=binding.run_id,
        run_spec_hash=binding.run_spec_hash,
        protocol_id=binding.protocol_id,
        protocol_version=binding.protocol_version,
        protocol_hash=binding.protocol_hash,
        schedule_hash=binding.schedule_hash,
        schedule_count=binding.schedule_count,
        artifact_hashes=MappingProxyType(dict(binding.artifact_hashes)),
        expected_agent_ids_hash=binding.expected_agent_ids_hash,
        expected_exposure_mode=binding.expected_exposure_mode,
        expected_exposure_graph_hash=binding.expected_exposure_graph_hash,
        expected_exposure_graph_artifact_id=binding.expected_exposure_graph_artifact_id,
        expected_exposure_graph_artifact_type=binding.expected_exposure_graph_artifact_type,
        expected_source_ws_artifact_hash=binding.expected_source_ws_artifact_hash,
        expected_source_ws_artifact_id=binding.expected_source_ws_artifact_id,
        expected_source_ws_artifact_type=binding.expected_source_ws_artifact_type,
        round0_root=binding.round0_root,  # type: ignore[arg-type]
        baseline_manifest_hash=binding.manifest_hash,
        current_manifest_hash=current_manifest_hash,
        next_event_ordinal=ordinal,
        current_event_id=(
            derive_event_id(binding.run_id, ordinal) if ordinal < binding.schedule_count else None
        ),
        private_state_root=private_root,
        public_stock_root=public_root,
        latest_public_pointer_root=pointer_root,
        feed_cursor_root=cursor_root,
        state_collection_root=canonical_payload_hash(
            {
                "private_state_root": private_root,
                "public_stock_root": public_root,
                "latest_public_pointer_root": pointer_root,
                "feed_cursor_root": cursor_root,
            }
        ),
        event_chain_head=chain_head,
        current_attempt_prefix=(),
    )
    return Checkpoint.from_payload(checkpoint.to_payload())
