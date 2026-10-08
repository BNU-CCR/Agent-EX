"""Offline command interface; no live HTTP or response text output."""

import json

from test_identity_network_benchmark_transport import DATA
from test_identity_network_benchmark_run import RUNTIME
from agent_ex.identity_network.benchmark_cli import main


def test_materialize_inspect_exclusive_output_and_no_stage_b(tmp_path, capsys):
    runtime = tmp_path / "runtime.json"
    runtime.write_text(json.dumps(RUNTIME), encoding="utf-8")
    packet = tmp_path / "packet.json"
    args = [
        "materialize",
        "--benchmark",
        str(DATA),
        "--runtime",
        str(runtime),
        "--mode",
        "preflight",
        "--out",
        str(packet),
    ]
    assert main(args) == 0
    assert len(json.loads(packet.read_text(encoding="utf-8"))["payload"]["entries"]) == 2
    assert main(args) == 2
    assert (
        main(
            [
                "inspect",
                "--benchmark",
                str(DATA),
                "--runtime",
                str(runtime),
                "--packet",
                str(packet),
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert '"top_k": 20' in output
    assert '"mode": "preflight"' in output


def test_missing_authorization_cli_does_not_write_archive(tmp_path, capsys):
    runtime = tmp_path / "runtime.json"
    runtime.write_text(json.dumps(RUNTIME), encoding="utf-8")
    packet = tmp_path / "packet.json"
    assert (
        main(
            [
                "materialize",
                "--benchmark",
                str(DATA),
                "--runtime",
                str(runtime),
                "--mode",
                "preflight",
                "--out",
                str(packet),
            ]
        )
        == 0
    )
    receipt = tmp_path / "receipt.json"
    receipt.write_text("{}", encoding="utf-8")
    assert (
        main(
            [
                "run",
                "--benchmark",
                str(DATA),
                "--runtime",
                str(runtime),
                "--packet",
                str(packet),
                "--root",
                str(tmp_path),
                "--receipt",
                str(receipt),
            ]
        )
        == 2
    )
    assert not (tmp_path / "benchmark.sqlite3").exists()
