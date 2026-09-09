"""Deterministic, replayable execution for offline Phase 0A probe cases."""

from __future__ import annotations

import time
from typing import Mapping

from ..domain import _require_id, _require_json_transport, _require_sha256, canonical_payload_hash
from .adapters import ProbeAdapter
from .contracts import (
    ProbeAttempt,
    ProbeCase,
    ProbeParseEvidence,
    ProbeRequest,
    ProbeResponse,
    ProbeRunProjection,
    ProbeRuntimePolicy,
)
from .parser import parse_probe_response


class ProbeRunCrash(RuntimeError):
    """Unexpected adapter crash carrying the last validated run projection."""

    def __init__(self, message: str, snapshot: ProbeRunProjection) -> None:
        super().__init__(message)
        self.snapshot = snapshot


def _snapshot(
    *,
    attempts: list[ProbeAttempt],
    run_instance_id: str,
    specification_hash: str,
    inventory_hash: str,
    runtime_policy: ProbeRuntimePolicy,
    generation_settings: Mapping[str, object],
    runtime_identity: Mapping[str, str],
    model_identity: Mapping[str, str],
    tokenizer_identity: Mapping[str, str],
    chat_template_hash: str,
    cases: tuple[ProbeCase, ...],
) -> ProbeRunProjection:
    return ProbeRunProjection.create(
        run_instance_id=run_instance_id,
        specification_hash=specification_hash,
        case_inventory_hash=inventory_hash,
        runtime_policy=runtime_policy,
        generation_settings=generation_settings,
        runtime_identity=runtime_identity,
        model_identity=model_identity,
        tokenizer_identity=tokenizer_identity,
        chat_template_hash=chat_template_hash,
        case_ids=tuple(item.probe_case_id for item in cases),
        attempts=tuple(attempts),
    )


def _inventory_hash(cases: tuple[ProbeCase, ...]) -> str:
    if type(cases) is not tuple or not cases:
        raise ValueError("cases must be a non-empty tuple")
    if any(not isinstance(case, ProbeCase) for case in cases):
        raise TypeError("cases must contain ProbeCase records")
    ids = [case.probe_case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("case inventory contains duplicate identities")
    return canonical_payload_hash(
        [case.to_payload() for case in sorted(cases, key=lambda item: item.probe_case_id)]
    )


def _execution_context_hash(
    *,
    generation_settings: Mapping[str, object],
    runtime_identity: Mapping[str, str],
    model_identity: Mapping[str, str],
    tokenizer_identity: Mapping[str, str],
    chat_template_hash: str,
) -> str:
    return canonical_payload_hash(
        {
            "generation_settings": generation_settings,
            "generation_settings_hash": canonical_payload_hash(generation_settings),
            "runtime_identity": runtime_identity,
            "model_identity": model_identity,
            "tokenizer_identity": tokenizer_identity,
            "chat_template_hash": chat_template_hash,
        }
    )


def _run_id(
    run_instance_id: str,
    specification_hash: str,
    inventory_hash: str,
    policy_hash: str,
    execution_context_hash: str,
) -> str:
    return "probe-run-" + canonical_payload_hash(
        {
            "run_instance_id": run_instance_id,
            "specification_hash": specification_hash,
            "case_inventory_hash": inventory_hash,
            "runtime_policy_hash": policy_hash,
            "execution_context_hash": execution_context_hash,
        }
    )


def _validate_inputs(
    *,
    specification_hash: str,
    cases: tuple[ProbeCase, ...],
    runtime_policy: ProbeRuntimePolicy,
    adapter: ProbeAdapter,
    generation_settings: Mapping[str, object],
    runtime_identity: Mapping[str, str],
    model_identity: Mapping[str, str],
    tokenizer_identity: Mapping[str, str],
    chat_template_hash: str,
) -> str:
    _require_sha256("specification_hash", specification_hash)
    if any(case.specification_hash != specification_hash for case in cases):
        raise ValueError("case specification hash drift detected")
    inventory_hash = _inventory_hash(cases)
    if not isinstance(runtime_policy, ProbeRuntimePolicy):
        raise TypeError("runtime_policy must be a ProbeRuntimePolicy")
    if not isinstance(adapter, ProbeAdapter):
        raise TypeError("adapter must implement ProbeAdapter")
    if not isinstance(generation_settings, Mapping) or not generation_settings:
        raise ValueError("generation_settings must be an explicit non-empty mapping")
    _require_json_transport(generation_settings, "generation_settings")
    expected_identity_fields = {
        "runtime_identity": (runtime_identity, ("provider", "runtime_version")),
        "model_identity": (model_identity, ("model", "revision")),
        "tokenizer_identity": (tokenizer_identity, ("tokenizer", "revision")),
    }
    for name, (identity, fields) in expected_identity_fields.items():
        if not isinstance(identity, Mapping) or tuple(identity) != fields:
            raise ValueError(f"{name} fields do not match the exact identity contract")
        if any(type(identity[field]) is not str or not identity[field].strip() for field in fields):
            raise ValueError(f"{name} values must be non-empty text")
    _require_sha256("chat_template_hash", chat_template_hash)
    return inventory_hash


def _validate_response_provenance(
    response: ProbeResponse,
    *,
    runtime_identity: Mapping[str, str],
    model_identity: Mapping[str, str],
    tokenizer_identity: Mapping[str, str],
    chat_template_hash: str,
) -> None:
    expected = (
        (response.runtime_identity, runtime_identity, "runtime identity"),
        (response.model_identity, model_identity, "model identity"),
        (response.tokenizer_identity, tokenizer_identity, "tokenizer identity"),
    )
    for actual, wanted, name in expected:
        if dict(actual) != dict(wanted):
            raise ValueError(f"{name} drift detected")
    if response.chat_template_hash != chat_template_hash:
        raise ValueError("chat template hash drift detected")


def _make_attempt(
    *,
    run_id: str,
    run_instance_id: str,
    specification_hash: str,
    inventory_hash: str,
    runtime_policy: ProbeRuntimePolicy,
    request: ProbeRequest,
    response: ProbeResponse,
    parse_evidence: ProbeParseEvidence | None,
    transport_counts: Mapping[str, int],
    retry_delay_seconds: float | None,
    retry_delay_source: str | None,
) -> ProbeAttempt:
    error_code = response.error_code
    transport_number = None if error_code is None else transport_counts[error_code]
    transport_budget = (
        None if error_code is None else runtime_policy.max_transport_attempts_by_code[error_code]
    )
    if response.outcome == "response":
        if parse_evidence is None:
            raise ValueError("semantic response requires versioned parse evidence")
        if not parse_evidence.success and parse_evidence.error["code"] == "refusal":
            status = "refused"
        elif parse_evidence.success:
            status = "parsed"
        else:
            status = "format_pending" if request.attempt_kind == "semantic" else "parse_failed"
    else:
        is_retryable = error_code in runtime_policy.retryable_error_codes
        exhausted = transport_number >= transport_budget  # type: ignore[operator]
        status = (
            "pending"
            if is_retryable and not exhausted and response.outcome != "oom"
            else "runtime_failed"
        )
        if status == "runtime_failed":
            retry_delay_seconds = None
            retry_delay_source = None
    return ProbeAttempt.create(
        probe_run_id=run_id,
        run_instance_id=run_instance_id,
        specification_hash=specification_hash,
        case_inventory_hash=inventory_hash,
        runtime_policy_hash=runtime_policy.record_hash,
        probe_case_id=request.probe_case_id,
        probe_case_hash=request.probe_case_hash,
        attempt_index=request.attempt_index,
        attempt_kind=request.attempt_kind,
        request=request,
        request_hash=request.record_hash,
        response=response,
        response_hash=response.record_hash,
        parse_evidence=parse_evidence,
        parse_evidence_hash=None if parse_evidence is None else parse_evidence.record_hash,
        transport_error_code=error_code,
        transport_retryable=(
            None if error_code is None else error_code in runtime_policy.retryable_error_codes
        ),
        transport_attempt_number_for_code=transport_number,
        transport_budget_for_code=transport_budget,
        retry_delay_seconds=retry_delay_seconds,
        retry_delay_source=retry_delay_source,
        case_status_after=status,
    )


def _continue_run(
    *,
    existing: tuple[ProbeAttempt, ...],
    run_instance_id: str,
    specification_hash: str,
    cases: tuple[ProbeCase, ...],
    inventory_hash: str,
    runtime_policy: ProbeRuntimePolicy,
    adapter: ProbeAdapter,
    generation_settings: Mapping[str, object],
    runtime_identity: Mapping[str, str],
    model_identity: Mapping[str, str],
    tokenizer_identity: Mapping[str, str],
    chat_template_hash: str,
    stop_after_attempts: int | None,
) -> ProbeRunProjection:
    if stop_after_attempts is not None:
        if type(stop_after_attempts) is not int or stop_after_attempts < 0:
            raise ValueError("stop_after_attempts must be a nonnegative integer or null")
    context_hash = _execution_context_hash(
        generation_settings=generation_settings,
        runtime_identity=runtime_identity,
        model_identity=model_identity,
        tokenizer_identity=tokenizer_identity,
        chat_template_hash=chat_template_hash,
    )
    run_id = _run_id(
        run_instance_id,
        specification_hash,
        inventory_hash,
        runtime_policy.record_hash,
        context_hash,
    )
    attempts = list(existing)
    made = 0
    by_case: dict[str, list[ProbeAttempt]] = {case.probe_case_id: [] for case in cases}
    for attempt in attempts:
        by_case[attempt.probe_case_id].append(attempt)
    for case in sorted(cases, key=lambda item: item.probe_case_id):
        chain = by_case[case.probe_case_id]
        current = "unstarted" if not chain else chain[-1].case_status_after
        if current in {"parsed", "parse_failed", "refused", "runtime_failed"}:
            continue
        transport_counts: dict[str, int] = {}
        for attempt in chain:
            if attempt.transport_error_code is not None:
                transport_counts[attempt.transport_error_code] = (
                    transport_counts.get(attempt.transport_error_code, 0) + 1
                )
        next_kind = "format_repair" if current == "format_pending" else "semantic"
        while current in {"unstarted", "pending", "format_pending"}:
            if stop_after_attempts is not None and made >= stop_after_attempts:
                return ProbeRunProjection.create(
                    run_instance_id=run_instance_id,
                    specification_hash=specification_hash,
                    case_inventory_hash=inventory_hash,
                    runtime_policy=runtime_policy,
                    generation_settings=generation_settings,
                    runtime_identity=runtime_identity,
                    model_identity=model_identity,
                    tokenizer_identity=tokenizer_identity,
                    chat_template_hash=chat_template_hash,
                    case_ids=tuple(item.probe_case_id for item in cases),
                    attempts=tuple(attempts),
                )
            try:
                if current == "pending":
                    retry_delay = chain[-1].retry_delay_seconds
                    if retry_delay is None:
                        raise ValueError("pending transport attempt requires retry delay evidence")
                    time.sleep(retry_delay)
                request = ProbeRequest.create(
                    case,
                    attempt_index=len(chain) + 1,
                    attempt_kind=next_kind,
                    generation_settings=generation_settings,
                )
                response = adapter.generate(request, timeout_seconds=runtime_policy.timeout_seconds)
                _validate_response_provenance(
                    response,
                    runtime_identity=runtime_identity,
                    model_identity=model_identity,
                    tokenizer_identity=tokenizer_identity,
                    chat_template_hash=chat_template_hash,
                )
                parse_evidence = None
                delay = None
                delay_source = None
                if response.outcome == "response":
                    parse_evidence = parse_probe_response(response)
                else:
                    error_code = response.error_code
                    if error_code not in runtime_policy.max_transport_attempts_by_code:
                        raise ValueError(
                            "adapter error code is outside the runtime policy partition"
                        )
                    if (
                        response.outcome == "oom"
                        and error_code not in runtime_policy.nonretryable_error_codes
                    ):
                        raise ValueError(
                            "OOM error codes must be explicitly classified as nonretryable"
                        )
                    transport_counts[error_code] = transport_counts.get(error_code, 0) + 1
                    retryable = error_code in runtime_policy.retryable_error_codes
                    exhausted = (
                        transport_counts[error_code]
                        >= runtime_policy.max_transport_attempts_by_code[error_code]
                    )
                    if retryable and not exhausted and response.outcome != "oom":
                        retry_after = response.retry_after_seconds
                        if runtime_policy.obey_retry_after and retry_after is not None:
                            if type(retry_after) not in {int, float} or float(retry_after) < 0:
                                raise ValueError("adapter retry-after evidence must be nonnegative")
                            delay = float(retry_after)
                            delay_source = "retry_after"
                        else:
                            delay = runtime_policy.backoff_seconds[transport_counts[error_code] - 1]
                            delay_source = "backoff"
                attempt = _make_attempt(
                    run_id=run_id,
                    run_instance_id=run_instance_id,
                    specification_hash=specification_hash,
                    inventory_hash=inventory_hash,
                    runtime_policy=runtime_policy,
                    request=request,
                    response=response,
                    parse_evidence=parse_evidence,
                    transport_counts=transport_counts,
                    retry_delay_seconds=delay,
                    retry_delay_source=delay_source,
                )
            except Exception as error:
                snapshot = _snapshot(
                    attempts=attempts,
                    run_instance_id=run_instance_id,
                    specification_hash=specification_hash,
                    inventory_hash=inventory_hash,
                    runtime_policy=runtime_policy,
                    generation_settings=generation_settings,
                    runtime_identity=runtime_identity,
                    model_identity=model_identity,
                    tokenizer_identity=tokenizer_identity,
                    chat_template_hash=chat_template_hash,
                    cases=cases,
                )
                raise ProbeRunCrash(
                    "probe attempt crashed before producing validated evidence", snapshot
                ) from error
            attempts.append(attempt)
            chain.append(attempt)
            made += 1
            current = attempt.case_status_after
            if current == "format_pending":
                next_kind = "format_repair"
            elif current == "pending":
                # Transport retries retain the semantic/format-repair purpose.
                next_kind = request.attempt_kind
    return ProbeRunProjection.create(
        run_instance_id=run_instance_id,
        specification_hash=specification_hash,
        case_inventory_hash=inventory_hash,
        runtime_policy=runtime_policy,
        generation_settings=generation_settings,
        runtime_identity=runtime_identity,
        model_identity=model_identity,
        tokenizer_identity=tokenizer_identity,
        chat_template_hash=chat_template_hash,
        case_ids=tuple(item.probe_case_id for item in cases),
        attempts=tuple(attempts),
    )


def execute_probe_run(
    *,
    run_instance_id: str,
    specification_hash: str,
    cases: tuple[ProbeCase, ...],
    runtime_policy: ProbeRuntimePolicy,
    adapter: ProbeAdapter,
    generation_settings: Mapping[str, object],
    runtime_identity: Mapping[str, str],
    model_identity: Mapping[str, str],
    tokenizer_identity: Mapping[str, str],
    chat_template_hash: str,
    stop_after_attempts: int | None = None,
) -> ProbeRunProjection:
    """Start one isolated run and execute cases in canonical order."""
    _require_id("run_instance_id", run_instance_id)
    inventory_hash = _validate_inputs(
        specification_hash=specification_hash,
        cases=cases,
        runtime_policy=runtime_policy,
        adapter=adapter,
        generation_settings=generation_settings,
        runtime_identity=runtime_identity,
        model_identity=model_identity,
        tokenizer_identity=tokenizer_identity,
        chat_template_hash=chat_template_hash,
    )
    return _continue_run(
        existing=(),
        run_instance_id=run_instance_id,
        specification_hash=specification_hash,
        cases=cases,
        inventory_hash=inventory_hash,
        runtime_policy=runtime_policy,
        adapter=adapter,
        generation_settings=generation_settings,
        runtime_identity=runtime_identity,
        model_identity=model_identity,
        tokenizer_identity=tokenizer_identity,
        chat_template_hash=chat_template_hash,
        stop_after_attempts=stop_after_attempts,
    )


def resume_probe_run(
    *,
    projection: ProbeRunProjection,
    specification_hash: str,
    cases: tuple[ProbeCase, ...],
    runtime_policy: ProbeRuntimePolicy,
    adapter: ProbeAdapter,
    generation_settings: Mapping[str, object],
    runtime_identity: Mapping[str, str],
    model_identity: Mapping[str, str],
    tokenizer_identity: Mapping[str, str],
    chat_template_hash: str,
    stop_after_attempts: int | None = None,
) -> ProbeRunProjection:
    """Resume only the exact same run after validating every frozen binding."""
    if not isinstance(projection, ProbeRunProjection):
        raise TypeError("projection must be a ProbeRunProjection")
    inventory_hash = _validate_inputs(
        specification_hash=specification_hash,
        cases=cases,
        runtime_policy=runtime_policy,
        adapter=adapter,
        generation_settings=generation_settings,
        runtime_identity=runtime_identity,
        model_identity=model_identity,
        tokenizer_identity=tokenizer_identity,
        chat_template_hash=chat_template_hash,
    )
    context_hash = _execution_context_hash(
        generation_settings=generation_settings,
        runtime_identity=runtime_identity,
        model_identity=model_identity,
        tokenizer_identity=tokenizer_identity,
        chat_template_hash=chat_template_hash,
    )
    expected_run_id = _run_id(
        projection.run_instance_id,
        specification_hash,
        inventory_hash,
        runtime_policy.record_hash,
        context_hash,
    )
    if (
        projection.probe_run_id != expected_run_id
        or projection.specification_hash != specification_hash
        or projection.case_inventory_hash != inventory_hash
        or projection.runtime_policy_hash != runtime_policy.record_hash
        or projection.execution_context_hash != context_hash
    ):
        raise ValueError("probe run specification, inventory, policy, or hash drift detected")
    settings_hash = canonical_payload_hash(generation_settings)
    if (
        projection.generation_settings_hash != settings_hash
        or projection.generation_settings != generation_settings
        or projection.runtime_identity != runtime_identity
        or projection.model_identity != model_identity
        or projection.tokenizer_identity != tokenizer_identity
        or projection.chat_template_hash != chat_template_hash
    ):
        raise ValueError("probe run execution context drift detected")
    if set(projection.case_statuses) != {case.probe_case_id for case in cases}:
        raise ValueError("probe run case inventory identities drift detected")
    for attempt in projection.attempts:
        if attempt.request.generation_settings_hash != settings_hash:
            raise ValueError("generation settings drift detected")
        _validate_response_provenance(
            attempt.response,
            runtime_identity=runtime_identity,
            model_identity=model_identity,
            tokenizer_identity=tokenizer_identity,
            chat_template_hash=chat_template_hash,
        )
    eligible = {"unstarted", "pending", "format_pending"}
    if any(value == "runtime_failed" for value in projection.case_statuses.values()) and not any(
        value in eligible for value in projection.case_statuses.values()
    ):
        raise ValueError("runtime_failed is irreversible within the same probe run")
    return _continue_run(
        existing=projection.attempts,
        run_instance_id=projection.run_instance_id,
        specification_hash=specification_hash,
        cases=cases,
        inventory_hash=inventory_hash,
        runtime_policy=runtime_policy,
        adapter=adapter,
        generation_settings=generation_settings,
        runtime_identity=runtime_identity,
        model_identity=model_identity,
        tokenizer_identity=tokenizer_identity,
        chat_template_hash=chat_template_hash,
        stop_after_attempts=stop_after_attempts,
    )
