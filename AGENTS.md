---
status: active
authority: project agent operating rules; subordinate to the specification chain and verified against the evidence chain
supersedes: informal handoff instructions in README.md and logs/notion-2026-05-31.md for future Paper 1 work
last-verified: 2026-07-29
---

# Agent-EX 协作规则

## 五分钟路由

1. 先读 `logs/2026-07-29-phase3a-handoff.md`，确认分支、worktree、已完成边界与恢复顺序。
2. 再读 `docs/project-overview.md`，区分历史证据、Paper 1 和后续研究。
3. Paper 1 的已批准研究边界先读 `docs/superpowers/specs/2026-07-29-paper1-phase4a-completion-design.md`，再用 `docs/superpowers/specs/2026-07-14-paper1-focused-research-design.md` 补充理论与统计背景。
4. 07-14实施计划只用于追溯已完成Phase 3A；其中Phase 4同步语义已失效。Phase 4B
   新计划须在07-29完成规格通过整份书面复核后创建。
5. 人类协议草案读 `docs/paper1-protocol.md`；未决项只在 `docs/research-qa.md` 决策。
6. 已确认选择读 `docs/decisions.md`；历史 pilot 读 `docs/archive-index.md`。

## 权威层级

- **规范链（规定应当发生什么）**：冻结的机器协议 YAML（创建后）→ 协议 schema（结构约束）→ 已确认的人类协议 → 07-29 Phase 4A完成规格 → 07-14聚焦规格 → 平台规格与实施计划 → overview/README/Notion/历史日志。低层材料不得覆盖高层冻结规范。
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
- `D-2026-07-29-08`至`19`及07-29完成规格已冻结事件级机制：不得继续实现旧的
  全员同步engine。事件必须读取前一成功提交状态并严格串行提交；失败不得改变状态
  或游标，重试/恢复必须保持同一event identity；sweep只作观测和checkpoint边界。
- `D-2026-07-29-09`已将私人意见状态与最近公开帖子分离；社会曝光只能读取公开
  帖子，`publish_flag`必须在运行前外生冻结。schema未修订前不得用现有
  `AgentState`/`OpinionRecord`结构假装已经支持两阶段状态。
- `D-2026-07-29-10`规定`private_state`为唯一primary；`public_stock`、
  `public_flow`和`expression_gap`是强制预注册secondary。不得按结果显著性调换排序。
- `D-2026-07-29-11`规定全部Agent都有正注意权重，公开表达采用hurdle–Beta；
  主模型注意与表达倾向独立，正相关仅作冻结敏感性。精确参数仍须
  `UNRESOLVED[...]`，不得使用90-9-1或coder默认值。
- `D-2026-07-29-12`规定主注意权重采用正截断对数正态并归一化`sum(w_i)=N`；
  截断Pareto和等权分别为重尾敏感性与无异质性机制基线。精确参数、校准阈值和
  制品在Phase 0冻结前必须保持`UNRESOLVED[...]`，不得按意见结果选择。
- `D-2026-07-29-13`规定E1使用每matched seed固定、逐节点保持WS度数、禁用真实
  WS边且全连通的shadow graph；E2使用原WS。构图算法和制品冻结前必须fail closed，
  不得按sweep/事件动态换人或在运行中修图。
- `D-2026-07-29-14`至`19`规定社会feed为有限未读过程：首激活可读邻居round-0帖，
  之后读取游标后的最新至多B条邻居公开帖，允许同源多帖、超量旧帖过期、不回填，
  入选后按冻结seed排列槽位。B=6只是Phase 0主候选，最终机器值冻结前仍须
  `UNRESOLVED[...]`；自身记忆同理以K=3为主候选而非coder默认值。
- prompt、exposure、原始响应、解析、重试、模型身份和 hash 必须可追溯。
- 任一尚未确认的研究参数必须引用 `docs/research-qa.md` 中的稳定 ID 并使用统一的 `UNRESOLVED[...]` 标记，不得用 coder 默认值填补。
- formal config 只要含未决字段就必须验证失败。
- 不修改或提交 `.codex/`；原始大规模结果不进入 Git，只提交 manifest、hash 与归档定位。
