"""Self-contained six-cell source candidates, with no launch authority or I/O."""

from ..artifacts import ArtifactEnvelope
from ..domain import _json_ready
from .contracts import STUDY_ID, study_cells
from .materialization import validate_population_execution_candidate
from .schedule_sources import validate_schedule_candidate
from .storage import StudyRunBinding


SCHEMA = "paper1.identity-network.six-cell-candidate.v1"


def build_six_cell_candidate(*, population_candidate, schedule_candidate, base_binding):
    """Derive canonical six-cell bindings only after both full source replays."""
    if not isinstance(base_binding, StudyRunBinding) or base_binding.cell != study_cells()[0]:
        raise ValueError("typed canonical A0B0 reference binding required")
    validate_schedule_candidate(schedule_candidate, base_binding)
    validate_population_execution_candidate(population_candidate, base_binding)
    groups = ArtifactEnvelope.from_payload(base_binding.to_payload()["groups"])
    bindings = tuple(
        StudyRunBinding.create(
            cell=cell,
            matched_seed=base_binding.matched_seed,
            groups=groups,
            aliases=base_binding.aliases,
            node_agent_ids=base_binding.node_agent_ids,
            topic_package=base_binding.topic_package,
            schedule=base_binding.schedule,
            ws=base_binding.ws,
            randomized=base_binding.randomized,
            common_inputs_hash=base_binding.common_inputs_hash,
        )
        for cell in study_cells()
    )
    return ArtifactEnvelope.create(
        artifact_type="sis-six-cell-candidate",
        schema_version=SCHEMA,
        algorithm_id="sis-common-source-six-cell-bindings",
        algorithm_version="1.0.0",
        input_hashes={
            "population_candidate": population_candidate.output_hash,
            "schedule_candidate": schedule_candidate.output_hash,
            "execution_inputs": base_binding.common_inputs_hash,
            **{b.cell.cell_id: b.record_hash for b in bindings},
        },
        rng_provenance=(),
        payload={
            "study_id": STUDY_ID,
            "population_candidate": population_candidate.to_payload(),
            "schedule_candidate": schedule_candidate.to_payload(),
            "bindings": tuple(b.to_payload() for b in bindings),
            "metadata": {
                "status": "preliminary",
                "research_parameter_status": "not_frozen",
                "formal_parameter_authority": False,
                "launch_authorized": False,
                "source_authority": "candidate_unattested",
            },
        },
    )


def validate_six_cell_candidate(artifact):
    """Replay an entire portable candidate; return exactly six typed bindings."""
    if not isinstance(artifact, ArtifactEnvelope):
        raise TypeError("typed six-cell candidate required")
    payload = _json_ready(artifact.payload)
    if (
        type(payload) is not dict
        or set(payload)
        != {"study_id", "population_candidate", "schedule_candidate", "bindings", "metadata"}
        or type(payload["bindings"]) is not list
        or len(payload["bindings"]) != 6
    ):
        raise ValueError("self-contained exact six-cell source candidate required")
    bindings = tuple(StudyRunBinding.from_payload(b) for b in payload["bindings"])
    if tuple(b.cell for b in bindings) != study_cells():
        raise ValueError("six-cell candidate binding inventory/order mismatch")
    expected = build_six_cell_candidate(
        population_candidate=ArtifactEnvelope.from_payload(payload["population_candidate"]),
        schedule_candidate=ArtifactEnvelope.from_payload(payload["schedule_candidate"]),
        base_binding=bindings[0],
    )
    if artifact != expected:
        raise ValueError("six-cell candidate differs from full shared source/binding replay")
    return bindings
