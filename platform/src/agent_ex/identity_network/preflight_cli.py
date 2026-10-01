"""Portable full-evidence stage-one preflight; never launch or send completions."""

import argparse
import json
import sys

from ..artifacts import ArtifactEnvelope
from ..calibration.environment import EnvironmentLock, PreliminaryEnvironmentInspection
from .candidate_cli import _read
from .launch import StudyApprovalReceipt
from .preflight import preflight_manipulation


SCHEMA = "paper1.identity-network.manipulation-preflight-request.v1"
_ARTIFACTS = {"candidate", "source_pack", "preregistration", "bridge"}
_SERVICE_FIELDS = {
    "intent",
    "approval",
    "environment_lock",
    "current_environment",
    "inspection",
    "vacancy",
    "new_start",
    "current_host_identity_hash",
    "observed_at",
}


def _exact(value, fields):
    if type(value) is not dict or set(value) != fields:
        raise ValueError("exact preflight request fields required")


def build_preflight_request(*, auth, receipt, evidence):
    """Serialize supplied evidence; creates neither human approval nor observations."""
    _exact(evidence, _ARTIFACTS | {"service_evidence"})
    e = evidence["service_evidence"]
    _exact(e, (_SERVICE_FIELDS - {"current_environment"}) | {"packet", "current_observation"})
    if e["packet"] != evidence["candidate"]:
        raise ValueError("candidate and service evidence differ")
    current = EnvironmentLock.create(
        e["current_observation"], authorization_hash=e["intent"].output_hash
    )
    serialized = {k: evidence[k].to_payload() for k in _ARTIFACTS}
    serialized["service_evidence"] = {
        **{
            k: e[k].to_payload()
            for k in ("intent", "approval", "environment_lock", "inspection", "vacancy")
        },
        "current_environment": current.to_payload(),
        **{k: e[k] for k in ("new_start", "current_host_identity_hash", "observed_at")},
    }
    return {
        "schema_version": SCHEMA,
        "authorization": auth.to_payload(),
        "receipt": receipt.to_payload(),
        "evidence": serialized,
    }


def parse_preflight_request(request):
    """Reconstruct typed evidence; preflight still replays all source derivations."""
    _exact(request, {"schema_version", "authorization", "receipt", "evidence"})
    if request["schema_version"] != SCHEMA:
        raise ValueError("unsupported preflight request schema")
    raw = request["evidence"]
    _exact(raw, _ARTIFACTS | {"service_evidence"})
    service = raw["service_evidence"]
    _exact(service, _SERVICE_FIELDS)
    evidence = {k: ArtifactEnvelope.from_payload(raw[k]) for k in _ARTIFACTS}
    intent = ArtifactEnvelope.from_payload(service["intent"])
    current = EnvironmentLock.from_payload(service["current_environment"])
    if current.authorization_hash != intent.output_hash:
        raise ValueError("current environment belongs to another service intent")
    evidence["service_evidence"] = {
        "packet": evidence["candidate"],
        "intent": intent,
        "approval": StudyApprovalReceipt.from_payload(service["approval"]),
        "environment_lock": EnvironmentLock.from_payload(service["environment_lock"]),
        # Reuse the lock's validated observation projection without changing legacy schema.
        "current_observation": current._observation(),
        "inspection": PreliminaryEnvironmentInspection.from_payload(service["inspection"]),
        "vacancy": ArtifactEnvelope.from_payload(service["vacancy"]),
        **{k: service[k] for k in ("new_start", "current_host_identity_hash", "observed_at")},
    }
    return {
        "auth": ArtifactEnvelope.from_payload(request["authorization"]),
        "receipt": StudyApprovalReceipt.from_payload(request["receipt"]),
        "evidence": evidence,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--runtime-repo", required=True)
    args = parser.parse_args(argv)
    try:
        report = preflight_manipulation(
            **parse_preflight_request(_read(args.request)),
            bundle_path=args.bundle,
            runtime_repo=args.runtime_repo,
        )
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print("Manipulation preflight refused: " + type(exc).__name__, file=sys.stderr)
        return 2
    print(json.dumps(report.to_payload(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
