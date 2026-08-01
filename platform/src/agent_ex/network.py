"""Deterministic mock network artifacts for Paper 1 Phase 4B-4."""

from __future__ import annotations

import math
import random
import statistics
from typing import Iterable, Mapping

import networkx as nx

from .artifacts import ArtifactEnvelope
from .domain import _require_int, canonical_payload_hash
from .rng import RNGProvenance


NETWORKX_VERSION = "3.6.1"
WS_ALGORITHM_ID = "paper1.mock_networkx_watts_strogatz"
WS_ALGORITHM_VERSION = "1.0.0"
SHADOW_ALGORITHM_ID = "paper1.mock_forbidden_edge_connected_double_swap"
SHADOW_ALGORITHM_VERSION = "1.0.0"
MAPPING_ALGORITHM_ID = "paper1.mock_fisher_yates_agent_node_mapping"
MAPPING_ALGORITHM_VERSION = "1.0.0"
STRUCTURE_GATE_ALGORITHM_ID = "paper1.mock_pure_structure_gate"
STRUCTURE_GATE_ALGORITHM_VERSION = "1.0.0"
RING_LATTICE_ALGORITHM_ID = "networkx.watts_strogatz_graph_p0"
RANDOM_NULL_ALGORITHM_ID = "networkx.gnm_random_graph"
_ENVELOPE_VERSION = "paper1.artifact-envelope.v1"
_NETWORKX_WS_RNG_IMPLEMENTATION = "networkx.py_random_state(int)->python.random.Random(MT19937)"
_PYTHON_RNG_IMPLEMENTATION = "python.random.Random(MT19937)"


if nx.__version__ != NETWORKX_VERSION:  # pragma: no cover - dependency lock is installation-gated
    raise RuntimeError(
        f"network artifact implementation requires networkx=={NETWORKX_VERSION}; "
        f"found {nx.__version__}"
    )


def _require_mock_only(mock_only: bool) -> None:
    if mock_only is not True:
        raise ValueError("Phase 4B-4 network artifacts must be explicitly mock_only")


def _validate_ws_parameters(n: int, k: int, p: float, matched_seed: int) -> float:
    _require_int("n", n, minimum=3)
    _require_int("k", k, minimum=2)
    _require_int("matched_seed", matched_seed)
    if k >= n:
        raise ValueError("k must be smaller than n")
    if k % 2:
        raise ValueError("k must be even for the registered WS construction")
    if isinstance(p, bool) or not isinstance(p, (int, float)):
        raise TypeError("p must be a finite number")
    numeric_p = float(p)
    if not math.isfinite(numeric_p) or not 0.0 <= numeric_p <= 1.0:
        raise ValueError("p must be between zero and one")
    return numeric_p


def _canonical_edge(left: int, right: int) -> tuple[int, int]:
    return (left, right) if left < right else (right, left)


def _canonical_edges(edges: Iterable[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    return tuple(sorted(_canonical_edge(left, right) for left, right in edges))


def _ws_construction_hash(n: int, k: int, p: float) -> str:
    return canonical_payload_hash(
        {
            "n": n,
            "k": k,
            "p": p,
            "networkx_version": NETWORKX_VERSION,
            "generator": "networkx.generators.random_graphs.watts_strogatz_graph",
        }
    )


def _graph_from_payload(payload: Mapping[str, object]) -> nx.Graph:
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    if not isinstance(nodes, (tuple, list)) or not isinstance(edges, (tuple, list)):
        raise ValueError("network artifact nodes and edges must be sequences")
    if any(type(node) is not int for node in nodes):
        raise TypeError("network nodes must be integers and cannot be boolean")
    for edge in edges:
        if not isinstance(edge, (tuple, list)) or len(edge) != 2:
            raise ValueError("network edges must contain exactly two endpoints")
        if any(type(endpoint) is not int for endpoint in edge):
            raise TypeError("network edge endpoints must be integers and cannot be boolean")
    graph = nx.Graph()
    graph.add_nodes_from(nodes)
    graph.add_edges_from(edges)
    return graph


def _structure_report(graph: nx.Graph) -> dict[str, object]:
    nodes = sorted(graph.nodes)
    degrees = tuple(graph.degree(node) for node in nodes)
    connected = bool(nodes) and nx.is_connected(graph)
    return {
        "node_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(),
        "degree_sequence": degrees,
        "mean_degree": statistics.fmean(degrees) if degrees else 0.0,
        "degree_sd": statistics.pstdev(degrees) if degrees else 0.0,
        "min_degree": min(degrees) if degrees else 0,
        "max_degree": max(degrees) if degrees else 0,
        "density": nx.density(graph),
        "average_clustering": nx.average_clustering(graph),
        "transitivity": nx.transitivity(graph),
        "connected": connected,
        "component_count": nx.number_connected_components(graph),
        "average_shortest_path_length": (
            nx.average_shortest_path_length(graph) if connected else None
        ),
        "diameter": nx.diameter(graph) if connected else None,
        "triangle_count": sum(nx.triangles(graph).values()) // 3,
    }


def _validate_common_graph_payload(
    artifact: ArtifactEnvelope,
    *,
    artifact_type: str,
    algorithm_id: str,
    algorithm_version: str,
) -> tuple[nx.Graph, Mapping[str, object]]:
    if not isinstance(artifact, ArtifactEnvelope):
        raise TypeError("network artifact must be an ArtifactEnvelope")
    if artifact.artifact_type != artifact_type:
        raise ValueError(f"network artifact_type must be {artifact_type}")
    if artifact.schema_version != _ENVELOPE_VERSION:
        raise ValueError("network artifact envelope version is not supported")
    if artifact.algorithm_id != algorithm_id or artifact.algorithm_version != algorithm_version:
        raise ValueError("network artifact algorithm identity does not match the contract")
    payload = artifact.payload
    if not isinstance(payload, Mapping):
        raise TypeError("network artifact payload must be a mapping")
    metadata = payload.get("metadata")
    if metadata != {"mock_only": True, "research_parameter_status": "not_frozen"}:
        raise ValueError("network artifact must remain mock_only / not_frozen")
    graph = _graph_from_payload(payload)
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    if tuple(nodes) != tuple(range(graph.number_of_nodes())):  # type: ignore[arg-type]
        raise ValueError("network nodes must be exactly 0..N-1 in canonical order")
    if graph.is_directed():
        raise ValueError("network must be undirected")
    if nx.number_of_selfloops(graph):
        raise ValueError("network contains a self-loop")
    if graph.number_of_edges() != len(edges):  # type: ignore[arg-type]
        raise ValueError("network contains duplicate edges")
    canonical = _canonical_edges(graph.edges)
    if tuple(tuple(edge) for edge in edges) != canonical:  # type: ignore[union-attr]
        raise ValueError("network edges must use canonical sorted order")
    if not nx.is_connected(graph):
        raise ValueError("network must be connected")
    actual_report = _structure_report(graph)
    if payload.get("structure_report") != actual_report:
        raise ValueError("network structure report does not match graph structure")
    return graph, actual_report


def build_ws_artifact(
    *, n: int, k: int, p: float, matched_seed: int, mock_only: bool
) -> ArtifactEnvelope:
    """Build one explicit-seed NetworkX WS artifact in matched-seed common scope."""

    _require_mock_only(mock_only)
    numeric_p = _validate_ws_parameters(n, k, p, matched_seed)
    provenance = RNGProvenance.create(
        matched_seed=matched_seed,
        namespace="ws_graph",
        coordinates={
            "artifact_kind": "mock_ws_graph",
            "n": n,
            "k": k,
            "p": numeric_p,
            "networkx_version": NETWORKX_VERSION,
            "algorithm_version": WS_ALGORITHM_VERSION,
        },
    )
    graph = nx.watts_strogatz_graph(
        n=n,
        k=k,
        p=numeric_p,
        seed=provenance.derived_seed,
        create_using=nx.Graph,
    )
    if set(graph.nodes) != set(range(n)):
        raise ValueError("WS generator returned an invalid node set")
    if graph.number_of_edges() != n * k // 2:
        raise ValueError("WS generator returned an invalid edge count")
    if not nx.is_connected(graph):
        raise ValueError("WS generator returned a disconnected candidate; fail closed")
    payload = {
        "schema_version": "paper1.mock-ws-graph.v1",
        "matched_seed": matched_seed,
        "parameters": {"n": n, "k": k, "p": numeric_p},
        "nodes": tuple(range(n)),
        "edges": _canonical_edges(graph.edges),
        "structure_report": _structure_report(graph),
        "library": {
            "name": "networkx",
            "version": NETWORKX_VERSION,
            "generator": "networkx.generators.random_graphs.watts_strogatz_graph",
        },
        "rng_implementation": _NETWORKX_WS_RNG_IMPLEMENTATION,
        "metadata": {"mock_only": True, "research_parameter_status": "not_frozen"},
    }
    artifact = ArtifactEnvelope.create(
        artifact_type="paper1.mock_ws_graph",
        schema_version=_ENVELOPE_VERSION,
        algorithm_id=WS_ALGORITHM_ID,
        algorithm_version=WS_ALGORITHM_VERSION,
        input_hashes={"construction_parameters": _ws_construction_hash(n, k, numeric_p)},
        payload=payload,
        rng_provenance=(provenance,),
    )
    validate_ws_artifact(artifact)
    return artifact


def validate_ws_artifact(artifact: ArtifactEnvelope) -> Mapping[str, object]:
    """Validate all frozen WS structural and provenance invariants."""

    graph, report = _validate_common_graph_payload(
        artifact,
        artifact_type="paper1.mock_ws_graph",
        algorithm_id=WS_ALGORITHM_ID,
        algorithm_version=WS_ALGORITHM_VERSION,
    )
    payload = artifact.payload
    assert isinstance(payload, Mapping)
    parameters = payload.get("parameters")
    if not isinstance(parameters, Mapping) or set(parameters) != {"n", "k", "p"}:
        raise ValueError("WS parameters do not match the contract")
    numeric_p = _validate_ws_parameters(
        parameters["n"],
        parameters["k"],
        parameters["p"],
        payload.get("matched_seed"),  # type: ignore[arg-type]
    )
    n = parameters["n"]
    k = parameters["k"]
    assert isinstance(n, int) and isinstance(k, int)
    if graph.number_of_nodes() != n or graph.number_of_edges() != n * k // 2:
        raise ValueError("WS graph dimensions do not match n/k")
    if numeric_p != parameters["p"]:
        raise ValueError("WS p is not canonical")
    if artifact.input_hashes != {"construction_parameters": _ws_construction_hash(n, k, numeric_p)}:
        raise ValueError("WS construction parameters do not match the input hash")
    expected_library = {
        "name": "networkx",
        "version": NETWORKX_VERSION,
        "generator": "networkx.generators.random_graphs.watts_strogatz_graph",
    }
    if payload.get("library") != expected_library:
        raise ValueError("WS graph library identity does not match the locked candidate")
    if payload.get("rng_implementation") != _NETWORKX_WS_RNG_IMPLEMENTATION:
        raise ValueError("WS graph RNG implementation does not match the locked candidate")
    if len(artifact.rng_provenance) != 1 or artifact.rng_provenance[0].namespace != "ws_graph":
        raise ValueError("WS graph RNG provenance is incomplete")
    provenance = artifact.rng_provenance[0]
    if provenance.matched_seed != payload.get("matched_seed") or provenance.coordinates != {
        "artifact_kind": "mock_ws_graph",
        "n": n,
        "k": k,
        "p": numeric_p,
        "networkx_version": NETWORKX_VERSION,
        "algorithm_version": WS_ALGORITHM_VERSION,
    }:
        raise ValueError("WS graph parameters do not match RNG provenance")
    if (
        provenance.derived_seed
        != RNGProvenance.create(
            matched_seed=payload["matched_seed"],  # type: ignore[arg-type]
            namespace="ws_graph",
            coordinates=provenance.coordinates,
        ).derived_seed
    ):
        raise ValueError("WS graph derived seed does not match RNG provenance")
    replay = nx.watts_strogatz_graph(
        n=n,
        k=k,
        p=numeric_p,
        seed=provenance.derived_seed,
        create_using=nx.Graph,
    )
    if _canonical_edges(replay.edges) != _canonical_edges(graph.edges):
        raise ValueError("WS graph does not match deterministic replay")
    return report


def _try_shadow_attempt(
    ws_graph: nx.Graph,
    *,
    rng: random.Random,
    trial_budget_per_edge: int,
) -> tuple[nx.Graph | None, dict[str, int]]:
    graph = ws_graph.copy()
    forbidden = set(_canonical_edges(ws_graph.edges))
    accepted_swaps = 0
    connectivity_checks = 0
    candidate_trials = 0

    while True:
        overlap = sorted(forbidden.intersection(_canonical_edges(graph.edges)))
        if not overlap:
            return graph, {
                "accepted_swaps": accepted_swaps,
                "connectivity_checks": connectivity_checks,
                "candidate_trials": candidate_trials,
                "forbidden_edges_remaining": 0,
            }
        first = overlap[rng.randrange(len(overlap))]
        candidates = [edge for edge in _canonical_edges(graph.edges) if edge != first]
        rng.shuffle(candidates)
        accepted = False
        used_trials = 0
        for second in candidates:
            orientations = (
                ((first[0], second[0]), (first[1], second[1])),
                ((first[0], second[1]), (first[1], second[0])),
            )
            if rng.randrange(2):
                orientations = (orientations[1], orientations[0])
            for raw_new_edges in orientations:
                if used_trials >= trial_budget_per_edge:
                    break
                used_trials += 1
                candidate_trials += 1
                if any(left == right for left, right in raw_new_edges):
                    continue
                new_edges = tuple(_canonical_edge(*edge) for edge in raw_new_edges)
                if len(set(new_edges)) != 2 or any(edge in forbidden for edge in new_edges):
                    continue
                remaining = {first, second}
                if any(graph.has_edge(*edge) and edge not in remaining for edge in new_edges):
                    continue
                graph.remove_edges_from((first, second))
                graph.add_edges_from(new_edges)
                connectivity_checks += 1
                if nx.is_connected(graph):
                    accepted_swaps += 1
                    accepted = True
                    break
                graph.remove_edges_from(new_edges)
                graph.add_edges_from((first, second))
            if accepted or used_trials >= trial_budget_per_edge:
                break
        if not accepted:
            return None, {
                "accepted_swaps": accepted_swaps,
                "connectivity_checks": connectivity_checks,
                "candidate_trials": candidate_trials,
                "forbidden_edges_remaining": len(
                    forbidden.intersection(_canonical_edges(graph.edges))
                ),
            }


def _replay_shadow_construction(
    ws_graph: nx.Graph,
    *,
    derived_seed: int,
    max_attempts: int,
    trial_budget_per_edge: int,
) -> tuple[nx.Graph, dict[str, object]] | None:
    """Run the registered bounded algorithm and return its exact graph and audit."""

    rng = random.Random(derived_seed)
    attempt_audits: list[dict[str, object]] = []
    for attempt in range(1, max_attempts + 1):
        graph, attempt_audit = _try_shadow_attempt(
            ws_graph,
            rng=rng,
            trial_budget_per_edge=trial_budget_per_edge,
        )
        attempt_audits.append(
            {
                "attempt_index": attempt,
                "succeeded": graph is not None,
                **attempt_audit,
            }
        )
        if graph is not None:
            return graph, {
                "accepted_swaps": sum(
                    item["accepted_swaps"]
                    for item in attempt_audits  # type: ignore[misc]
                ),
                "connectivity_checks": sum(
                    item["connectivity_checks"]
                    for item in attempt_audits  # type: ignore[misc]
                ),
                "candidate_trials": sum(
                    item["candidate_trials"]
                    for item in attempt_audits  # type: ignore[misc]
                ),
                "forbidden_edges_remaining": 0,
                "attempts_used": attempt,
                "max_attempts": max_attempts,
                "trial_budget_per_edge": trial_budget_per_edge,
                "max_candidate_trials_per_attempt": (
                    graph.number_of_edges() * trial_budget_per_edge
                ),
                "attempt_audits": tuple(attempt_audits),
            }
    return None


def build_shadow_artifact(
    ws_artifact: ArtifactEnvelope,
    *,
    matched_seed: int,
    max_attempts: int,
    trial_budget_per_edge: int,
    mock_only: bool,
) -> ArtifactEnvelope:
    """Eliminate every WS edge through bounded connected degree-preserving swaps."""

    _require_mock_only(mock_only)
    _require_int("matched_seed", matched_seed)
    _require_int("max_attempts", max_attempts, minimum=1)
    _require_int("trial_budget_per_edge", trial_budget_per_edge, minimum=1)
    validate_ws_artifact(ws_artifact)
    if ws_artifact.payload["matched_seed"] != matched_seed:  # type: ignore[index]
        raise ValueError("shadow matched_seed must match the WS graph matched_seed")
    ws_graph = _graph_from_payload(ws_artifact.payload)  # type: ignore[arg-type]
    for node, degree in ws_graph.degree:
        allowed_capacity = ws_graph.number_of_nodes() - 1 - degree
        if degree > allowed_capacity:
            raise ValueError(
                f"shadow constraints are impossible at node {node}: forbidden-edge capacity"
            )
    provenance = RNGProvenance.create(
        matched_seed=matched_seed,
        namespace="shadow_graph",
        coordinates={
            "artifact_kind": "mock_shadow_graph",
            "ws_output_hash": ws_artifact.output_hash,
            "algorithm_version": SHADOW_ALGORITHM_VERSION,
            "max_attempts": max_attempts,
            "trial_budget_per_edge": trial_budget_per_edge,
        },
    )
    result = _replay_shadow_construction(
        ws_graph,
        derived_seed=provenance.derived_seed,
        max_attempts=max_attempts,
        trial_budget_per_edge=trial_budget_per_edge,
    )
    if result is None:
        raise ValueError(
            "shadow construction exhausted its bounded budget: "
            f"max_attempts={max_attempts}, trial_budget_per_edge={trial_budget_per_edge}"
        )
    graph, audit = result
    payload = {
        "schema_version": "paper1.mock-shadow-graph.v1",
        "matched_seed": matched_seed,
        "source_ws_artifact_id": ws_artifact.artifact_id,
        "nodes": tuple(range(graph.number_of_nodes())),
        "edges": _canonical_edges(graph.edges),
        "structure_report": _structure_report(graph),
        "construction_audit": audit,
        "library": {"name": "networkx", "version": NETWORKX_VERSION},
        "rng_implementation": _PYTHON_RNG_IMPLEMENTATION,
        "metadata": {"mock_only": True, "research_parameter_status": "not_frozen"},
    }
    artifact = ArtifactEnvelope.create(
        artifact_type="paper1.mock_shadow_graph",
        schema_version=_ENVELOPE_VERSION,
        algorithm_id=SHADOW_ALGORITHM_ID,
        algorithm_version=SHADOW_ALGORITHM_VERSION,
        input_hashes={
            "ws_graph": ws_artifact.output_hash,
            "construction_budget": canonical_payload_hash(
                {
                    "max_attempts": max_attempts,
                    "trial_budget_per_edge": trial_budget_per_edge,
                }
            ),
        },
        payload=payload,
        rng_provenance=(provenance,),
    )
    _validate_shadow_artifact(artifact, ws_artifact, expected_replay=result)
    return artifact


def validate_shadow_artifact(
    artifact: ArtifactEnvelope, ws_artifact: ArtifactEnvelope
) -> Mapping[str, object]:
    """Validate shadow degree matching, disjointness, connectivity, and provenance."""

    return _validate_shadow_artifact(artifact, ws_artifact)


def _validate_shadow_artifact(
    artifact: ArtifactEnvelope,
    ws_artifact: ArtifactEnvelope,
    *,
    expected_replay: tuple[nx.Graph, dict[str, object]] | None = None,
) -> Mapping[str, object]:
    """Validate a shadow artifact, optionally reusing the builder's exact replay."""

    validate_ws_artifact(ws_artifact)
    ws_graph = _graph_from_payload(ws_artifact.payload)  # type: ignore[arg-type]
    graph, report = _validate_common_graph_payload(
        artifact,
        artifact_type="paper1.mock_shadow_graph",
        algorithm_id=SHADOW_ALGORITHM_ID,
        algorithm_version=SHADOW_ALGORITHM_VERSION,
    )
    if tuple(graph.degree(node) for node in range(graph.number_of_nodes())) != tuple(
        ws_graph.degree(node) for node in range(ws_graph.number_of_nodes())
    ):
        raise ValueError("shadow degree sequence does not match WS node by node")
    if set(_canonical_edges(graph.edges)).intersection(_canonical_edges(ws_graph.edges)):
        raise ValueError("shadow graph contains a forbidden WS edge")
    payload = artifact.payload
    assert isinstance(payload, Mapping)
    if payload.get("source_ws_artifact_id") != ws_artifact.artifact_id:
        raise ValueError("shadow source WS artifact identity does not match")
    if artifact.input_hashes.get("ws_graph") != ws_artifact.output_hash:
        raise ValueError("shadow input hash does not match the WS artifact")
    audit = payload.get("construction_audit")
    if not isinstance(audit, Mapping):
        raise ValueError("shadow construction audit is missing")
    if audit.get("forbidden_edges_remaining") != 0:
        raise ValueError("shadow construction audit reports forbidden edges")
    expected_audit_fields = {
        "accepted_swaps",
        "connectivity_checks",
        "candidate_trials",
        "forbidden_edges_remaining",
        "attempts_used",
        "max_attempts",
        "trial_budget_per_edge",
        "max_candidate_trials_per_attempt",
        "attempt_audits",
    }
    if set(audit) != expected_audit_fields:
        raise ValueError("shadow construction audit fields do not match the contract")
    scalar_audit_fields = expected_audit_fields - {"attempt_audits"}
    for name in scalar_audit_fields:
        if type(audit[name]) is not int:
            raise TypeError(f"shadow construction audit {name} must be an integer")
    attempts_used = audit["attempts_used"]
    max_attempts = audit["max_attempts"]
    candidate_trials = audit["candidate_trials"]
    accepted_swaps = audit["accepted_swaps"]
    connectivity_checks = audit["connectivity_checks"]
    if not 1 <= attempts_used <= max_attempts:
        raise ValueError("shadow attempts_used must be within the frozen attempt budget")
    if candidate_trials < 0:
        raise ValueError("shadow candidate_trials must be non-negative")
    if accepted_swaps < 0 or accepted_swaps > candidate_trials:
        raise ValueError("shadow accepted_swaps must be between zero and candidate_trials")
    if connectivity_checks < 0:
        raise ValueError("shadow connectivity_checks must be non-negative")
    if not accepted_swaps <= connectivity_checks <= candidate_trials:
        raise ValueError("shadow connectivity checks must cover accepted swaps within trials")
    if len(artifact.rng_provenance) != 1 or artifact.rng_provenance[0].namespace != "shadow_graph":
        raise ValueError("shadow graph RNG provenance is incomplete")
    provenance = artifact.rng_provenance[0]
    coordinates = provenance.coordinates
    expected_coordinate_fields = {
        "artifact_kind",
        "ws_output_hash",
        "algorithm_version",
        "max_attempts",
        "trial_budget_per_edge",
    }
    if set(coordinates) != expected_coordinate_fields:
        raise ValueError("shadow construction budget provenance is incomplete")
    if (
        provenance.matched_seed != payload.get("matched_seed")
        or coordinates["artifact_kind"] != "mock_shadow_graph"
        or coordinates["ws_output_hash"] != ws_artifact.output_hash
        or coordinates["algorithm_version"] != SHADOW_ALGORITHM_VERSION
        or coordinates["max_attempts"] != audit.get("max_attempts")
    ):
        raise ValueError("shadow construction budget does not match RNG provenance")
    trial_budget = coordinates["trial_budget_per_edge"]
    if type(trial_budget) is not int or trial_budget < 1:
        raise ValueError("shadow trial budget provenance must be a positive integer")
    expected_max_trials = graph.number_of_edges() * trial_budget
    if (
        audit["trial_budget_per_edge"] != trial_budget
        or audit["max_candidate_trials_per_attempt"] != expected_max_trials
    ):
        raise ValueError("shadow trial budget audit does not match RNG provenance")
    if candidate_trials > attempts_used * expected_max_trials:
        raise ValueError("shadow candidate_trials exceeds the bounded construction budget")
    attempt_audits = audit["attempt_audits"]
    if not isinstance(attempt_audits, (tuple, list)) or len(attempt_audits) != attempts_used:
        raise ValueError("shadow attempt audit count must equal attempts_used")
    expected_attempt_fields = {
        "attempt_index",
        "succeeded",
        "accepted_swaps",
        "connectivity_checks",
        "candidate_trials",
        "forbidden_edges_remaining",
    }
    for index, attempt_audit in enumerate(attempt_audits, start=1):
        if not isinstance(attempt_audit, Mapping) or set(attempt_audit) != expected_attempt_fields:
            raise ValueError("shadow per-attempt audit fields do not match the contract")
        if (
            type(attempt_audit["attempt_index"]) is not int
            or attempt_audit["attempt_index"] != index
        ):
            raise ValueError("shadow per-attempt audit indices must be consecutive")
        if type(attempt_audit["succeeded"]) is not bool:
            raise TypeError("shadow per-attempt succeeded flag must be boolean")
        for name in expected_attempt_fields - {"attempt_index", "succeeded"}:
            if type(attempt_audit[name]) is not int or attempt_audit[name] < 0:
                raise ValueError(f"shadow per-attempt audit {name} must be a non-negative integer")
        if attempt_audit["candidate_trials"] > expected_max_trials:
            raise ValueError("shadow per-attempt candidate trials exceed the bounded budget")
        if attempt_audit["succeeded"] is not (index == attempts_used):
            raise ValueError("shadow only the final used attempt may succeed")
        if (attempt_audit["forbidden_edges_remaining"] == 0) is not attempt_audit["succeeded"]:
            raise ValueError("shadow per-attempt completion does not match forbidden-edge audit")
    for name in ("accepted_swaps", "connectivity_checks", "candidate_trials"):
        if audit[name] != sum(item[name] for item in attempt_audits):
            raise ValueError("shadow construction audit does not match deterministic replay totals")
    if payload.get("library") != {"name": "networkx", "version": NETWORKX_VERSION}:
        raise ValueError("shadow graph library identity does not match the locked candidate")
    if payload.get("rng_implementation") != _PYTHON_RNG_IMPLEMENTATION:
        raise ValueError("shadow graph RNG implementation does not match the locked candidate")
    expected_budget_hash = canonical_payload_hash(
        {
            "max_attempts": coordinates["max_attempts"],
            "trial_budget_per_edge": coordinates["trial_budget_per_edge"],
        }
    )
    if artifact.input_hashes != {
        "ws_graph": ws_artifact.output_hash,
        "construction_budget": expected_budget_hash,
    }:
        raise ValueError("shadow construction budget does not match the input hash")
    replay_result = expected_replay or _replay_shadow_construction(
        ws_graph,
        derived_seed=provenance.derived_seed,
        max_attempts=coordinates["max_attempts"],
        trial_budget_per_edge=trial_budget,
    )
    if replay_result is None:
        raise ValueError("shadow deterministic replay exhausted its bounded budget")
    replay_graph, replay_audit = replay_result
    if (
        _canonical_edges(replay_graph.edges) != _canonical_edges(graph.edges)
        or dict(audit) != replay_audit
    ):
        raise ValueError("shadow graph or construction audit does not match deterministic replay")
    return report


def build_agent_node_mapping(
    *,
    population_artifact: ArtifactEnvelope,
    round0_initialization_artifact: ArtifactEnvelope,
    network_artifact: ArtifactEnvelope,
    matched_seed: int,
    mock_only: bool,
) -> ArtifactEnvelope:
    """Randomly map canonical population records to graph nodes in common seed scope."""

    _require_mock_only(mock_only)
    _require_int("matched_seed", matched_seed)
    if population_artifact.artifact_type != "paper1.mock_population":
        raise ValueError("mapping population artifact type does not match the contract")
    if round0_initialization_artifact.artifact_type != "paper1.mock_round0_initialization":
        raise ValueError("mapping round0 initialization artifact type does not match the contract")
    for name, source in (
        ("population", population_artifact),
        ("round0 initialization", round0_initialization_artifact),
    ):
        if not isinstance(source.payload, Mapping):
            raise TypeError(f"{name} artifact payload must be a mapping")
        if source.payload.get("matched_seed") != matched_seed:
            raise ValueError(f"{name} matched_seed must match mapping matched_seed")
        if source.payload.get("metadata") != {
            "mock_only": True,
            "research_parameter_status": "not_frozen",
        }:
            raise ValueError(f"{name} artifact must remain mock_only / not_frozen")
    members = population_artifact.payload.get("members")
    records = round0_initialization_artifact.payload.get("round0_records")
    if not isinstance(members, (tuple, list)) or not members:
        raise ValueError("population members must be a non-empty sequence")
    if not isinstance(records, (tuple, list)):
        raise ValueError("round0 records must be a sequence")
    agent_ids = tuple(
        member.get("agent_id") if isinstance(member, Mapping) else None for member in members
    )
    if any(not isinstance(agent_id, str) or not agent_id.strip() for agent_id in agent_ids):
        raise ValueError("population agent IDs must contain non-empty strings")
    if len(set(agent_ids)) != len(agent_ids):
        raise ValueError("population agent IDs must be unique")
    round0_agent_ids = tuple(
        record.get("agent_id") if isinstance(record, Mapping) else None for record in records
    )
    if round0_agent_ids != agent_ids:
        raise ValueError("round0 agent IDs must match population agent IDs one by one")
    if network_artifact.artifact_type != "paper1.mock_ws_graph":
        raise ValueError("agent-node position frame must be a validated WS graph artifact")
    validate_ws_artifact(network_artifact)
    if network_artifact.payload["matched_seed"] != matched_seed:  # type: ignore[index]
        raise ValueError("mapping matched_seed must match the WS graph matched_seed")
    graph = _graph_from_payload(network_artifact.payload)  # type: ignore[arg-type]
    if len(agent_ids) != graph.number_of_nodes():
        raise ValueError("agent_ids must have exactly one record per graph node")
    population_order_hash = canonical_payload_hash(tuple(agent_ids))
    provenance = RNGProvenance.create(
        matched_seed=matched_seed,
        namespace="agent_node_mapping",
        coordinates={
            "artifact_kind": "mock_agent_node_mapping",
            "network_output_hash": network_artifact.output_hash,
            "population_order_hash": population_order_hash,
            "population_output_hash": population_artifact.output_hash,
            "round0_output_hash": round0_initialization_artifact.output_hash,
            "algorithm_version": MAPPING_ALGORITHM_VERSION,
        },
    )
    nodes = list(range(graph.number_of_nodes()))
    random.Random(provenance.derived_seed).shuffle(nodes)
    assignments = tuple(
        {"agent_id": agent_id, "node_id": node_id}
        for agent_id, node_id in zip(agent_ids, nodes, strict=True)
    )
    payload = {
        "schema_version": "paper1.mock-agent-node-mapping.v1",
        "matched_seed": matched_seed,
        "network_artifact_id": network_artifact.artifact_id,
        "population_artifact_id": population_artifact.artifact_id,
        "population_output_hash": population_artifact.output_hash,
        "population_matched_seed": population_artifact.payload["matched_seed"],
        "round0_initialization_artifact_id": round0_initialization_artifact.artifact_id,
        "round0_initialization_output_hash": round0_initialization_artifact.output_hash,
        "round0_initialization_matched_seed": round0_initialization_artifact.payload[
            "matched_seed"
        ],
        "network_output_hash": network_artifact.output_hash,
        "network_matched_seed": network_artifact.payload["matched_seed"],
        "assignments": assignments,
        "metadata": {"mock_only": True, "research_parameter_status": "not_frozen"},
    }
    return ArtifactEnvelope.create(
        artifact_type="paper1.mock_agent_node_mapping",
        schema_version=_ENVELOPE_VERSION,
        algorithm_id=MAPPING_ALGORITHM_ID,
        algorithm_version=MAPPING_ALGORITHM_VERSION,
        input_hashes={
            "network_graph": network_artifact.output_hash,
            "population": population_artifact.output_hash,
            "round0_initialization": round0_initialization_artifact.output_hash,
        },
        payload=payload,
        rng_provenance=(provenance,),
    )


def build_structural_gate_artifact(
    ws_artifact: ArtifactEnvelope,
    *,
    matched_seed: int,
    random_null_replicates: int,
    mock_only: bool,
) -> ArtifactEnvelope:
    """Compute a pure-structure D-07 gate without reading opinion state."""

    _require_mock_only(mock_only)
    _require_int("matched_seed", matched_seed)
    _require_int("random_null_replicates", random_null_replicates, minimum=1)
    validate_ws_artifact(ws_artifact)
    if ws_artifact.payload["matched_seed"] != matched_seed:  # type: ignore[index]
        raise ValueError("structure gate matched_seed must match the WS artifact")
    parameters = ws_artifact.payload["parameters"]  # type: ignore[index]
    n = parameters["n"]  # type: ignore[index]
    k = parameters["k"]  # type: ignore[index]
    ws_graph = _graph_from_payload(ws_artifact.payload)  # type: ignore[arg-type]
    ring_provenance = RNGProvenance.create(
        matched_seed=matched_seed,
        namespace="structure_ring_lattice",
        coordinates={
            "artifact_kind": "mock_structure_ring_lattice",
            "ws_output_hash": ws_artifact.output_hash,
            "algorithm_id": RING_LATTICE_ALGORITHM_ID,
            "algorithm_version": STRUCTURE_GATE_ALGORITHM_VERSION,
        },
    )
    ring = nx.watts_strogatz_graph(
        n=n, k=k, p=0.0, seed=ring_provenance.derived_seed, create_using=nx.Graph
    )
    random_provenance = RNGProvenance.create(
        matched_seed=matched_seed,
        namespace="structure_random_null",
        coordinates={
            "artifact_kind": "mock_structure_random_nulls",
            "ws_output_hash": ws_artifact.output_hash,
            "algorithm_id": RANDOM_NULL_ALGORITHM_ID,
            "algorithm_version": STRUCTURE_GATE_ALGORITHM_VERSION,
            "replicates": random_null_replicates,
        },
    )
    seed_rng = random.Random(random_provenance.derived_seed)
    random_reports = []
    for replicate in range(random_null_replicates):
        graph = nx.gnm_random_graph(
            n=n,
            m=ws_graph.number_of_edges(),
            seed=seed_rng.randrange(2**63),
            directed=False,
        )
        if not nx.is_connected(graph):
            raise ValueError(f"random null graph {replicate} is disconnected; fail closed")
        random_reports.append(_structure_report(graph))
    ws_report = _structure_report(ws_graph)
    ring_report = _structure_report(ring)
    random_clustering = statistics.fmean(report["average_clustering"] for report in random_reports)
    random_path = statistics.fmean(
        report["average_shortest_path_length"] for report in random_reports
    )
    if random_clustering <= 0 or random_path <= 0:
        raise ValueError("random null metrics must be strictly positive")
    clustering_ratio = ws_report["average_clustering"] / random_clustering
    path_ratio = ws_report["average_shortest_path_length"] / random_path
    payload = {
        "schema_version": "paper1.mock-pure-structure-gate.v1",
        "matched_seed": matched_seed,
        "source_ws_artifact_id": ws_artifact.artifact_id,
        "source_ws_output_hash": ws_artifact.output_hash,
        "algorithms": {
            "gate": f"{STRUCTURE_GATE_ALGORITHM_ID}@{STRUCTURE_GATE_ALGORITHM_VERSION}",
            "ring_lattice": RING_LATTICE_ALGORITHM_ID,
            "random_null": RANDOM_NULL_ALGORITHM_ID,
            "library": {"name": "networkx", "version": NETWORKX_VERSION},
        },
        "parameters": {
            "n": n,
            "edge_count": ws_graph.number_of_edges(),
            "random_null_replicates": random_null_replicates,
            "disconnected_null_rule": "fail",
        },
        "baselines": {
            "ring_lattice": ring_report,
            "random_graphs": tuple(random_reports),
        },
        "observed_ws": ws_report,
        "relative_metrics": {
            "clustering_vs_ring_lattice": ws_report["average_clustering"]
            / ring_report["average_clustering"],
            "clustering_vs_random": clustering_ratio,
            "path_length_vs_random": path_ratio,
            "small_world_coefficient": clustering_ratio / path_ratio,
        },
        "opinion_inputs_read": (),
        "metadata": {"mock_only": True, "research_parameter_status": "not_frozen"},
    }
    return ArtifactEnvelope.create(
        artifact_type="paper1.mock_pure_structure_gate",
        schema_version=_ENVELOPE_VERSION,
        algorithm_id=STRUCTURE_GATE_ALGORITHM_ID,
        algorithm_version=STRUCTURE_GATE_ALGORITHM_VERSION,
        input_hashes={
            "ws_graph": ws_artifact.output_hash,
            "baseline_contract": canonical_payload_hash(
                {
                    "ring_lattice": RING_LATTICE_ALGORITHM_ID,
                    "random_null": RANDOM_NULL_ALGORITHM_ID,
                    "random_null_replicates": random_null_replicates,
                    "disconnected_null_rule": "fail",
                    "networkx_version": NETWORKX_VERSION,
                }
            ),
        },
        payload=payload,
        rng_provenance=(ring_provenance, random_provenance),
    )


def validate_structural_gate_artifact(
    artifact: ArtifactEnvelope, ws_artifact: ArtifactEnvelope
) -> Mapping[str, object]:
    """Recompute and validate the complete pure-structure gate contract."""

    validate_ws_artifact(ws_artifact)
    if artifact.artifact_type != "paper1.mock_pure_structure_gate":
        raise ValueError("structure gate artifact type does not match the contract")
    if artifact.algorithm_id != STRUCTURE_GATE_ALGORITHM_ID or (
        artifact.algorithm_version != STRUCTURE_GATE_ALGORITHM_VERSION
    ):
        raise ValueError("structure gate algorithm identity does not match the contract")
    if not isinstance(artifact.payload, Mapping):
        raise TypeError("structure gate payload must be a mapping")
    if artifact.payload.get("opinion_inputs_read") != ():
        raise ValueError("pure structure gate must not read opinion inputs")
    parameters = artifact.payload.get("parameters")
    if not isinstance(parameters, Mapping):
        raise ValueError("structure gate parameters are missing")
    replicates = parameters.get("random_null_replicates")
    _require_int("random_null_replicates", replicates, minimum=1)  # type: ignore[arg-type]
    expected = build_structural_gate_artifact(
        ws_artifact,
        matched_seed=ws_artifact.payload["matched_seed"],  # type: ignore[index,arg-type]
        random_null_replicates=replicates,  # type: ignore[arg-type]
        mock_only=True,
    )
    if artifact != expected:
        raise ValueError("structure gate audit, RNG, algorithm, or input hash drift detected")
    metrics = artifact.payload["relative_metrics"]
    assert isinstance(metrics, Mapping)
    return metrics
