---
status: active
authority: project agent operating rules; subordinate to the specification chain and verified against the evidence chain
supersedes: informal handoff instructions in README.md and logs/notion-2026-05-31.md for future Paper 1 work
last-verified: 2026-07-16
---

# Agent-EX 协作规则

## 五分钟路由

1. 先读 `docs/project-overview.md`，区分历史证据、Paper 1 和后续研究。
2. Paper 1 的已批准研究边界读 `docs/superpowers/specs/2026-07-14-paper1-focused-research-design.md`。
3. 实施顺序读 `docs/superpowers/plans/2026-07-14-paper1-platform-implementation-plan.md`。
4. 人类协议草案读 `docs/paper1-protocol.md`；未决项只在 `docs/research-qa.md` 决策。
5. 已确认选择读 `docs/decisions.md`；历史 pilot 读 `docs/archive-index.md`。

## 权威层级

- **规范链（规定应当发生什么）**：冻结的机器协议 YAML（创建后）→ 协议 schema（结构约束）→ 已确认的人类协议 → 07-14 聚焦规格 → 平台规格与实施计划 → overview/README/Notion/历史日志。低层材料不得覆盖高层冻结规范。
- **证据链（证明实际发生了什么）**：原始 attempt/event → checkpoint 与冻结数据集 → run manifest 及其 hash/归档定位 → 汇总与论文结果。manifest/event 只能记录实际执行，不得反向覆盖或修改冻结协议。

实际执行与冻结协议不一致时，该 run 应标记为偏离/不合规并停止进入主分析；不能因为 manifest 忠实记录了偏离就把偏离视为新的规范。

## Paper 1 红线

- 主矩阵固定为 `identity 2 × continuity 2 × exposure 3 = 12 cells`。
- 正式规模固定为 N=1000、T=50、首批10个 matched seeds，盲态规则最多扩到20个。
- 主模型路线为自部署 Qwen3-8B BF16、non-thinking、vLLM；具体 revision 在 Phase 0B 冻结。
- API 仅作固定 snapshot 的外部稳健性子集，不解释为“API 部署效应”。
- Paper 1 主实验不微调权重。
- 不把 RLHF/abliterated、动态重连、真人—AI 混合网络、weak/lifelong 复合 prompt 塞回主矩阵。
- 不把 N 当重复数；seed/run 才是主要独立重复单位。
- 不把单向端点集中称为经典双峰极化。

## 实施规则

- 旧 pilot 原地冻结；新研究能力只进入 `platform/`。
- Notebook 只调用公开接口和展示结果，不得承载正式主循环或指标定义。
- 同轮更新必须读取不可变的上一轮快照并同步提交。
- prompt、exposure、原始响应、解析、重试、模型身份和 hash 必须可追溯。
- 任一尚未确认的研究参数必须引用 `docs/research-qa.md` 中的稳定 ID 并使用统一的 `UNRESOLVED[...]` 标记，不得用 coder 默认值填补。
- formal config 只要含未决字段就必须验证失败。
- 不修改或提交 `.codex/`；原始大规模结果不进入 Git，只提交 manifest、hash 与归档定位。
