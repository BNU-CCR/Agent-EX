from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot pilot score dynamics.")
    parser.add_argument("--run-dir", required=True, help="Path to one results/pilot/<timestamp> directory.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_dir = Path(args.run_dir)
    metrics_path = run_dir / "round_metrics.csv"
    if not metrics_path.exists():
        raise FileNotFoundError(f"Missing metrics file: {metrics_path}")

    df = pd.read_csv(metrics_path)
    fig, axes = plt.subplots(2, 1, figsize=(8, 6), sharex=True)

    axes[0].plot(df["round"], df["mean_score"], marker="o")
    axes[0].set_ylabel("Mean score")
    axes[0].set_ylim(1, 10)
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(df["round"], df["variance_score"], marker="o", color="tab:orange")
    axes[1].set_xlabel("Round")
    axes[1].set_ylabel("Variance")
    axes[1].grid(True, alpha=0.3)

    fig.suptitle("Opinion score dynamics")
    fig.tight_layout()
    output_path = run_dir / "score_dynamics.png"
    fig.savefig(output_path, dpi=200)
    print(f"Saved figure to {output_path}")


if __name__ == "__main__":
    main()
