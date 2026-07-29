---
status: active navigation baseline
authority: project scope and evidence map; not an execution protocol
supersedes: README.md and logs/notion-2026-05-31.md as the entry point for work after 2026-07-14
last-verified: 2026-07-29
---

# Agent-EX 项目总览

Agent-EX 研究 LLM-agent 在多轮在线讨论中的意见与理由演化。现实背景是生成式 Agent 可能作为新型社交机器人进入公共讨论；Paper 1 的直接证据边界仍是由 LLM-agent 构成的模拟网络，而不是真人平台上的平均社会效应。

## 三层项目状态

| 层级 | 内容 | 可作何种证据 |
|---|---|---|
| 历史 pilot | pilot-1.0/2.0/3.0，N=20 或参考实现 | 机制线索、迁移回归和失败案例，不能替代正式实验 |
| Paper 1 | 固定 WS 网络上的生成式意见动力学；12-cell 可识别设计 | 指定模型、议题、persona 操作和暴露条件下的因果对比 |
| 后续项目 | Paper 2 安全对齐、真实网络外部效度、长期 benchmark | 尚未实施，不得写成已有能力或发现 |

## Paper 1 已确认骨架

- 研究对象：异质初始立场的 LLM-agent 讨论网络。
- 因素：身份信息、身份连续性要求、社会暴露。
- 社会暴露：self-history only、degree-matched shuffled social、固定 WS 邻居。
- 主要结果：`ΔS_T = Δ log((B+ε)/(W+ε))`，并同时报告 B 与 W。
- 主要 estimand：continuity 对 `WS - shuffled` 的 matched-seed DiD 调节，跨两个 identity 水平等权平均。
- 正式矩阵：N=1000、T=50、12 cells、10 matched seeds，按一次盲态 nuisance-variance 重估最多扩至20个。
- 主模型路线：Qwen3-8B BF16、non-thinking、固定 revision、自部署 vLLM；API 只作外部稳健性子集。

协议细节见 `docs/paper1-protocol.md`，未决参数见 `docs/research-qa.md`。本页不复制或覆盖协议。

## 已有证据的边界

pilot-3.0 的 weak 条件出现高分端集中，lifelong strong 条件保留较多中间立场；BA/WS 在 N=20 的终点差异有限。这些结果用于提出问题和回归检查。由于复合 prompt、规模、解析、参数传递和恢复机制存在限制，不能据此宣称正式 Paper 1 已验证“双层结构”或网络效应。

## 代码与知识路线

- 历史代码：`pilot-1.0/`、`pilot-2.0/`、`pilot-3.0/`，冻结。
- 正式平台：`platform/` 已完成 Phase 3A 协议、领域记录、运行身份、FrozenSchedule、manifest 与证据图基础；后续新能力只进入该目录。
- 规范链：07-14 聚焦规格 → 已确认的人类协议 → schema 约束下的冻结机器协议；它规定应当发生什么。
- 证据链：原始 attempt/event → checkpoint/冻结数据集 → run manifest 与归档 hash → 汇总结果；它记录实际发生了什么。
- manifest/event 不得覆盖冻结协议；任何不一致均是需要显式标记并排除主分析的协议偏离，而不是新的规范。
- 历史思路：README、Notion 交接和 `design/`，只作追溯。

## 当前实现 checkpoint

- 活跃分支：`codex/paper1-platform`。
- Phase 3A 提交：`7e5731b`。
- 主工作区 `main` 尚未集成该分支；在 `main` 中看不到 `platform/` 不代表代码丢失。
- 恢复开发前先读 `logs/2026-07-29-phase3a-handoff.md`。
- formal 仍被未冻结研究决策阻断；当前通过的是平台基础验证，不是正式实验结果。
