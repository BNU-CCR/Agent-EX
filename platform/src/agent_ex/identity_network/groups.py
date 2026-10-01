"""Exactly balanced neutral memberships, validated once outside event loops."""

from collections import defaultdict
from dataclasses import dataclass
import random
from types import MappingProxyType
from typing import Mapping

from ..artifacts import ArtifactEnvelope
from ..domain import _require_int, canonical_payload_hash
from ..rng import RNGProvenance


def build_group_assignment(
    *, initial_stances: Mapping[str, int], matched_seed: int
) -> ArtifactEnvelope:
    _require_int("matched_seed", matched_seed)
    if not isinstance(initial_stances, Mapping) or not initial_stances:
        raise ValueError("a nonempty initial stance mapping is required")
    strata = defaultdict(list)
    for agent, stance in initial_stances.items():
        if not isinstance(agent, str) or not agent.strip():
            raise ValueError("agent IDs must be nonempty strings")
        if type(stance) is not int:
            raise TypeError("initial stance must be an integer label")
        strata[stance].append(agent)
    inputs = dict(sorted(initial_stances.items()))
    input_hash = canonical_payload_hash(inputs)
    memberships = {}
    provenance = []
    for stance, agents in sorted(strata.items()):
        if len(agents) % 2:
            raise ValueError("exact group balance requires even counts in each stance stratum")
        rng = RNGProvenance.create(
            matched_seed=matched_seed,
            namespace="minimal_groups",
            coordinates={
                "artifact_kind": "minimal_groups",
                "initial_stances_hash": input_hash,
                "stance": stance,
            },
        )
        shuffled = sorted(agents)
        random.Random(rng.derived_seed).shuffle(shuffled)
        midpoint = len(shuffled) // 2
        memberships.update({a: "blue" if i < midpoint else "green" for i, a in enumerate(shuffled)})
        provenance.append(rng)
    return ArtifactEnvelope.create(
        artifact_type="identity_network_minimal_groups",
        schema_version="paper1.artifact-envelope.v1",
        algorithm_id="paper1.stratified_balanced_minimal_groups",
        algorithm_version="1.0.0",
        input_hashes={"initial_stances": input_hash},
        rng_provenance=tuple(provenance),
        payload={
            "study_id": "paper1.identity-network.v1",
            "matched_seed": matched_seed,
            "initial_stances": inputs,
            "memberships": dict(sorted(memberships.items())),
            "metadata": {
                "status": "preliminary",
                "research_parameter_status": "not_frozen",
                "formal_parameter_authority": False,
            },
        },
    )


@dataclass(frozen=True, slots=True, init=False)
class GroupContext:
    memberships: Mapping[str, str]
    artifact_hash: str

    @classmethod
    def from_artifact(cls, artifact: ArtifactEnvelope) -> "GroupContext":
        if not isinstance(artifact, ArtifactEnvelope):
            raise TypeError("expected ArtifactEnvelope")
        try:
            replay = build_group_assignment(
                initial_stances=artifact.payload["initial_stances"],
                matched_seed=artifact.payload["matched_seed"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid group artifact replay inputs") from exc
        if replay != artifact:
            raise ValueError("group artifact fails deterministic replay")
        result = object.__new__(cls)
        object.__setattr__(
            result, "memberships", MappingProxyType(dict(artifact.payload["memberships"]))
        )
        object.__setattr__(result, "artifact_hash", canonical_payload_hash(artifact.to_payload()))
        return result

    def group_for(self, agent_id: str) -> str:
        try:
            return self.memberships[agent_id]
        except KeyError as exc:
            raise ValueError(f"unknown agent: {agent_id}") from exc
