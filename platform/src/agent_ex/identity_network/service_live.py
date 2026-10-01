"""Linux read-only process/listener observations; no health calls or service actions.

This is a momentary observation, not a lease: the runner must recheck before
dispatch. Host/container procfs and installed code are trusted input boundaries.
Never read socket contents, model responses, environment variables or raw reasons.
"""

from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sys
from uuid import UUID

from ..artifacts import ArtifactEnvelope
from ..domain import _require_int, _require_sha256, _require_timestamp, canonical_payload_hash
from ..phase0b.service_bridge import _SERVICE_START_FIELDS, _verified_record


_PROC_ROOT = Path("/proc")
_PLATFORM = sys.platform


def _readlink(path):
    return os.readlink(path)


def _hostname():
    return socket.gethostname()


def _utcnow():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def observe_linux_host():
    if _PLATFORM != "linux":
        raise ValueError("Linux procfs observations required")
    boot = (_PROC_ROOT / "sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    if str(UUID(boot)) != boot:
        raise ValueError("canonical Linux boot identity required")
    hostname = _hostname()
    if type(hostname) is not str or not hostname.strip():
        raise ValueError("explicit container hostname required")
    host_hash = canonical_payload_hash(
        {
            "schema_version": "paper1.identity-network.linux-host.v1",
            "boot_id": boot,
            "hostname": hostname,
        }
    )
    return ArtifactEnvelope.create(
        artifact_type="sis-linux-host-observation",
        schema_version="paper1.identity-network.linux-host-observation.v1",
        algorithm_id="sis-linux-boot-container-identity",
        algorithm_version="1.0.0",
        input_hashes={},
        rng_provenance=(),
        payload={
            "host_identity_hash": host_hash,
            "observed_at": _utcnow(),
            "dispatch_authorized": False,
            "formal_parameter_authority": False,
        },
    )


def _process_snapshot(pid):
    directory = _PROC_ROOT / str(pid)
    stat = (directory / "stat").read_text(encoding="utf-8")
    beginning, separator, remainder = stat.rpartition(") ")
    fields = remainder.split()
    if (
        not separator
        or beginning.split(" (", 1)[0] != str(pid)
        or len(fields) < 20
        or fields[0] in ("Z", "X", "x")
        or not fields[19].isdigit()
        or int(fields[19]) <= 0
    ):
        raise ValueError("live process stat/start identity invalid")
    with (directory / "cmdline").open("rb") as source:
        command = source.read(1024 * 1024 + 1)
    if not command or len(command) > 1024 * 1024 or not command.endswith(b"\0"):
        raise ValueError("live process command identity invalid")
    executable = _readlink(directory / "exe")
    if not executable.startswith("/") or executable.endswith(" (deleted)"):
        raise ValueError("live process executable identity invalid")
    return fields[19], hashlib.sha256(command).hexdigest(), executable


def _loopback_listener_inodes():
    inodes = set()
    for name, loopback in (("tcp", "0100007F"), ("tcp6", None)):
        lines = (_PROC_ROOT / "net" / name).read_text(encoding="ascii").splitlines()[1:]
        for line in lines:
            columns = line.split()
            if len(columns) < 10:
                raise ValueError("live listener table is malformed")
            address, port = columns[1].rsplit(":", 1)
            if columns[3] != "0A" or int(port, 16) != 8000:
                continue
            if address != loopback or not columns[9].isdigit() or int(columns[9]) <= 0:
                raise ValueError("live listener is not exclusive IPv4 loopback8000")
            inodes.add(columns[9])
    if not inodes:
        raise ValueError("live loopback8000 listener missing")
    return frozenset(inodes)


def _owned_socket_inodes(pid):
    owned = set()
    for fd in (_PROC_ROOT / str(pid) / "fd").iterdir():
        try:
            target = _readlink(fd)
        except FileNotFoundError:
            continue  # Other non-listening FDs may close during enumeration.
        match = re.fullmatch(r"socket:\[([0-9]+)\]", target)
        if match:
            owned.add(match[1])
    return owned


def observe_linux_service(start, *, expected_host_identity_hash):
    """Bind two consistent proc/listener snapshots to an exact recorded start."""
    try:
        host = observe_linux_host()
        _require_sha256("expected host", expected_host_identity_hash)
        if host.payload["host_identity_hash"] != expected_host_identity_hash:
            raise ValueError("live host differs from prior vacancy")
        start = _verified_record(
            "service start",
            start,
            _SERVICE_START_FIELDS,
            "paper1.calibration.service-start-identity.v1",
            judge_metadata=False,
        )
        _require_int("service PID", start["pid"], minimum=1)
        pid = start["pid"]
        expected = start["proc_start_time"], start["cmdline_sha256"], start["executable"]
        if _process_snapshot(pid) != expected:
            raise ValueError("live process differs from recorded start")
        namespace = _readlink(_PROC_ROOT / str(pid) / "ns/net")
        if namespace != _readlink(_PROC_ROOT / "self/ns/net"):
            raise ValueError("live process network namespace differs from client")
        before = _loopback_listener_inodes()
        if not before.issubset(_owned_socket_inodes(pid)):
            raise ValueError("live loopback listener belongs to another process")
        if (
            _process_snapshot(pid) != expected
            or before != _loopback_listener_inodes()
            or not before.issubset(_owned_socket_inodes(pid))
            or _readlink(_PROC_ROOT / str(pid) / "ns/net") != namespace
            or _readlink(_PROC_ROOT / "self/ns/net") != namespace
            or observe_linux_host().payload["host_identity_hash"] != expected_host_identity_hash
        ):
            raise ValueError("live service changed during observation")
        observed_at = _utcnow()
        if _require_timestamp("started_at", start["started_at"]) > _require_timestamp(
            "observed_at", observed_at
        ):
            raise ValueError("live service start is in the future")
        return ArtifactEnvelope.create(
            artifact_type="sis-linux-live-service-observation",
            schema_version="paper1.identity-network.live-service-observation.v1",
            algorithm_id="sis-proc-process-and-loopback-owner",
            algorithm_version="1.0.0",
            input_hashes={"service_start": start["record_hash"]},
            rng_provenance=(),
            payload={
                "host_identity_hash": expected_host_identity_hash,
                "observed_at": observed_at,
                "pid": pid,
                "proc_start_time": expected[0],
                "cmdline_sha256": expected[1],
                "executable": expected[2],
                "loopback_listener_owned": True,
                "dispatch_authorized": False,
                "formal_parameter_authority": False,
            },
        )
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ValueError("Linux live service observation refused") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("host")
    service = commands.add_parser("service")
    service.add_argument("--start", required=True)
    service.add_argument("--host-identity-hash", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "host":
            report = observe_linux_host()
        else:
            from .candidate_cli import _read

            report = observe_linux_service(
                _read(args.start), expected_host_identity_hash=args.host_identity_hash
            )
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print("Linux observation refused: " + type(exc).__name__, file=sys.stderr)
        return 2
    print(json.dumps(report.to_payload(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
