"""Offline benchmark trial identities; not model requests or dispatch authority."""

import re

from ..artifacts import ArtifactEnvelope
from ..domain import canonical_payload_hash
from .benchmark import validate_frozen_benchmark

NAMESPACE = "sis-mc-stage-a-v1"
SEED_RECIPE = "canonical-json-sha256-first-u32-big-endian-mask31-v1"
VARIANTS = ("BB", "BG", "GG", "GB")
GROUPS = {"B": "Blue", "G": "Green"}


def derive_generation_seed(case_id, repeat_id):
    """Fixed hash recipe, no random fallback and no stimulus-dependent seed search."""
    if (
        not isinstance(case_id, str)
        or re.fullmatch(r"MC-D[123]-[UD]-0[1-5]", case_id) is None
        or type(repeat_id) is not int
        or repeat_id not in (1, 2)
    ):
        raise ValueError("invalid seed case/repeat identity")
    digest = canonical_payload_hash(
        {
            "namespace": NAMESPACE,
            "case_id": case_id,
            "repeat_id": repeat_id,
        }
    )
    return int(digest[:8], 16) & 0x7FFFFFFF


def build_benchmark_trial_inventory(benchmark, *, expected_hash, stage="pure_label"):
    """Pure, content-bound materialization; no renderer, model, endpoint or HTTP."""
    validate_frozen_benchmark(benchmark, expected_hash=expected_hash)
    if stage not in {"pure_label", "stable_group"}:
        raise ValueError("only frozen Stage-A/Stage-B inventories allowed")
    cases, trials = [], []
    seed_keys = set()
    for case in benchmark["cases"]:
        fixed = {
            **case,
            "topic": benchmark["topic"],
            "focal_context": benchmark["focal_context"],
            "persona_context": benchmark["persona_context"],
            "self_history": benchmark["self_history"],
            "pre_confidence": benchmark["pre_confidence"],
            "source_id": case["case_id"],
        }
        content_hash = canonical_payload_hash(fixed)
        cases.append(
            {
                "case_id": case["case_id"],
                "fixed_content": fixed,
                "fixed_content_hash": content_hash,
            }
        )
        for repeat in (1, 2):
            seed = derive_generation_seed(case["case_id"], repeat)
            if seed in seed_keys:
                raise ValueError("generation seed collision; no automatic reseeding")
            seed_keys.add(seed)
            for variant in VARIANTS:
                identity = {
                    "stage": stage,
                    "benchmark_hash": expected_hash,
                    "case_id": case["case_id"],
                    "repeat_id": repeat,
                    "variant": variant,
                }
                trials.append(
                    {
                        "trial_id": "mc-trial-" + canonical_payload_hash(identity),
                        "case_id": case["case_id"],
                        "repeat_id": repeat,
                        "variant": variant,
                        "focal_group": GROUPS[variant[0]],
                        "source_group": GROUPS[variant[1]],
                        "source_id": case["case_id"],
                        "sampling_seed": seed,
                        "fixed_content_hash": content_hash,
                    }
                )
    return ArtifactEnvelope.create(
        artifact_type="sis-benchmark-trial-inventory",
        schema_version="sis.manipulation.benchmark-trials.v1",
        algorithm_id="sis-offline-benchmark-trials",
        algorithm_version="1.0.0",
        input_hashes={"benchmark": expected_hash},
        rng_provenance=(),
        payload={
            "stage": stage,
            "trial_count": 240,
            "cases": cases,
            "trials": trials,
            "seed_recipe": {"namespace": NAMESPACE, "algorithm": SEED_RECIPE},
            "order": "case-order-repeat-1-2-variants-BB-BG-GG-GB",
            "inventory_kind": "offline-trial-identities-not-rendered-requests",
            "dispatch_authorized": False,
            "cloud_launch_eligible": False,
            "formal_parameter_authority": False,
        },
    )


def replay_benchmark_trial_inventory(inventory, benchmark, *, expected_hash):
    """Cold recomputation rejects drift even if the attacker rehashes an envelope."""
    if not isinstance(inventory, ArtifactEnvelope):
        raise ValueError("benchmark trial inventory required")
    rebuilt = build_benchmark_trial_inventory(
        benchmark, expected_hash=expected_hash, stage=inventory.payload["stage"]
    )
    if inventory != rebuilt:
        raise ValueError("benchmark trial inventory replay mismatch")
    return rebuilt
