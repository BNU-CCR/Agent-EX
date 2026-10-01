# Agent-EX

Agent-EX 是一个研究 **LLM-agent 在多轮在线讨论中的意见、理由与公开表达如何演化** 的可复现实验平台。当前首要项目是 Paper 1：在固定网络结构中识别人口身份线索、历史立场连续性要求与社会暴露方式对生成式 Agent 意见动力学的影响。

> **截至 2026-09-22：**正式平台的协议、事件执行、持久化、恢复和证据链已经搭建；真实 Qwen 校准与 797 项盲判证据链已经完成并核验。真实 N=20 动力学仍在 Phase 0B 接入阶段，N=1000、T=50 的正式主实验尚未启动。

## 项目定位

本仓库分为三个证据层级：

| 层级 | 内容 | 可以支持什么 |
|---|---|---|
| 历史 pilot | `pilot-1.0/`、`pilot-2.0/`、`pilot-3.0/` | 机制线索、失败案例和迁移回归；不能替代正式实验 |
| Paper 1 | `platform/` 与当前协议、制品、运行和分析链 | 指定模型、议题、persona 操作和暴露条件下的可审计实验 |
| 后续研究 | Paper 2、真实网络外部效度和长期 benchmark | 尚未实施，不得写成已有能力或研究发现 |

Paper 1 的直接证据边界是由 LLM-agent 构成的模拟讨论网络，不是真人平台上的平均社会效应。

## 当前状态（2026-09-22）

### 已完成并核验

- Paper 1 已收束为固定的 `identity 2 × continuity 2 × exposure 3 = 12 cells` 设计。
- Phase 3A 完成协议/schema gate、领域记录、运行身份、冻结 schedule、manifest 与证据图基础。
- Phase 4B 完成 mock-only 的人口/persona/network/schedule/state/feed/prompt、SQLite v6、checkpoint/recovery、严格串行事件引擎与过程审计。
- mock 规模门覆盖 N=20/100/1000；单 cell 的 50,000-event 流水线已真实执行，但使用的是 mock adapter，不是模型实验。
- Phase 0A-0 完成 816-case 离线校准骨架、恢复、盲审、gate、report 和 bundle 合同。
- Phase 0A-1 已在云端自部署 Qwen/vLLM 上完成 816 个真实校准样例：797 个最终结构化解析成功、19 个解析失败；全部 841 次请求均收到响应。
- 对 797 个可判定样例执行的盲判任务已达到 `797/797 coded`、`0 unresolved intent`，并通过 durable store 终态重放核验。

### 已实现但尚待收口

- Phase 0B 已有 provider-neutral 真实事件 adapter、诊断 pipeline、matrix/report runner 等提交。
- 本地仍有 N=20/T=2 materializer 和安全标签导出器改动待独立审查、Linux 验证与正式提交。
- 797 项盲判的安全语义汇总仍须经过字段白名单、哈希绑定且不含原始文本的批准导出链；完成计数本身不是语义结果。

### 尚未完全完成

- 真实 N=20、12-cell、480-event 动力学诊断运行。
- Phase 0B 的模型 revision、chat template、generation 参数、B/K、重试/超时、性能门与归档位置冻结。
- N=200/500 的有限规模检验。
- N=1000、T=50、12 cells、10 个 matched seeds 的正式主实验及统计分析。

## Paper 1 研究设计

### 核心问题

在人口背景异质、初始立场匹配且网络结构固定的 LLM-agent 群体中：

1. 人口身份线索是否改变意见更新和公开表达？
2. 要求维持历史立场连续性是否改变意见修正？
3. 真实 WS 邻居暴露相对度数匹配的 shuffled social exposure，是否产生不同的群体动力学？

### 固定主矩阵

- **Identity：**人口身份线索不可见 / 可见。
- **Continuity：**无历史一致性要求 / 有历史一致性要求。
- **Exposure：**self-history only / degree-matched shuffled social / 固定 WS 邻居。
- **规模：**N=1000、T=50、12 cells、首批 10 个 matched seeds；只允许按预注册的盲态规则扩展至 20 个 seeds。
- **主模型路线：**固定 revision 的 Qwen3-8B BF16、non-thinking、自部署 vLLM；API 只作为固定 snapshot 的外部稳健性子集。

`private_state` 是唯一 primary。`public_stock`、`public_flow` 与 `expression_gap` 是强制预注册 secondary。精确公式和仍未冻结的研究参数必须继续使用 `UNRESOLVED[...]`，不能由实现者填默认值。

## 已完成的平台能力

`platform/` 当前提供：

- draft/formal 协议校验、schema 镜像、人类摘要同步和未决参数 fail-closed；
- 确定性 population、persona、WS/shadow graph、node mapping 与制品哈希；
- 异质激活权重、公开表达、有限未读 feed、自身记忆与冻结 schedule；
- prompt 渲染、严格 JSON parser、mock/loopback/真实 vLLM adapter 边界；
- 严格串行 event identity、attempt identity、授权重试与禁止重复发送；
- SQLite v6 事务存储、compact checkpoint、close/open 恢复与 crash-window reconciliation；
- manifest、environment lock、process audit、盲态 judge、终态 projection 与哈希证据链；
- Windows 本地工程验证和 Linux/GPU 云端校准工作流。

Notebook 只负责编排和展示，不能承载正式主循环、指标定义或协议权威。

## 证据链与研究边界

项目同时维护两条不能混淆的链：

- **规范链：**冻结机器协议 → schema → 已确认的人类协议 → 已批准规格 → 计划与说明文档。它规定应该发生什么。
- **证据链：**原始 attempt/event → checkpoint 与冻结数据集 → run manifest/hash → 聚合与论文结果。它证明实际发生了什么。

实际执行偏离冻结协议时，该 run 必须标为偏离并停止进入主分析；不能用忠实记录偏离的 manifest 反向修改规范。

Phase 0A-1 的终态事实为：797 个 item states、797 coded、0 unresolved intent。终态 projection record hash 为 `b09e0a242018c1bc48c00fb0af0f87740e8c420080e73e0411de095db761873d`；终态写入前最后一份 projection 文件 SHA-256 为 `6c65dbc6b7d27f709821b8da1751b5eca7b18b6e377efa7b66fde7cae898fd0e`。这些值证明运行完成与证据一致性，不表示某个议题、条件或理论假设已经获得支持。

## 仓库导航

| 路径 | 作用 |
|---|---|
| [`platform/`](platform/) | Paper 1 唯一活跃实现 |
| [`docs/project-overview.md`](docs/project-overview.md) | 项目范围和证据地图 |
| [`docs/paper1-protocol.md`](docs/paper1-protocol.md) | 人类可读 Paper 1 协议 |
| [`docs/research-qa.md`](docs/research-qa.md) | 未决研究参数及稳定 ID |
| [`docs/decisions.md`](docs/decisions.md) | 已确认选择与证据记录 |
| [`docs/archive-index.md`](docs/archive-index.md) | 历史 pilot 与归档入口 |
| [`task_plan.md`](task_plan.md) | 长期阶段和任务状态 |
| [`progress.md`](progress.md) | 详细执行日志 |
| [`findings.md`](findings.md) | 研究与工程发现 |
| [`logs/`](logs/) | 经验证的阶段交接与证据摘要 |
| [`reports/`](reports/) | 脱敏 preliminary/diagnostic 报告 |
| [`docs/2026-09-22-summer-progress-review.md`](docs/2026-09-22-summer-progress-review.md) | 暑期完整复盘与 Web-safe 接续材料 |
| [Notion：AI Agent 实验](https://brook-ceiling-fb4.notion.site/AI-Agent-162a7a6cb77f83e2944181eccac5a519?source=copy_link) | 早期研究设计、组会材料、论文初稿与文献追踪的历史资料源 |

> **Notion 使用边界：**该工作区用于追溯尚未完全迁入 Git 的早期初稿和研究演化。新 Agent 可以读取它补充历史语境，但其中的旧参数、旧矩阵和旧实施方案不具备当前规范权威；如与本仓库冻结协议、schema、已确认决策或证据链冲突，以仓库内现行权威文件为准。

## 五分钟接续顺序

新成员或新 Agent 应按以下顺序阅读：

1. [`AGENTS.md`](AGENTS.md)
2. [`logs/2026-07-29-phase3a-handoff.md`](logs/2026-07-29-phase3a-handoff.md)
3. [`docs/project-overview.md`](docs/project-overview.md)
4. [`docs/superpowers/specs/2026-07-29-paper1-phase4a-completion-design.md`](docs/superpowers/specs/2026-07-29-paper1-phase4a-completion-design.md)
5. [`docs/superpowers/specs/2026-07-14-paper1-focused-research-design.md`](docs/superpowers/specs/2026-07-14-paper1-focused-research-design.md)
6. [`docs/paper1-protocol.md`](docs/paper1-protocol.md)、[`docs/research-qa.md`](docs/research-qa.md) 与 [`docs/decisions.md`](docs/decisions.md)
7. 当前阶段最近的 `logs/`、批准规格和实施计划

## 本地开发与云端运行

### 本地

- 从 `platform/pyproject.toml` 与锁文件创建隔离 Python 环境，不复制旧虚拟环境。
- 默认只运行当前工作包相关的专项测试；正式发布门才运行 full、coverage、Ruff、format、`pip check` 与 diff/hygiene 检查。
- 大型 SQLite、checkpoint、原始响应、缓存、coverage 和云端制品不进入 Git。
- 不修改或提交 `.codex/`，不使用历史 pilot 承载新能力。

### 云端

- 先冻结并批准 source bundle、manifest、environment lock 和运行授权哈希，再启动真实请求。
- 云端只接收经过核验的提交快照；凭据通过平台安全机制注入，不写入仓库。
- 原始回答留在受控归档；Git 只保存脱敏聚合、manifest/hash 和归档定位。
- 恢复时先检查 durable state、未决 dispatch 和恢复合同，禁止盲目重发。

## 当前阻塞与未来七天

当前最短关键路径：

1. 完成安全标签导出器的 Linux-only 验证和独立审查；
2. 收口 N=20/T=2 materializer，证明精确 20 agents、12 cells、2 events/agent 和 480 events；
3. 将真实 vLLM event adapter 接入 provider-neutral pipeline 与 SQLite v6；
4. 执行两个事件的真实 preflight，验证 E0/E1/E2、身份/连续性 persona 和恢复链；
5. 运行 480-event diagnostic matrix，生成明确标注 `preliminary / diagnostic / not_frozen` 的组会结果；
6. 根据吞吐、失败率、语义质量和资源观测冻结 Phase 0B，再进入 N=200/500 规模门。

只有真实模型、真实 12-cell event pipeline、冻结参数、完整运行身份和证据链共同通过后，才算具备启动正式主实验的资格。

## 历史 pilot 与暑期复盘

历史 pilot 已冻结，只用于追溯：详见 [`docs/archive-index.md`](docs/archive-index.md)。

2026 年暑期从研究问题收敛、Phase 3A/4A/4B 平台建设，到 Phase 0A 云端校准与当前 Phase 0B 边界的完整记录，见 [`docs/2026-09-22-summer-progress-review.md`](docs/2026-09-22-summer-progress-review.md)。
