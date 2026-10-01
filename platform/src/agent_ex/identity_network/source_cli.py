"""Read-only approved-bundle check. Never upload, checkout, launch or dispatch."""

import argparse
import json
import os
import stat
import sys

from ..artifacts import ArtifactEnvelope
from .candidate_cli import _read, _safe_path
from .launch import StudyApprovalReceipt, validate_service_start_approval
from .source_bundle import MAX_BUNDLE_BYTES, verify_source_bundle


def verify_approved_bundle(*, request, bundle_path, prerequisite_repo):
    if type(request) is not dict or set(request) != {"candidate", "intent", "approval"}:
        raise ValueError("exact source verification request fields required")
    candidate = ArtifactEnvelope.from_payload(request["candidate"])
    intent = ArtifactEnvelope.from_payload(request["intent"])
    approval = StudyApprovalReceipt.from_payload(request["approval"])
    path = _safe_path(bundle_path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags), "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BUNDLE_BYTES:
            raise ValueError("bounded regular source bundle required")
        content = source.read(MAX_BUNDLE_BYTES + 1)
    p = intent.payload
    validate_service_start_approval(
        intent,
        approval,
        packet=candidate,
        actual_source_commit=p["source_commit"],
        bundle_bytes=content,
    )
    verified = verify_source_bundle(
        bundle_bytes=content,
        expected_commit=p["source_commit"],
        expected_hash=p["source_bundle_hash"],
        expected_size=p["source_bundle_size"],
        prerequisite_repo=prerequisite_repo,
    )
    return ArtifactEnvelope.create(
        artifact_type="sis-approved-source-bundle-verification",
        schema_version="paper1.identity-network.approved-source-bundle-verification.v1",
        algorithm_id="sis-source-bytes-pack-and-scoped-receipt",
        algorithm_version="1.0.0",
        input_hashes={
            **verified.input_hashes,
            "intent": intent.output_hash,
            "approval": approval.record_hash,
            "candidate": candidate.output_hash,
        },
        rng_provenance=(),
        payload=verified.payload,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("verify")
    check.add_argument("--request", required=True)
    check.add_argument("--bundle", required=True)
    check.add_argument("--prerequisite-repo", required=True)
    args = parser.parse_args(argv)
    try:
        report = verify_approved_bundle(
            request=_read(args.request),
            bundle_path=args.bundle,
            prerequisite_repo=args.prerequisite_repo,
        )
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print("source verification refused: " + type(exc).__name__, file=sys.stderr)
        return 2
    print(json.dumps(report.to_payload(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
