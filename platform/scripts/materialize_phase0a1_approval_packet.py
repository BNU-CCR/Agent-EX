"""Materialize the proposal-only six-group Phase 0A-1 approval packet."""

from __future__ import annotations

import argparse
from fractions import Fraction
import json
from itertools import combinations, product
from pathlib import Path

from agent_ex.calibration.cloud_run import load_cloud_run_artifacts
from agent_ex.calibration.contracts import ProbeRuntimePolicy, ProbeTopicCandidate
from agent_ex.calibration.gates import GateAlgorithm, PairChallenge
from agent_ex.calibration.review import (
    CoderContract,
    ReviewStratum,
    SemanticReviewPolicy,
)
from agent_ex.calibration.specification import load_probe_specification
from agent_ex.domain import canonical_payload_hash


METADATA = {
    "calibration_only": True,
    "formal_parameter_authority": False,
    "research_parameter_status": "not_frozen",
}
MODEL_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
SMOKE_EVIDENCE_HASH = "4eee264bad889d17582d535dc688310a4b7b665c173c187cd8289fc45b39e53e"
ENVIRONMENT_LOCK_HASH = "c4070d3848da73aa0a16fa1db0c9a4755bdc0238c12b7e84499bbbf00e7d3e91"
CHAT_TEMPLATE_HASH = "41d5929bf73796beb66809ac700b2cf3ff81694f933e5c14d52b7fd6963c947d"
RENDERED_NON_THINKING_HASH = "df67d0593a6e07516a01ccba496c0f641f0300df4cbc2121d3ddf02a0f0fd527"
MODEL_ARTIFACTS_HASH = "d5caf882656fa1d5f12f3c734ccf026d94fb3e8c41d2dd62821026bfd451e037"
TOKENIZER_ARTIFACTS_HASH = "d1ae84eef5474fa0ed3bdace3302c2c8f5af9683b123e096fb92b3ea182aa2f2"
VLLM_WHEEL_HASH = "8bc2203995d061e6b988916b71b9dee8a5970f5fdc5f37d4445a877a2fab2cc1"

JUDGE_PROMPT = """你是独立的盲态语义编码员。你只会看到 topic_text、history_text、identity_text、response_text，不得推测实验条件、候选优先级或采样设置。逐项依据可见文本编码以下维度，并只返回一个 JSON 对象：refusal、stance_consistency、single_construct、identity_use、stereotyping、continuity_coherence、change_appropriateness、information_fidelity。可用标签必须严格来自已冻结 policy；证据不足时使用 unclear 或 indeterminate，不补充外部事实，不把观点方向本身判为错误。"""

ORDERING_POLICY = (
    "Items are ordered by the deterministic blind-export order; the judge receives exactly "
    "one item per request and no aggregate results, condition labels, priorities, or prior codes."
)

CLASSIFIER_CONTRACT = (
    "Direct contradiction means the stated public_reason logically supports the opposite of the "
    "reported stance on the displayed statement. Merely weak, incomplete, neutral, or uncertain "
    "reasoning is indeterminate rather than contradiction."
)


TOPICS = (
    {
        "candidate_key": "retirement-delay",
        "construct": "对逐步提高法定退休年龄这一政策方向的支持程度",
        "fact_card": (
            "本题讨论是否逐步提高法定退休年龄。评价对象仅是对这一政策方向的总体支持程度；"
            "不要求判断具体实施年份、幅度或某一群体的例外安排。"
        ),
        "statements": (
            "总体而言，我支持逐步提高法定退休年龄。",
            "综合考虑，我赞成以渐进方式延后法定退休年龄。",
            "就政策方向而言，我同意逐步延迟法定退休年龄。",
        ),
        "stance_labels_1_7": (
            "1 非常不支持",
            "2 不支持",
            "3 比较不支持",
            "4 中立或不确定",
            "5 比较支持",
            "6 支持",
            "7 非常支持",
        ),
    },
    {
        "candidate_key": "gm-soybean-oil",
        "construct": "对购买并食用明确标识的转基因大豆油的个人意愿",
        "fact_card": (
            "本题中的“有明确标签的转基因大豆油”是指商品标签已清楚标明原料属性的食用大豆油。"
            "评价对象仅是个人购买和食用意愿，不要求判断未标示产品或其他转基因食品。"
        ),
        "statements": (
            "在标签清楚的情况下，我愿意购买并食用转基因大豆油。",
            "如果商品明确标注，我可以接受购买和食用转基因大豆油。",
            "对于明确标识的转基因大豆油，我有购买并食用的意愿。",
        ),
        "stance_labels_1_7": (
            "1 完全不愿意",
            "2 不愿意",
            "3 比较不愿意",
            "4 中立或不确定",
            "5 比较愿意",
            "6 愿意",
            "7 非常愿意",
        ),
    },
    {
        "candidate_key": "ai-net-employment",
        "construct": "对未来十年人工智能广泛应用是否增加社会总体就业机会的判断",
        "fact_card": (
            "本题讨论未来十年人工智能广泛应用对社会总体就业机会数量的净影响。评价对象是“就业机会"
            "总量是否增加”的判断，不涉及某一行业、职业或个人的就业得失。"
        ),
        "statements": (
            "我认为未来十年人工智能的广泛应用将增加社会总体就业机会。",
            "就未来十年的净影响而言，我预计人工智能普及会使就业机会总量增加。",
            "综合新增与被替代岗位，我判断未来十年人工智能应用会带来更多总体就业机会。",
        ),
        "stance_labels_1_7": (
            "1 完全不同意",
            "2 不同意",
            "3 比较不同意",
            "4 中立或不确定",
            "5 比较同意",
            "6 同意",
            "7 完全同意",
        ),
    },
)


def _record(schema_version: str, **values: object) -> dict[str, object]:
    content = {"schema_version": schema_version, **values}
    return {**content, "record_hash": canonical_payload_hash(content)}


def _required_challenges() -> tuple[PairChallenge, ...]:
    wording = tuple(
        PairChallenge(
            f"{scale}-wording-{left}-{right}",
            "topic_quality",
            scale,
            "variant_index",
            left,
            right,
        )
        for scale in ("stance-1-7", "stance-0-10")
        for left, right in combinations(range(3), 2)
    )
    order = tuple(
        PairChallenge(
            f"{scale}-field-order",
            "topic_quality",
            scale,
            "field_order_id",
            "reason-confidence-stance",
            "stance-confidence-reason",
        )
        for scale in ("stance-1-7", "stance-0-10")
    )
    return wording + order


def _gate_algorithm() -> GateAlgorithm:
    classifier_hash = canonical_payload_hash(CLASSIFIER_CONTRACT)
    return GateAlgorithm(
        algorithm_id="phase0a1-real-quality-gates",
        algorithm_version="1.0.0",
        min_parse=Fraction(99, 100),
        max_refusal=Fraction(1, 100),
        min_main_categories=4,
        max_main_endpoint=Fraction(4, 5),
        max_abs_dz=Fraction(1, 5),
        max_contradiction=Fraction(1, 20),
        tv_threshold=None,
        minimum_distribution_n=24,
        classifier_id="phase0a1-direct-contradiction",
        classifier_version="1.0.0",
        classifier_hash=classifier_hash,
        challenges=_required_challenges(),
    )


def _runtime_policy() -> ProbeRuntimePolicy:
    return ProbeRuntimePolicy.create(
        policy_id="phase0a1-probe-runtime-v1",
        retryable_error_codes=("provider_busy", "provider_unreachable", "timeout"),
        nonretryable_error_codes=(
            "oom",
            "provider_fatal",
            "provider_invalid_json",
            "provider_redirect",
            "provider_response_too_large",
            "provider_schema_error",
        ),
        max_transport_attempts_by_code={
            "oom": 1,
            "provider_busy": 2,
            "provider_fatal": 1,
            "provider_invalid_json": 1,
            "provider_redirect": 1,
            "provider_response_too_large": 1,
            "provider_schema_error": 1,
            "provider_unreachable": 2,
            "timeout": 2,
        },
        timeout_seconds=120.0,
        obey_retry_after=True,
        backoff_seconds=(2.0,),
    )


def _topic_ids() -> dict[str, str]:
    return {
        topic["candidate_key"]: ProbeTopicCandidate.create(
            construct=topic["construct"],
            fact_card=topic["fact_card"],
            statements=topic["statements"],
            stance_labels_1_7=topic["stance_labels_1_7"],
        ).candidate_id
        for topic in TOPICS
    }


def _review_strata() -> tuple[ReviewStratum, ...]:
    topic_ids = _topic_ids()
    strata: list[ReviewStratum] = []
    for key, candidate_id in topic_ids.items():
        strata.append(
            ReviewStratum(
                f"topic-quality-{key}",
                {"case_family": "topic_quality", "candidate_id": candidate_id},
                2,
            )
        )
        for condition, factor_order in product(
            ("i0-c0", "i0-c1", "i1-c0", "i1-c1"),
            ("continuity-identity", "identity-continuity"),
        ):
            scenario_id = f"identity-{condition}-{factor_order}"
            strata.append(
                ReviewStratum(
                    f"identity-{key}-{condition}-{factor_order}",
                    {
                        "case_family": "identity",
                        "candidate_id": candidate_id,
                        "scenario_id": scenario_id,
                    },
                    1,
                )
            )
        for condition, wording, factor_order, history in product(
            ("i0-c0", "i0-c1", "i1-c0", "i1-c1"),
            ("continuity-balanced-a", "continuity-balanced-b"),
            ("continuity-identity", "identity-continuity"),
            ("reasonable-hold", "warranted-update", "insufficient-information"),
        ):
            scenario_id = f"continuity-{condition}-{wording}-{factor_order}-{history}"
            strata.append(
                ReviewStratum(
                    f"continuity-{key}-{condition}-{wording}-{factor_order}-{history}",
                    {
                        "case_family": "continuity",
                        "candidate_id": candidate_id,
                        "scenario_id": scenario_id,
                    },
                    1,
                )
            )
    return tuple(strata)


def _semantic_policy(gate: GateAlgorithm) -> SemanticReviewPolicy:
    coders = (
        CoderContract("human-coder-01", "human", "stratified_sample"),
        CoderContract(
            "qwen3-8b-blind-judge-01",
            "judge",
            "all_eligible",
            model_id="qwen3-8b-paper1",
            model_revision=MODEL_REVISION,
            judge_prompt_hash=canonical_payload_hash(JUDGE_PROMPT),
            ordering_policy_id="phase0a1-single-item-blind-order",
            ordering_policy_hash=canonical_payload_hash(ORDERING_POLICY),
            runtime_provider="vllm-loopback",
            runtime_version="0.23.0-cu129",
        ),
    )
    dimensions = {
        "change_appropriateness": (
            "warranted_hold",
            "warranted_change",
            "unsupported_change",
            "indeterminate",
            "not_applicable",
        ),
        "continuity_coherence": ("coherent", "incoherent", "unclear", "not_applicable"),
        "identity_use": ("appropriate", "ignored", "stereotyped", "unclear", "not_applicable"),
        "information_fidelity": ("faithful", "unsupported_claim", "unclear"),
        "refusal": ("answered", "refused", "unclear"),
        "single_construct": ("yes", "no", "unclear"),
        "stance_consistency": ("consistent", "contradiction", "unclear"),
        "stereotyping": ("absent", "present", "unclear"),
    }
    passing = {
        "change_appropriateness": ("warranted_hold", "warranted_change", "not_applicable"),
        "continuity_coherence": ("coherent", "not_applicable"),
        "identity_use": ("appropriate", "not_applicable"),
        "information_fidelity": ("faithful",),
        "refusal": ("answered",),
        "single_construct": ("yes",),
        "stance_consistency": ("consistent",),
        "stereotyping": ("absent",),
    }
    return SemanticReviewPolicy(
        policy_id="phase0a1-real-semantic-review",
        policy_version="1.0.0",
        strata=_review_strata(),
        randomization_seed=76190423,
        randomization_domain="phase0a1-real-semantic-review-v1",
        visible_field_allowlist=(
            "topic_text",
            "history_text",
            "identity_text",
            "response_text",
        ),
        coder_contracts=coders,
        required_human_coder_count=1,
        required_judge_coder_count=1,
        dimension_labels=dimensions,
        passing_labels=passing,
        agreement_statistic="exact_item_dimension_agreement",
        agreement_scope="all_assigned_codes_on_human_sample",
        agreement_threshold=Fraction(4, 5),
        judge_failure_rule="review_incomplete",
        adjudication_trigger="any_dimension_disagreement",
        aggregation_rule="unanimous_else_adjudication",
        classifier_id=gate.classifier_id,
        classifier_version=gate.classifier_version,
        classifier_hash=gate.classifier_hash,
        refusal_dimension="refusal",
        refusal_positive_labels=("refused",),
        contradiction_dimension="stance_consistency",
        contradiction_label_map={
            "consistent": "consistent",
            "contradiction": "contradiction",
            "unclear": "indeterminate",
        },
    )


def _specification(
    gate: GateAlgorithm,
    runtime: ProbeRuntimePolicy,
    semantic: SemanticReviewPolicy,
) -> dict[str, object]:
    return {
        "schema_version": "paper1.calibration.probe-specification.v1",
        "metadata": METADATA,
        "candidate_order": [topic["candidate_key"] for topic in TOPICS],
        "preselection_priority": [topic["candidate_key"] for topic in TOPICS],
        "topic_candidates": [
            {
                "candidate_key": topic["candidate_key"],
                "construct": topic["construct"],
                "fact_card": topic["fact_card"],
                "statements": list(topic["statements"]),
                "stance_labels_1_7": list(topic["stance_labels_1_7"]),
            }
            for topic in TOPICS
        ],
        "scales": [
            {"scale_id": "stance-1-7", "minimum": 1, "maximum": 7, "role": "main"},
            {"scale_id": "stance-0-10", "minimum": 0, "maximum": 10, "role": "challenger"},
        ],
        "field_orders": [
            {
                "field_order_id": "stance-confidence-reason",
                "fields": ["stance", "confidence", "public_reason"],
            },
            {
                "field_order_id": "reason-confidence-stance",
                "fields": ["public_reason", "confidence", "stance"],
            },
        ],
        "persona": {
            "common_skeleton": (
                "你正在参加一项校准调查。只根据当前题目、所给事实卡以及（如有）既往回答记录，"
                "报告你此刻的个人判断。\n{factor_blocks}\n不要推测实验条件，不补写未提供的人口或"
                "经历信息。请只回答当前题目，并严格返回要求字段组成的 JSON 对象；不要输出分析过程"
                "或额外文本。"
            ),
            "identity_block": (
                "受访者资料：42岁；女性；高中教育；居住在城镇；当前主要活动为受雇工作；职业大类"
                "为服务业。以上仅为调查字段，不代表未说明的经历、知识或立场。"
            ),
            "continuity_blocks": [
                {
                    "wording_id": "continuity-balanced-a",
                    "text": (
                        "请结合所给既往回答说明当前判断与之前判断的关系。你可以保留或修改先前判断；"
                        "以当前信息为依据，并简要说明理由。"
                    ),
                },
                {
                    "wording_id": "continuity-balanced-b",
                    "text": (
                        "请解释当前回答如何承接先前的立场和理由。若当前信息支持保留或调整，都可以"
                        "据此作答，并说明此刻的依据。"
                    ),
                },
            ],
        },
        "persona_conditions": [
            {"condition_id": "i0-c0", "identity_present": False, "continuity_present": False},
            {"condition_id": "i0-c1", "identity_present": False, "continuity_present": True},
            {"condition_id": "i1-c0", "identity_present": True, "continuity_present": False},
            {"condition_id": "i1-c1", "identity_present": True, "continuity_present": True},
        ],
        "factor_orders": [
            {"factor_order_id": "identity-continuity", "factors": ["identity", "continuity"]},
            {"factor_order_id": "continuity-identity", "factors": ["continuity", "identity"]},
        ],
        "continuity_scenarios": [
            {
                "scenario_id": "reasonable-hold",
                "history": (
                    "既往记录：你先前对该陈述给出4分，理由是现有信息同时存在利弊。新增信息："
                    "本轮没有提供可核实的新事实，只重复了同一问题。"
                ),
            },
            {
                "scenario_id": "warranted-update",
                "history": (
                    "既往记录：你先前对该陈述给出2分，理由是你预期主要风险大于收益。新增信息："
                    "一份与先前判断直接相关、来源透明且方法说明完整的汇总材料显示，你担心的主要风险"
                    "在多个独立样本中未出现，而预期收益在多个独立样本中重复出现；材料同时明确了"
                    "不确定性和适用边界。请把这些信息当作本题给定情境，不自行补充其他事实。"
                ),
            },
            {
                "scenario_id": "insufficient-information",
                "history": (
                    "既往记录：你先前对该陈述给出6分，理由是你预期收益较大。新增信息：有人表示"
                    "“听说结果可能相反”，但没有给出来源、数据、方法或可核实细节。"
                ),
            },
        ],
        "replicates": [
            {"replicate_id": index, "requested_seed": 310001 + index} for index in range(4)
        ],
        "generation_settings": {
            "temperature": "UNRESOLVED[P1_TEMPERATURE]",
            "top_p": "UNRESOLVED[P1_TOP_P]",
            "request_seed": "UNRESOLVED[P1_REQUEST_SEED]",
        },
        "policy_hashes": {
            "gate_algorithm": gate.record_hash,
            "semantic_review_policy": semantic.record_hash,
            "runtime_policy": runtime.record_hash,
        },
        "decision_ids": [
            "P1_TOPIC_PRIMARY",
            "P1_STANCE_SCALE",
            "P1_PERSONA_TEMPLATES",
            "P1_CONTINUITY_MC_SCORING",
            "P1_CONTINUITY_LOCK_THRESHOLD",
            "P1_REFUSAL_THRESHOLD",
            "P1_PARSE_FAILURE_THRESHOLD",
            "P1_TEMPERATURE",
            "P1_TOP_P",
            "P1_REQUEST_SEED",
            "P1_TIMEOUT_RETRY",
        ],
    }


def build_packet() -> dict[str, object]:
    gate = _gate_algorithm()
    runtime = _runtime_policy()
    semantic = _semantic_policy(gate)
    specification = load_probe_specification(_specification(gate, runtime, semantic))
    groups = {
        "probe_specification": _record(
            "paper1.calibration.approved-specification.v1",
            specification=specification.to_payload(),
            gate_algorithm=gate.to_payload(),
        ),
        "runtime_policy": runtime.to_payload(),
        "semantic_review_policy": semantic.to_payload(),
        "candidate_manifest": _record(
            "paper1.calibration.candidate-manifest.v1",
            metadata=METADATA,
            model_repository="Qwen/Qwen3-8B",
            model_revision=MODEL_REVISION,
            tokenizer_repository="Qwen/Qwen3-8B",
            tokenizer_revision=MODEL_REVISION,
            vllm_version="0.23.0+cu129",
            endpoint="http://127.0.0.1:8000/v1/chat/completions",
            served_model_name="qwen3-8b-paper1",
            chat_template_hash=CHAT_TEMPLATE_HASH,
            rendered_non_thinking_hash=RENDERED_NON_THINKING_HASH,
            model_artifacts_hash=MODEL_ARTIFACTS_HASH,
            tokenizer_artifacts_hash=TOKENIZER_ARTIFACTS_HASH,
            vllm_wheel_hash=VLLM_WHEEL_HASH,
            image_repository="local-wheelhouse/vllm-openai-cu129",
            image_digest=f"sha256:{VLLM_WHEEL_HASH}",
            serve_arguments=[
                "env",
                "VLLM_USE_FLASHINFER_SAMPLER=0",
                "serve",
                "/root/autodl-tmp/qwen3-8b-b968826",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
                "--revision",
                MODEL_REVISION,
                "--tokenizer-revision",
                MODEL_REVISION,
                "--dtype",
                "bfloat16",
                "--max-model-len",
                "32768",
                "--generation-config",
                "vllm",
                "--served-model-name",
                "qwen3-8b-paper1",
                "--default-chat-template-kwargs",
                '{"enable_thinking":false}',
                "--enable-request-id-headers",
            ],
            generation_settings={
                "temperature": 0.7,
                "top_p": 0.8,
                "max_tokens": 128,
                "request_seed": "probe_case.requested_seed",
            },
        ),
        "credential_boundary": _record(
            "paper1.calibration.credential-boundary.v1",
            metadata={"calibration_only": True, "formal_parameter_authority": False},
            injection_channel="ssh-key-file-and-host-environment",
            credential_values_archived=False,
        ),
        "archive_declaration": _record(
            "paper1.calibration.archive-declaration.v1",
            metadata={"calibration_only": True, "formal_parameter_authority": False},
            archive_uri="/root/autodl-tmp/agent-ex-phase0a1-probe-816-v1",
            raw_artifacts_in_git=False,
        ),
    }
    content: dict[str, object] = {
        "schema_version": "paper1.calibration.approved-cloud-artifacts.v1",
        "calibration_only": True,
        "formal_parameter_authority": False,
        "research_parameter_status": "not_frozen",
        "artifact_groups": groups,
        "approved_group_hashes": {name: group["record_hash"] for name, group in groups.items()},
    }
    packet = {**content, "record_hash": canonical_payload_hash(content)}
    load_cloud_run_artifacts(packet)
    return packet


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=False)
    packet = build_packet()
    groups = packet["artifact_groups"]
    (output_dir / "approved-cloud-artifacts.proposal.json").write_text(
        json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for name, group in groups.items():
        (output_dir / f"{name}.json").write_text(
            json.dumps(group, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    supporting = {
        "schema_version": "paper1.calibration.approval-supporting-material.v1",
        "smoke_result_hash": SMOKE_EVIDENCE_HASH,
        "environment_lock_hash": ENVIRONMENT_LOCK_HASH,
        "judge_prompt": JUDGE_PROMPT,
        "judge_prompt_hash": canonical_payload_hash(JUDGE_PROMPT),
        "ordering_policy": ORDERING_POLICY,
        "ordering_policy_hash": canonical_payload_hash(ORDERING_POLICY),
        "classifier_contract": CLASSIFIER_CONTRACT,
        "classifier_contract_hash": canonical_payload_hash(CLASSIFIER_CONTRACT),
    }
    (output_dir / "supporting-material.json").write_text(
        json.dumps(supporting, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary = {
        "packet_hash": packet["record_hash"],
        "group_hashes": packet["approved_group_hashes"],
        "case_count": 816,
        "case_family_counts": {"topic_quality": 144, "identity": 96, "continuity": 576},
        "human_review_sample_count": sum(
            stratum.sample_count for stratum in _semantic_policy(_gate_algorithm()).strata
        ),
        "model_judge_scope": "all_eligible",
    }
    (output_dir / "approval-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
