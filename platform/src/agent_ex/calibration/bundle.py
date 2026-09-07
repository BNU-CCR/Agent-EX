"""Exact, immutable and atomically written Phase 0A evidence bundles."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, fields
from fractions import Fraction
import json
import os
from pathlib import Path
import shutil
from typing import Mapping

from ..artifacts import ArtifactEnvelope
from ..domain import (
    _freeze,
    _json_ready,
    _require_evidence_uri,
    _require_id,
    _require_json_transport,
    _require_sha256,
    canonical_payload_hash,
)
from .contracts import (
    ProbeCase,
    ProbeParseEvidence,
    ProbeRequest,
    ProbeResponse,
    ProbeRunProjection,
)
from .gates import (
    GateAlgorithm,
    PairChallenge,
    SemanticGateEvidence,
    TopicSelection,
)
from .report import FreezeProposal, ProbeReport
from .report import ProposalArtifact, _reject_forbidden, build_probe_report
from .review import BlindReviewExport, SemanticReviewBundle
from .specification import load_probe_specification


PROBE_BUNDLE_FILES = (
    "manifest.json",
    "specification.json",
    "case-inventory.json",
    "requests.json",
    "raw-responses.json",
    "parse-evidence.json",
    "machine-metrics.json",
    "blind-review-export.json",
    "blind-review-import.json",
    "gate-report.json",
    "freeze-proposal.json",
)

_SCHEMAS = {
    "manifest": "paper1.calibration.probe-bundle-manifest.v1",
    "case_inventory": "paper1.calibration.case-inventory.v1",
    "requests": "paper1.calibration.request-inventory.v1",
    "raw": "paper1.calibration.raw-response-evidence.v1",
    "parse": "paper1.calibration.parse-evidence-inventory.v1",
    "metrics": "paper1.calibration.machine-metrics.v1",
}
_METADATA = {
    "calibration_only": True,
    "formal_parameter_authority": False,
    "research_parameter_status": "not_frozen",
}
_MAX_FILE_BYTES = 128 * 1024 * 1024
_MAX_JSON_DEPTH = 96


def _metadata() -> dict[str, object]:
    return dict(_METADATA)


def _require_exact_metadata(value: object) -> None:
    if type(value) is not dict or set(value) != set(_METADATA):
        raise ValueError("bundle metadata fields do not match the exact contract")
    if any(
        type(value[key]) is not type(expected) or value[key] != expected
        for key, expected in _METADATA.items()
    ):
        raise ValueError("bundle metadata must remain calibration-only without authority")


def _with_hash(schema: str, values: Mapping[str, object]) -> dict[str, object]:
    content = {"schema_version": schema, **values, "metadata": _metadata()}
    return _json_ready({**content, "content_hash": canonical_payload_hash(content)})


def _validate_wrapper(
    payload: object,
    *,
    schema: str,
    fields_: set[str],
) -> dict[str, object]:
    if type(payload) is not dict or set(payload) != fields_ | {
        "schema_version",
        "metadata",
        "content_hash",
    }:
        raise ValueError("bundle payload fields do not match the exact contract")
    _require_json_transport(payload, "bundle payload")
    if payload["schema_version"] != schema:
        raise ValueError("bundle payload schema or metadata is invalid")
    _require_exact_metadata(payload["metadata"])
    content = {key: value for key, value in payload.items() if key != "content_hash"}
    if payload["content_hash"] != canonical_payload_hash(content):
        raise ValueError("bundle payload content hash drift")
    return payload


def _fraction(value: object, name: str) -> Fraction | None:
    if value is None:
        return None
    if type(value) is not dict or set(value) != {"numerator", "denominator"}:
        raise ValueError(f"{name} must be an exact fraction payload")
    if any(type(value[key]) is not int for key in value):
        raise TypeError(f"{name} fraction values must be integers")
    return Fraction(value["numerator"], value["denominator"])


def _gate_algorithm_from_payload(payload: object) -> GateAlgorithm:
    if type(payload) is not dict:
        raise TypeError("gate algorithm payload must be an object")
    base = {field.name for field in fields(GateAlgorithm)}
    derived = {
        "implementation",
        "inventory_policy",
        "challenge_coverage",
        "aggregation",
        "pair_strata",
        "contradiction_labels",
    }
    if set(payload) != base | derived or type(payload["challenges"]) is not list:
        raise ValueError("gate algorithm payload fields do not match its exact contract")
    challenges = []
    for item in payload["challenges"]:
        if type(item) is not dict or set(item) != {field.name for field in fields(PairChallenge)}:
            raise ValueError("pair challenge payload fields do not match its contract")
        challenges.append(PairChallenge(**item))
    algorithm = GateAlgorithm(
        algorithm_id=payload["algorithm_id"],
        algorithm_version=payload["algorithm_version"],
        min_parse=_fraction(payload["min_parse"], "min_parse"),
        max_refusal=_fraction(payload["max_refusal"], "max_refusal"),
        min_main_categories=payload["min_main_categories"],
        max_main_endpoint=_fraction(payload["max_main_endpoint"], "max_main_endpoint"),
        max_abs_dz=_fraction(payload["max_abs_dz"], "max_abs_dz"),
        max_contradiction=_fraction(payload["max_contradiction"], "max_contradiction"),
        tv_threshold=_fraction(payload["tv_threshold"], "tv_threshold"),
        minimum_distribution_n=payload["minimum_distribution_n"],
        classifier_id=payload["classifier_id"],
        classifier_version=payload["classifier_version"],
        classifier_hash=payload["classifier_hash"],
        challenges=tuple(challenges),
    )  # type: ignore[arg-type]
    if algorithm.to_payload() != payload:
        raise ValueError("gate algorithm payload differs from canonical reconstruction")
    return algorithm


def _selection_from_payload(payload: object) -> TopicSelection:
    expected = {
        "status",
        "primary",
        "robustness",
        "report_hashes",
        "formal_parameter_authority",
        "calibration_only",
        "research_parameter_status",
    }
    if (
        type(payload) is not dict
        or set(payload) != expected
        or type(payload["report_hashes"]) is not list
    ):
        raise ValueError("topic selection payload fields do not match the contract")
    if (
        payload["formal_parameter_authority"] is not False
        or payload["calibration_only"] is not True
        or payload["research_parameter_status"] != "not_frozen"
    ):
        raise ValueError("topic selection claims invalid authority")
    return TopicSelection(
        payload["status"],
        payload["primary"],
        payload["robustness"],
        tuple(payload["report_hashes"]),
    )  # type: ignore[arg-type]


def _normalize_request_payload(payload: object) -> object:
    """Restore semantic field order where older in-memory records encode it explicitly."""
    if type(payload) is not dict:
        return payload
    value = deepcopy(payload)
    messages = value.get("rendered_messages")
    if type(messages) is list:
        value["rendered_messages"] = [
            {"role": item["role"], "content": item["content"]}
            if type(item) is dict and set(item) == {"role", "content"}
            else item
            for item in messages
        ]
    return value


def _normalize_case_payload(payload: object) -> object:
    if type(payload) is not dict:
        return payload
    value = deepcopy(payload)
    messages = value.get("rendered_messages")
    if type(messages) is list:
        value["rendered_messages"] = [
            {"role": item["role"], "content": item["content"]}
            if type(item) is dict and set(item) == {"role", "content"}
            else item
            for item in messages
        ]
    return value


def _normalize_response_payload(payload: object) -> object:
    if type(payload) is not dict:
        return payload
    value = deepcopy(payload)
    tokenizer = value.get("tokenizer_identity")
    if type(tokenizer) is dict and set(tokenizer) == {"tokenizer", "revision"}:
        value["tokenizer_identity"] = {
            "tokenizer": tokenizer["tokenizer"],
            "revision": tokenizer["revision"],
        }
    return value


def _normalize_projection_payload(payload: object) -> object:
    if type(payload) is not dict:
        return payload
    value = deepcopy(payload)
    tokenizer = value.get("tokenizer_identity")
    if type(tokenizer) is dict and set(tokenizer) == {"tokenizer", "revision"}:
        value["tokenizer_identity"] = {
            "tokenizer": tokenizer["tokenizer"],
            "revision": tokenizer["revision"],
        }
    attempts = value.get("attempts")
    if type(attempts) is list:
        for attempt in attempts:
            if type(attempt) is dict:
                attempt["request"] = _normalize_request_payload(attempt.get("request"))
                attempt["response"] = _normalize_response_payload(attempt.get("response"))
    return value


def _content_payloads(report: ProbeReport) -> dict[str, object]:
    source = report.source
    requests = tuple(attempt.request for attempt in source.projection.attempts)
    responses = tuple(attempt.response for attempt in source.projection.attempts)
    result: dict[str, object] = {
        "specification.json": source.specification.to_payload(),
        "case-inventory.json": _with_hash(
            _SCHEMAS["case_inventory"],
            {
                "specification_hash": report.specification_hash,
                "case_inventory_hash": report.case_inventory_hash,
                "cases": tuple(case.to_payload() for case in source.cases),
            },
        ),
        "requests.json": _with_hash(
            _SCHEMAS["requests"],
            {
                "probe_run_id": source.projection.probe_run_id,
                "requests": tuple(request.to_payload() for request in requests),
            },
        ),
        "raw-responses.json": _with_hash(
            _SCHEMAS["raw"],
            {
                "probe_run_id": source.projection.probe_run_id,
                "projection": source.projection.to_payload(),
                "responses": tuple(response.to_payload() for response in responses),
            },
        ),
        "parse-evidence.json": _with_hash(
            _SCHEMAS["parse"],
            {
                "probe_run_id": source.projection.probe_run_id,
                "parse_evidence": tuple(item.to_payload() for item in source.parse_evidence),
            },
        ),
        "machine-metrics.json": _with_hash(
            _SCHEMAS["metrics"],
            {
                "gate_algorithm": source.gate_algorithm.to_payload(),
                "semantic_gate_evidence": tuple(
                    item.to_payload() for item in source.semantic_gate_evidence
                ),
                "gate_reports": tuple(item.to_payload() for item in source.gate_reports),
            },
        ),
        "blind-review-export.json": source.semantic_review.review_export.to_payload(),
        "blind-review-import.json": source.semantic_review.to_payload(),
        "gate-report.json": report.to_payload(),
        "freeze-proposal.json": report.freeze_proposal.to_payload(),
    }
    for payload in result.values():
        _reject_forbidden(payload)
    return result


def _manifest(
    report: ProbeReport,
    content_payloads: Mapping[str, object],
    *,
    manifest_algorithms: Mapping[str, str],
    external_archive_locator: str,
) -> dict[str, object]:
    if type(manifest_algorithms) is not dict or not manifest_algorithms:
        raise ValueError("manifest_algorithms must be an explicit non-empty JSON object")
    if tuple(manifest_algorithms) != tuple(sorted(manifest_algorithms)):
        manifest_algorithms = dict(sorted(manifest_algorithms.items()))
    for name, version in manifest_algorithms.items():
        _require_id("manifest algorithm", name)
        _require_id("manifest algorithm version", version)
    _reject_forbidden(manifest_algorithms, free_form=True)
    _require_evidence_uri("external_archive_locator", external_archive_locator)
    source = report.source
    file_hashes = {
        name: canonical_payload_hash(content_payloads[name])
        for name in PROBE_BUNDLE_FILES
        if name != "manifest.json"
    }
    values = {
        "schema_version": _SCHEMAS["manifest"],
        "probe_run_id": source.projection.probe_run_id,
        "run_instance_id": source.projection.run_instance_id,
        "status": report.status,
        "specification_hash": report.specification_hash,
        "case_inventory_hash": report.case_inventory_hash,
        "report_projection_hash": report.report_projection_hash,
        "run_evidence_hash": report.run_evidence_hash,
        "inventory_counts": {
            "cases": len(source.cases),
            "attempts": len(source.projection.attempts),
            "requests": len(source.projection.attempts),
            "responses": len(source.projection.attempts),
            "parse_evidence": len(source.parse_evidence),
            "review_items": len(source.semantic_review.review_export.items),
            "independent_codes": len(source.semantic_review.independent_codes),
            "adjudications": len(source.semantic_review.adjudications),
            "gate_reports": len(source.gate_reports),
        },
        "algorithms": dict(manifest_algorithms),
        "external_archive_locator": external_archive_locator,
        "file_hashes": file_hashes,
        "metadata": _metadata(),
    }
    _reject_forbidden(values, free_form=False)
    return {**values, "manifest_hash": canonical_payload_hash(values)}


@dataclass(frozen=True, slots=True)
class ProbeBundle:
    report: ProbeReport
    payloads: Mapping[str, object]

    def __post_init__(self) -> None:
        if type(self.report) is not ProbeReport:
            raise TypeError("probe bundle requires a ProbeReport")
        if not isinstance(self.payloads, Mapping) or set(self.payloads) != set(PROBE_BUNDLE_FILES):
            raise ValueError("probe bundle file inventory is incomplete or contains extras")
        object.__setattr__(self, "payloads", _freeze(self.payloads))

    @property
    def specification_hash(self) -> str:
        return self.report.specification_hash

    @property
    def case_inventory_hash(self) -> str:
        return self.report.case_inventory_hash

    @property
    def report_projection_hash(self) -> str:
        return self.report.report_projection_hash

    @property
    def run_evidence_hash(self) -> str:
        return self.report.run_evidence_hash

    def payload_for(self, name: str) -> object:
        if type(name) is not str or name not in PROBE_BUNDLE_FILES:
            raise ValueError("unknown probe bundle filename")
        return _json_ready(self.payloads[name])

    def to_payloads(self) -> dict[str, object]:
        return {name: self.payload_for(name) for name in PROBE_BUNDLE_FILES}

    @classmethod
    def from_payloads(cls, payloads: Mapping[str, object]) -> ProbeBundle:
        if type(payloads) is not dict or set(payloads) != set(PROBE_BUNDLE_FILES):
            raise ValueError("probe bundle file inventory is incomplete or contains extras")
        for payload in payloads.values():
            _require_json_transport(payload, "probe bundle file payload")
            _reject_forbidden(payload)
        manifest = payloads["manifest.json"]
        manifest_fields = {
            "schema_version",
            "probe_run_id",
            "run_instance_id",
            "status",
            "specification_hash",
            "case_inventory_hash",
            "report_projection_hash",
            "run_evidence_hash",
            "inventory_counts",
            "algorithms",
            "external_archive_locator",
            "file_hashes",
            "metadata",
            "manifest_hash",
        }
        if type(manifest) is not dict or set(manifest) != manifest_fields:
            raise ValueError("manifest payload fields do not match the exact contract")
        if manifest["schema_version"] != _SCHEMAS["manifest"]:
            raise ValueError("manifest schema or metadata is invalid")
        _require_exact_metadata(manifest["metadata"])
        manifest_content = {key: value for key, value in manifest.items() if key != "manifest_hash"}
        if manifest["manifest_hash"] != canonical_payload_hash(manifest_content):
            raise ValueError("manifest hash drift")
        if type(manifest["file_hashes"]) is not dict or set(manifest["file_hashes"]) != set(
            PROBE_BUNDLE_FILES
        ) - {"manifest.json"}:
            raise ValueError("manifest file hash inventory is incomplete")
        for name, digest in manifest["file_hashes"].items():
            _require_sha256("manifest file hash", digest)
            if digest != canonical_payload_hash(payloads[name]):
                raise ValueError(f"bundle file hash drift: {name}")
        specification_payload = payloads["specification.json"]
        envelope = ArtifactEnvelope.from_payload(specification_payload)  # type: ignore[arg-type]
        specification = load_probe_specification(envelope.to_payload()["payload"])
        if specification.to_payload() != envelope.to_payload():
            raise ValueError("specification file differs from strict canonical reconstruction")
        inventory = _validate_wrapper(
            payloads["case-inventory.json"],
            schema=_SCHEMAS["case_inventory"],
            fields_={"specification_hash", "case_inventory_hash", "cases"},
        )
        if type(inventory["cases"]) is not list:
            raise TypeError("case inventory cases must use a JSON array")
        cases = tuple(
            ProbeCase.from_payload(_normalize_case_payload(item))  # type: ignore[arg-type]
            for item in inventory["cases"]
        )
        raw = _validate_wrapper(
            payloads["raw-responses.json"],
            schema=_SCHEMAS["raw"],
            fields_={"probe_run_id", "projection", "responses"},
        )
        projection = ProbeRunProjection.from_payload(  # type: ignore[arg-type]
            _normalize_projection_payload(raw["projection"])
        )
        if type(raw["responses"]) is not list:
            raise TypeError("raw responses must use a JSON array")
        responses = tuple(
            ProbeResponse.from_payload(_normalize_response_payload(item))  # type: ignore[arg-type]
            for item in raw["responses"]
        )
        requests_payload = _validate_wrapper(
            payloads["requests.json"],
            schema=_SCHEMAS["requests"],
            fields_={"probe_run_id", "requests"},
        )
        if type(requests_payload["requests"]) is not list:
            raise TypeError("requests must use a JSON array")
        requests = tuple(
            ProbeRequest.from_payload(_normalize_request_payload(item))  # type: ignore[arg-type]
            for item in requests_payload["requests"]
        )
        expected_requests = tuple(attempt.request for attempt in projection.attempts)
        expected_responses = tuple(attempt.response for attempt in projection.attempts)
        if requests != expected_requests or responses != expected_responses:
            raise ValueError("request/response cross-file identity or hash drift")
        parse_payload = _validate_wrapper(
            payloads["parse-evidence.json"],
            schema=_SCHEMAS["parse"],
            fields_={"probe_run_id", "parse_evidence"},
        )
        if type(parse_payload["parse_evidence"]) is not list:
            raise TypeError("parse evidence must use a JSON array")
        parses = tuple(
            ProbeParseEvidence.from_payload(item) for item in parse_payload["parse_evidence"]
        )
        review = SemanticReviewBundle.from_payload(payloads["blind-review-import.json"])  # type: ignore[arg-type]
        review_export = BlindReviewExport.from_payload(payloads["blind-review-export.json"])  # type: ignore[arg-type]
        if review_export.to_payload() != review.review_export.to_payload():
            raise ValueError("blind review export/import cross-file hash drift")
        metrics = _validate_wrapper(
            payloads["machine-metrics.json"],
            schema=_SCHEMAS["metrics"],
            fields_={"gate_algorithm", "semantic_gate_evidence", "gate_reports"},
        )
        algorithm = _gate_algorithm_from_payload(metrics["gate_algorithm"])
        if (
            type(metrics["semantic_gate_evidence"]) is not list
            or type(metrics["gate_reports"]) is not list
        ):
            raise TypeError("machine metric repeated fields must use JSON arrays")
        bridge = tuple(
            SemanticGateEvidence(**item)  # type: ignore[arg-type]
            for item in metrics["semantic_gate_evidence"]
        )
        report_payload = payloads["gate-report.json"]
        if type(report_payload) is not dict:
            raise TypeError("gate report file must contain a JSON object")
        selection = _selection_from_payload(report_payload.get("topic_selection"))
        proposal = FreezeProposal.from_payload(payloads["freeze-proposal.json"])  # type: ignore[arg-type]
        if report_payload.get("freeze_proposal") != proposal.to_payload():
            raise ValueError("freeze proposal cross-file hash drift")
        artifacts = tuple(
            ProposalArtifact.from_payload(item.to_payload())
            for item in proposal.supporting_artifacts
        )
        # Rebuild reports from the GateReport source requirements through build_probe_report.
        # The public evaluator, rather than serialized pass/fail booleans, is authoritative.
        from .gates import evaluate_quality_gates

        expected_reports = tuple(
            evaluate_quality_gates(
                specification,
                cases,
                projection,
                algorithm,
                bridge,
                candidate_key=key,
            )
            for key in ("retirement-delay", "gm-soybean-oil", "ai-net-employment")
        )
        if canonical_payload_hash(
            tuple(item.to_payload() for item in expected_reports)
        ) != canonical_payload_hash(metrics["gate_reports"]):
            raise ValueError("machine gate report differs from deterministic replay")
        rebuilt_report = build_probe_report(
            specification=specification,
            cases=cases,
            projection=projection,
            parse_evidence=parses,
            semantic_review=review,
            semantic_gate_evidence=bridge,
            gate_algorithm=algorithm,
            gate_reports=expected_reports,
            topic_selection=selection,
            proposed_values=proposal.proposed_values,
            proposal_artifacts=artifacts,
            unresolved_decision_ids=proposal.unresolved_decision_ids,
        )
        if rebuilt_report.to_payload() != report_payload:
            raise ValueError("report payload differs from full upstream replay")
        rebuilt = build_probe_bundle(
            rebuilt_report,
            manifest_algorithms=manifest["algorithms"],  # type: ignore[arg-type]
            external_archive_locator=manifest["external_archive_locator"],  # type: ignore[arg-type]
        )
        if rebuilt.to_payloads() != payloads:
            raise ValueError("probe bundle payloads differ from canonical reconstruction")
        counts = manifest["inventory_counts"]
        if (
            type(counts) is not dict
            or counts != rebuilt.payload_for("manifest.json")["inventory_counts"]
        ):  # type: ignore[index]
            raise ValueError("manifest inventory counts differ from reconstructed evidence")
        return rebuilt


def build_probe_bundle(
    report: ProbeReport,
    *,
    manifest_algorithms: Mapping[str, str],
    external_archive_locator: str,
) -> ProbeBundle:
    if type(report) is not ProbeReport:
        raise TypeError("build_probe_bundle requires a ProbeReport")
    contents = _content_payloads(report)
    manifest = _manifest(
        report,
        contents,
        manifest_algorithms=dict(sorted(manifest_algorithms.items())),
        external_archive_locator=external_archive_locator,
    )
    payloads = {"manifest.json": manifest, **contents}
    return ProbeBundle(report, payloads)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"forbidden JSON constant: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _check_depth(value: object, depth: int = 0) -> None:
    if depth > _MAX_JSON_DEPTH:
        raise ValueError("JSON payload exceeds maximum nesting depth")
    if isinstance(value, Mapping):
        for item in value.values():
            _check_depth(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _check_depth(item, depth + 1)


def _write_json_file(path: Path, payload: object) -> None:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    with path.open("xb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def write_probe_bundle_atomic(target: Path, bundle: ProbeBundle) -> None:
    """Write exactly one new bundle directory; never overwrite or select latest."""
    if not isinstance(target, Path) or type(bundle) is not ProbeBundle:
        raise TypeError("atomic bundle write requires an explicit Path and ProbeBundle")
    if target.exists() or target.is_symlink():
        raise FileExistsError(target)
    parent = target.parent
    if not parent.is_dir():
        raise FileNotFoundError("probe bundle parent directory must already exist")
    staging = target.with_name(target.name + ".partial")
    if staging.exists() or staging.is_symlink():
        raise FileExistsError(staging)
    staging.mkdir(parents=False, exist_ok=False)
    created = True
    try:
        for name in PROBE_BUNDLE_FILES:
            _write_json_file(staging / name, bundle.payload_for(name))
        _fsync_directory(staging)
        os.replace(staging, target)
        created = False
        _fsync_directory(parent)
    except BaseException:
        if created and staging.exists() and staging.is_dir() and not staging.is_symlink():
            shutil.rmtree(staging, ignore_errors=True)
        raise


def load_probe_bundle(target: Path) -> ProbeBundle:
    if not isinstance(target, Path) or not target.is_dir() or target.is_symlink():
        raise ValueError("probe bundle target must be an existing regular directory")
    entries = tuple(target.iterdir())
    if {entry.name for entry in entries} != set(PROBE_BUNDLE_FILES):
        raise ValueError("probe bundle file inventory is incomplete or contains extras")
    if any(not entry.is_file() or entry.is_symlink() for entry in entries):
        raise ValueError("probe bundle entries must be regular files without symlinks")
    payloads: dict[str, object] = {}
    for name in PROBE_BUNDLE_FILES:
        path = target / name
        size = path.stat().st_size
        if size > _MAX_FILE_BYTES:
            raise ValueError("probe bundle file exceeds maximum size")
        try:
            payload = json.loads(
                path.read_text(encoding="utf-8"),
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_json_constant,
            )
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ValueError(f"invalid JSON bundle file: {name}") from error
        _check_depth(payload)
        payloads[name] = payload
    return ProbeBundle.from_payloads(payloads)


__all__ = [
    "PROBE_BUNDLE_FILES",
    "ProbeBundle",
    "build_probe_bundle",
    "load_probe_bundle",
    "write_probe_bundle_atomic",
]
