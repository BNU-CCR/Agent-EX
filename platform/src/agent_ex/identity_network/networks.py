"""Bounded connected double-edge swaps, not legacy forbidden-edge shadows."""

import random
from typing import Mapping

import networkx as nx

from ..artifacts import ArtifactEnvelope
from ..domain import _require_int
from ..network import _canonical_edges, _structure_report, validate_ws_artifact
from ..rng import RNGProvenance


def build_randomized_counterpart(
    ws_artifact: ArtifactEnvelope,
    *,
    matched_seed: int,
    swap_target: int,
    max_trials: int,
) -> ArtifactEnvelope:
    _require_int("matched_seed", matched_seed)
    _require_int("swap_target", swap_target, minimum=1)
    _require_int("max_trials", max_trials, minimum=1)
    validate_ws_artifact(ws_artifact)
    if matched_seed != ws_artifact.payload["matched_seed"]:
        raise ValueError("matched seed must equal the WS counterpart seed")
    graph = nx.Graph()
    graph.add_nodes_from(ws_artifact.payload["nodes"])
    graph.add_edges_from(ws_artifact.payload["edges"])
    if not nx.is_connected(graph):
        raise ValueError("WS counterpart must be connected")
    rng = RNGProvenance.create(
        matched_seed=matched_seed,
        namespace="identity_network_randomized",
        coordinates={
            "artifact_kind": "identity_network_randomized",
            "ws_hash": ws_artifact.output_hash,
            "swap_target": swap_target,
            "max_trials": max_trials,
        },
    )
    local = random.Random(rng.derived_seed)
    accepted = 0
    trials = 0
    # Freeze and replay graph construction once, never inside the event loop.
    while trials < max_trials and accepted < swap_target:
        trials += 1
        (a, b), (c, d) = local.sample(_canonical_edges(graph.edges), 2)
        if len({a, b, c, d}) != 4:
            continue
        if local.randrange(2):
            c, d = d, c
        if graph.has_edge(a, c) or graph.has_edge(b, d):
            continue
        graph.remove_edges_from(((a, b), (c, d)))
        graph.add_edges_from(((a, c), (b, d)))
        if not nx.is_connected(graph):
            graph.remove_edges_from(((a, c), (b, d)))
            graph.add_edges_from(((a, b), (c, d)))
            continue
        accepted += 1
    if accepted != swap_target:
        raise ValueError("swap budget exhausted before target; no graph emitted")
    edges = _canonical_edges(graph.edges)
    if edges == tuple(ws_artifact.payload["edges"]):
        raise ValueError("swaps returned the original graph; choose an explicit different budget")
    return ArtifactEnvelope.create(
        artifact_type="identity_network_randomized_graph",
        schema_version="paper1.artifact-envelope.v1",
        algorithm_id="paper1.connected_degree_preserving_double_swap",
        algorithm_version="1.0.0",
        input_hashes={"ws": ws_artifact.output_hash},
        rng_provenance=(rng,),
        payload={
            "matched_seed": matched_seed,
            "nodes": tuple(sorted(graph.nodes)),
            "edges": edges,
            "swap_target": swap_target,
            "max_trials": max_trials,
            "accepted_swaps": accepted,
            "attempted_swaps": trials,
            "original_edge_overlap": len(set(edges) & set(ws_artifact.payload["edges"])),
            "structure_report": _structure_report(graph),
            "networkx_version": nx.__version__,
            "metadata": {
                "status": "preliminary",
                "research_parameter_status": "not_frozen",
                "formal_parameter_authority": False,
            },
        },
    )


def validate_randomized_counterpart(
    artifact: ArtifactEnvelope,
    ws_artifact: ArtifactEnvelope,
) -> Mapping[str, object]:
    if not isinstance(artifact, ArtifactEnvelope):
        raise TypeError("expected ArtifactEnvelope")
    try:
        replay = build_randomized_counterpart(
            ws_artifact,
            matched_seed=artifact.payload["matched_seed"],
            swap_target=artifact.payload["swap_target"],
            max_trials=artifact.payload["max_trials"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid randomized graph replay inputs") from exc
    if artifact != replay:
        raise ValueError("randomized graph fails deterministic replay")
    return artifact.payload["structure_report"]
