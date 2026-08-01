"""Orthogonal mock persona rendering for Phase 4B-3."""

from __future__ import annotations

from collections import Counter
from string import Formatter
from typing import Mapping

from .artifacts import ArtifactEnvelope
from .domain import canonical_payload_hash


_TEMPLATE_FIELDS = {
    "schema_version",
    "common_skeleton",
    "identity_block_template",
    "continuity_block",
    "required_identity_fields",
    "forbidden_phrases",
    "metadata",
}
_CONDITION_FIELDS = {"identity_present", "continuity_present"}
_RENDERED_PAYLOAD_FIELDS = {
    "schema_version",
    "template_artifact_id",
    "population_member_hash",
    "condition",
    "common_skeleton",
    "identity_block",
    "continuity_block",
    "rendered_text",
    "metadata",
}
_PLATFORM_IDENTITY_FIELDS = frozenset(
    {"age_band", "gender", "education", "urban", "activity", "occupation"}
)
_PLATFORM_FORBIDDEN_PHRASES = (
    "never change",
    "永不改变",
    "do not be influenced",
    "不要被影响",
    "抗从众",
    "坚持",
    "捍卫",
    "忠于",
    "除非证据确凿",
    "保持原有价值观",
    "最大变化一步",
    "at most one point",
)


def _reject_platform_forbidden_text(visible_text: str) -> None:
    normalized_visible_text = visible_text.casefold()
    for phrase in _PLATFORM_FORBIDDEN_PHRASES:
        if phrase.casefold() in normalized_visible_text:
            raise ValueError(f"persona contains platform-forbidden phrase: {phrase}")


def _validated_template(template_artifact: ArtifactEnvelope) -> Mapping[str, object]:
    if (
        not isinstance(template_artifact, ArtifactEnvelope)
        or template_artifact.artifact_type != "paper1.mock_persona_template"
    ):
        raise TypeError("template_artifact must be a mock persona template ArtifactEnvelope")
    payload = template_artifact.payload
    if set(payload) != _TEMPLATE_FIELDS:
        raise ValueError("persona template fields do not match the mock contract")
    if payload["schema_version"] != "paper1.mock-persona-template.v1":
        raise ValueError("persona template schema version is not supported")
    if payload["metadata"]["mock_only"] is not True:  # type: ignore[index]
        raise ValueError("Phase 4B-3 persona templates must be explicitly mock_only")
    skeleton = payload["common_skeleton"]
    identity_template = payload["identity_block_template"]
    continuity_block = payload["continuity_block"]
    if not all(isinstance(value, str) for value in (skeleton, identity_template, continuity_block)):
        raise TypeError("persona skeleton and factor blocks must be strings")
    if not identity_template.strip() or not continuity_block.strip():
        raise ValueError("present factor blocks must be non-empty")
    if skeleton.count("{identity_block}") != 1 or skeleton.count("{continuity_block}") != 1:
        raise ValueError("common skeleton must contain each factor marker exactly once")
    required_fields = payload["required_identity_fields"]
    forbidden = payload["forbidden_phrases"]
    if not isinstance(required_fields, tuple) or not required_fields:
        raise ValueError("required_identity_fields must be a non-empty tuple")
    if len(required_fields) != len(set(required_fields)) or set(required_fields) != (
        _PLATFORM_IDENTITY_FIELDS
    ):
        raise ValueError(
            "required_identity_fields must equal the platform identity field allowlist"
        )
    parsed_fields: list[str] = []
    try:
        parsed = tuple(Formatter().parse(identity_template))
    except ValueError as error:
        raise ValueError("identity block template format syntax is invalid") from error
    for _, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue
        if field_name not in _PLATFORM_IDENTITY_FIELDS:
            raise ValueError(f"identity block template has unknown format field: {field_name}")
        if format_spec or conversion:
            raise ValueError("identity block template fields must not use format modifiers")
        parsed_fields.append(field_name)
    counts = Counter(parsed_fields)
    if any(counts[field] != 1 for field in _PLATFORM_IDENTITY_FIELDS):
        raise ValueError(
            "identity block template must contain each frozen format field exactly once"
        )
    if not isinstance(forbidden, tuple):
        raise TypeError("forbidden_phrases must be a tuple")
    visible_template_text = skeleton + identity_template + continuity_block
    _reject_platform_forbidden_text(visible_template_text)
    normalized_visible_text = visible_template_text.casefold()
    for phrase in forbidden:
        if not isinstance(phrase, str) or not phrase:
            raise ValueError("forbidden phrases must be non-empty strings")
        if phrase.casefold() in normalized_visible_text:
            raise ValueError(f"persona template contains forbidden phrase: {phrase}")
    return payload


def render_persona(
    template_artifact: ArtifactEnvelope,
    population_member: Mapping[str, object],
    condition: Mapping[str, bool],
) -> ArtifactEnvelope:
    """Render one condition by mechanically inserting only approved factor blocks."""

    template = _validated_template(template_artifact)
    if not isinstance(condition, Mapping) or set(condition) != _CONDITION_FIELDS:
        raise ValueError("condition must contain exactly identity_present and continuity_present")
    if any(type(condition[field]) is not bool for field in _CONDITION_FIELDS):
        raise TypeError("persona condition values must be booleans")
    if not isinstance(population_member, Mapping) or set(population_member) != {
        "agent_id",
        "donor_id",
        "fields",
    }:
        raise ValueError("population_member fields do not match the population contract")
    fields = population_member["fields"]
    if not isinstance(fields, Mapping):
        raise TypeError("population member fields must be a mapping")
    required_fields = template["required_identity_fields"]
    assert isinstance(required_fields, tuple)
    missing = [field for field in required_fields if field not in fields]
    if missing:
        raise ValueError(f"population member is missing identity field: {missing[0]}")
    for field in required_fields:
        value = fields[field]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"identity field must be a non-empty string: {field}")

    identity_block = ""
    if condition["identity_present"]:
        identity_template = template["identity_block_template"]
        assert isinstance(identity_template, str)
        try:
            identity_block = identity_template.format(
                **{field: fields[field] for field in required_fields}
            )
        except (KeyError, IndexError, ValueError) as error:
            raise ValueError("identity block template placeholders are invalid") from error
    continuity_block = template["continuity_block"] if condition["continuity_present"] else ""
    assert isinstance(continuity_block, str)
    skeleton = template["common_skeleton"]
    assert isinstance(skeleton, str)
    rendered_text = skeleton.replace("{identity_block}", identity_block).replace(
        "{continuity_block}", continuity_block
    )
    member_hash = canonical_payload_hash(population_member)
    payload = {
        "schema_version": "paper1.mock-rendered-persona.v1",
        "template_artifact_id": template_artifact.artifact_id,
        "population_member_hash": member_hash,
        "condition": dict(condition),
        "common_skeleton": skeleton,
        "identity_block": identity_block,
        "continuity_block": continuity_block,
        "rendered_text": rendered_text,
        "metadata": {"mock_only": True, "research_parameter_status": "not_frozen"},
    }
    return ArtifactEnvelope.create(
        artifact_type="paper1.mock_rendered_persona",
        schema_version="paper1.artifact-envelope.v1",
        algorithm_id="paper1.mock_persona_renderer",
        algorithm_version="1.0.0",
        input_hashes={"population_member": member_hash, "template": template_artifact.output_hash},
        payload=payload,
        rng_provenance=(),
    )


def validate_persona_factor_diff(
    rendered_templates: tuple[ArtifactEnvelope, ...],
) -> dict[str, object]:
    """Prove that four rendered conditions differ only in the two factor blocks."""

    if not isinstance(rendered_templates, tuple) or len(rendered_templates) != 4:
        raise ValueError("rendered_templates must contain exactly four artifacts")
    payloads = []
    envelope_invariants = (
        "artifact_type",
        "schema_version",
        "algorithm_id",
        "algorithm_version",
        "input_hashes",
        "rng_provenance",
    )
    for artifact in rendered_templates:
        if (
            not isinstance(artifact, ArtifactEnvelope)
            or artifact.artifact_type != "paper1.mock_rendered_persona"
        ):
            raise TypeError("rendered_templates must contain rendered persona artifacts")
        if not isinstance(artifact.payload, Mapping) or set(artifact.payload) != (
            _RENDERED_PAYLOAD_FIELDS
        ):
            raise ValueError("rendered persona payload fields do not match the contract")
        payloads.append(artifact.payload)
    for invariant in envelope_invariants:
        if len({repr(getattr(artifact, invariant)) for artifact in rendered_templates}) != 1:
            raise ValueError(f"persona envelope invariant differs: {invariant}")
    expected_conditions = {
        (False, False),
        (False, True),
        (True, False),
        (True, True),
    }
    observed_conditions = set()
    for payload in payloads:
        condition = payload["condition"]
        if not isinstance(condition, Mapping) or set(condition) != _CONDITION_FIELDS:
            raise ValueError("rendered persona condition fields do not match the contract")
        if any(type(condition[field]) is not bool for field in _CONDITION_FIELDS):
            raise TypeError("rendered persona condition values must be booleans")
        observed_conditions.add((condition["identity_present"], condition["continuity_present"]))
    if observed_conditions != expected_conditions:
        raise ValueError("rendered personas must cover all four factor conditions")
    allowed_payload_differences = {
        "condition",
        "identity_block",
        "continuity_block",
        "rendered_text",
    }
    for invariant in sorted(_RENDERED_PAYLOAD_FIELDS - allowed_payload_differences):
        if len({repr(payload[invariant]) for payload in payloads}) != 1:
            raise ValueError(f"persona invariant differs outside factor blocks: {invariant}")

    identity_blocks: dict[bool, set[str]] = {False: set(), True: set()}
    continuity_blocks: dict[bool, set[str]] = {False: set(), True: set()}
    for payload in payloads:
        condition = payload["condition"]
        identity_present = condition["identity_present"]  # type: ignore[index]
        continuity_present = condition["continuity_present"]  # type: ignore[index]
        identity_block = payload["identity_block"]
        continuity_block = payload["continuity_block"]
        rendered_text = payload["rendered_text"]
        if not all(
            isinstance(value, str) for value in (identity_block, continuity_block, rendered_text)
        ):
            raise TypeError("rendered persona factor blocks and visible text must be strings")
        _reject_platform_forbidden_text(rendered_text)
        identity_blocks[identity_present].add(identity_block)  # type: ignore[arg-type]
        continuity_blocks[continuity_present].add(continuity_block)  # type: ignore[arg-type]
        skeleton = payload["common_skeleton"]
        expected_text = skeleton.replace("{identity_block}", identity_block).replace(  # type: ignore[union-attr,arg-type]
            "{continuity_block}",
            continuity_block,  # type: ignore[arg-type]
        )
        if payload["rendered_text"] != expected_text:
            raise ValueError("rendered persona differs outside the approved factor blocks")
    if identity_blocks[False] != {""} or continuity_blocks[False] != {""}:
        raise ValueError("absent factor conditions must be true omissions")
    if len(identity_blocks[True]) != 1 or len(continuity_blocks[True]) != 1:
        raise ValueError("present factor blocks must be reused byte-for-byte")
    if identity_blocks[True] == {""} or continuity_blocks[True] == {""}:
        raise ValueError("present factor blocks must be non-empty")
    return {
        "valid": True,
        "condition_count": 4,
        "allowed_differences": ["identity_block", "continuity_block"],
    }
