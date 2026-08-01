<!-- BEGIN GENERATED PROTOCOL SUMMARY -->
```yaml
protocol_id: P1-LLM-OPINION-DYNAMICS
execution_hash: 89c97f896d7c6a0490e04c223e812df648499cc5ca71b9978fedaacc68f0b0c5
primary_outcome_id: UNRESOLVED[P1_PRIMARY_OUTCOME]
primary_estimand_id: P1_PRIMARY_WS_SHADOW_AVERAGE_EFFECT
key_secondary_estimand_ids:
- P1_SECONDARY_CONTINUITY_WS_SHADOW_MODERATION
outcome_priority:
  primary: private_state
  required_secondary:
  - public_stock
  - public_flow
  - expression_gap
process_contract:
  activation_mode: weighted_random_sequential_with_replacement
  feed_message_capacity: UNRESOLVED[P1_MAX_NEIGHBORS]
  event_identity: run_id_plus_event_ordinal
  resume_cursor: next_event_ordinal
network_freeze_contract:
  library_version: UNRESOLVED[P1_NETWORK_LIBRARY_VERSION]
  ws_builder_algorithm: UNRESOLVED[P1_WS_BUILDER_ALGORITHM]
  shadow_builder_algorithm: UNRESOLVED[P1_SHADOW_BUILDER_ALGORITHM]
  shadow_max_attempts: UNRESOLVED[P1_SHADOW_MAX_ATTEMPTS]
  shadow_trial_budget_per_edge: UNRESOLVED[P1_SHADOW_TRIAL_BUDGET_PER_EDGE]
  structure_gate_algorithm_version: UNRESOLVED[P1_STRUCTURE_GATE_ALGORITHM_VERSION]
  ring_lattice_algorithm: UNRESOLVED[P1_RING_LATTICE_BASELINE_ALGORITHM]
  random_null_algorithm: UNRESOLVED[P1_RANDOM_GRAPH_NULL_ALGORITHM]
  random_null_replicates: UNRESOLVED[P1_RANDOM_GRAPH_NULL_REPLICATES]
factor_levels:
  identity:
  - identity_absent
  - identity_present
  continuity:
  - continuity_absent
  - continuity_present
  exposure:
  - self_history_only
  - shuffled_social
  - ws_neighbors
cell_ids:
- P1-I0-C0-E0
- P1-I0-C0-E1
- P1-I0-C0-E2
- P1-I0-C1-E0
- P1-I0-C1-E1
- P1-I0-C1-E2
- P1-I1-C0-E0
- P1-I1-C0-E1
- P1-I1-C0-E2
- P1-I1-C1-E0
- P1-I1-C1-E1
- P1-I1-C1-E2
formal_scale:
  population_size: 1000
  rounds: 50
  matched_seeds_initial: 10
  matched_seeds_max: 20
model_route:
  provider: self_hosted
  model_id: Qwen/Qwen3-8B
  precision: bf16
  thinking: false
  runtime: vllm
```
<!-- END GENERATED PROTOCOL SUMMARY -->

---
status: draft; not confirmed or frozen
authority: human-readable protocol draft derived from the approved focused spec; machine execution is forbidden until unresolved fields are frozen
supersedes: pilot-3.0 four-condition design for future formal Paper 1 runs; does not supersede pilot evidence
last-verified: 2026-07-29
---

> **2026-07-29 Phase 4B状态：** schema、draft YAML与页首generated summary已完成
> Phase 4A/4A.1协议迁移。当前草案仍不可用于formal run：event ordinal、private/public
> 与checkpoint的domain记录将在Phase 4B-2迁移，且机器协议仍含未冻结研究参数、
> `decision_provenance`尚无正式审批记录。上述任一阻断未关闭时都必须fail closed。

# Paper 1 研究协议草案

**Protocol ID:** `P1-LLM-OPINION-DYNAMICS`
**Protocol version:** `UNRESOLVED[P1_PROTOCOL_VERSION]`

机器协议以 `protocol.version` 为唯一版本路径。议题块只保存稳定 `topic.id`、公开陈述
`topic.statement` 及其 `topic.statement_sha256`，不得加入 `prompt`、`system` 或
`instruction` 字段。四个 identity×continuity persona 组合只登记 `template_id` 与
`template_sha256`；模板正文是受版本控制的外部制品，不进入机器协议自由文本字段。

formal 冻结还必须让 `decision_provenance` 完整覆盖 schema 的每个 `P1_*` 决策 ID，
逐项记录 `decision_record_id`、严格 RFC3339 UTC 的 `approved_at` 与非空
`approvers`，并与 `docs/decisions.md` 的 fenced YAML 记录精确一致。决策 ID 必须是
对应记录 `field_ids` 的完整成员，且至少一名 approver 必须精确匹配
`docs/research-qa.md` 登记的 owner 角色。每个 `field_id` 都必须以其 schema
`x-decision-id` 所标注字段的实际 JSON pointer 值组成 canonical payload，并将其
SHA-256 精确写入对应记录的 `artifact_hashes[field_id]`。canonical payload 是
`{JSON pointer: actual value}` 映射，按键排序、无多余空白、UTF-8 编码后计算
SHA-256。全文子串、伪 approver 或未绑定字段均不构成审批。formal validation 会
自动校验本页 generated summary，且要求 generated summary 标记恰好出现一对并
顺序正确；不同步即拒绝运行。

## 1. 研究对象与边界

研究异质初始立场的 LLM-agent 在固定讨论网络中经历多轮局部信息暴露、理由生成与异质加权随机顺序更新后形成的意见形态。实验不直接估计真实公众或真实平台部署 AI Agent 的平均社会效应，也不研究关系拓扑演化。

Paper 1 主实验排除 RLHF/abliterated、权重微调、真人—AI 混合网络、推荐算法、动态重连、多模型/多语言全因子，以及 pilot 的 weak/lifelong 复合 prompt。

## 2. 因素与稳定 cell IDs

- Identity：`I0=identity_absent`；`I1=identity_present`。
- Continuity：`C0=continuity_absent`；`C1=continuity_present`。
- Exposure：`E0=self_history_only`；`E1=shuffled_social`；`E2=ws_neighbors`。

| Cell ID | Identity | Continuity | Exposure |
|---|---|---|---|
| P1-I0-C0-E0 | absent | absent | self history only |
| P1-I0-C0-E1 | absent | absent | shuffled social |
| P1-I0-C0-E2 | absent | absent | WS neighbors |
| P1-I0-C1-E0 | absent | present | self history only |
| P1-I0-C1-E1 | absent | present | shuffled social |
| P1-I0-C1-E2 | absent | present | WS neighbors |
| P1-I1-C0-E0 | present | absent | self history only |
| P1-I1-C0-E1 | present | absent | shuffled social |
| P1-I1-C0-E2 | present | absent | WS neighbors |
| P1-I1-C1-E0 | present | present | self history only |
| P1-I1-C1-E1 | present | present | shuffled social |
| P1-I1-C1-E2 | present | present | WS neighbors |

Identity 只能增删人口学和议题相关经历块，不能泄露方向性长期立场。Continuity 只能增删历史解释连贯要求，并必须明确允许被有说服力的信息改变。所有条件禁止抗从众、最大步长、“永不改变”和固定方向性价值立场。

## 3. 共享对象与更新合同

同一 matched seed 的12个 cells 共享人口、身份材料、初始立场与理由、WS图和逐节点度数保持的shadow graph、注意/表达参数、完整激活与发布日程、模型版本和生成参数。一个run内事件严格串行，每个成功事件读取前一成功提交后的状态并立即提交；不同run可并行。

每个Agent在round 0均有一条公开初始帖，结构性潜水者只在其后保持沉默。`self_history_only`不接收其他Agent信息；`shuffled_social`只从固定shadow graph邻居读取，`ws_neighbors`只从固定WS一阶邻居读取。每次激活最多读取游标后的最新B条新公开帖，首激活可读取round-0帖，不足不回填、过量旧帖过期、允许同一发送者多帖；入选消息再按预生成随机槽位呈现。模型自身记忆只含最近K次成功私人更新。失败事件不改变任何研究状态或游标，重试/恢复必须重放同一事件。所有schedule、映射、实际exposure和原始attempt必须保存和验证。

## 4. 结果与 estimand

单一primary outcome为`UNRESOLVED[P1_PRIMARY_OUTCOME]`，须在读取正式结果前由统计
规格冻结。旧候选组际结构指标为预注册终点`UNRESOLVED[P1_ENDPOINT_TSTAR]`的：

`S_t = log((B_t + ε)/(W_t + ε))`，`ΔS_T = S_T* - S_0`

其中 `ε=UNRESOLVED[P1_LOG_EPSILON]`；B/W 的精确总体权重和缺组规则见 `UNRESOLVED[P1_BW_FORMULA]`。报告 ΔS 时必须同时展示 B 与 W。

primary estimand是在`identity × continuity`四个persona条件上等权平均的
`WS - shadow` matched-seed差异，迁移后ID为
`P1_PRIMARY_WS_SHADOW_AVERAGE_EFFECT`。continuity对该差异的DiD调节为关键
secondary；identity交互、`WS-self`、完整轨迹、分布形态和文本多样性均为
secondary/exploratory。

## 5. 规模与模型

- 构念/真实模型校准：N=20/50/100。
- 有限规模 gate：在主对比上运行 N=200/500/1000；具体 cells/seeds 为 `UNRESOLVED[P1_SCALE_GATE_DESIGN]`。
- 正式主实验：N=1000、T=50、12 cells、首批10 matched seeds；按冻结的盲态规则一次扩至最多20个。
- 主模型：Qwen3-8B BF16、non-thinking、vLLM 自部署、全矩阵；revision 为 `UNRESOLVED[P1_MODEL_REVISION]`。
- API：固定 snapshot 的外部稳健性子集，最终 cells 由 `UNRESOLVED[P1_API_ROBUSTNESS_CELLS]` 审批冻结；schema 允许从12个 canonical cell IDs 中选择1至12个不重复 cells。推荐但不强制的核心8-cell 候选为 `P1-I0-C0-E1/E2`、`P1-I0-C1-E1/E2`、`P1-I1-C0-E1/E2`、`P1-I1-C1-E1/E2`，即全部 identity×continuity 下的 shuffled 与 WS。规模暂拟 N=200、T=50、5 matched seeds，仅由 `UNRESOLVED[P1_API_ROBUSTNESS_SCALE_FREEZE]` 冻结。它是模型系统比较，不是 API 部署效应。
- 主实验不微调权重；量化权重不得与 BF16 主矩阵混跑。

## 6. Gates、失败与停止

Phase 0A 必须证明 identity 只改变身份信息、continuity 提高连贯性但不锁死、四 persona cells 非退化、量表只测单一构念，且议题无不可接受的单向偏置/拒答。

Phase 0B必须完成mock N=20/100/1000、真实N=20/50/100、形态dry run、吞吐/成本/
失败率和primary matched contrast方差诊断。有限规模与正式gate仍需冻结
`UNRESOLVED[P1_GATE_PRIMARY_OUTCOME_STABILITY]`、
`UNRESOLVED[P1_GATE_FAILURE_MAX]`、`UNRESOLVED[P1_GATE_THROUGHPUT_MIN]`、
`UNRESOLVED[P1_GATE_MEMORY_MAX]`和`UNRESOLVED[P1_GATE_DURATION_MAX]`。旧
`P1_GATE_DELTA_STABILITY`只可登记候选组际结构secondary诊断，不控制主实验准入。

每个预期事件只有成功提交才推进主状态链；重试耗尽则记录failed attempt/event并立即
停止run，且不改变状态或游标。只有所有预期事件均succeeded的complete run可进入主
分析。`excluded`只能是对成功事件或完整run的分析层标记，不是继续状态链的替代终态；
Paper 1主路径禁止imputed/fallback。任何例外必须由
`UNRESOLVED[P1_ANALYSIS_ELIGIBILITY]`另行冻结，不得用结果方向决定继续、删seed或改协议。

## 7. 推断与证据边界

seed/run 是独立重复单位；同 seed 条件采用配对/区组分析。最终推断方法为
`UNRESOLVED[P1_PRIMARY_INFERENCE]`。首10 seeds 的盲态扩样只能读取在四个persona
条件上等权平均的`WS-shadow` seed-level对比之中心化残差，不得输出均值、方向、CI、
p值或cell均值；`δ_min=UNRESOLVED[P1_DELTA_MIN]`。

允许的结论限于指定模型、议题、persona 与暴露条件下的 LLM-agent 意见动力学。不得把 persona 当真实身份、把固定网络称为关系网络演化、把单向漂移称为两极化，或把 N=1000 当作外部效度保证。

所有未决项的 owner、候选、推荐和最迟 gate 见 `docs/research-qa.md`。本协议在这些字段及机器协议未冻结前不得启动 formal run。
