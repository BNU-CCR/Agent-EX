from __future__ import annotations

import asyncio
import csv
import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from agent import build_messages
from llm_client import LLMClient, extract_score
from metrics import convergence_half_life, round_metrics
from network import build_neighbor_context, network_stats, sample_neighbors


def make_run_dir(results_dir: str | Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(results_dir) / timestamp
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def select_active_nodes(
    all_nodes: list[int],
    n_activated: int,
    rng: random.Random,
) -> list[int]:
    if n_activated >= len(all_nodes):
        return all_nodes[:]
    return sorted(rng.sample(all_nodes, n_activated))


async def run_simulation(
    graph,
    agents,
    client: LLMClient,
    config: dict[str, Any],
    run_dir: Path,
) -> dict[str, Any]:
    topic = config["topic"]
    seed = int(config.get("seed", 42))
    rng = random.Random(seed)

    experiment_cfg = config["experiment"]
    sampling_cfg = config["sampling"]
    generation_cfg = config["generation"]

    n_rounds = int(experiment_cfg["n_rounds"])
    n_activated = int(experiment_cfg["n_activated_per_round"])
    alpha = float(sampling_cfg["alpha"])
    max_neighbors = int(sampling_cfg["max_neighbors"])
    memory_window = int(sampling_cfg["memory_window"])
    temperature = float(generation_cfg["temperature"])
    max_tokens = int(generation_cfg["max_tokens"])
    enable_thinking = bool(generation_cfg.get("enable_thinking", False))
    concurrency = int(generation_cfg.get("concurrency", 2))

    raw_path = run_dir / "raw_outputs.jsonl"
    metrics_path = run_dir / "round_metrics.csv"
    semaphore = asyncio.Semaphore(concurrency)
    all_round_metrics: list[dict[str, Any]] = []
    all_nodes = list(graph.nodes())

    async def process_agent(round_id: int, node_id: int) -> dict[str, Any]:
        sampled = sample_neighbors(graph, node_id, alpha, max_neighbors, rng)
        neighbor_context = build_neighbor_context(agents, sampled, memory_window)
        messages = build_messages(agents[node_id], topic, neighbor_context)
        async with semaphore:
            raw_response = await asyncio.to_thread(
                client.generate,
                messages,
                temperature,
                max_tokens,
                enable_thinking,
            )
        parsed_score = extract_score(raw_response)
        parse_ok = parsed_score is not None
        final_score = parsed_score if parsed_score is not None else agents[node_id].current_score
        return {
            "round": round_id,
            "agent_id": node_id,
            "role_description": agents[node_id].role_description,
            "sampled_neighbors": sampled,
            "score": final_score,
            "parse_ok": parse_ok,
            "text": raw_response.strip(),
            "raw_response": raw_response,
        }

    with raw_path.open("w", encoding="utf-8") as raw_file:
        for round_id in range(1, n_rounds + 1):
            active_nodes = select_active_nodes(all_nodes, n_activated, rng)
            outputs = await asyncio.gather(
                *(process_agent(round_id, node_id) for node_id in active_nodes)
            )

            for row in outputs:
                agents[row["agent_id"]].add_record(
                    round_id=round_id,
                    text=row["text"],
                    score=int(row["score"]),
                )
                graph.nodes[row["agent_id"]]["current_score"] = int(row["score"])
                raw_file.write(json.dumps(row, ensure_ascii=False) + "\n")

            current_scores = [agent.current_score for agent in agents.values()]
            parse_ok_values = [bool(row["parse_ok"]) for row in outputs]
            metrics_row = round_metrics(round_id, current_scores, parse_ok_values)
            all_round_metrics.append(metrics_row)
            print(
                f"Round {round_id}/{n_rounds}: "
                f"mean={metrics_row['mean_score']:.2f}, "
                f"var={metrics_row['variance_score']:.2f}, "
                f"parse_fail={metrics_row['parse_failure_rate']:.0%}"
            )

    if all_round_metrics:
        with metrics_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(all_round_metrics[0].keys()))
            writer.writeheader()
            writer.writerows(all_round_metrics)
    else:
        metrics_path.touch()

    summary = {
        "run_dir": str(run_dir),
        "network_stats": network_stats(graph),
        "convergence_half_life": convergence_half_life(all_round_metrics),
        "final_metrics": all_round_metrics[-1] if all_round_metrics else None,
    }
    with (run_dir / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    with (run_dir / "config_used.yaml").open("w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
    with (run_dir / "network_stats.json").open("w", encoding="utf-8") as f:
        json.dump(network_stats(graph), f, ensure_ascii=False, indent=2)

    return summary
