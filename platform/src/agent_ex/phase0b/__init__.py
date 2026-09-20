"""Public contracts for the preliminary Phase 0B real-Qwen diagnostic."""

from .contracts import (
    DiagnosticAdapterBinding,
    DiagnosticAttemptPolicy,
    DiagnosticRunAuthorization,
    DiagnosticTerminalReport,
)
from .matrix import DiagnosticMatrixCandidate, build_diagnostic_n20_matrix_candidate
from .pipeline import (
    DiagnosticEventLoopResult,
    DiagnosticEventState,
    DiagnosticPipelineEvidence,
    DiagnosticPipelineResult,
    DiagnosticPreparedEvent,
    apply_diagnostic_vllm_response,
    prepare_diagnostic_event,
    run_diagnostic_vllm_event_loop,
)
from .report import build_phase0b_preliminary_report
from .run import (
    DiagnosticFakeSliceResult,
    DiagnosticMatrixRunResult,
    DiagnosticRunPreflight,
    Phase0BJsonlStagingStore,
    preflight_diagnostic_run,
    run_fake_diagnostic_matrix,
    run_fake_diagnostic_slice,
    verify_diagnostic_matrix_run,
)
from .vllm_event_adapter import (
    PHASE0B_VLLM_ENDPOINT,
    Phase0BDispatchJournal,
    Phase0BVllmEventAdapter,
    Phase0BVllmEventRequest,
    Phase0BVllmEventResponse,
    Phase0BVllmTransportEvidence,
)

__all__ = [
    "DiagnosticAdapterBinding",
    "DiagnosticAttemptPolicy",
    "DiagnosticEventLoopResult",
    "DiagnosticEventState",
    "DiagnosticFakeSliceResult",
    "DiagnosticMatrixRunResult",
    "DiagnosticMatrixCandidate",
    "DiagnosticPipelineEvidence",
    "DiagnosticPipelineResult",
    "DiagnosticPreparedEvent",
    "DiagnosticRunPreflight",
    "DiagnosticRunAuthorization",
    "DiagnosticTerminalReport",
    "PHASE0B_VLLM_ENDPOINT",
    "Phase0BDispatchJournal",
    "Phase0BJsonlStagingStore",
    "Phase0BVllmEventAdapter",
    "Phase0BVllmEventRequest",
    "Phase0BVllmEventResponse",
    "Phase0BVllmTransportEvidence",
    "apply_diagnostic_vllm_response",
    "build_diagnostic_n20_matrix_candidate",
    "build_phase0b_preliminary_report",
    "preflight_diagnostic_run",
    "prepare_diagnostic_event",
    "run_fake_diagnostic_matrix",
    "run_diagnostic_vllm_event_loop",
    "run_fake_diagnostic_slice",
    "verify_diagnostic_matrix_run",
]
