"""Offline materialize/inspect and gated run/resume/verify/report commands."""

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import sys

from ..artifacts import ArtifactEnvelope
from ..domain import _json_ready
from .benchmark_run import build_bound_packet, run_benchmark, verify_benchmark, _validate_packet
from .dispatch import _strict_json
from .manipulation_store import file_signature


def _load(path):
    target = Path(path).absolute()
    info = file_signature(target)
    if info[2] > 16 * 1024 * 1024:
        raise ValueError("input JSON exceeds bounded size")
    content = target.read_text(encoding="utf-8")
    if file_signature(target) != info:
        raise ValueError("input changed during read")
    return _strict_json(content)


def _write_new(path, payload):
    target = Path(path).absolute()
    data = (
        json.dumps(_json_ready(payload), ensure_ascii=False, allow_nan=False, indent=2).encode(
            "utf-8"
        )
        + b"\n"
    )
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    snapshot = sub.add_parser(
        "runtime-snapshot", help="read local model files, do not load model or call HTTP"
    )
    snapshot.add_argument("--model-dir", required=True)
    snapshot.add_argument("--revision", required=True)
    snapshot.add_argument("--served-model-name", required=True)
    snapshot.add_argument("--out", required=True)
    for command in ("materialize", "inspect", "run", "resume", "verify", "report"):
        item = sub.add_parser(command)
        item.add_argument("--benchmark", required=True)
        item.add_argument("--runtime", required=True)
        if command == "materialize":
            item.add_argument("--mode", choices=("preflight", "stage-a"), required=True)
            item.add_argument("--out", required=True)
        else:
            item.add_argument("--packet", required=True)
            if command in {"run", "resume", "verify", "report"}:
                item.add_argument("--root", required=True)
            if command in {"run", "resume"}:
                item.add_argument("--receipt", required=True)
                item.add_argument("--preflight-root")
            if command == "report":
                item.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "runtime-snapshot":
            from .benchmark_snapshot import snapshot_runtime

            runtime = snapshot_runtime(
                args.model_dir,
                model_revision=args.revision,
                served_model_name=args.served_model_name,
                vllm_version=importlib.metadata.version("vllm"),
            )
            _write_new(args.out, runtime)
            print(json.dumps(runtime, ensure_ascii=False, indent=2))
            return 0
        benchmark, runtime = _load(args.benchmark), _load(args.runtime)
        if args.command == "materialize":
            packet = build_bound_packet(benchmark, runtime, mode=args.mode)
            _write_new(args.out, packet.to_payload())
            result = {
                "packet_hash": packet.output_hash,
                "mode": args.mode,
                "dispatch_authorized": False,
            }
        else:
            packet = ArtifactEnvelope.from_payload(_load(args.packet))
            _validate_packet(benchmark, packet, runtime)
            if args.command == "inspect":
                result = {
                    "packet_hash": packet.output_hash,
                    "mode": packet.payload["mode"],
                    "trial_count": len(packet.payload["entries"]),
                    "runtime": runtime,
                    "dispatch_authorized": False,
                    "request_examples": [
                        json.loads(entry["wire_body"]) for entry in packet.payload["entries"][:2]
                    ],
                }
            elif args.command in {"run", "resume"}:
                result = run_benchmark(
                    args.root,
                    benchmark=benchmark,
                    packet=packet,
                    runtime=runtime,
                    receipt=_load(args.receipt),
                    resume=args.command == "resume",
                    preflight_root=args.preflight_root,
                )
            else:
                result = verify_benchmark(
                    args.root, benchmark=benchmark, packet=packet, runtime=runtime
                )
                if args.command == "report":
                    _write_new(args.out, result)
        print(json.dumps(_json_ready(result), ensure_ascii=False, allow_nan=False, indent=2))
        return 0
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        RuntimeError,
        importlib.metadata.PackageNotFoundError,
    ) as error:
        print(f"benchmark command refused: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
