---
status: active navigation baseline
authority: project scope and evidence map; not an execution protocol
supersedes: README.md and logs/notion-2026-05-31.md as the entry point for work after 2026-07-14
last-verified: 2026-09-10
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
- 结果层级：`private_state`是唯一primary；`public_stock`、`public_flow`和
  `expression_gap`是强制预注册secondary。精确primary公式仍须在Phase 0冻结。
- 主要 estimand：在四个identity×continuity条件上等权平均的`WS - shuffled`
  matched-seed差异；continuity对该差异的DiD调节是关键secondary。
- 正式矩阵：N=1000、T=50、12 cells、10 matched seeds，按一次盲态 nuisance-variance 重估最多扩至20个。
- 主模型路线：Qwen3-8B BF16、non-thinking、固定 revision、自部署 vLLM；API 只作外部稳健性子集。

协议细节见 `docs/paper1-protocol.md`，未决参数见 `docs/research-qa.md`，研究选择的证据与
修订理由见 `docs/paper1-design-rationale.md`。本页不复制或覆盖协议。

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

### 2026-09-10 Phase 0A-1

- Phase 0A-1 design approved and independently reviewed。
- 云端只读预检已完成，SSH免密连接通过；观测环境为RTX 5090 32GB、Ubuntu 22.04、
  Python 3.12.3、PyTorch 2.8.0+cu128及150GB数据盘。
- 尚无真实模型响应、运行时冻结、decision record或正式实验。
- Phase 0A-1仍在推进，尚未达到阶段验收边界。

- Phase 0A-0 离线 probe 骨架分支：`codex/paper1-phase0`，状态为
  `complete / independently reviewed`。它已完成严格 specification/case/attempt/
  semantic-review/gate/report/bundle 合同和确定性离线 facade；真实模型、网络和正式
  参数权限均未启用。
- 修复后发布验证为 `1463 passed, 2 skipped, 1 deselected`；coverage 同计数，
  production `14,600 statements / 2,102 missed / 86%`。计划指定的协议、安装和离线
  集成专项为 `163 passed`。规格、代码质量和最终验证三路独立复核均为 `APPROVED`，
  P0--P3 为零。
- 四 replicate 离线 fixture 产生 816 个逻辑 cases（topic quality 144、identity 96、
  continuity 576）和 2,448 条 request/response/parse 证据；报告状态仅为
  `proposal_only`。精确哈希、依赖身份与复核证据见
  `logs/2026-09-05-phase0a0-offline-probe.md`。
- 下一步是 Phase 0A-1 云端真实小样本 probe：在 owner 批准候选文本、runtime policy、
  semantic-review policy、Qwen/vLLM 栈、云端凭据和外部归档位置后执行。它不是正式
  N=1000/T=50 主实验；其他 Phase 0B 与统计项继续 fail closed。
- Phase 4B release-candidate分支：`codex/paper1-phase4b`，Task 7提交`7749609`已与远端一致。
- `platform/`已组合12-cell mock矩阵、严格串行pipeline、SQLite v6、compact checkpoint v5、
  close/open恢复与只读process audit；N=20/100/1000和50,000-event mock规模门已通过。
- 精确提交、哈希、资源测量和跨Windows/Linux恢复说明见
  `logs/2026-09-04-phase4b-handoff.md`。
- Phase 4B已通过最终full/coverage、协议/安装/Git门及规格、代码质量、最终验证三路独立终审，
  状态为`complete / independently reviewed`。
- 即使Phase 4B完成，formal仍被未冻结研究决策阻断；下一步是Phase 0A/0B与真实模型
  小规模校准，不是直接运行正式主实验。
