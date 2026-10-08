"""Pure validation of human-approved benchmark content; never dispatches trials."""

from collections import Counter
from types import MappingProxyType

from ..domain import canonical_payload_hash


TOP_KEYS = frozenset(
    "schema_version research_content_status approved_on approval_reference "
    "dispatch_authorized cloud_launch_eligible formal_parameter_authority "
    "statistically_independent_arguments topic focal_context persona_context "
    "self_history pre_confidence confidence_policy cases".split()
)
CASE_KEYS = frozenset(
    "case_id content_unit_id topic_reference focal_stance source_stance stance_distance "
    "direction source_message source_reason reason_family argument_provenance human_review "
    "shared_reason_family_ids".split()
)
MAPPING = ["非常不支持", "不支持", "比较不支持", "中立或不确定", "比较支持", "支持", "非常支持"]
PERSONA = "你是一名成年公民，日常会接触社会公共事务，也会阅读和讨论有关政策的话题。"
CONTEXT = "当前讨论的是逐步提高法定退休年龄的总体政策方向。你的当前态度为中立（4分）。"
FACT_CARD = (
    "本题讨论是否逐步提高法定退休年龄。评价对象仅是对这一政策方向的总体支持程度；"
    "不要求判断具体实施年份、幅度或某一群体的例外安排。"
)


def validate_frozen_benchmark(payload, *, expected_hash):
    """Bind an externally approved hash, then return immutable non-stimulus metadata.

    This is content validation, not authentication of the researcher, runtime approval,
    argument independence, factual accuracy, or permission to call an inference service.
    """
    if canonical_payload_hash(payload) != expected_hash:
        raise ValueError("benchmark approval hash mismatch")
    if not isinstance(payload, dict) or set(payload) != TOP_KEYS:
        raise ValueError("benchmark keys mismatch")
    fixed = {
        "schema_version": "sis.manipulation.benchmark-frozen.v1",
        "research_content_status": "frozen",
        "approved_on": "2026-10-08",
        "approval_reference": "D-2026-10-08-01",
        "focal_context": CONTEXT,
        "persona_context": PERSONA,
        "self_history": [],
        "pre_confidence": None,
        "confidence_policy": "post-only-descriptive-no-change",
        "topic": {
            "candidate_key": "retirement-delay",
            "statement": "总体而言，我支持逐步提高法定退休年龄。",
            "fact_card": FACT_CARD,
            "stance_mapping": MAPPING,
        },
    }
    for key, value in fixed.items():
        if payload[key] != value:
            raise ValueError(f"benchmark fixed field mismatch: {key}")
    for key in (
        "dispatch_authorized",
        "cloud_launch_eligible",
        "formal_parameter_authority",
        "statistically_independent_arguments",
    ):
        if payload[key] is not False:
            raise ValueError(f"benchmark authority must remain false: {key}")
    cases = payload["cases"]
    if not isinstance(cases, list) or len(cases) != 30:
        raise ValueError("benchmark requires thirty cases")
    strata = Counter()
    messages, reasons = set(), set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict) or set(case) != CASE_KEYS:
            raise ValueError("case keys mismatch")
        distance = index // 10 + 1
        direction = "upward" if index % 10 < 5 else "downward"
        letter = "U" if direction == "upward" else "D"
        ordinal = index % 5 + 1
        case_id = f"MC-D{distance}-{letter}-{ordinal:02}"
        unit = f"AD-{index + 1:03}"
        source = 4 + distance * (1 if direction == "upward" else -1)
        for key, value in {
            "focal_stance": 4,
            "source_stance": source,
            "stance_distance": distance,
        }.items():
            if type(case[key]) is not int or case[key] != value:
                raise ValueError(f"case stance mismatch: {key}")
        expected = {
            "case_id": case_id,
            "content_unit_id": unit,
            "direction": direction,
            "topic_reference": "retirement-delay-generic-proposal-v2",
            "human_review": "approved",
            "shared_reason_family_ids": (
                ["age-rule-justification"] if unit in ("AD-004", "AD-023") else []
            ),
            "argument_provenance": {
                "kind": "assistant_draft_human_approved",
                "revision": "v3-plus-AD028-final",
                "source": "docs/benchmarks/retirement-30-case-draft-v3.md",
            },
        }
        if any(case[key] != value for key, value in expected.items()):
            raise ValueError("case identity/review/provenance mismatch")
        message, reason, family = (
            case["source_message"],
            case["source_reason"],
            case["reason_family"],
        )
        if not all(
            isinstance(text, str) and text.strip() == text and text
            for text in (
                message,
                reason,
                family,
            )
        ):
            raise ValueError("case text must be nonempty exact strings")
        stance_sentence = f"我{MAPPING[source - 1]}逐步提高法定退休年龄。"
        if (
            message != stance_sentence + reason
            or reason.count("。") != 1
            or not reason.endswith("。")
        ):
            raise ValueError("case must contain one viewpoint and one exact reason")
        if any(cue in message for cue in ("Blue", "Green", "蓝组", "绿组")):
            raise ValueError("group cue in fixed message")
        messages.add(message)
        reasons.add(reason)
        strata[distance, direction] += 1
    if len(messages) != 30 or len(reasons) != 30 or sorted(strata.values()) != [5] * 6:
        raise ValueError("duplicate content or stratum imbalance")
    return MappingProxyType(
        {
            "case_count": 30,
            "content_hash": expected_hash,
            "research_content_status": "frozen",
            "dispatch_authorized": False,
        }
    )
