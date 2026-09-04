"""Thin mock-only orchestration over the strict serial event pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence

from .adapters.mock import MockAdapter
from .checkpoint import (
    build_checkpoint,
    build_checkpoint_with_projection,
    write_checkpoint_atomic,
)
from .domain import _freeze, derive_event_id
from .engine import AttemptInvocationResult
from .execution_evidence import MockAttemptPolicyBinding
from .parser import ParserLimits
from .pipeline import MockEventPipeline
from .prompt import PromptLimits
from .storage import RunStorage


def _strict_nonnegative_integer(name: str, value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative strict integer")
    return value


@dataclass(frozen=True, slots=True)
class MockEventInvocation:
    event_ordinal: int
    event_id: str
    feed_capacity: int
    memory_window: int
    parser_limits: ParserLimits
    prompt_limits: PromptLimits
    policy: MockAttemptPolicyBinding
    model_identity: Mapping[str, str]
    request_parameters: Mapping[str, object]
    model_seed: int
    adapter: MockAdapter
    reconciliation: AttemptInvocationResult | None
    http_status: int | None
    usage: Mapping[str, object]
    finish_reason: str | None

    def __post_init__(self) -> None:
        _strict_nonnegative_integer("event_ordinal", self.event_ordinal)
        if type(self.event_id) is not str or not self.event_id:
            raise ValueError("event_id must be non-empty text")
        for name in ("feed_capacity", "memory_window"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive strict integer")
        if not isinstance(self.parser_limits, ParserLimits):
            raise TypeError("parser_limits must be typed")
        if not isinstance(self.prompt_limits, PromptLimits):
            raise TypeError("prompt_limits must be typed")
        if not isinstance(self.policy, MockAttemptPolicyBinding):
            raise TypeError("policy must be a MockAttemptPolicyBinding")
        if not isinstance(self.model_identity, Mapping) or not self.model_identity:
            raise ValueError("model_identity must be a non-empty mapping")
        if not all(
            type(key) is str and type(value) is str for key, value in self.model_identity.items()
        ):
            raise TypeError("model_identity must contain text keys and values")
        if not isinstance(self.request_parameters, Mapping):
            raise TypeError("request_parameters must be a mapping")
        if type(self.model_seed) is not int:
            raise TypeError("model_seed must be a strict integer")
        if not isinstance(self.adapter, MockAdapter):
            raise TypeError("adapter must be a MockAdapter")
        if self.reconciliation is not None and not isinstance(
            self.reconciliation, AttemptInvocationResult
        ):
            raise TypeError("reconciliation must be typed or None")
        if self.http_status is not None and type(self.http_status) is not int:
            raise TypeError("http_status must be a strict integer or None")
        if not isinstance(self.usage, Mapping):
            raise TypeError("usage must be a mapping")
        if self.finish_reason is not None and type(self.finish_reason) is not str:
            raise TypeError("finish_reason must be text or None")
        object.__setattr__(self, "model_identity", _freeze(self.model_identity))
        object.__setattr__(self, "request_parameters", _freeze(self.request_parameters))
        object.__setattr__(self, "usage", _freeze(self.usage))


@dataclass(frozen=True, slots=True)
class MockRunControl:
    target_event_ordinal: int
    checkpoint_ordinals: tuple[int, ...]
    checkpoint_paths: tuple[Path, ...]

    def __post_init__(self) -> None:
        _strict_nonnegative_integer("target_event_ordinal", self.target_event_ordinal)
        if not isinstance(self.checkpoint_ordinals, tuple) or not all(
            type(value) is int for value in self.checkpoint_ordinals
        ):
            raise TypeError("checkpoint_ordinals must be a tuple of strict integers")
        if not isinstance(self.checkpoint_paths, tuple) or not all(
            isinstance(value, Path) for value in self.checkpoint_paths
        ):
            raise TypeError("checkpoint_paths must be a tuple of Paths")


@dataclass(frozen=True, slots=True)
class MockRunReport:
    run_id: str
    starting_event_ordinal: int
    next_event_ordinal: int
    executed_event_count: int
    completed: bool
    checkpoint_hashes: Mapping[int, str]
    final_checkpoint_hash: str
    final_storage_projection_hash: str

    def __post_init__(self) -> None:
        if type(self.run_id) is not str or not self.run_id:
            raise ValueError("run report run_id must be non-empty text")
        for name in (
            "starting_event_ordinal",
            "next_event_ordinal",
            "executed_event_count",
        ):
            _strict_nonnegative_integer(name, getattr(self, name))
        if type(self.completed) is not bool:
            raise TypeError("completed must be boolean")
        if not isinstance(self.checkpoint_hashes, Mapping):
            raise TypeError("checkpoint_hashes must be a mapping")
        for ordinal, digest in self.checkpoint_hashes.items():
            _strict_nonnegative_integer("checkpoint hash ordinal", ordinal)
            if type(digest) is not str or len(digest) != 64:
                raise ValueError("checkpoint hashes must be SHA-256 text")
        for name in ("final_checkpoint_hash", "final_storage_projection_hash"):
            value = getattr(self, name)
            if type(value) is not str or len(value) != 64:
                raise ValueError(f"{name} must be SHA-256 text")
        object.__setattr__(
            self, "checkpoint_hashes", MappingProxyType(dict(self.checkpoint_hashes))
        )


def execute_mock_run(
    pipeline: MockEventPipeline,
    storage: RunStorage,
    invocations: Sequence[MockEventInvocation],
    control: MockRunControl,
) -> MockRunReport:
    """Execute one exact invocation prefix solely through ``pipeline.execute``."""

    if not isinstance(storage, RunStorage):
        raise TypeError("storage must be a RunStorage")
    if not isinstance(control, MockRunControl):
        raise TypeError("control must be a MockRunControl")
    if not isinstance(invocations, Sequence) or isinstance(invocations, (str, bytes)):
        raise TypeError("invocations must be a sequence")
    invocation_values = tuple(invocations)
    if not all(isinstance(item, MockEventInvocation) for item in invocation_values):
        raise TypeError("invocations must contain MockEventInvocation values")
    try:
        pipeline_run_id = pipeline.run_id
    except AttributeError as error:
        raise TypeError("pipeline must expose its read-only run identity") from error
    if pipeline_run_id != storage.binding.run_id:
        raise ValueError("pipeline and storage must belong to the same run")
    start = storage.progress.next_event_ordinal
    target = control.target_event_ordinal
    if target < start or target > storage.progress.expected_event_count:
        raise ValueError("target event ordinal is outside current storage bounds")
    expected_ordinals = tuple(range(start, target))
    if tuple(item.event_ordinal for item in invocation_values) != expected_ordinals:
        raise ValueError("mock invocation ledger must exact-cover the requested prefix")
    if any(
        item.event_id != derive_event_id(storage.binding.run_id, item.event_ordinal)
        for item in invocation_values
    ):
        raise ValueError("mock invocation event identity drifts from the bound run")
    ordinals = control.checkpoint_ordinals
    paths = control.checkpoint_paths
    if len(ordinals) != len(paths):
        raise ValueError("checkpoint ordinal/path arrays must have equal length")
    if ordinals != tuple(sorted(set(ordinals))):
        raise ValueError("checkpoint ordinals must be unique and strictly increasing")
    if any(ordinal <= start or ordinal > target for ordinal in ordinals):
        raise ValueError("checkpoint ordinals must lie inside the newly executed prefix")
    resolved_paths = tuple(path.resolve(strict=False) for path in paths)
    if len(set(resolved_paths)) != len(resolved_paths):
        raise ValueError("checkpoint paths must be unique after resolution")
    targets = dict(zip(ordinals, paths, strict=True))
    checkpoint_hashes: dict[int, str] = {}
    final_checkpoint = None
    final_storage_projection_hash = None
    executed = 0
    for invocation in invocation_values:
        outcome = pipeline.execute(
            feed_capacity=invocation.feed_capacity,
            memory_window=invocation.memory_window,
            parser_limits=invocation.parser_limits,
            prompt_limits=invocation.prompt_limits,
            policy=invocation.policy,
            model_identity=invocation.model_identity,
            request_parameters=invocation.request_parameters,
            model_seed=invocation.model_seed,
            adapter=invocation.adapter,
            http_status=invocation.http_status,
            usage=invocation.usage,
            finish_reason=invocation.finish_reason,
            reconciliation=invocation.reconciliation,
        )
        executed += 1
        if outcome.lifecycle.state not in {"committed", "complete"}:
            raise RuntimeError("mock run stopped before a successful commit")
        next_ordinal = storage.progress.next_event_ordinal
        if next_ordinal != invocation.event_ordinal + 1:
            raise RuntimeError("pipeline did not commit the exact invocation ordinal")
        if next_ordinal in targets:
            if next_ordinal == target:
                checkpoint, final_storage_projection_hash = build_checkpoint_with_projection(
                    storage
                )
                final_checkpoint = checkpoint
            else:
                checkpoint = build_checkpoint(storage)
            checkpoint_hashes[next_ordinal] = write_checkpoint_atomic(
                targets[next_ordinal], checkpoint
            )
    if final_checkpoint is None:
        final_checkpoint, final_storage_projection_hash = build_checkpoint_with_projection(storage)
    assert final_storage_projection_hash is not None
    if storage.progress.next_event_ordinal != target:
        raise RuntimeError("mock run did not reach the requested target ordinal")
    if set(checkpoint_hashes) != set(targets):
        raise RuntimeError("mock run did not write the exact requested checkpoint set")
    return MockRunReport(
        run_id=storage.binding.run_id,
        starting_event_ordinal=start,
        next_event_ordinal=storage.progress.next_event_ordinal,
        executed_event_count=executed,
        completed=final_checkpoint.resume_action == "complete",
        checkpoint_hashes=checkpoint_hashes,
        final_checkpoint_hash=final_checkpoint.checkpoint_hash,
        final_storage_projection_hash=final_storage_projection_hash,
    )
