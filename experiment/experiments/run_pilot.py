from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from config import deep_update, load_yaml
from llm_client import LLMClient
from network import build_ba_network, network_stats
from simulator import make_run_dir, run_simulation


PROVIDER_DEFAULTS = {
    "qwen_api": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3-8b",
        "api_key_env": "DASHSCOPE_API_KEY",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "api_key_env": "DEEPSEEK_API_KEY",
    },
    "vllm_local": {
        "base_url": "http://localhost:8000/v1",
        "model": "Qwen/Qwen2.5-7B-Instruct",
        "api_key_env": "VLLM_API_KEY",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local/API pilot experiment.")
    parser.add_argument("--config", default="config/experiment.yaml")
    parser.add_argument("--provider", choices=PROVIDER_DEFAULTS.keys(), default="qwen_api")
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument("--api-key-env")
    parser.add_argument("--n-agents", type=int)
    parser.add_argument("--n-rounds", type=int)
    parser.add_argument("--n-activated", type=int)
    parser.add_argument("--concurrency", type=int)
    parser.add_argument("--dry-run", action="store_true", help="Build network and config without calling an API.")
    return parser.parse_args()


def apply_cli_overrides(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    experiment_overrides: dict[str, Any] = {}
    generation_overrides: dict[str, Any] = {}

    if args.n_agents is not None:
        experiment_overrides["n_agents"] = args.n_agents
    if args.n_rounds is not None:
        experiment_overrides["n_rounds"] = args.n_rounds
    if args.n_activated is not None:
        experiment_overrides["n_activated_per_round"] = args.n_activated
    if args.concurrency is not None:
        generation_overrides["concurrency"] = args.concurrency

    if experiment_overrides:
        overrides["experiment"] = experiment_overrides
    if generation_overrides:
        overrides["generation"] = generation_overrides

    return deep_update(config, overrides)


def resolve_model_config(args: argparse.Namespace) -> dict[str, str]:
    model_config = dict(PROVIDER_DEFAULTS[args.provider])
    if args.base_url:
        model_config["base_url"] = args.base_url
    if args.model:
        model_config["model"] = args.model
    if args.api_key_env:
        model_config["api_key_env"] = args.api_key_env
    return model_config


async def main() -> None:
    args = parse_args()
    config_path = (ROOT / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    config = apply_cli_overrides(load_yaml(config_path), args)
    model_config = resolve_model_config(args)
    config["model"] = {"provider": args.provider, **model_config}

    n_agents = int(config["experiment"]["n_agents"])
    m = int(config["network"]["m"])
    seed = int(config.get("seed", 42))
    graph, agents = build_ba_network(n_agents=n_agents, m=m, seed=seed)

    results_dir = ROOT / config["output"]["results_dir"]
    run_dir = make_run_dir(results_dir)
    print(f"Run directory: {run_dir}")
    print(f"Network stats: {network_stats(graph)}")

    if args.dry_run:
        print("Dry run completed. No API calls were made.")
        return

    if args.provider == "vllm_local" and not os.environ.get(model_config["api_key_env"]):
        os.environ[model_config["api_key_env"]] = "EMPTY"

    client = LLMClient(
        base_url=model_config["base_url"],
        model=model_config["model"],
        api_key_env=model_config["api_key_env"],
        max_retries=int(config["generation"].get("max_retries", 2)),
        timeout_seconds=int(config["generation"].get("timeout_seconds", 60)),
    )
    summary = await run_simulation(graph, agents, client, config, run_dir)
    print("Simulation finished.")
    print(summary)


if __name__ == "__main__":
    asyncio.run(main())
