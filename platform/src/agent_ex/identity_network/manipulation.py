"""Bounded check stimuli, not a classifier, significance gate or HTTP runner."""

from dataclasses import dataclass
import json
import math
import random
from typing import Mapping

from ..artifacts import ArtifactEnvelope
from ..domain import _require_int, _require_sha256, canonical_payload_hash
from ..rng import RNGProvenance
from .prompts import RENDERER_VERSION, StudyPrompt


@dataclass(frozen=True, slots=True)
class CheckCase:
    case_id: str
    base_prompt: StudyPrompt
    sampling_seed: int

    def __post_init__(self):
        if not isinstance(self.case_id, str) or not self.case_id.strip():
            raise ValueError("case identity must be explicit")
        _require_int("sampling_seed", self.sampling_seed)
        if not isinstance(self.base_prompt, StudyPrompt):
            raise TypeError("a bound blind base prompt is required")
        if self.base_prompt.evidence["renderer_version"] != RENDERER_VERSION:
            raise ValueError("check renderer is unsupported")
        if self.base_prompt.evidence["cell_id"] != "SIS-A0-B1":
            raise ValueError("use the blind social input fixture, not a study outcome")
        if len(self.base_prompt.evidence["source_agent_ids"]) != 1:
            raise ValueError("each controlled check requires exactly one source")


@dataclass(frozen=True, slots=True)
class StageTwoReceipt:
    stage_one_report_hash: str
    preregistered_criteria_hash: str
    decision: str
    researcher: str

    def __post_init__(self):
        _require_sha256("stage-one report", self.stage_one_report_hash)
        _require_sha256("criteria", self.preregistered_criteria_hash)
        if self.decision != "no_signal":
            raise ValueError("stage two requires a researcher no_signal decision")
        if not isinstance(self.researcher, str) or not self.researcher.strip():
            raise ValueError("researcher attribution is required")

    def to_payload(self):
        return {
            "stage_one_report_hash": self.stage_one_report_hash,
            "preregistered_criteria_hash": self.preregistered_criteria_hash,
            "decision": self.decision,
            "researcher": self.researcher,
        }


def build_manipulation_pack(
    *,
    cases: tuple[CheckCase, ...],
    stage: str,
    matched_seed: int,
    generation_settings: Mapping[str, object],
    stage_two_receipt: StageTwoReceipt | None = None,
) -> ArtifactEnvelope:
    if stage not in ("pure_label", "shared_group_framing"):
        raise ValueError("only the two predefined stages exist")
    if stage == "shared_group_framing" and not isinstance(stage_two_receipt, StageTwoReceipt):
        raise ValueError("stage two requires a report/criteria researcher receipt")
    if stage == "pure_label" and stage_two_receipt is not None:
        raise ValueError("stage-one pack must not include a stage-two receipt")
    if (
        not isinstance(cases, tuple)
        or not cases
        or any(not isinstance(c, CheckCase) for c in cases)
    ):
        raise ValueError("explicit nonempty check cases are required")
    if len({c.case_id for c in cases}) != len(cases):
        raise ValueError("duplicate check case identity")
    if not isinstance(generation_settings, Mapping) or set(generation_settings) != {
        "temperature",
        "top_p",
        "max_tokens",
    }:
        raise ValueError("explicit generation settings are required")
    temperature, top_p = generation_settings["temperature"], generation_settings["top_p"]
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (temperature, top_p)):
        raise ValueError("generation settings must be finite numbers")
    if temperature < 0 or not 0 < top_p <= 1:
        raise ValueError("generation settings are out of range")
    _require_int("max_tokens", generation_settings["max_tokens"], minimum=1)
    cases = tuple(sorted(cases, key=lambda c: c.case_id))
    fixture_hash = canonical_payload_hash(
        tuple(
            {
                "case_id": c.case_id,
                "base_prompt_hash": c.base_prompt.prompt_hash,
                "base_evidence_hash": c.base_prompt.evidence_hash,
                "sampling_seed": c.sampling_seed,
            }
            for c in cases
        )
    )
    trials = []
    for case in cases:
        for receiver_group in ("Blue", "Green"):
            for relation in ("same", "other"):
                source_group = (
                    receiver_group
                    if relation == "same"
                    else ("Green" if receiver_group == "Blue" else "Blue")
                )
                visible = json.loads(case.base_prompt.messages[1]["content"])
                visible["self_group"] = receiver_group
                visible["social_messages"][0]["source_group"] = source_group
                if stage == "shared_group_framing":
                    visible["shared_group_context"] = (
                        f"You participate in a stable discussion group called {receiver_group} throughout this discussion."
                    )
                messages = (
                    dict(case.base_prompt.messages[0]),
                    {
                        "role": "user",
                        "content": json.dumps(visible, ensure_ascii=False, sort_keys=True),
                    },
                )
                trials.append(
                    {
                        "trial_id": f"{case.case_id}/{stage}/{receiver_group}/{relation}",
                        "case_id": case.case_id,
                        "self_group": receiver_group,
                        "source_group": source_group,
                        "relation": relation,
                        "base_evidence_hash": case.base_prompt.evidence_hash,
                        "messages": messages,
                        "prompt_hash": canonical_payload_hash(messages),
                        "sampling_seed": case.sampling_seed,
                    }
                )
    order = RNGProvenance.create(
        matched_seed=matched_seed,
        namespace="identity_check_order",
        coordinates={
            "artifact_kind": "identity_check_pack",
            "fixtures_hash": fixture_hash,
            "stage": stage,
        },
    )
    random.Random(order.derived_seed).shuffle(trials)
    # Receipt records attribution only; actual report and criteria must be
    # verified before dispatch. Materialization is not authorization to run.
    return ArtifactEnvelope.create(
        artifact_type="identity_network_manipulation_pack",
        schema_version="paper1.artifact-envelope.v1",
        algorithm_id="paper1.paired_minimal_group_check",
        algorithm_version="1.0.0",
        input_hashes={"fixtures": fixture_hash},
        rng_provenance=(order,),
        payload={
            "stage": stage,
            "fixtures": tuple(
                {
                    "case_id": c.case_id,
                    "base_messages": c.base_prompt.messages,
                    "base_prompt_hash": c.base_prompt.prompt_hash,
                    "base_evidence": c.base_prompt.evidence,
                    "base_evidence_hash": c.base_prompt.evidence_hash,
                    "sampling_seed": c.sampling_seed,
                }
                for c in cases
            ),
            "trials": tuple(trials),
            "generation_settings": dict(generation_settings),
            "stage_two_receipt": stage_two_receipt.to_payload() if stage_two_receipt else None,
            "metadata": {
                "status": "preliminary",
                "research_parameter_status": "not_frozen",
                "formal_parameter_authority": False,
                "dispatch_authorized": False,
            },
        },
    )
