"""SIS pre-service intent and scoped human approval attribution.

These pure contracts never start services or send requests. Receipt hashes bind
content, not signatures: the caller must obtain attribution from trusted human
approval evidence, rather than inventing an approval by calling create().
"""

from dataclasses import dataclass, fields
import hashlib
from pathlib import PurePosixPath
import re

from ..artifacts import ArtifactEnvelope
from ..domain import (
    _require_int,
    _require_sha256,
    _require_string,
    _require_timestamp,
    canonical_payload_hash,
)
from .materialization import _reject_unresolved
from .service_inputs import project_pre_service_inputs


SERVICE_CONFIG_FIELDS = {
    "serve_script",
    "control_python",
    "executable",
    "model_path",
    "cmdline_sha256",
}
INTENT_SCHEMA = "paper1.identity-network.service-launch-intent.v1"


def _posix_path(name, value):
    _require_string(name, value)
    if (
        "\\" in value
        or "%" in value
        or value != value.strip()
        or not value.startswith("/")
        or value == "/"
        or str(PurePosixPath(value)) != value
        or ".." in PurePosixPath(value).parts
    ):
        raise ValueError(f"{name} requires a canonical absolute POSIX path")


def build_service_launch_intent(
    *, packet, source_commit, source_bundle_hash, source_bundle_size, service_config, archive_root
):
    """Bind approved fixed inputs and executable configuration before start."""
    fixed = project_pre_service_inputs(packet)
    if type(source_commit) is not str or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        raise ValueError("exact source commit required")
    _require_sha256("source_bundle_hash", source_bundle_hash)
    _require_int("source_bundle_size", source_bundle_size, minimum=1)
    if type(service_config) is not dict or set(service_config) != SERVICE_CONFIG_FIELDS:
        raise ValueError("exact service configuration required")
    _reject_unresolved((service_config, archive_root))
    for name in SERVICE_CONFIG_FIELDS - {"cmdline_sha256"}:
        _posix_path(name, service_config[name])
    _require_sha256("cmdline_sha256", service_config["cmdline_sha256"])
    _posix_path("archive_root", archive_root)
    base = PurePosixPath("/root/autodl-tmp")
    if not PurePosixPath(archive_root).is_relative_to(base) or PurePosixPath(archive_root) == base:
        raise ValueError("explicit dedicated archive child under /root/autodl-tmp required")
    return ArtifactEnvelope.create(
        artifact_type="sis-service-launch-intent",
        schema_version=INTENT_SCHEMA,
        algorithm_id="sis-pre-service-source-binding",
        algorithm_version="1.0.0",
        input_hashes={
            "fixed_inputs": fixed.output_hash,
            "source_bundle": source_bundle_hash,
            "service_config": canonical_payload_hash(service_config),
        },
        rng_provenance=(),
        payload={
            "fixed_inputs": fixed.to_payload(),
            "fixed_inputs_hash": fixed.output_hash,
            "source_commit": source_commit,
            "source_bundle_hash": source_bundle_hash,
            "source_bundle_size": source_bundle_size,
            "service_config": service_config,
            "archive_root": archive_root,
            "scope": "sis_preliminary_service_start",
            "dispatch_authorized": False,
            "formal_parameter_authority": False,
            "status": "preliminary",
            "research_parameter_status": "not_frozen",
        },
    )


def validate_service_launch_intent(intent, packet):
    if not isinstance(intent, ArtifactEnvelope):
        raise TypeError("typed SIS service launch intent required")
    p = intent.to_payload()["payload"]
    expected = build_service_launch_intent(
        packet=packet,
        source_commit=p["source_commit"],
        source_bundle_hash=p["source_bundle_hash"],
        source_bundle_size=p["source_bundle_size"],
        service_config=p["service_config"],
        archive_root=p["archive_root"],
    )
    if intent != expected:
        raise ValueError("service intent differs from full fixed source replay")


@dataclass(frozen=True, slots=True)
class StudyApprovalReceipt:
    schema_version: str
    target_hash: str
    scope: str
    researcher: str
    approved_at: str
    decision: str
    formal_parameter_authority: bool
    record_hash: str

    def __post_init__(self):
        if self.schema_version != "paper1.identity-network.human-approval.v1":
            raise ValueError("SIS approval schema required")
        _require_sha256("target_hash", self.target_hash)
        if self.scope not in ("service_start", "diagnostic_dispatch"):
            raise ValueError("explicit service-start or diagnostic-dispatch approval required")
        _require_string("researcher", self.researcher)
        _reject_unresolved((self.researcher, self.approved_at))
        _require_timestamp("approved_at", self.approved_at)
        if self.decision != "approve" or self.formal_parameter_authority is not False:
            raise ValueError("receipt must be explicit preliminary approval")
        _require_sha256("record_hash", self.record_hash)
        if self.record_hash != canonical_payload_hash(self.content_payload()):
            raise ValueError("receipt record hash mismatch")

    def content_payload(self):
        return {
            field.name: getattr(self, field.name)
            for field in fields(self)
            if field.name != "record_hash"
        }

    def to_payload(self):
        return {**self.content_payload(), "record_hash": self.record_hash}

    @classmethod
    def create(cls, *, target_hash, scope, researcher, approved_at):
        content = dict(
            schema_version="paper1.identity-network.human-approval.v1",
            target_hash=target_hash,
            scope=scope,
            researcher=researcher,
            approved_at=approved_at,
            decision="approve",
            formal_parameter_authority=False,
        )
        return cls(**content, record_hash=canonical_payload_hash(content))

    @classmethod
    def from_payload(cls, payload):
        if type(payload) is not dict or set(payload) != {field.name for field in fields(cls)}:
            raise ValueError("exact SIS human approval fields required")
        return cls(**payload)


def validate_service_start_approval(intent, receipt, *, packet, actual_source_commit, bundle_bytes):
    """Check source bytes and scoped receipt before any external service action."""
    validate_service_launch_intent(intent, packet)
    if not isinstance(receipt, StudyApprovalReceipt):
        raise TypeError("typed SIS approval receipt required")
    receipt = StudyApprovalReceipt.from_payload(receipt.to_payload())
    if receipt.scope != "service_start" or receipt.target_hash != intent.output_hash:
        raise ValueError("receipt does not approve this exact service start intent")
    p = intent.payload
    if (
        actual_source_commit != p["source_commit"]
        or type(bundle_bytes) is not bytes
        or len(bundle_bytes) != p["source_bundle_size"]
        or hashlib.sha256(bundle_bytes).hexdigest() != p["source_bundle_hash"]
    ):
        raise ValueError("actual source commit/bundle differs from approved intent")
