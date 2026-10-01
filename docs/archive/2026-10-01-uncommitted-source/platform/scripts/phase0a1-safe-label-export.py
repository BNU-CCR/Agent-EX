#!/usr/bin/env python3
"""Emit a hash-bound raw-free label export from one immutable judge projection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from agent_ex.calibration.safe_label_export import build_safe_label_export


class _FailClosedArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError("invalid command line")


def _run() -> str:
    parser = _FailClosedArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--approval-receipt", type=Path, required=True)
    parser.add_argument("--approved-receipt-hash", required=True)
    args = parser.parse_args()
    payload = build_safe_label_export(
        run_root=args.run_root,
        approval_receipt_path=args.approval_receipt,
        approved_receipt_hash=args.approved_receipt_hash,
    )
    return json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True)


def main() -> int:
    try:
        encoded = _run()
    except Exception:
        sys.stderr.write("SAFE_LABEL_EXPORT_FAILED:E001\n")
        return 2
    sys.stdout.write(f"{encoded}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
