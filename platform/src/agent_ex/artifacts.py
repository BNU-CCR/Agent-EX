"""Versioned immutable artifact envelopes for reproducible Paper 1 inputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .domain import (
    _freeze,
    _json_ready,
    _require_id,
    _require_json_transport,
    _require_sha256,
    _require_string,
    canonical_payload_hash,
)
from .rng import RNGProvenance


def _identity_payload(
    *,
    artifact_type: str,
    schema_version: str,
    algorithm_id: str,
    algorithm_version: str,
    input_hashes: Mapping[str, str],
    output_hash: str,
    rng_provenance: tuple[RNGProvenance, ...],
) -> dict[str, object]:
    return {
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        "algorithm_id": algorithm_id,
        "algorithm_version": algorithm_version,
        "input_hashes": input_hashes,
        "output_hash": output_hash,
        "rng_provenance": tuple(item.to_payload() for item in rng_provenance),
    }


@dataclass(frozen=True, slots=True)
class ArtifactEnvelope:
    """Bind artifact content to its algorithm, inputs, and RNG provenance."""

    artifact_id: str
    artifact_type: str
    schema_version: str
    algorithm_id: str
    algorithm_version: str
    input_hashes: Mapping[str, str]
    output_hash: str
    rng_provenance: tuple[RNGProvenance, ...]
    payload: object

    def __post_init__(self) -> None:
        _require_id("artifact_id", self.artifact_id)
        _require_id("artifact_type", self.artifact_type)
        _require_string("schema_version", self.schema_version)
        _require_id("algorithm_id", self.algorithm_id)
        _require_string("algorithm_version", self.algorithm_version)
        if not isinstance(self.input_hashes, Mapping):
            raise TypeError("input_hashes must be a mapping")
        for name, digest in self.input_hashes.items():
            _require_id("input_hashes key", name)
            try:
                _require_sha256(f"input_hashes[{name}]", digest)
            except (TypeError, ValueError) as error:
                raise ValueError(f"input_hashes[{name}] must be a canonical SHA-256") from error
        if not isinstance(self.rng_provenance, tuple):
            raise TypeError("rng_provenance must be a tuple")
        if not all(isinstance(item, RNGProvenance) for item in self.rng_provenance):
            raise TypeError("rng_provenance must contain RNGProvenance values")
        _require_json_transport(self.payload, "artifact payload")
        _require_sha256("output_hash", self.output_hash)
        actual_output_hash = canonical_payload_hash(self.payload)
        if self.output_hash != actual_output_hash:
            raise ValueError("output_hash does not match artifact payload")
        expected_id = self._derive_artifact_id()
        if self.artifact_id != expected_id:
            raise ValueError("artifact_id does not match envelope identity")
        object.__setattr__(self, "input_hashes", _freeze(self.input_hashes))
        object.__setattr__(self, "payload", _freeze(self.payload))

    def _derive_artifact_id(self) -> str:
        identity = _identity_payload(
            artifact_type=self.artifact_type,
            schema_version=self.schema_version,
            algorithm_id=self.algorithm_id,
            algorithm_version=self.algorithm_version,
            input_hashes=self.input_hashes,
            output_hash=self.output_hash,
            rng_provenance=self.rng_provenance,
        )
        return "artifact-" + canonical_payload_hash(identity)

    @classmethod
    def create(
        cls,
        *,
        artifact_type: str,
        schema_version: str,
        algorithm_id: str,
        algorithm_version: str,
        input_hashes: Mapping[str, str],
        payload: object,
        rng_provenance: tuple[RNGProvenance, ...],
    ) -> ArtifactEnvelope:
        _require_json_transport(payload, "artifact payload")
        output_hash = canonical_payload_hash(payload)
        identity = _identity_payload(
            artifact_type=artifact_type,
            schema_version=schema_version,
            algorithm_id=algorithm_id,
            algorithm_version=algorithm_version,
            input_hashes=input_hashes,
            output_hash=output_hash,
            rng_provenance=rng_provenance,
        )
        return cls(
            artifact_id="artifact-" + canonical_payload_hash(identity),
            artifact_type=artifact_type,
            schema_version=schema_version,
            algorithm_id=algorithm_id,
            algorithm_version=algorithm_version,
            input_hashes=input_hashes,
            output_hash=output_hash,
            rng_provenance=rng_provenance,
            payload=payload,
        )

    def to_payload(self) -> dict[str, object]:
        return _json_ready(
            {
                "artifact_id": self.artifact_id,
                "artifact_type": self.artifact_type,
                "schema_version": self.schema_version,
                "algorithm_id": self.algorithm_id,
                "algorithm_version": self.algorithm_version,
                "input_hashes": self.input_hashes,
                "output_hash": self.output_hash,
                "rng_provenance": tuple(item.to_payload() for item in self.rng_provenance),
                "payload": self.payload,
            }
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ArtifactEnvelope:
        if type(payload) is not dict:
            raise TypeError("artifact envelope payload must be a JSON object")
        expected_fields = {
            "artifact_id",
            "artifact_type",
            "schema_version",
            "algorithm_id",
            "algorithm_version",
            "input_hashes",
            "output_hash",
            "rng_provenance",
            "payload",
        }
        if set(payload) != expected_fields:
            raise ValueError("artifact envelope payload fields do not match the contract")
        if type(payload["input_hashes"]) is not dict:
            raise TypeError("artifact envelope input_hashes must be a JSON object")
        if type(payload["rng_provenance"]) is not list:
            raise TypeError("artifact envelope rng_provenance must be a JSON array")
        _require_json_transport(payload, "artifact envelope payload")
        return cls(
            artifact_id=payload["artifact_id"],  # type: ignore[arg-type]
            artifact_type=payload["artifact_type"],  # type: ignore[arg-type]
            schema_version=payload["schema_version"],  # type: ignore[arg-type]
            algorithm_id=payload["algorithm_id"],  # type: ignore[arg-type]
            algorithm_version=payload["algorithm_version"],  # type: ignore[arg-type]
            input_hashes=payload["input_hashes"],  # type: ignore[arg-type]
            output_hash=payload["output_hash"],  # type: ignore[arg-type]
            rng_provenance=tuple(
                RNGProvenance.from_payload(item)  # type: ignore[arg-type]
                for item in payload["rng_provenance"]  # type: ignore[union-attr]
            ),
            payload=payload["payload"],
        )
