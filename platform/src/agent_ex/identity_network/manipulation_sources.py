"""Explicit source-bound round-zero checks; no sampling, approval or transport.

This is a controlled single-message check, not a network event or a replacement
for a six-cell pilot. Sources remain candidate_unattested until human review.
"""

from typing import Mapping

from ..artifacts import ArtifactEnvelope
from ..domain import _json_ready, _require_int
from ..memory import build_memory_view
from ..state import PrivateUpdate, PublicPost
from .candidate import validate_six_cell_candidate
from .manipulation import (
    CheckCase,
    StageTwoReceipt,
    build_manipulation_pack,
    validate_manipulation_pack,
)
from .prompts import ShownPost, render_study_prompt


def build_source_bound_manipulation_pack(
    *,
    candidate,
    selections,
    stage,
    matched_seed,
    generation_settings,
    stage_two_receipt: StageTwoReceipt | None = None,
):
    """Use explicit receiver/source/seed selections and the shared initial memory.

    No neighbour is inferred: controlled sources are explicitly selected by the
    researcher, not sampled from a treatment graph. All four trials keep the
    receiver's actual persona/initial private history and the same public post.
    """
    binding = validate_six_cell_candidate(candidate)[1]
    if not isinstance(selections, tuple) or not selections:
        raise ValueError("explicit nonempty selections required")
    common = candidate.to_payload()["payload"]["population_candidate"]["payload"][
        "execution_inputs"
    ]["payload"]
    updates = {u["agent_id"]: PrivateUpdate.from_payload(u) for u in common["initial_updates"]}
    cases = []
    for s in selections:
        if not isinstance(s, Mapping) or set(s) != {
            "case_id",
            "receiver_id",
            "source_id",
            "sampling_seed",
        }:
            raise ValueError("selection fields must match explicit source contract")
        if (
            type(s["receiver_id"]) is not str
            or type(s["source_id"]) is not str
            or s["receiver_id"] not in updates
            or s["source_id"] not in updates
            or s["receiver_id"] == s["source_id"]
        ):
            raise ValueError("selection requires distinct bound receiver and source")
        _require_int("sampling_seed", s["sampling_seed"])
        own = updates[s["receiver_id"]]
        post = PublicPost.from_private_update(updates[s["source_id"]], mock_only=True)
        memory = build_memory_view(
            private_updates=(own,),
            topic_package=binding.topic_package,
            matched_seed=binding.matched_seed,
            agent_id=own.agent_id,
            window=common["memory_window"],
            mock_only=True,
        )
        prompt = render_study_prompt(
            cell=binding.cell,
            groups=binding.groups,
            receiver_id=own.agent_id,
            persona_text=common["persona_by_agent"][own.agent_id],
            topic_package=binding.topic_package,
            pre_state={"stance": own.stance_label, "reason": own.reason},
            self_history=tuple(
                {
                    "stance": item.stance_label,
                    "reason": item.private_reason,
                    "published": item.published,
                }
                for item in memory.items
            ),
            posts=(
                ShownPost(
                    post.post_id,
                    post.author_agent_id,
                    binding.aliases[post.author_agent_id],
                    post.stance_label,
                    post.public_reason,
                ),
            ),
        )
        cases.append(CheckCase(s["case_id"], prompt, s["sampling_seed"]))
    pack = build_manipulation_pack(
        cases=tuple(cases),
        stage=stage,
        matched_seed=matched_seed,
        generation_settings=generation_settings,
        stage_two_receipt=stage_two_receipt,
    )
    validate_manipulation_pack(pack, topic_package=binding.topic_package)
    return ArtifactEnvelope.create(
        artifact_type="sis-source-bound-manipulation-pack",
        schema_version="paper1.identity-network.manipulation-sources.v1",
        algorithm_id="sis-explicit-round0-check-sources",
        algorithm_version="1.0.0",
        input_hashes={"candidate": candidate.output_hash, "pack": pack.output_hash},
        rng_provenance=(),
        payload={
            "candidate": candidate.to_payload(),
            "selections": tuple(dict(s) for s in sorted(selections, key=lambda s: s["case_id"])),
            "history_mode": "shared_memory_round0",
            "source_mode": "explicit_controlled_single_round0_post",
            "pack": pack.to_payload(),
            "metadata": {
                "status": "preliminary",
                "research_parameter_status": "not_frozen",
                "formal_parameter_authority": False,
                "dispatch_authorized": False,
                "source_authority": "candidate_unattested",
            },
        },
    )


def validate_source_bound_manipulation_pack(artifact, *, candidate):
    """Replay all sources against the independently supplied candidate; return pack."""
    try:
        if not isinstance(artifact, ArtifactEnvelope):
            raise ValueError("typed source-bound pack required")
        p = _json_ready(artifact.payload)
        if set(p) != {"candidate", "selections", "history_mode", "source_mode", "pack", "metadata"}:
            raise ValueError("source wrapper fields drift")
        source = ArtifactEnvelope.from_payload(p["candidate"])
        if source != candidate:
            raise ValueError("candidate source differs")
        binding = validate_six_cell_candidate(candidate)[1]
        pack = ArtifactEnvelope.from_payload(p["pack"])
        validate_manipulation_pack(pack, topic_package=binding.topic_package)
        receipt = pack.payload["stage_two_receipt"]
        rebuilt = build_source_bound_manipulation_pack(
            candidate=candidate,
            selections=tuple(p["selections"]),
            stage=pack.payload["stage"],
            matched_seed=pack.rng_provenance[0].matched_seed,
            generation_settings=pack.payload["generation_settings"],
            stage_two_receipt=StageTwoReceipt(**dict(receipt)) if receipt is not None else None,
        )
        if rebuilt != artifact:
            raise ValueError("source-bound derivation drift")
        return pack
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise ValueError("source-bound manipulation validation failed") from exc
