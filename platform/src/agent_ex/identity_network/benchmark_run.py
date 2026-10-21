"""Stage-A local orchestration and report; actual dispatch requires explicit receipt."""

from datetime import datetime, timezone
import http.client
from pathlib import Path
import re
import subprocess

from ..artifacts import ArtifactEnvelope
from ..domain import _json_ready, canonical_payload_hash
from .benchmark_adapter import BenchmarkVllmAdapter, SAMPLING
from .benchmark_analysis import analyze_benchmark_outcomes
from .benchmark_store import BenchmarkStore
from .benchmark_trials import build_benchmark_trial_inventory
from .benchmark_transport import build_benchmark_transport_candidate
from .benchmark_stage_b import B_MODES, validate_stage_a_report, stage_a_report_payload
from .manipulation_lock import ManipulationRunLock

BENCHMARK_HASH = "9c2345580024523794a2d433500229d55e166414f18f5c0bd06baba893c8eb10"
RUNTIME_KEYS = {
    "model_id",
    "model_revision",
    "model_files_hash",
    "tokenizer_hash",
    "chat_template_hash",
    "vllm_version",
    "dtype",
    "enable_thinking",
    "served_model_name",
    "endpoint",
}


def validate_runtime(runtime):
    if type(runtime) is not dict or set(runtime) != RUNTIME_KEYS:
        raise ValueError("exact complete runtime identity required")
    if (
        runtime["model_id"] != "Qwen/Qwen3-8B"
        or runtime["dtype"] != "bfloat16"
        or runtime["enable_thinking"] is not False
    ):
        raise ValueError("approved model/BF16/nonthinking binding required")
    if (
        type(runtime["model_revision"]) is not str
        or re.fullmatch(r"[0-9a-f]{40}", runtime["model_revision"]) is None
    ):
        raise ValueError("exact model revision required")
    for field in ("model_files_hash", "tokenizer_hash", "chat_template_hash"):
        if type(runtime[field]) is not str or re.fullmatch(r"[0-9a-f]{64}", runtime[field]) is None:
            raise ValueError("complete runtime content hashes required")
    for field in ("vllm_version", "served_model_name"):
        if (
            type(runtime[field]) is not str
            or not runtime[field].strip()
            or "UNRESOLVED" in runtime[field]
        ):
            raise ValueError("explicit observed runtime value required")
    if runtime["endpoint"] != "http://127.0.0.1:8000/v1/chat/completions":
        raise ValueError("local vLLM endpoint required")
    return canonical_payload_hash(runtime)


def build_bound_packet(benchmark, runtime, *, mode, stage_a_report=None):
    runtime_hash = validate_runtime(runtime)
    if mode in B_MODES:
        stage_a_report = stage_a_report_payload(stage_a_report)
        validate_stage_a_report(
            stage_a_report,
            runtime_hash=runtime_hash,
            packet_hash=build_bound_packet(benchmark, runtime, mode="stage-a").output_hash,
        )
    candidate = build_benchmark_transport_candidate(
        benchmark=benchmark,
        expected_hash=BENCHMARK_HASH,
        generation_settings=SAMPLING,
        served_model_name=runtime["served_model_name"],
        adapter_binding_hash=runtime_hash,
        mode=mode,
        stage_a_report=stage_a_report,
    )
    return ArtifactEnvelope.create(
        artifact_type="sis-stage-b-bound-packet" if mode in B_MODES else "sis-stage-a-bound-packet",
        schema_version="sis.stage-b.bound-packet.v1"
        if mode in B_MODES
        else "sis.stage-a.bound-packet.v1",
        algorithm_id="sis-stage-b-runtime-binding"
        if mode in B_MODES
        else "sis-stage-a-runtime-binding",
        algorithm_version="1.0.0",
        input_hashes={**dict(candidate.input_hashes), "runtime": runtime_hash},
        rng_provenance=(),
        payload={
            **_json_ready(candidate.payload),
            "runtime": runtime,
            "runtime_identity_recorded": True,
            "runtime_live_verified": False,
            "runtime_approved": False,
            "dispatch_authorized": False,
        },
    )


def _validate_packet(benchmark, packet, runtime):
    if packet != build_bound_packet(
        benchmark,
        runtime,
        mode=packet.payload["mode"],
        stage_a_report=packet.payload.get("stage_a_evidence"),
    ):
        raise ValueError("packet differs from frozen source/runtime derivation")


def validate_receipt(receipt, packet, runtime, *, require_current=True):
    fields = {
        "schema_version",
        "packet_hash",
        "runtime_hash",
        "source_commit",
        "approved_by",
        "decision",
        "expires_at",
        "mode",
    }
    if (
        type(receipt) is not dict
        or set(receipt) != fields
        or receipt["schema_version"] != "sis.stage-a.run-approval.v1"
    ):
        raise ValueError("exact human execution receipt required")
    if (
        receipt["decision"] != "approve"
        or receipt["mode"] != packet.payload["mode"]
        or receipt["packet_hash"] != packet.output_hash
        or receipt["runtime_hash"] != validate_runtime(runtime)
    ):
        raise ValueError("execution approval does not bind current packet/runtime/mode")
    if type(receipt["approved_by"]) is not str or not receipt["approved_by"].strip():
        raise ValueError("human approval attribution required")
    if (
        type(receipt["source_commit"]) is not str
        or re.fullmatch(r"[0-9a-f]{40}", receipt["source_commit"]) is None
    ):
        raise ValueError("exact source commit required")
    try:
        expiry = datetime.fromisoformat(receipt["expires_at"])
        if expiry.tzinfo is None or (require_current and expiry <= datetime.now(timezone.utc)):
            raise ValueError("expired or timezone-free execution approval")
    except (TypeError, ValueError) as error:
        raise ValueError("valid unexpired execution approval required") from error


def _verify_source_checkout(commit):
    root = Path(__file__).resolve().parents[4]
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--", "platform/src"], cwd=root, text=True
    ).strip()
    if current != commit or dirty:
        raise ValueError("executing source checkout differs from approved clean commit")
    expected = root / "platform/src/agent_ex/identity_network/benchmark_run.py"
    if expected.resolve() != Path(__file__).resolve():
        raise ValueError("module origin differs from approved source checkout")


def _verify_stage_a_store(stage_a_root, *, benchmark, packet, runtime):
    if packet.payload["mode"] not in B_MODES:
        return
    if stage_a_root is None:
        raise ValueError("actual complete Stage-A store required for Stage-B")
    a_packet = build_bound_packet(benchmark, runtime, mode="stage-a")
    actual = verify_benchmark(stage_a_root, benchmark=benchmark, packet=a_packet, runtime=runtime)
    validate_stage_a_report(
        actual, runtime_hash=validate_runtime(runtime), packet_hash=a_packet.output_hash
    )
    if canonical_payload_hash(stage_a_report_payload(actual)) != canonical_payload_hash(
        packet.payload["stage_a_evidence"]
    ):
        raise ValueError("Stage-A cold execution evidence differs from bound report")


def run_benchmark(
    root,
    *,
    benchmark,
    packet,
    runtime,
    receipt,
    resume,
    preflight_root=None,
    stage_a_root=None,
    connection_factory=http.client.HTTPConnection,
):
    _validate_packet(benchmark, packet, runtime)
    validate_receipt(receipt, packet, runtime)
    _verify_stage_a_store(stage_a_root, benchmark=benchmark, packet=packet, runtime=runtime)
    _verify_source_checkout(receipt["source_commit"])
    if packet.payload["mode"] in {"stage-a", "stage-b"}:
        if preflight_root is None:
            raise ValueError("verified independent two-event preflight required")
        preflight = build_bound_packet(
            benchmark,
            runtime,
            mode="preflight-b" if packet.payload["mode"] == "stage-b" else "preflight",
            stage_a_report=packet.payload.get("stage_a_evidence"),
        )
        technical = BenchmarkStore.verify(preflight_root, pack=preflight)
        if technical["phase"] != "COMPLETE" or technical["valid_count"] != 2:
            raise ValueError("two-event technical preflight incomplete")
        validate_receipt(technical["execution_receipt"], preflight, runtime, require_current=False)
        if technical["execution_receipt"]["source_commit"] != receipt["source_commit"]:
            raise ValueError("technical preflight used a different source commit")
    with ManipulationRunLock.acquire(root) as lease:
        opener = BenchmarkStore.open if resume else BenchmarkStore.create
        with opener(root, pack=packet, lease=lease, receipt=receipt) as store:
            adapter = BenchmarkVllmAdapter(
                runtime["endpoint"],
                served_model_name=runtime["served_model_name"],
                connection_factory=connection_factory,
            )
            adapter.bind_dispatch_journal(store.record_before_dispatch)
            while True:
                state = store.summary()
                if state["saved_response_pending"]:
                    store.resolve_saved_response()
                elif state["next_action"] == "DISPATCH":
                    response = adapter.generate(store.current_request(), timeout_seconds=180.0)
                    store.save_response(response)
                    store.resolve_saved_response()
                else:
                    return store.summary()


def verify_benchmark(root, *, benchmark, packet, runtime, stage_a_root=None):
    _validate_packet(benchmark, packet, runtime)
    _verify_stage_a_store(stage_a_root, benchmark=benchmark, packet=packet, runtime=runtime)
    evidence = BenchmarkStore.verify(root, pack=packet)
    outcomes = evidence.pop("outcomes")
    historical_receipt = evidence.pop("execution_receipt")
    validate_receipt(historical_receipt, packet, runtime, require_current=False)
    result = {
        **evidence,
        "transport_evidence_verified": True,
        "runtime_hash": validate_runtime(runtime),
        "stage_b_dispatch_authorized": False,
        "status": "preliminary",
        "outcomes_hash": canonical_payload_hash(outcomes),
        **(
            {"stage": "stable_group", "stage_c_dispatch_authorized": False}
            if packet.payload["mode"] in B_MODES
            else {}
        ),
    }
    if packet.payload["mode"] in {"preflight", "preflight-b"}:
        return {
            **result,
            "technical_preflight_passed": evidence["phase"] == "COMPLETE" and len(outcomes) == 2,
        }
    inventory = build_benchmark_trial_inventory(
        benchmark, expected_hash=BENCHMARK_HASH, stage=packet.payload["stage"]
    )
    analysis = analyze_benchmark_outcomes(
        benchmark, inventory, outcomes, expected_hash=BENCHMARK_HASH
    )
    return {**result, "analysis": analysis}
