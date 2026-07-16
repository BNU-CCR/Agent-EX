---
status: active archive index
authority: historical-use restrictions and provenance map; not an execution protocol
supersedes: README.md as the authoritative guide to whether pilot assets may be reused
last-verified: 2026-07-16
---

# 历史 Pilot 索引

冻结含义：旧目录原地保留，只允许安全修复、归档说明或复现旧结果；任何新的正式研究能力进入 `platform/`。

| 版本 | 目的与时间 | 可保留证据/模式 | 已知限制与禁止复用 | 数据完整性 |
|---|---|---|---|---|
| pilot-1.0 | 2026-05，自研 BA 与 AI劳动预实验 | 轻量状态对象、NetworkX、邻居抽样、OpenAI-compatible adapter 形态、async 同步提交 | 固定角色、stubbornness、方向性 prompt、共享 RNG、失败沿用旧值、末尾一次保存；不得作正式结果 | `pilot-1.0/results/` 在本 worktree 不存在；历史报告可读，原始数据未由 Git 验证 |
| pilot-2.0 | 2026-05，Piao 参考实现与 Qwen API 适配 | 消息/更新/传播/重连分层、epoch checkpoint 概念、WS 资产 | 全局状态、超长 utils、重复 prompt、超大重试、类型混用、动态重连主循环；早期解析有 label/reasoning 风险 | `pilot-2.0/output_pol/` 在本 worktree 不存在；仅报告与代码受 Git 追踪 |
| pilot-3.0 | 2026-05，N=20/T=30 四条件×五seed探索 | 上一轮快照/同步提交语义、运行记录契约、matched seed 组织、迁移回归方向 | Notebook 主循环、20角色切片、weak/lifelong 复合 prompt、共享异步 RNG、top_p 记录未传递、无恢复、失败静默保留、latest-run 不验完整性 | `pilot-3.0/run.ipynb` 存在；`pilot-3.0/results/` 在本 worktree 不存在，05-31 结果表只能视为历史报告 |

## 历史设计文件

- `logs/notion-2026-05-31.md`：pilot-3.0 与课程论文的完整交接，已被07-14设计取代为执行来源。
- `logs/notion-2026-05-23.md`、`design/research_design.md`：RLHF/abliterated 大设计，路由至 Paper 2。
- `design/methodology_review_2026-05-23.md`、`design/decisions_log.md`、会议笔记：保留研究脉络，不向正式配置提供默认值。
- `paper-revision/`：独立的理论文章修订线，不属于 Paper 1 平台协议。

## Git 与外部来源

本知识基线基于 Git `0f9e5ad8a71c8fb8423044504f839bf5b4a24170`。对应 Notion 页面与外部原始数据 URI 尚未形成可验证的一一映射，记录为 `UNRESOLVED[P1_ARCHIVE_PROVENANCE_MAP]`。
