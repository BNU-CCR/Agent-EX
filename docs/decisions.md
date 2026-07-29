---
status: active decision log
authority: confirmed project decisions subordinate to the frozen machine protocol; run manifests are execution evidence only
supersedes: scattered decision statements in README.md, design/ and Notion handoffs
last-verified: 2026-07-29
---

# 决策记录

下列 fenced YAML 是 formal gate 唯一可读取的审批记录。当前机器协议仍为 draft，
因此尚无已冻结字段记录；后续每条记录必须完整填写
`decision_record_id`、UTC `approved_at`、`approvers`、`field_ids` 与
`artifact_hashes`。`artifact_hashes` 必须逐一覆盖记录中的每个 `field_id`，其值是
该决策 ID 在 schema 中标注字段的实际 JSON pointer 值所组成 canonical payload 的
SHA-256；payload 是按键排序、无多余空白并以 UTF-8 编码的
`{JSON pointer: actual value}` 映射。本页其余叙述仅保留研究决策语境，不能通过
字符串命中充当审批。

<!-- BEGIN DECISION RECORDS -->
```yaml
records: []
```
<!-- END DECISION RECORDS -->

## D-2026-07-14-01：Paper 1 聚焦矩阵

**状态：** 已确认。
**决定：** 采用 identity 2 × continuity 2 × social exposure 3 的12 cells；唯一 primary outcome 为 `Δlog((B+ε)/(W+ε))`；唯一 primary estimand 为 continuity 对 `WS-shuffled` 的 matched-seed DiD 调节。正式规模 N=1000、T=50、首批10 matched seeds，按一次盲态 nuisance-variance 重估最多20个。

**理由：** 将身份信息、历史连续性和网络暴露拆开识别，避免 pilot 的复合 prompt confound；N 与 seed 分别解决网络规模和独立重复问题。

**未选择：** weak/lifelong × BA/WS 主矩阵；把 RLHF、动态重连或多模型并入 Paper 1。

## D-2026-07-16-01：开放权重主模型与 API 稳健性分工

**状态：** 已确认策略；部分运行字段待 Phase 0B 冻结。
**决定：**

- 主模型使用 Qwen3-8B BF16、non-thinking，通过 vLLM 自部署，运行完整正式矩阵。
- 固定精确模型 revision；其 hash 记为 `UNRESOLVED[P1_MODEL_REVISION]`，由 Phase 0B 实测后冻结。
- Paper 1 主实验不微调权重；不把量化权重与 BF16 主矩阵混用。
- API 仅运行预注册的固定 snapshot 外部稳健性子集；推荐的核心8 cells 只是会审候选，不是 schema 常量。最终可从12个 canonical cell IDs 中审批1至12个不重复 cells，并由 `UNRESOLVED[P1_API_ROBUSTNESS_CELLS]` 冻结；N/T/seeds 暂拟 N=200、T=50、5 matched seeds并由 `UNRESOLVED[P1_API_ROBUSTNESS_SCALE_FREEZE]` 冻结。
- API 与开放模型的差异只能解释为模型系统稳健性，不得解释为“API 部署效应”。

**理由：** 固定权重、tokenizer、模板和推理栈提高百万级生成的可追溯性和可复现性；API 提供有限外部效度而不支配主检验。

**未选择：** 全矩阵依赖滚动 API 别名；在 Paper 1 中用 LoRA/领域微调同时改变权重；把 API 结果纳入主假设检验。

## D-2026-07-16-02：文档权威边界

**状态：** 已确认实施。
**决定：** 07-14 聚焦规格是协议冻结前的研究设计权威；05-31 README/Notion 和 `design/` 保留历史语境，不再提供正式执行参数。规范链中的 schema 约束冻结机器协议；证据链中的 attempt/event、冻结数据与 manifest 记录实际发生。证据不得覆盖规范，执行偏离必须标记为不合规。
