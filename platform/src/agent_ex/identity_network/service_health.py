"""Bounded loopback health observation, not approval or permission to dispatch."""

import hashlib
import argparse
import json
import sys
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

from ..artifacts import ArtifactEnvelope
from .service_live import observe_linux_service


_ENDPOINT = "http://127.0.0.1:8000/health"


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _read_health():
    # Ignore ambient HTTP_PROXY and prohibit forwarding a local request elsewhere.
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    with opener.open(_ENDPOINT, timeout=5) as response:
        if response.getcode() != 200:
            raise ValueError("service health must return HTTP200")
        body = response.read(8193)
        if len(body) > 8192:
            raise ValueError("service health response exceeds limit")
        return body


def observe_service_health(start, *, expected_host_identity_hash):
    """Observe recorded process/listener before and after a fresh health request.

    Procfs and installed code are trusted boundaries. This is not an atomic lease,
    model identity proof, or a substitute for approval/source/environment checks.
    Only the health body hash is retained; no completion endpoint is contacted.
    """
    before = observe_linux_service(start, expected_host_identity_hash=expected_host_identity_hash)
    try:
        body = _read_health()
    except (OSError, ValueError) as exc:
        raise ValueError("live service health refused") from exc
    after = observe_linux_service(start, expected_host_identity_hash=expected_host_identity_hash)
    identity = ("host_identity_hash", "pid", "proc_start_time", "cmdline_sha256", "executable")
    if any(before.payload[key] != after.payload[key] for key in identity):
        raise ValueError("service identity changed across health request")
    return ArtifactEnvelope.create(
        artifact_type="sis-live-service-health-observation",
        schema_version="paper1.identity-network.live-service-health.v1",
        algorithm_id="sis-bracketed-loopback-health",
        algorithm_version="1.0.0",
        input_hashes={
            "service_start": before.input_hashes["service_start"],
            "before": before.output_hash,
            "after": after.output_hash,
        },
        rng_provenance=(),
        payload={
            "endpoint": _ENDPOINT,
            "status_code": 200,
            "response_sha256": hashlib.sha256(body).hexdigest(),
            "response_size": len(body),
            "before_observed_at": before.payload["observed_at"],
            "observed_at": after.payload["observed_at"],
            "host_identity_hash": expected_host_identity_hash,
            "dispatch_authorized": False,
            "formal_parameter_authority": False,
        },
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True)
    parser.add_argument("--host-identity-hash", required=True)
    args = parser.parse_args(argv)
    try:
        from .candidate_cli import _read

        result = observe_service_health(
            _read(args.start), expected_host_identity_hash=args.host_identity_hash
        )
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print("Health observation refused: " + type(exc).__name__, file=sys.stderr)
        return 2
    print(json.dumps(result.to_payload(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
