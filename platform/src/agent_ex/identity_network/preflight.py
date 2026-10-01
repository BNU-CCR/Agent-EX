"""Compose stage-one approval/source/checkout/live checks without dispatch.

Fresh procfs and HTTP observations are required, never supplied cached reports.
This is not a lease, runner, or proof of already-loaded Python module identity.
"""

from pathlib import Path
import re

from ..artifacts import ArtifactEnvelope
from ..domain import _require_timestamp
from .manipulation_authorization import validate_manipulation_dispatch_approval
from .service_health import observe_service_health
from .service_live import _utcnow
from .source_bundle import _git
from .source_cli import verify_approved_bundle


def observe_runtime_checkout(repo, *, expected_commit):
    """Read exact clean worktree HEAD/tree; ignored files and loaded code excluded."""
    if type(expected_commit) is not str or re.fullmatch(r"[0-9a-f]{40}", expected_commit) is None:
        raise ValueError("exact SHA1 source commit required")
    root = Path(repo).resolve(strict=True)
    top = Path(_git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve(strict=True)
    if root != top:
        raise ValueError("exact runtime checkout root required")
    tracked = _git(root, "ls-files", "-v", "-z").split(b"\0")
    if any(line and (line[:1] == b"S" or line[:1].islower()) for line in tracked):
        raise ValueError("runtime index may hide tracked changes")
    commit = _git(root, "rev-parse", "HEAD").decode().strip()
    if commit != expected_commit or _git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("runtime source is not the approved clean commit")
    tree = _git(root, "rev-parse", "HEAD^{tree}").decode().strip()
    return ArtifactEnvelope.create(
        artifact_type="sis-runtime-checkout-observation",
        schema_version="paper1.identity-network.runtime-checkout.v1",
        algorithm_id="sis-readonly-clean-git-checkout",
        algorithm_version="1.0.0",
        input_hashes={},
        rng_provenance=(),
        payload={
            "source_commit": commit,
            "source_tree": tree,
            "git_dirty": False,
            "dispatch_authorized": False,
            "formal_parameter_authority": False,
        },
    )


def preflight_manipulation(*, auth, receipt, evidence, bundle_path, runtime_repo):
    """Fully replay v1 stage-one gate once, then bind actual local observations.

    No automatic restart, retry, completion, or output-directory creation occurs.
    The calling runner still owns execution-origin, fresh archive and durable
    intent checks and must recheck identity immediately before actual transport.
    """
    checked_at = _utcnow()
    validate_manipulation_dispatch_approval(auth, receipt, checked_at=checked_at, **evidence)
    service = evidence["service_evidence"]
    source = verify_approved_bundle(
        request={
            "candidate": evidence["candidate"].to_payload(),
            "intent": service["intent"].to_payload(),
            "approval": service["approval"].to_payload(),
        },
        bundle_path=bundle_path,
        prerequisite_repo=runtime_repo,
    )
    commit = service["intent"].payload["source_commit"]
    before = observe_runtime_checkout(runtime_repo, expected_commit=commit)
    if before.payload["source_tree"] != source.payload["source_tree"]:
        raise ValueError("runtime tree differs from approved source bundle")
    health = observe_service_health(
        service["new_start"], expected_host_identity_hash=service["current_host_identity_hash"]
    )
    after = observe_runtime_checkout(runtime_repo, expected_commit=commit)
    if before != after:
        raise ValueError("runtime checkout changed during preflight")
    if not (
        _require_timestamp("checked_at", checked_at)
        <= _require_timestamp("health before", health.payload["before_observed_at"])
        <= _require_timestamp("health after", health.payload["observed_at"])
    ):
        raise ValueError("fresh preflight chronology is inconsistent")
    return ArtifactEnvelope.create(
        artifact_type="sis-manipulation-preflight-observation",
        schema_version="paper1.identity-network.manipulation-preflight.v1",
        algorithm_id="sis-approved-source-bridge-checkout-live-preflight",
        algorithm_version="1.0.0",
        input_hashes={
            "authorization": auth.output_hash,
            "receipt": receipt.record_hash,
            "source": source.output_hash,
            "runtime": after.output_hash,
            "health": health.output_hash,
            "bridge": evidence["bridge"].output_hash,
        },
        rng_provenance=(),
        payload={
            "checked_at": checked_at,
            "observed_at": health.payload["observed_at"],
            "trial_count": auth.payload["trial_count"],
            "stage": "pure_label",
            "source_commit": commit,
            "dispatch_authorized": False,
            "formal_parameter_authority": False,
            "status": "preliminary",
        },
    )
