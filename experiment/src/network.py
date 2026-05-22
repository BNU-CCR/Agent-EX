from __future__ import annotations

import random
from collections.abc import Mapping
from typing import Any

import networkx as nx
import numpy as np

from agent import Agent, default_roles


def build_ba_network(n_agents: int, m: int, seed: int) -> tuple[nx.Graph, dict[int, Agent]]:
    if n_agents <= m:
        raise ValueError("n_agents must be greater than BA parameter m")

    graph = nx.barabasi_albert_graph(n_agents, m, seed=seed)
    roles = default_roles()
    rng = np.random.default_rng(seed)
    agents: dict[int, Agent] = {}

    for node_id in graph.nodes:
        role_info = roles[node_id % len(roles)]
        role_description, initial_score, stubbornness = role_info
        agents[node_id] = Agent(
            agent_id=node_id,
            role_description=role_description,
            initial_score=initial_score,
            current_score=initial_score,
            stubbornness=stubbornness,
        )
        graph.nodes[node_id]["role_description"] = role_description
        graph.nodes[node_id]["initial_score"] = initial_score
        graph.nodes[node_id]["current_score"] = initial_score
        graph.nodes[node_id]["stubbornness"] = stubbornness

    return graph, agents


def network_stats(graph: nx.Graph) -> dict[str, Any]:
    degrees = [degree for _, degree in graph.degree()]
    return {
        "n_nodes": graph.number_of_nodes(),
        "n_edges": graph.number_of_edges(),
        "average_degree": float(np.mean(degrees)) if degrees else 0.0,
        "max_degree": int(max(degrees)) if degrees else 0,
        "min_degree": int(min(degrees)) if degrees else 0,
    }


def sample_neighbors(
    graph: nx.Graph,
    node_id: int,
    alpha: float,
    max_neighbors: int,
    rng: random.Random,
) -> list[int]:
    neighbors = list(graph.neighbors(node_id))
    if not neighbors:
        return []

    sample_size = min(max_neighbors, len(neighbors))
    if alpha == 0:
        return rng.sample(neighbors, sample_size)

    weights = [graph.degree(neighbor) ** alpha for neighbor in neighbors]
    selected: list[int] = []
    available = neighbors[:]
    available_weights = weights[:]

    for _ in range(sample_size):
        chosen = rng.choices(available, weights=available_weights, k=1)[0]
        idx = available.index(chosen)
        selected.append(chosen)
        available.pop(idx)
        available_weights.pop(idx)

    return selected


def build_neighbor_context(
    agents: Mapping[int, Agent],
    sampled_neighbors: list[int],
    memory_window: int,
) -> str:
    lines: list[str] = []
    for neighbor_id in sampled_neighbors:
        neighbor = agents[neighbor_id]
        records = neighbor.visible_history(memory_window)
        if not records:
            lines.append(
                f"邻居{neighbor_id}（{neighbor.role_description}）：尚未发言；初始评分 {neighbor.current_score}/10。"
            )
            continue
        for record in records:
            lines.append(
                f"邻居{neighbor_id} 第{record.round_id}轮（评分{record.score}/10）：{record.text}"
            )
    return "\n".join(lines)
