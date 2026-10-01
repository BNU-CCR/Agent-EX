"""Linux-only, controlled export of ordinal judge labels.

Threat model: an owner reviews source and evidence identities out of band, places an
immutable receipt under ``APPROVAL_ROOT``, and supplies that receipt's independently
approved hash.  This boundary prevents accidental self-approval and evidence drift;
it does not claim to resist a privileged/root attacker able to replace code, receipts,
or the running interpreter.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
from typing import Callable, Mapping, TypeVar

from ..domain import canonical_payload_hash
from .judge_contracts import JudgeExecutionManifest, JudgeRequestRenderer
from .judge_runner import (
    JudgeApprovedOrder,
    JudgeAttemptResolution,
    JudgeProjection,
)
from .review import SemanticReviewPolicy


SCHEMA = "paper1.calibration.judge-safe-label-export.v2"
APPROVAL_RECEIPT_SCHEMA = "paper1.calibration.judge-safe-label-export-approval-receipt.v1"
APPROVAL_PACKET_SCHEMA = "paper1.calibration.judge-safe-label-export-approval-packet.v2"
APPROVAL_ROOT = Path("/root/autodl-tmp/agent-ex-approvals")
MAX_DIMENSIONS = 16
MAX_LABELS_PER_DIMENSION = 16
_MAX_JSON_BYTES = 64 * 1024 * 1024
_READ_CHUNK = 1024 * 1024
_RAW_MARKERS = {
    "raw",
    "raw_bytes",
    "raw_bytes_base64",
    "output_bytes",
    "output_bytes_base64",
    "response_bytes",
    "response_bytes_base64",
}
_PATH_FIELDS = {
    "projection_path",
    "reconciliation_dir",
    "manifest_path",
    "policy_path",
    "renderer_path",
    "blind_pack_path",
    "blind_index_path",
    "approved_order_path",
}
_RECEIPT_FIELDS = {
    "schema_version",
    "packet_path",
    "approved_packet_hash",
    "production_authorization_hash",
    "combined_packet_hash",
    "reviewed_module_sha256",
    "reviewed_script_sha256",
    "blind_pack_hash",
    "blind_index_hash",
    "approved_order_hash",
    "policy_hash",
    "vocabulary_hash",
    "dimension_count",
    "label_counts",
    "preliminary",
    "incomplete",
    "not_frozen",
    "formal_parameter_authority",
    "record_hash",
}
_PACKET_FIELDS = {
    "schema_version",
    "run_root",
    "paths",
    "cutoff",
    "expected_total",
    "production_authorization_hash",
    "combined_packet_hash",
    "projection_hash",
    "manifest_hash",
    "policy_hash",
    "renderer_hash",
    "blind_pack_hash",
    "blind_index_hash",
    "approved_order_hash",
    "vocabulary",
    "vocabulary_hash",
    "dimension_count",
    "label_counts",
    "preliminary",
    "incomplete",
    "not_frozen",
    "formal_parameter_authority",
    "record_hash",
}
_OUTPUT_FIELDS = {
    "schema_version",
    "status",
    "source",
    "snapshot",
    "analysis",
    "vocabulary",
    "items",
    "aggregate_counts",
    "record_hash",
}
_OUTPUT_STATUS_FIELDS = {
    "preliminary",
    "incomplete",
    "not_frozen",
    "formal_parameter_authority",
}
_OUTPUT_SOURCE_FIELDS = {
    "approval_receipt_hash",
    "production_authorization_hash",
    "combined_packet_hash",
    "manifest_hash",
    "projection_hash",
    "blind_pack_hash",
    "blind_index_hash",
    "approved_order_hash",
    "policy_hash",
    "renderer_hash",
}
_OUTPUT_ITEM_FIELDS = {
    "ordinal",
    "item_hash",
    "completed_attempt_hash",
    "resolution_hash",
    "parse_record_hash",
    "source_output_sha256",
    "label_ordinals",
}
T = TypeVar("T")


def _exact(value: object, fields: set[str], label: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != fields:
        raise ValueError(f"{label} requires exact fields")
    return value


def _sha(name: str, value: object) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256")
    return value


def _status_is_preliminary(value: Mapping[str, object]) -> bool:
    return (
        value.get("preliminary") is True
        and value.get("incomplete") is True
        and value.get("not_frozen") is True
        and value.get("formal_parameter_authority") is False
    )


def _relative_path(value: object, label: str) -> PurePosixPath:
    if (
        type(value) is not str
        or not value
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"{label} must be a control-free relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{label} must remain beneath its fixed root")
    return path


def _validate_vocabulary_shape(dimension_count: object, label_counts: object) -> list[int]:
    if (
        type(dimension_count) is not int
        or not 1 <= dimension_count <= MAX_DIMENSIONS
        or type(label_counts) is not list
        or len(label_counts) != dimension_count
        or any(
            type(count) is not int or not 2 <= count <= MAX_LABELS_PER_DIMENSION
            for count in label_counts
        )
    ):
        raise ValueError("vocabulary shape exceeds the strict ordinal limits")
    return label_counts


def validate_approval_receipt_payload(
    payload: Mapping[str, object], *, approved_receipt_hash: str
) -> None:
    """Validate the independently approved receipt without reading run evidence."""

    receipt = _exact(payload, _RECEIPT_FIELDS, "approval receipt")
    if receipt["schema_version"] != APPROVAL_RECEIPT_SCHEMA:
        raise ValueError("approval receipt schema differs")
    approved_receipt_hash = _sha("approved receipt hash", approved_receipt_hash)
    record_hash = _sha("approval receipt record hash", receipt["record_hash"])
    content = {key: value for key, value in receipt.items() if key != "record_hash"}
    if record_hash != canonical_payload_hash(content) or record_hash != approved_receipt_hash:
        raise ValueError("approved receipt hash differs from immutable receipt content")
    _relative_path(receipt["packet_path"], "packet path")
    for field in _RECEIPT_FIELDS - {
        "schema_version",
        "packet_path",
        "dimension_count",
        "label_counts",
        "preliminary",
        "incomplete",
        "not_frozen",
        "formal_parameter_authority",
    }:
        _sha(field, receipt[field])
    _validate_vocabulary_shape(receipt["dimension_count"], receipt["label_counts"])
    if not _status_is_preliminary(receipt):
        raise ValueError("approval receipt status must remain preliminary and incomplete")


def _reviewed_exporter_source_paths() -> tuple[Path, Path]:
    module_path = Path(__file__)
    script_path = module_path.parents[3] / "scripts" / "phase0a1-safe-label-export.py"
    return module_path, script_path


def verify_reviewed_exporter_sources(receipt: Mapping[str, object]) -> None:
    """Bind the running implementation to the code hashes reviewed by the owner."""

    module_path, script_path = _reviewed_exporter_source_paths()
    for field, path in (
        ("reviewed_module_sha256", module_path),
        ("reviewed_script_sha256", script_path),
    ):
        try:
            encoded = _read_absolute_regular_file(path)
        except OSError as error:
            raise ValueError("reviewed exporter source cannot be read") from error
        if hashlib.sha256(encoded).hexdigest() != receipt[field]:
            raise ValueError("reviewed exporter source hash differs from the receipt")


def validate_nonraw_json_tree(value: object) -> None:
    """Apply the recursive non-raw schema gate after JSON decoding."""

    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                raise ValueError("non-raw JSON keys must be strings")
            lowered = key.lower()
            if any(marker in lowered for marker in _RAW_MARKERS):
                raise ValueError("non-raw JSON contains a raw marker")
            validate_nonraw_json_tree(child)
    elif type(value) is list:
        for child in value:
            validate_nonraw_json_tree(child)
    elif type(value) is str:
        lowered = value.lower()
        if any(marker in lowered for marker in _RAW_MARKERS):
            raise ValueError("non-raw JSON contains a raw marker")
    elif value is not None and type(value) not in {bool, int, float}:
        raise ValueError("non-raw JSON contains an unsupported value type")


def _require_linux_backend() -> None:
    required = (
        sys.platform.startswith("linux"),
        os.name == "posix",
        hasattr(os, "O_NOFOLLOW"),
        hasattr(os, "O_DIRECTORY"),
        os.open in os.supports_dir_fd,
    )
    if not all(required):
        raise RuntimeError("secure label export requires Linux handle-relative IO")


def _validate_trusted_absolute_root(path: Path) -> None:
    encoded = str(path)
    if (
        not path.is_absolute()
        or any(ord(character) < 32 or ord(character) == 127 for character in encoded)
        or any(component in {"", ".", ".."} for component in path.parts[1:])
    ):
        raise ValueError("trusted root must be a control-free canonical absolute path")


def _open_absolute_directory(path: Path) -> int:
    _validate_trusted_absolute_root(path)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(Path(path.anchor), flags)
    try:
        for component in path.parts[1:]:
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_relative(root_fd: int, relative: PurePosixPath, *, directory: bool = False) -> int:
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_NOFOLLOW
    descriptor = os.dup(root_fd)
    try:
        for index, component in enumerate(relative.parts):
            want_directory = directory or index < len(relative.parts) - 1
            child = os.open(
                component,
                directory_flags if want_directory else file_flags,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _bounded_read(descriptor: int) -> bytes:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode) or not 0 <= before.st_size <= _MAX_JSON_BYTES:
        raise ValueError("trusted JSON input is not a bounded regular file")
    remaining = before.st_size
    chunks: list[bytes] = []
    while remaining:
        chunk = os.read(descriptor, min(_READ_CHUNK, remaining))
        if not chunk:
            raise ValueError("trusted JSON input ended before its fstat size")
        chunks.append(chunk)
        remaining -= len(chunk)
    if os.read(descriptor, 1):
        raise ValueError("trusted JSON input grew while being read")
    after = os.fstat(descriptor)
    before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_identity != after_identity:
        raise ValueError("trusted JSON input identity changed while being read")
    return b"".join(chunks)


def _read_absolute_regular_file(path: Path) -> bytes:
    _validate_trusted_absolute_root(path.parent)
    relative = _relative_path(path.name, "trusted file name")
    root_fd = _open_absolute_directory(path.parent)
    try:
        descriptor = _open_relative(root_fd, relative)
        try:
            return _bounded_read(descriptor)
        finally:
            os.close(descriptor)
    finally:
        os.close(root_fd)


def _read_json(
    root_fd: int, relative: PurePosixPath, *, raw_allowed: bool = False
) -> dict[str, object]:
    descriptor = _open_relative(root_fd, relative)
    try:
        encoded = _bounded_read(descriptor)
    finally:
        os.close(descriptor)
    try:
        payload = json.loads(encoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("trusted input is not canonical JSON") from error
    if type(payload) is not dict:
        raise ValueError("trusted input must be one JSON object")
    if not raw_allowed:
        validate_nonraw_json_tree(payload)
    return payload


def _read_contract(
    root_fd: int,
    relative: PurePosixPath,
    parser: Callable[[Mapping[str, object]], T],
    *,
    raw_allowed: bool = False,
) -> T:
    return parser(_read_json(root_fd, relative, raw_allowed=raw_allowed))


def _validate_output_status(value: object) -> None:
    status = _exact(value, _OUTPUT_STATUS_FIELDS, "safe label export status")
    if not _status_is_preliminary(status):
        raise ValueError("safe label export status differs from preliminary boundary")


def validate_safe_label_export_payload(payload: Mapping[str, object]) -> None:
    """Validate the ordinal-only, raw-free output and recompute every aggregate."""

    top = _exact(payload, _OUTPUT_FIELDS, "safe label export")
    if top["schema_version"] != SCHEMA:
        raise ValueError("safe label export schema differs")
    _validate_output_status(top["status"])
    source = _exact(top["source"], _OUTPUT_SOURCE_FIELDS, "safe label export source")
    for field, value in source.items():
        _sha(field, value)
    snapshot = _exact(top["snapshot"], {"cutoff", "expected_total"}, "snapshot")
    cutoff = snapshot["cutoff"]
    expected_total = snapshot["expected_total"]
    if (
        type(cutoff) is not int
        or type(expected_total) is not int
        or not 0 <= cutoff <= expected_total
    ):
        raise ValueError("snapshot inventory is invalid")
    analysis = _exact(top["analysis"], {"module_sha256", "script_sha256"}, "analysis")
    _sha("module_sha256", analysis["module_sha256"])
    _sha("script_sha256", analysis["script_sha256"])
    vocabulary = _exact(
        top["vocabulary"],
        {"vocabulary_hash", "dimension_count", "label_counts"},
        "vocabulary",
    )
    _sha("vocabulary_hash", vocabulary["vocabulary_hash"])
    label_counts = _validate_vocabulary_shape(
        vocabulary["dimension_count"], vocabulary["label_counts"]
    )
    items = top["items"]
    if type(items) is not list or len(items) != cutoff:
        raise ValueError("item inventory differs from cutoff")
    aggregate = [[0 for _ in range(count)] for count in label_counts]
    for ordinal, item in enumerate(items):
        exact = _exact(item, _OUTPUT_ITEM_FIELDS, "ordinal item")
        if exact["ordinal"] != ordinal:
            raise ValueError("item ordinal differs from contiguous order")
        for field in _OUTPUT_ITEM_FIELDS - {"ordinal", "label_ordinals"}:
            _sha(field, exact[field])
        labels = exact["label_ordinals"]
        if type(labels) is not list or len(labels) != len(label_counts):
            raise ValueError("label ordinal count differs from vocabulary shape")
        for dimension_ordinal, (label_ordinal, count) in enumerate(
            zip(labels, label_counts, strict=True)
        ):
            if type(label_ordinal) is not int or not 0 <= label_ordinal < count:
                raise ValueError("label ordinal is outside the approved vocabulary shape")
            aggregate[dimension_ordinal][label_ordinal] += 1
    if top["aggregate_counts"] != aggregate or any(
        sum(dimension) != cutoff for dimension in aggregate
    ):
        raise ValueError("aggregate counts differ from ordinal item labels")
    content = {key: value for key, value in top.items() if key != "record_hash"}
    _sha("record_hash", top["record_hash"])
    if top["record_hash"] != canonical_payload_hash(content):
        raise ValueError("safe label export record hash differs")


def _validate_packet(
    packet: Mapping[str, object], receipt: Mapping[str, object], *, run_root: Path
) -> tuple[dict[str, object], dict[str, tuple[str, ...]]]:
    value = _exact(packet, _PACKET_FIELDS, "approval packet")
    if value["schema_version"] != APPROVAL_PACKET_SCHEMA:
        raise ValueError("approval packet schema differs")
    content = {key: item for key, item in value.items() if key != "record_hash"}
    if (
        _sha("packet record hash", value["record_hash"]) != canonical_payload_hash(content)
        or value["record_hash"] != receipt["approved_packet_hash"]
    ):
        raise ValueError("approval packet differs from receipt")
    if value["run_root"] != str(run_root):
        raise ValueError("approval packet run root differs")
    paths = _exact(value["paths"], _PATH_FIELDS, "approval packet paths")
    for name, path in paths.items():
        _relative_path(path, name)
    for field in (
        "production_authorization_hash",
        "combined_packet_hash",
        "projection_hash",
        "manifest_hash",
        "policy_hash",
        "renderer_hash",
        "blind_pack_hash",
        "blind_index_hash",
        "approved_order_hash",
        "vocabulary_hash",
    ):
        _sha(field, value[field])
    for field in (
        "production_authorization_hash",
        "combined_packet_hash",
        "policy_hash",
        "blind_pack_hash",
        "blind_index_hash",
        "approved_order_hash",
        "vocabulary_hash",
        "dimension_count",
        "label_counts",
        "preliminary",
        "incomplete",
        "not_frozen",
        "formal_parameter_authority",
    ):
        if value[field] != receipt[field]:
            raise ValueError("approval packet differs from receipt bindings")
    if not _status_is_preliminary(value):
        raise ValueError("approval packet status differs")
    label_counts = _validate_vocabulary_shape(value["dimension_count"], value["label_counts"])
    vocabulary = value["vocabulary"]
    if type(vocabulary) is not dict or list(vocabulary) != sorted(vocabulary):
        raise ValueError("approval packet vocabulary must use canonical dimension order")
    parsed: dict[str, tuple[str, ...]] = {}
    for dimension, labels in vocabulary.items():
        if type(dimension) is not str or type(labels) is not list:
            raise ValueError("approval packet vocabulary is malformed")
        if any(
            type(token) is not str
            or not token
            or len(token) > 64
            or any(ord(character) < 33 or ord(character) > 126 for character in token)
            for token in [dimension, *labels]
        ):
            raise ValueError("approval packet vocabulary contains an unsafe token")
        parsed[dimension] = tuple(labels)
    if [len(labels) for labels in parsed.values()] != label_counts:
        raise ValueError("approval packet vocabulary differs from its approved shape")
    if canonical_payload_hash(value["vocabulary"]) != value["vocabulary_hash"]:
        raise ValueError("approval packet vocabulary hash differs")
    return paths, parsed


def build_safe_label_export(
    *,
    run_root: Path,
    approval_receipt_path: Path,
    approved_receipt_hash: str,
) -> dict[str, object]:
    """Build one ordinal-only export after owner-receipt and source verification."""

    _require_linux_backend()
    approval_root = APPROVAL_ROOT
    approval_fd = _open_absolute_directory(approval_root)
    try:
        try:
            receipt_relative = PurePosixPath(
                approval_receipt_path.relative_to(approval_root).as_posix()
            )
        except ValueError as error:
            raise ValueError(
                "approval receipt must remain below the fixed approval root"
            ) from error
        receipt_relative = _relative_path(receipt_relative.as_posix(), "approval receipt path")
        if receipt_relative.name != f"{approved_receipt_hash}.json":
            raise ValueError("approval receipt filename differs from its approved hash")
        receipt = _read_json(approval_fd, receipt_relative)
    finally:
        os.close(approval_fd)
    validate_approval_receipt_payload(receipt, approved_receipt_hash=approved_receipt_hash)
    verify_reviewed_exporter_sources(receipt)

    run_fd = _open_absolute_directory(run_root)
    try:
        packet = _read_json(run_fd, _relative_path(receipt["packet_path"], "packet path"))
        paths, vocabulary = _validate_packet(packet, receipt, run_root=run_root)

        def rel(name: str) -> PurePosixPath:
            return _relative_path(paths[name], name)

        projection = _read_contract(run_fd, rel("projection_path"), JudgeProjection.from_payload)
        manifest = _read_contract(run_fd, rel("manifest_path"), JudgeExecutionManifest.from_payload)
        policy = _read_contract(run_fd, rel("policy_path"), SemanticReviewPolicy.from_payload)
        renderer = _read_contract(run_fd, rel("renderer_path"), JudgeRequestRenderer.from_payload)
        pack = _read_json(run_fd, rel("blind_pack_path"))
        index = _read_json(run_fd, rel("blind_index_path"))
        order = _read_contract(run_fd, rel("approved_order_path"), JudgeApprovedOrder.from_payload)
        observed = {
            "projection_hash": projection.record_hash,
            "manifest_hash": manifest.record_hash,
            "policy_hash": policy.record_hash,
            "renderer_hash": renderer.record_hash,
            "blind_pack_hash": pack.get("record_hash"),
            "blind_index_hash": index.get("record_hash"),
            "approved_order_hash": order.record_hash,
        }
        if any(observed[field] != packet[field] for field in observed):
            raise ValueError("run evidence differs from approval packet hashes")
        derived_order = JudgeApprovedOrder.from_manifest_bound_payloads(manifest, pack, index)
        if derived_order.to_payload() != order.to_payload():
            raise ValueError("approved order differs from pack and index")
        if (
            manifest.authorization_hash != receipt["production_authorization_hash"]
            or manifest.renderer_hash != renderer.record_hash
            or renderer.policy_hash != policy.record_hash
            or projection.manifest_hash != manifest.record_hash
            or projection.item_order != tuple(item.item_id for item in order.items)
            or set(projection.item_states) != {item.item_id for item in order.items}
            or {name: tuple(labels) for name, labels in policy.dimension_labels.items()}
            != vocabulary
        ):
            raise ValueError("approved evidence chain differs from receipt")
        cutoff = packet["cutoff"]
        if type(cutoff) is not int or cutoff < 0 or packet["expected_total"] != len(order.items):
            raise ValueError("approval packet inventory differs")
        coded = 0
        for ordinal, approved in enumerate(order.items):
            state = projection.item_states[approved.item_id]
            if (
                state.order_index != ordinal
                or state.item_hash != approved.item_hash
                or approved.policy_hash != policy.record_hash
            ):
                raise ValueError("projection differs from approved order")
            if state.status != "coded":
                break
            coded += 1
        if coded != cutoff or any(
            projection.item_states[item.item_id].status == "coded" for item in order.items[coded:]
        ):
            raise ValueError("approved cutoff differs from contiguous coded prefix")
        reconciliation = rel("reconciliation_dir")
        counts = [[0 for _ in labels] for labels in vocabulary.values()]
        items: list[dict[str, object]] = []
        for ordinal, approved in enumerate(order.items[:cutoff]):
            state = projection.item_states[approved.item_id]
            resolution_hash = _sha("resolution hash", state.resolution_hash)
            resolution = _read_contract(
                run_fd,
                reconciliation / f"{resolution_hash}.json",
                JudgeAttemptResolution.from_payload,
                raw_allowed=True,
            )
            attempt = resolution.attempt
            parsed = attempt.parse
            if (
                resolution.record_hash != resolution_hash
                or resolution.item_id != approved.item_id
                or resolution.outcome != "coded"
                or resolution.failure_code is not None
                or resolution.attempt_hash != state.completed_attempt_hash
                or parsed is None
                or not parsed.success
                or set(parsed.labels) != set(vocabulary)
                or parsed.policy_hash != policy.record_hash
            ):
                raise ValueError("resolution differs from approved coded state")
            label_ordinals: list[int] = []
            for dimension_ordinal, (dimension, allowed) in enumerate(vocabulary.items()):
                try:
                    label_ordinal = allowed.index(parsed.labels[dimension])
                except (KeyError, ValueError) as error:
                    raise ValueError("coded label differs from approved vocabulary") from error
                label_ordinals.append(label_ordinal)
                counts[dimension_ordinal][label_ordinal] += 1
            items.append(
                {
                    "ordinal": ordinal,
                    "item_hash": approved.item_hash,
                    "completed_attempt_hash": state.completed_attempt_hash,
                    "resolution_hash": resolution.record_hash,
                    "parse_record_hash": parsed.record_hash,
                    "source_output_sha256": parsed.raw_bytes_sha256,
                    "label_ordinals": label_ordinals,
                }
            )
    finally:
        os.close(run_fd)

    content: dict[str, object] = {
        "schema_version": SCHEMA,
        "status": {
            "preliminary": True,
            "incomplete": True,
            "not_frozen": True,
            "formal_parameter_authority": False,
        },
        "source": {
            "approval_receipt_hash": receipt["record_hash"],
            "production_authorization_hash": receipt["production_authorization_hash"],
            "combined_packet_hash": receipt["combined_packet_hash"],
            "manifest_hash": manifest.record_hash,
            "projection_hash": projection.record_hash,
            "blind_pack_hash": receipt["blind_pack_hash"],
            "blind_index_hash": receipt["blind_index_hash"],
            "approved_order_hash": receipt["approved_order_hash"],
            "policy_hash": receipt["policy_hash"],
            "renderer_hash": renderer.record_hash,
        },
        "snapshot": {"cutoff": cutoff, "expected_total": len(order.items)},
        "analysis": {
            "module_sha256": receipt["reviewed_module_sha256"],
            "script_sha256": receipt["reviewed_script_sha256"],
        },
        "vocabulary": {
            "vocabulary_hash": receipt["vocabulary_hash"],
            "dimension_count": receipt["dimension_count"],
            "label_counts": receipt["label_counts"],
        },
        "items": items,
        "aggregate_counts": counts,
    }
    payload = {**content, "record_hash": canonical_payload_hash(content)}
    validate_safe_label_export_payload(payload)
    return payload
