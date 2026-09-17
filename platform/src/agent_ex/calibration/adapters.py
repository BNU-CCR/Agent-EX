"""Provider-neutral adapter boundary for independent Phase 0A probes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Mapping

from ..domain import canonical_payload_hash
from .contracts import ProbeRequest, ProbeResponse


@dataclass(frozen=True, slots=True)
class ProbeScriptStep:
    outcome: str
    raw_response: str | None
    error_code: str | None
    retry_after_seconds: float | None

    def __post_init__(self) -> None:
        if self.outcome == "response":
            if (
                type(self.raw_response) is not str
                or self.error_code is not None
                or self.retry_after_seconds is not None
            ):
                raise ValueError("response step requires raw_response without error_code")
        elif self.outcome in {"timeout", "oom", "provider_error"}:
            if self.raw_response is not None:
                raise ValueError("typed error step cannot contain raw_response")
            if type(self.error_code) is not str or not self.error_code.strip():
                raise ValueError("typed error step requires error_code")
            if self.retry_after_seconds is not None:
                if type(self.retry_after_seconds) is not float:
                    raise TypeError("retry_after_seconds must be a float or null")
                if self.retry_after_seconds < 0 or not math.isfinite(self.retry_after_seconds):
                    raise ValueError("retry_after_seconds must be finite and nonnegative")
        else:
            raise ValueError("unsupported scripted probe outcome")


class ProbeAdapter(ABC):
    @abstractmethod
    def generate(
        self,
        request: ProbeRequest,
        *,
        timeout_seconds: float | None = None,
        connect_timeout_seconds: float | None = None,
        read_timeout_seconds: float | None = None,
    ) -> ProbeResponse:
        """Generate one response, enforcing the supplied timeout at the provider boundary."""


class ScriptedProbeAdapter(ProbeAdapter):
    """Deterministic offline adapter that consumes each keyed step exactly once."""

    def __init__(self, steps: Mapping[tuple[str, int], ProbeScriptStep]) -> None:
        if not isinstance(steps, Mapping):
            raise TypeError("steps must be a mapping")
        copied: dict[tuple[str, int], ProbeScriptStep] = {}
        for key, step in steps.items():
            if (
                type(key) is not tuple
                or len(key) != 2
                or type(key[0]) is not str
                or type(key[1]) is not int
                or isinstance(key[1], bool)
            ):
                raise TypeError("scripted step keys must be (probe_case_id, attempt_index)")
            if not isinstance(step, ProbeScriptStep):
                raise TypeError("scripted values must be ProbeScriptStep records")
            copied[key] = step
        self._steps = MappingProxyType(copied)
        self._consumed: set[tuple[str, int]] = set()

    def generate(
        self,
        request: ProbeRequest,
        *,
        timeout_seconds: float | None = None,
        connect_timeout_seconds: float | None = None,
        read_timeout_seconds: float | None = None,
    ) -> ProbeResponse:
        if not isinstance(request, ProbeRequest):
            raise TypeError("request must be a ProbeRequest")
        if timeout_seconds is not None:
            if type(timeout_seconds) is not float:
                raise TypeError("timeout_seconds must be a float or null")
            if timeout_seconds <= 0 or not math.isfinite(timeout_seconds):
                raise ValueError("timeout_seconds must be finite and positive")
        key = (request.probe_case_id, request.attempt_index)
        if key not in self._steps:
            raise ValueError("missing scripted probe step")
        if key in self._consumed:
            raise ValueError("scripted probe step was already consumed")
        self._consumed.add(key)
        step = self._steps[key]
        return ProbeResponse.from_script_step(
            request=request,
            outcome=step.outcome,
            raw_response=step.raw_response,
            error_code=step.error_code,
            adapter_identity={"provider": "scripted-probe", "runtime_version": "1.0.0"},
            model_identity={"model": "synthetic", "revision": "offline-v1"},
            tokenizer_identity={"tokenizer": "synthetic", "revision": "offline-v1"},
            chat_template_hash=canonical_payload_hash("synthetic-chat-template-v1"),
            provider_request_id=f"scripted-{request.request_id}",
            provider_seed_supported=True,
            provider_seed_echo=request.requested_seed,
            retry_after_seconds=step.retry_after_seconds,
        )
