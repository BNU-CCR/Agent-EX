"""Public contracts for the preliminary Phase 0B real-Qwen diagnostic."""

from .contracts import (
    DiagnosticAdapterBinding,
    DiagnosticAttemptPolicy,
    DiagnosticRunAuthorization,
    DiagnosticTerminalReport,
)
from .matrix import DiagnosticMatrixCandidate, build_diagnostic_n20_matrix_candidate
from .run import (
    DiagnosticFakeSliceResult,
    DiagnosticRunPreflight,
    Phase0BJsonlStagingStore,
    preflight_diagnostic_run,
    run_fake_diagnostic_slice,
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
    "DiagnosticFakeSliceResult",
    "DiagnosticMatrixCandidate",
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
    "build_diagnostic_n20_matrix_candidate",
    "preflight_diagnostic_run",
    "run_fake_diagnostic_slice",
]
