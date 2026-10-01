"""Pre-service approval sources remain fixed when actual start identity arrives."""

import pytest

from agent_ex.artifacts import ArtifactEnvelope
from agent_ex.domain import canonical_payload_hash
from agent_ex.identity_network.candidate import (
    build_six_cell_candidate,
    validate_six_cell_candidate,
)
from agent_ex.identity_network.materialization import build_population_execution_candidate
from test_identity_network_candidate import sources
from test_identity_network_execution_inputs import rebind
from test_identity_network_materialization import arguments


def test_service_rebinding_changes_runtime_candidate_but_not_pre_service_inputs():
    from agent_ex.identity_network.service_inputs import (
        project_pre_service_inputs,
        bind_candidate_service,
    )

    original = build_six_cell_candidate(**sources())
    projected = project_pre_service_inputs(original)
    bound = bind_candidate_service(original, service_start_identity_hash="f" * 64)
    assert bound.output_hash != original.output_hash
    assert project_pre_service_inputs(bound) == projected
    old = validate_six_cell_candidate(original)
    new = validate_six_cell_candidate(bound)
    assert all(a.common_inputs_hash != b.common_inputs_hash for a, b in zip(old, new, strict=True))
    assert all(
        a.schedule == b.schedule and a.groups == b.groups for a, b in zip(old, new, strict=True)
    )
    common = bound.payload["population_candidate"]["payload"]["execution_inputs"]["payload"]
    assert common["adapter_binding"]["service_start_identity_hash"] == "f" * 64
    assert (
        common["initial_updates"]
        == original.payload["population_candidate"]["payload"]["initial_updates"]
    )
    assert projected.payload["launch_authorized"] is False
    assert projected.payload["formal_parameter_authority"] is False
    assert bind_candidate_service(bound, service_start_identity_hash="f" * 64) == bound


@pytest.mark.parametrize(
    "field", ("memory_window", "feed_capacity", "generation_settings", "model_revision")
)
def test_pre_service_inputs_bind_all_nonservice_execution_choices(field):
    from agent_ex.identity_network.service_inputs import project_pre_service_inputs
    from agent_ex.phase0b.contracts import DiagnosticAdapterBinding

    kwargs = sources()
    original = build_six_cell_candidate(**kwargs)
    values = arguments()
    values["binding"] = kwargs["base_binding"]
    values["model_seeds"] = tuple(17 for _ in values["binding"].schedule.slots)
    if field == "generation_settings":
        values[field] = {**values[field], "max_tokens": values[field]["max_tokens"] + 1}
    elif field == "model_revision":
        adapter = values["adapter_binding"].to_payload()
        adapter[field] = "e" * 40
        adapter["record_hash"] = canonical_payload_hash(
            {k: v for k, v in adapter.items() if k != "record_hash"}
        )
        values["adapter_binding"] = DiagnosticAdapterBinding.from_payload(adapter)
    else:
        values[field] += 2
    population = build_population_execution_candidate(**values)
    common = ArtifactEnvelope.from_payload(population.to_payload()["payload"]["execution_inputs"])
    changed = build_six_cell_candidate(
        population_candidate=population,
        schedule_candidate=kwargs["schedule_candidate"],
        base_binding=rebind(values["binding"], common),
    )
    assert project_pre_service_inputs(changed) != project_pre_service_inputs(original)


@pytest.mark.parametrize("digest", (None, "UNRESOLVED[SIS_SERVICE]", "bad", True))
def test_rebinding_requires_explicit_start_hash(digest):
    from agent_ex.identity_network.service_inputs import bind_candidate_service

    with pytest.raises((ValueError, TypeError)):
        bind_candidate_service(
            build_six_cell_candidate(**sources()), service_start_identity_hash=digest
        )


def test_invalid_rehashed_candidate_not_projected_or_rebound():
    from agent_ex.identity_network.service_inputs import (
        project_pre_service_inputs,
        bind_candidate_service,
    )

    packet = build_six_cell_candidate(**sources())
    payload = packet.to_payload()["payload"]
    payload["metadata"]["launch_authorized"] = True
    corrupted = ArtifactEnvelope.create(
        artifact_type=packet.artifact_type,
        schema_version=packet.schema_version,
        algorithm_id=packet.algorithm_id,
        algorithm_version=packet.algorithm_version,
        input_hashes=packet.input_hashes,
        rng_provenance=packet.rng_provenance,
        payload=payload,
    )
    with pytest.raises(ValueError):
        project_pre_service_inputs(corrupted)
    with pytest.raises(ValueError):
        bind_candidate_service(corrupted, service_start_identity_hash="f" * 64)
