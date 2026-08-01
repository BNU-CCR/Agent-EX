"""Deterministic, namespaced RNG provenance without shared mutable state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .domain import (
    _freeze,
    _json_ready,
    _require_int,
    _require_json_transport,
    _require_string,
    canonical_payload_hash,
)


RNG_DERIVATION_VERSION = "agent-ex.sha256.v1"

_REGISTERED_NAMESPACES = frozenset(
    {
        "population",
        "initial_stance",
        "initial_reason",
        "ws_graph",
        "agent_node_mapping",
        "shadow_graph",
        "structure_ring_lattice",
        "structure_random_null",
        "attention",
        "expression",
        "activation",
        "publish",
        "round0_tiebreak",
        "message_slot",
        "model_sampling",
    }
)
_EVENT_LEVEL_NAMESPACES = frozenset(
    {
        "activation",
        "publish",
        "message_slot",
        "model_sampling",
    }
)


def _reject_attempt_index(value: object) -> None:
    if isinstance(value, Mapping):
        if "attempt_index" in value:
            raise ValueError("attempt_index cannot participate in RNG derivation")
        for item in value.values():
            _reject_attempt_index(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_attempt_index(item)


def _validated_key(
    matched_seed: int,
    namespace: str,
    coordinates: Mapping[str, object],
) -> dict[str, object]:
    _require_int("matched_seed", matched_seed)
    _require_string("namespace", namespace)
    if namespace not in _REGISTERED_NAMESPACES:
        raise ValueError(f"namespace is not registered: {namespace}")
    if not isinstance(coordinates, Mapping):
        raise TypeError("coordinates must be a mapping")
    if "artifact_kind" not in coordinates:
        raise ValueError("coordinates must bind artifact_kind")
    _require_string("coordinates[artifact_kind]", coordinates["artifact_kind"])
    if namespace in _EVENT_LEVEL_NAMESPACES:
        if "event_ordinal" not in coordinates:
            raise ValueError(f"{namespace} RNG coordinates must include event_ordinal")
        _require_int("coordinates[event_ordinal]", coordinates["event_ordinal"])
    _freeze(coordinates)
    _reject_attempt_index(coordinates)
    return {
        "derivation_version": RNG_DERIVATION_VERSION,
        "matched_seed": matched_seed,
        "namespace": namespace,
        "coordinates": coordinates,
    }


def derive_rng_seed(
    matched_seed: int,
    namespace: str,
    coordinates: Mapping[str, object],
) -> int:
    """Derive an independent local seed from stable, explicit coordinates."""

    key = _validated_key(matched_seed, namespace, coordinates)
    digest = canonical_payload_hash(key)
    return int(digest[:16], 16)


@dataclass(frozen=True, slots=True)
class RNGProvenance:
    """Auditable RNG key and its deterministic derived local seed."""

    derivation_version: str
    matched_seed: int
    namespace: str
    coordinates: Mapping[str, object]
    derived_seed: int

    def __post_init__(self) -> None:
        if self.derivation_version != RNG_DERIVATION_VERSION:
            raise ValueError(f"derivation_version must be {RNG_DERIVATION_VERSION}")
        key = _validated_key(self.matched_seed, self.namespace, self.coordinates)
        _require_int("derived_seed", self.derived_seed)
        expected = derive_rng_seed(self.matched_seed, self.namespace, self.coordinates)
        if self.derived_seed != expected:
            raise ValueError("derived_seed does not match RNG namespace coordinates")
        object.__setattr__(self, "coordinates", _freeze(key["coordinates"]))

    @classmethod
    def create(
        cls,
        *,
        matched_seed: int,
        namespace: str,
        coordinates: Mapping[str, object],
    ) -> RNGProvenance:
        return cls(
            derivation_version=RNG_DERIVATION_VERSION,
            matched_seed=matched_seed,
            namespace=namespace,
            coordinates=coordinates,
            derived_seed=derive_rng_seed(matched_seed, namespace, coordinates),
        )

    def to_payload(self) -> dict[str, object]:
        return _json_ready(
            {
                "derivation_version": self.derivation_version,
                "matched_seed": self.matched_seed,
                "namespace": self.namespace,
                "coordinates": self.coordinates,
                "derived_seed": self.derived_seed,
            }
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> RNGProvenance:
        if type(payload) is not dict:
            raise TypeError("RNG provenance payload must be a JSON object")
        expected_fields = {
            "derivation_version",
            "matched_seed",
            "namespace",
            "coordinates",
            "derived_seed",
        }
        if set(payload) != expected_fields:
            raise ValueError("RNG provenance payload fields do not match the contract")
        if type(payload["coordinates"]) is not dict:
            raise TypeError("RNG provenance coordinates must be a JSON object")
        _require_json_transport(payload, "RNG provenance payload")
        return cls(
            derivation_version=payload["derivation_version"],  # type: ignore[arg-type]
            matched_seed=payload["matched_seed"],  # type: ignore[arg-type]
            namespace=payload["namespace"],  # type: ignore[arg-type]
            coordinates=payload["coordinates"],  # type: ignore[arg-type]
            derived_seed=payload["derived_seed"],  # type: ignore[arg-type]
        )
