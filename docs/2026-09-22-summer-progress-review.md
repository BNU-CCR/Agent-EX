---
status: current project review; preliminary evidence boundaries apply
authority: navigation and handoff summary; subordinate to the specification and evidence chains
date: 2026-09-22
audience: group meeting, project collaborators, and web-based GPT handoff
---

# 2026 暑期 Agent-EX 项目进展复盘

本文整理 2026 年 7 月至 9 月 Agent-EX / Paper 1 的研究与工程进展，服务三个用途：周四组会汇报、项目内部复盘，以及没有聊天历史的网页端 GPT 接续。它不是执行协议，也不替代冻结规格、机器协议或运行证据。

## 一、组会一页摘要

### 暑期目标

暑期目标不是直接堆出一批不可复现的模型输出，而是把早期 pilot 中混在一起的研究操作、运行逻辑和分析口径拆开，形成一个可以回答 Paper 1、能够恢复、能够审计、并可扩展到正式规模的实验平台。

Paper 1 聚焦的问题是：在固定网络结构中，**人口身份线索可见性、历史立场连续性要求和社会暴露方式**，如何共同影响 LLM-agent 的非公开立场、公开表达和群体动力学。

### 已完成的核心工作

1. **研究问题已经收敛。** 主矩阵固定为 `identity 2 × continuity 2 × exposure 3 = 12 cells`，正式规模固定为 N=1000、T=50、首批 10 个 matched seeds。
2. **协议与证据地基已经建成。** 项目具有 draft/formal gate、schema、运行身份、event/attempt identity、manifest、哈希、SQLite v6、checkpoint、恢复和过程审计。
3. **完整 mock 平台已经通过规模与恢复验证。** N=20/100/1000 的矩阵与恢复门通过；单 cell 真实执行过 50,000 个 mock pipeline events。
4. **真实模型校准已经跑通。** 自部署 Qwen/vLLM 完成 816 个校准样例，797 个最终结构化解析成功，机械解析成功率 97.67%；全部 841 次请求均收到响应。
5. **盲判证据链已经完成。** 797 个可判定样例的盲判任务达到 797/797 coded、0 unresolved intent，并通过 durable store 终态重放核验。
6. **Phase 0B 快速实验通道已经搭到最后接线阶段。** provider-neutral adapter、diagnostic pipeline、matrix/report runner 已有提交；真实 N=20/T=2 materializer 和安全导出器正在收口。

### 可汇报的真实量化里程碑

| 里程碑 | 已核验事实 | 能说明什么 | 不能说明什么 |
|---|---:|---|---|
| Phase 3A | 353 passed | 协议与领域基础完成 | 真实模型已运行 |
| Phase 4B | 1124 passed、2 skipped、1 deselected；85% production coverage | mock 平台、恢复与规模门成立 | 正式研究参数已冻结 |
| 50,000-event gate | 单 cell 50,000 个 mock events 完成 | 主循环和存储具备规模能力 | Qwen 在正式规模下的吞吐 |
| Phase 0A-0 | 1463 passed、2 skipped、1 deselected；86% coverage | 离线校准与证据合同完整 | 真实语义质量或模型效应 |
| Phase 0A-1 | 816 样例；797 parsed；19 parse-failed；841/841 请求有响应 | 真实 Qwen 校准链打通 | 网络动力学或处理效应 |
| Blind judge | 797/797 coded；0 unresolved intent | 盲判运行完成且可重放 | 标签含义已经安全汇总、参数已经冻结 |

真实 Qwen 校准的脱敏运行摘要还显示：墙钟时间约 23.1 分钟；请求延迟均值 0.874 秒、中位数 0.894 秒、P95 1.173 秒；输入 312,720 tokens、输出 68,944 tokens。解析失败全部出现在 topic-quality 样例中，但这只能视为格式可解析性现象，不能据此选择议题。

### 当前边界与问题

- 目前没有完成真实 N=20 网络动力学，因此不能把校准样例称为“正式实验结果”。
- 797 项盲判虽已完成，但安全语义导出仍需经过白名单字段、哈希绑定和 Linux 验证；现在只能报告运行完成性，不能自行读取 raw response 后做统计。
- Phase 0B 的 N=20/T=2 materializer 和安全导出器仍有本地未提交改动，需要独立审查。
- 一批模型 revision、generation、B/K、retry/timeout、性能门和归档参数仍未冻结，formal config 应继续 fail closed。
- 正式 N=1000、T=50、12-cell、10-seed 主实验尚未运行。

### 未来七天计划

1. 收口安全标签导出器和 N=20/T=2 materializer，不再扩展平台范围。
2. 用两个真实事件完成云端 preflight，验证真实 adapter、状态更新、SQLite、恢复和证据绑定。
3. 运行 12 cells × 20 agents × 2 events = 480 events 的真实 diagnostic matrix。
4. 生成一页 preliminary 图表与限制说明，为组会提供第一批真实网络实验数据。
5. 根据吞吐、失败率和语义质量决定 N=200/500 的规模门，不直接跳到 N=1000。

## 二、完整技术进展

### 7 月：研究问题收敛与规范链建立

7 月之前的 pilot 已经显示出一些可能的机制线索，但也暴露了复合 prompt、身份与立场混杂、解析脆弱、参数硬编码和恢复不可审计等问题。暑期第一步因此不是继续扩大 pilot，而是重新定义证据边界。

7 月 14 日起，项目通过 `5ec53be`、`b0166fe`、`e288ed6` 和 `0f9e5ad` 等提交完成平台设计、Paper 1 聚焦和 N=1000 分级方案。关键收敛包括：

- Paper 1 只研究固定网络上的意见与理由演化，不把动态重连、RLHF、真人—AI 网络等重新塞回主矩阵；
- 将身份信息、连续性要求和社会暴露拆成可识别的正交操作；
- N 是群体规模，不是独立重复数；seed/run 才是主要独立重复单位；
- 历史 pilot 原地冻结，新研究能力只进入 `platform/`；
- 规范链与证据链分离，任何执行偏离必须被标记而不能反向修改协议。

这一阶段的主要权威材料是 [`docs/superpowers/specs/2026-07-14-paper1-focused-research-design.md`](superpowers/specs/2026-07-14-paper1-focused-research-design.md) 和 [`docs/superpowers/specs/2026-07-29-paper1-phase4a-completion-design.md`](superpowers/specs/2026-07-29-paper1-phase4a-completion-design.md)。

### 7 月下旬：Phase 3A、4A 与 4B

Phase 3A 在提交 `7e5731b` 完成协议/schema gate、领域记录、运行身份、FrozenSchedule、RunManifest、恢复游标与证据图，最终记录为 353 passed，并通过 Ruff、format、dependency 与独立审查。这个里程碑意味着“协议与证据地基完成”，不意味着模型实验已经运行。

Phase 4A 随后系统处理议题、量表、人口、初始立场/理由、persona、WS 网络、激活、公开表达、feed 与记忆。项目最终否决“全员同步”主方案，采用固定 WS 上的异质加权随机顺序激活，并将私人状态更新和公开表达拆为两个阶段。

冻结的研究红线包括：

- `private_state` 是唯一 primary；`public_stock`、`public_flow`、`expression_gap` 为强制 secondary；
- 所有 Agent 具有正注意权重，公开表达采用 hurdle–Beta；
- E1 为固定、逐节点保度、禁用真实 WS 边且连通的 shadow graph，E2 使用原 WS；
- 社会 feed 是有限未读过程，B=6 和自身记忆 K=3 仍只是 Phase 0 主候选，不是 coder 默认值；
- 任何未决参数必须引用 `docs/research-qa.md` 的稳定 ID 并保持 `UNRESOLVED[...]`。

### 8 月：事件级实验平台建设

8 月的工作按 `domain → artifacts → network → schedule → state/feed → prompt/parser` 展开：

- `09768d3` 完成 Phase 4B-2 domain migration；
- `728198a` 完成 topic/population/initialization/persona mock artifacts；
- `b2fe2d6` 完成 WS、shadow graph 和 node mapping；
- `67c0efb` 完成异质激活与冻结 schedule；
- `d4176c3` 完成 private/public state、feed 与 memory；
- `57d0fd4` 完成 prompt/parser/mock adapter pipeline。

该阶段最重要的变化是：正式机制从早期全员同步循环改为严格事件级语义。每个事件读取前一成功提交状态；失败不得改变状态或游标；retry/resume 必须保持同一 event identity；sweep 只作为观测和 checkpoint 边界。

### 8 月下旬至 9 月：持久化、恢复与证据链

8 月 30 日至 9 月 4 日，项目完成：

- SQLite v6 事务存储；
- compact checkpoint v5 与 legacy replay；
- 严格串行 lifecycle engine；
- invocation、response、parse、authorization、reconciliation 的逐事件证据；
- crash-window 恢复与禁止重复发送；
- N=20/100/1000 mock matrix 和 50,000-event release gate。

Phase 4B 最终 full 为 1124 passed、2 skipped、1 deselected，production coverage 85%；规格、代码质量和最终验证三路复核无 P0–P3。N=100 的 12 cells 共执行 1,200 个真实 mock events；N=1000/T=50 完成 12-cell shape validation；单 cell 50,000-event pipeline gate 用时约 5 小时 45 分。

这一大规模 gate 发现 checkpoint v4 在合法 retry 历史下会超过旧文件上限，最终没有简单继续抬高限制，而是设计 compact v5：完整失败与授权正文留在 SQLite，checkpoint 只保存有序内容哈希和最小因果引用。这个过程说明，大规模前先做恢复与容量门是必要的。

### 9 月：Phase 0A-0、Phase 0A-1 与云端部署

Phase 0A-0 在 9 月 5–9 日完成离线 specification、case、attempt、score、semantic review、gate、report、freeze proposal 和 bundle 合同。四个 replicate 展开为 816 个逻辑 cases：topic quality 144、identity 96、continuity 576。最终 full/coverage 都是 1463 passed、2 skipped、1 deselected，production coverage 86%。这一阶段完全是 scripted/offline，不含真实模型。

Phase 0A-1 把同一套合同推进到云端真实 Qwen/vLLM。过程中解决了：

- 本地包导入边界与循环依赖；
- CUDA/vLLM 版本识别和新 GPU sampler 启动；
- service 生命周期、进程清理和受控超时；
- 可恢复 smoke、owner manifest、环境锁与 bundle/hash 审批；
- confidence 合同缺失与无状态格式修复上下文不足；
- 盲态 judge 的授权、生命周期、路径竞态、原子物化、恢复和证据封存。

第一次 816-case 真实运行虽然 transport 完整，但 measurement contract 缺失独立 confidence 约束，导致 674 个 parse failures，因此被不可逆标记为 diagnostic incomplete，没有用于候选比较。修复统一合同后重新执行，得到 797 个成功解析和 19 个 parse failures。

这一失败不是白费：它直接证明“模型能回答”与“测量合同可用于比较”是两件不同的事，也验证了平台可以拒绝看似完成但不合格的运行。

### 797 条盲判的完成与终态核验

真实校准完成后，平台为 797 个成功解析样例生成盲判任务。为了避免读取 raw response、重复发送或中断后产生双重编码，9 月 18–20 日又补齐：

- blinded materialization 与 request authorization；
- response/parse 与 semantic policy 绑定；
- service 生命周期与安全 I/O；
- append-only journal、dispatch intent、attempt、resolution 与 reconciliation；
- resumable judge store 和 projection 性能优化。

9 月 21 日仓库记录过一个 609/797 前缀快照：当时前 609 项为 coded，第 610 项存在未决 dispatch。该快照只是当时的真实阶段证据，并不与次日终态冲突。

2026-09-22 对 durable store 执行完整重放并运行 `verify_terminal_projection()` 后确认：

- exactly 797 item states；
- 797 coded；
- 0 unresolved intent；
- terminal projection record hash：`b09e0a242018c1bc48c00fb0af0f87740e8c420080e73e0411de095db761873d`；
- 终态写入前最后一份 projection 文件 SHA-256：`6c65dbc6b7d27f709821b8da1751b5eca7b18b6e377efa7b66fde7cae898fd0e`。

这些证据证明盲判任务完整、终态一致且可重放。它们不透露标签分布，也不授权议题选择或参数冻结。安全语义汇总仍必须经过经审查的脱敏导出器。

### 当前 Phase 0B 的真实完成边界

9 月 20 日以后，项目已经提交 diagnostic contracts、真实 vLLM event adapter、provider-neutral pipeline bridge、event loop、matrix runner、report 和 real-runner gate。它们使 Phase 0B 不再是空白。

但当前还不能声称“真实 N=20 实验已跑”：

- 现有已提交 runner 的早期形态曾出现 `agent-0000/self_history_only` 的单代理假运行路径，不能冒充 20-agent dynamics；
- 精确 20 agents、12 cells、2 events/agent、480 events、E0/E1/E2 wiring 和每 cell 独立 SQLite v6 的 materializer 改动尚待收口与独立复核；
- 安全标签导出器在 Windows 专项验证通过，但 Linux-only 安全读取仍需云端验证；
- Phase 0B 真实云端任务必须等待明确服务交接，不能与校准 judge 抢占同一服务。

因此最诚实的当前状态是：**正式平台主体和校准证据链已完成；第一批真实网络动力学数据尚差最后的本地收口、两事件 preflight 和 480-event diagnostic run。**

## 三、关键问题与工程教训

### 1. 最大耗时不是一次模型生成，而是证据正确性

816 个真实校准样例本身约 23 分钟完成。后续耗时主要来自：发现测量合同缺陷、修复恢复与盲判链、逐项可重放编码，以及防止中断后重复发送。未来 N=5000 是否需要数周，取决于是否沿用逐条串行 judge/落盘方式，而不是简单按当前墙钟线性外推。

正式规模需要把“研究事件必须严格串行”和“独立判分/导出可以批处理”分开优化，并减少全量 projection 重写、频繁 fsync 和二次模型调用。

### 2. 云端本地部署仍然会遇到网络问题

模型部署后，推理本身在本机 GPU 上运行，但首次下载模型、依赖与 wheel，上传 bundle，以及远端服务管理仍依赖网络。解决方向是：预下载/缓存模型、固定镜像和 lock、可恢复上传、减少重复环境构建，而不是把运行中的每个请求改回外部 API。

### 3. “能跑”不等于“测量有效”

第一轮 816-case 运行 transport 全部成功，却因 confidence 合同和无状态 repair context 缺陷而 measurement invalid。平台正确地拒绝把它纳入比较。这比产生一份不可解释的漂亮结果更重要。

### 4. mock 规模通过不等于真实多 Agent 动力学通过

Phase 4B 已证明存储、恢复和事件主循环的工程形状，但 mock adapter 不代表真实模型质量。类似地，单代理 self-history smoke 只能证明 transport，不能称为 N=20 网络实验。今后所有汇报都必须明确区分这两层。

### 5. 额度中断不应终止云端长任务

云端任务应通过独立后台进程、durable store 和日志运行；本地 Agent 只做低频只读监控。这样即使 Codex 额度耗尽、断网或电脑暂时不可用，已经启动的云端程序仍继续运行。监控频率应按阶段调整，健康时不重复启动、不频繁读取大日志。

### 6. 分支和 worktree 必须区分

暑期大部分已提交工作位于 `codex/paper1-phase0`；`main` 是其祖先。分支历史应通过 fast-forward 汇入 main，不 squash、不 rebase。未提交的 Phase 0B 工作仍保留在 Phase 0 worktree，不能因为整理 GitHub 分支而丢弃或混入文档提交。

## 四、从现在到正式实验的关键路径

### 阶段 A：取得可用于组会的第一批真实动力学数据

1. 完成安全导出器的 Linux 验证和 independent review。
2. 完成 N=20/T=2 materializer 的精确不变量验证。
3. 用现有真实 vLLM adapter 执行两个事件 preflight。
4. 执行 480-event diagnostic matrix。
5. 输出只基于脱敏聚合的图表、运行指标和限制说明。

目标产物必须标记为 `preliminary / diagnostic / not_frozen`，可用于组会展示，但不能进入 Paper 1 主分析。

### 阶段 B：冻结 Phase 0B

根据真实运行观测冻结：模型/tokenizer/chat-template revision、generation 参数、B/K、retry/timeout、吞吐与失败率门、归档位置和仍未决的研究参数。冻结必须基于预先声明的质量/工程门，不得根据想要的意见结果选值。

### 阶段 C：有限规模检验

依次运行 N=200/500，验证 GPU 吞吐、存储增长、恢复时间、解析/语义失败率和 seed-level 分析。只有这些门通过，才授权 N=1000。

### 阶段 D：正式主实验

运行 N=1000、T=50、12 cells、首批 10 matched seeds。主分析以 seed/run 为独立重复单位；是否扩至 20 seeds 只按预注册的盲态 nuisance-variance 规则决定。

## 五、周四组会建议讲法

建议用五页结构：

1. **研究问题：**为什么要研究身份线索、连续性要求和网络暴露对 LLM-agent 意见动力学的影响。
2. **暑期方法成果：**从不可审计 pilot 转为 12-cell、事件级、可恢复的平台。
3. **真实进展：**816 个 Qwen 校准样例、97.67% 解析成功、797/797 盲判终态完成。
4. **当前边界：**这些是校准与证据链，不是正式网络效应；真实 480-event diagnostic 是下一步。
5. **下一周交付：**完成 N=20/T=2 preflight 和第一批 preliminary dynamics 图表。

可以用的一句话总结：

> 暑期完成了从研究设计、可恢复实验平台到真实模型校准和盲判证据链的闭环；当前尚未得到正式 Paper 1 结果，但已经进入第一批真实多 Agent 动力学数据的最后接线阶段。

不建议使用的表述：

- “已经证明网络结构导致极化”；
- “797 条结果支持某个议题或条件”；
- “平台全部完成，可以直接跑 N=1000”；
- “50,000-event gate 是真实 Qwen 主实验”。

## 六、Web-safe GPT 接续附录

本节可直接提供给网页端 GPT。它只包含仓库相对路径、提交 ID、非敏感哈希和研究边界，不包含凭据、操作端点、私人路径或原始回答。

### 当前 Git 状态

- 暑期最新提交线：`codex/paper1-phase0`。
- 文档整理前，`main` 位于 `092bcac`，是 Phase 0 提交线的严格祖先。
- 关键里程碑提交：
  - `7e5731b`：Phase 3A protocol/domain foundation；
  - `092bcac`：Phase 4B mock integration complete；
  - `9bbd31f`：Phase 0A offline probe complete；
  - `bf2f63a`：judge projection 性能优化；
  - `f60ce2c`：609/797 前缀元数据快照；
  - `9607657`：暑期复盘与分支整合设计安全边界。
- `platform/src/agent_ex/phase0b/` 和相关测试存在尚待独立收口的 N=20 materializer 改动；不要覆盖、丢弃或把它们误写成已提交完成。
- 分支整合应采用固定 OID 的 `git merge --ff-only`，不 squash、不 rebase、不 force-push。

### 权威阅读顺序

1. [`../AGENTS.md`](../AGENTS.md)
2. [`../logs/2026-07-29-phase3a-handoff.md`](../logs/2026-07-29-phase3a-handoff.md)
3. [`project-overview.md`](project-overview.md)
4. [`superpowers/specs/2026-07-29-paper1-phase4a-completion-design.md`](superpowers/specs/2026-07-29-paper1-phase4a-completion-design.md)
5. [`superpowers/specs/2026-07-14-paper1-focused-research-design.md`](superpowers/specs/2026-07-14-paper1-focused-research-design.md)
6. [`paper1-protocol.md`](paper1-protocol.md)、[`research-qa.md`](research-qa.md)、[`decisions.md`](decisions.md)
7. [`../logs/2026-09-04-phase4b-handoff.md`](../logs/2026-09-04-phase4b-handoff.md)
8. [`../logs/2026-09-05-phase0a0-offline-probe.md`](../logs/2026-09-05-phase0a0-offline-probe.md)
9. [`superpowers/plans/2026-09-20-phase0b-n20-fast-track.md`](superpowers/plans/2026-09-20-phase0b-n20-fast-track.md)

### 不得违反的研究红线

- 主矩阵固定为 2×2×3；正式规模固定为 N=1000、T=50、首批 10 matched seeds。
- 主模型路线为固定 revision 的 Qwen3-8B BF16、non-thinking、vLLM。
- 不把 RLHF、动态重连、真人—AI 网络或 weak/lifelong 复合 prompt 放回主矩阵。
- 不把 N 当独立重复数，不把单向端点集中称为经典双峰极化。
- 事件必须读取前一成功提交状态并严格串行提交；失败不改变状态或游标。
- `private_state` 是唯一 primary；强制 secondary 不得按显著性改排序。
- 未决参数必须保持 `UNRESOLVED[...]`；formal config 含未决字段必须失败。
- 原始大规模结果不进入 Git，只提交 manifest、hash、脱敏聚合和归档定位。

### 当前可信证据

- 816-case 校准：797 parsed、19 parse-failed、841/841 transport responses。
- 盲判终态：797 states、797 coded、0 unresolved intent。
- terminal projection record hash：`b09e0a242018c1bc48c00fb0af0f87740e8c420080e73e0411de095db761873d`。
- last pre-terminal projection SHA-256：`6c65dbc6b7d27f709821b8da1751b5eca7b18b6e377efa7b66fde7cae898fd0e`。
- 609/797 报告是较早的真实前缀快照，不是终态，也不包含语义统计。

### 下一步最小工作包

1. 审查并提交安全标签导出器，完成 Linux-only 安全测试。
2. 审查并提交 N=20/T=2 materializer，验证 20 agents、12 cells、480 events 与独立 SQLite。
3. 接通 real vLLM event adapter、provider-neutral pipeline、retry/resume/checkpoint/verify/report。
4. 先跑两个事件 preflight，再跑 480-event diagnostic matrix。
5. 只从批准的脱敏聚合生成组会图表。

### 禁止重复或误做的工作

- 不重跑已完成的 797-item judge，不合并旧 v1 与终态 v2 证据。
- 不从 raw response 或包含原始文本的 reconciliation/attempt 文件自行提取标签。
- 不把 `agent-0000/self_history_only` smoke 当作 N=20 dynamics。
- 不为追求速度跳过 event identity、dispatch intent、恢复和证据绑定。
- 不在 Phase 0B 冻结前启动正式 N=1000 主实验。
- 不清理或覆盖当前未提交 Phase 0B 文件；应在独立工作包中审查、验证和提交。
