# Agent-EX Paper 1 与长期实验平台设计规格

**日期：** 2026-07-14
**状态：** 已通过独立规格审阅，待用户确认
**范围：** 项目知识归档、Paper 1 研究协议、长期复用实验平台

## 1. 背景与目标

Agent-EX 已完成 pilot-1.0、pilot-2.0 和 pilot-3.0 三轮探索。现有工作证明了 LLM-agent 在线意见演化流程可以跑通，也发现 weak 条件较 lifelong 复合条件更容易出现高分端饱和。但当前实现仍以 Notebook 为主，实验操作、统计口径、文档和代码存在冲突，不能直接扩展至正式 Paper 1。

本项目下一阶段的首要交付是 Paper 1，同时建设一个可供 Paper 2、GLM-agent benchmark 和后续研究复用的实验平台。成功状态不是“重写一个 Notebook”，而是：

1. 历史 pilot 可追溯、不可误用；
2. Paper 1 有唯一、明确、版本化的研究协议；
3. 正式实验由单一、可测试、可恢复的 Python 平台执行；
4. 任一结果可追溯到研究协议、机器配置、代码版本、prompt、模型身份和原始事件；
5. 平台能在不复制核心代码的情况下承载后续 Paper。

## 2. 范围与非目标

### 2.1 本阶段范围

- 整理项目知识体系与 source of truth；
- 冻结并索引 pilot-1.0/2.0/3.0；
- 形成 Paper 1 正式协议；
- 建立长期实验平台；
- 实现 Paper 1 的人口、persona、网络/曝光、模型调用、同步演化、存储、验证和分析；
- 先完成校准和有限规模 gate，再启动已固定 N=1000 正式矩阵。

### 2.2 非目标

- 本阶段不实现 Paper 2 的 RLHF/abliterated 全因子设计；
- 不把基金页中的 GLM benchmark、真实社交媒体 Study 2、关系重组和完整 message pool 全部塞入 Paper 1 MVP；
- 不试图构建通用社会模拟产品或 Web 平台；
- 不物理移动或重写旧 pilot；
- 不把 pilot-3.0 结果重新包装成已验证的“双层结构”。

## 3. 知识体系与权威边界

### 3.1 文档职责

| 文件 | 职责 | 权威范围 |
|------|------|----------|
| `README.md` | 五分钟项目入口 | 当前状态、目录、最短运行路径 |
| `AGENTS.md` | AI 接手规则 | 当前主线、禁用旧方案、文档路由、实验红线 |
| `docs/project-overview.md` | 长期项目总览 | Paper 之间的关系与已有证据 |
| `docs/research-program.md` | 长期研究计划 | Paper 1/2/基金 benchmark 的问题分工 |
| `docs/paper1-protocol.md` | Paper 1 人类可读协议 | 构念、条件、样本、指标、统计和排除规则 |
| `docs/research-qa.md` | 长期设计问答 | 开放问题、候选答案和状态 |
| `docs/decisions.md` | 决策记录 | 已确认决策、理由和替代方案 |
| `docs/reproducibility.md` | 可复现规范 | 环境、随机性、数据、模型、运行身份 |
| `docs/archive-index.md` | 历史索引 | pilot 的价值、限制和禁止复用内容 |
| `task_plan.md` | 当前阶段计划 | 当前执行状态，不存外部指令 |
| `findings.md` | 发现库 | 审计、研究和外部材料摘要 |
| `progress.md` | 跨会话日志 | 已完成操作、测试和错误 |

### 3.2 Source of truth

- 研究意图和理论写作可在 Notion 中迭代；
- `platform/protocols/paper1.schema.json` 定义稳定字段 ID、类型、枚举和必填项，是协议结构的唯一 schema；
- `platform/configs/paper1/protocol.yaml` 是按该 schema 验证的规范化协议数据，是构念、estimand、条件、指标、排除规则和停止规则的机器执行真相；
- `docs/paper1-protocol.md` 是由规范化协议数据生成并允许在标记区外补充理论解释的人类可读版本；生成区不得手工编辑；
- 其他运行 YAML 只引用 `protocol_id`、`protocol_version` 和稳定字段 ID，不得重定义协议语义；
- 自动验证必须检查 schema、引用完整性，并重新生成 Markdown 后执行无差异检查；
- protocol freeze 后任何执行字段变化都必须提升 `protocol_version`、写入决策日志并产生新的 `run_spec_hash`；纯解释性文字修改不改变执行版本；
- 实际请求与结果以 run manifest 和事件数据为准；
- README 和 Notion 不得覆盖实际运行记录；
- 每个里程碑后同步 Notion、本地文档和交接说明。

## 4. 归档策略

pilot-1.0、pilot-2.0 和 pilot-3.0 原地保留并冻结，暂不移动目录。`docs/archive-index.md` 必须记录：

- 版本目的与时间；
- 可保留的研究证据；
- 可参考的代码模式；
- 已知漏洞；
- 不得用于正式 Paper 1 的内容；
- 结果数据位置与完整性状态；
- 对应 Git commit/Notion 页面。

冻结意味着除安全修复、归档说明或复现旧结果外，不再向旧 pilot 添加新研究能力。所有新实现进入 `platform/`。

## 5. Paper 1 研究设计原则

Paper 1 的聚焦研究设计以 `docs/superpowers/specs/2026-07-14-paper1-focused-research-design.md` 为准。本节保留平台设计阶段的原则性约束；如有冲突，以聚焦研究设计及后续冻结的 `docs/paper1-protocol.md` 为准。

### 5.1 可识别性优先

Paper 1 必须明确主要 estimand，不能继续把身份、立场锚定、抗从众和变化幅度限制捆绑为一个“persona 强度”。建议首个可识别设计以两个正交因素为起点：

- 身份信息：无 / 有；
- 一致性指令：无 / 有。

所有条件使用同一人口材料、初始分布和初始理由资源。身份信息不能直接写入方向性长期立场；一致性指令不能直接规定变化幅度。若后续增加 persona 梯度，每一级只增加一个预先定义的组件。

### 5.2 构念分离

至少分离两个问题：

- 预测判断：未来十年 AI 大规模替代岗位的可能程度；
- 规范态度：是否支持企业使用 AI 替代人类岗位。

Paper 1 在协议中指定一个 primary stance，另一个作为 secondary outcome，避免把事实预测与价值支持混为一谈。

### 5.3 社会暴露识别

正式设计至少区分：

- 无邻居的重复生成/自我记忆基线；
- WS 真实邻居暴露；
- degree-matched shuffled-neighbor 暴露。

这用于区分模型自身时间漂移、自我历史效应、收到社会信息的效应与网络拓扑效应。BA 在主效应稳定后作为 robustness，而不是 Paper 1 MVP 的必需主因子。

### 5.4 双层结构

“组内主流化—组间差异化”必须在实验前定义群体，不得用结局聚类后反向证明。群体身份应与初始立场正交或平衡。主要测量包括：

- 总方差；
- 组内方差；
- 组间方差分量/ICC；
- 跨群体迁移；
- 群体内外文本语义分散度。

若 Paper 1 MVP 无法加入可识别群体设计，应将“双层结构”降为理论扩展，不列为已验证主结论。

### 5.5 规模与重复

- mock 阶段验证 N=20/100/1000；
- 真实 API 校准先使用 N=20/50/100；
- 正式主实验固定为 N=1000、T=50、12 cells、首批10个 matched seeds；按一次预注册的盲态 nuisance-variance 重估最多扩至20个；
- N=200/500 仅用于主对比的有限规模 gate，不进入正式主结论；
- N 和 seed 解决不同问题，N=1000 不得替代独立重复；
- Phase 0 与有限规模 gate 决定是否允许启动既定正式矩阵，不得用观察到的效应方向事后改写正式规模。

## 6. 平台架构

```text
platform/
├── pyproject.toml
├── src/agent_ex/
│   ├── domain.py
│   ├── population.py
│   ├── persona.py
│   ├── networks.py
│   ├── exposure.py
│   ├── prompts.py
│   ├── models.py
│   ├── engine.py
│   ├── storage.py
│   ├── metrics.py
│   ├── validation.py
│   └── analysis.py
├── configs/paper1/
├── tests/
├── scripts/
└── notebooks/
```

### 6.1 模块职责

- `domain.py`：不可变状态、Agent、消息、事件和结果 schema；
- `population.py`：任意 N 的人口生成、平衡和可追溯抽样；
- `persona.py`：正交实验操作，不包含网络或模型逻辑；
- `networks.py`：WS、BA 和外部图的生成/加载；
- `exposure.py`：谁实际看到谁，返回结构化 exposure record；
- `prompts.py`：从协议和状态生成 prompt，并计算 prompt hash；
- `models.py`：统一的 real/mock adapter、重试、限流和响应元数据；
- `engine.py`：不可变快照、并发生成、同步提交；
- `storage.py`：逐轮事件追加、checkpoint、幂等恢复、manifest；
- `metrics.py`：唯一指标定义；
- `validation.py`：运行前协议校验、运行后完整性校验；
- `analysis.py`：seed-blocked 主分析、敏感性分析和图表数据。

Notebook 只能调用公开接口、展示结果和制作图表，不得重新定义 Agent、prompt、网络、指标或主循环。

## 7. 运行数据流

```text
Paper 1 协议
→ 机器配置校验
→ 人口与网络生成
→ run manifest
→ 每轮不可变状态快照
→ 每个 Agent 独立 exposure 与 RNG
→ 模型生成和结构化解析
→ 同步提交
→ 事件追加与 checkpoint
→ 完整性验证
→ 分析数据集冻结
→ 统计分析与图表
```

`event_id` 是逻辑事件和幂等写入的唯一键。恢复时按 `run_id` 查询所有非终态 `event_id`；已进入终态的事件不得重复调用模型或重复写入。

运行与请求身份遵循以下契约：

- `run_spec_hash`：对规范化后的 protocol、run config、模型请求参数、模型标识、代码 Git SHA 和环境 lock hash 做内容寻址；相同实验规范得到相同 hash；
- `run_id`：`run_spec_hash + replicate_seed + launch_nonce` 的唯一实例标识；恢复同一实例沿用原 `run_id`，重跑则产生新 `launch_nonce`；
- `event_id`：由 `run_id + round + agent_id` 派生，是逻辑生成事件和幂等写入键；
- `attempt_id`：由 `event_id + attempt_index` 派生；每次重试均新增 attempt，不覆盖先前请求；
- 每个 attempt 保存实际 exposure record、渲染后 prompt、请求参数、provider request id、原始响应、解析结果、错误、token usage、时间戳及各自内容 hash；
- manifest 中的 prompt template hash 用于标识模板族，逐请求 rendered prompt hash 记录在 attempt；二者不得混用。

## 8. 错误处理与可恢复性

- 区分认证/参数错误、限流、暂时性服务器错误和解析错误；
- 仅对可恢复错误使用指数退避和 jitter；`Retry-After` 仅在已验证 provider 确实返回且语义明确时使用，否则采用由 `UNRESOLVED[P1_TIMEOUT_RETRY]` 冻结的退避规则；
- 单 Agent 最终失败必须记录失败事件，不得无日志地沿用旧分数；
- 是否允许 fallback、重试后排除或保持原值由协议明确；
- 每轮或更细粒度地追加写入并 flush；
- run manifest 记录 expected/actual count、最后完成轮次和失败清单；
- 分析入口拒绝不完整、协议不匹配或 hash 不一致的 run；
- 同秒重复启动不得覆盖已有 run。

每个逻辑事件必须进入以下终态之一：

- `succeeded`：得到有效结构化结果；
- `failed`：重试耗尽且无协议允许的替代结果；
- `excluded`：按预注册规则从目标分析集排除，但保留全部事件；
- `imputed`：仅在协议预先允许时生成插补值，并保留原失败状态与插补方法；
- `fallback`：仅在协议预先允许时由指定备用模型/规则得到结果，并记录来源。

`complete` 只表示所有预期事件均达到某个终态，不等于可进入主分析。manifest 分别记录 expected、succeeded、failed、excluded、imputed 和 fallback 数量。默认 Paper 1 主分析仅接受 `failed=0`、`imputed=0`、`fallback=0` 且排除比例未超过协议阈值的 complete run；其他 complete run 只能进入协议明确指定的敏感性分析。仍有非终态事件的 run 为 `incomplete`，分析入口一律拒绝。恢复只继续非终态事件。

## 9. 随机性与可复现性

- 人口、网络、exposure 和模型采样使用分离的 seed namespace；
- 为每个 `(base_seed, round, agent_id, component)` 派生独立 RNG；
- API 若支持生成 seed，记录并传入；不支持时明确标记为非确定性重复；
- manifest 至少记录：Git SHA、dirty 状态、协议版本、配置 hash、prompt hash、模型/provider 返回身份、参数、request id、finish reason、token usage、时间戳和依赖环境；
- 商用滚动模型别名不能被描述为严格可复现模型版本；
- 原始数据可不进入 Git，但数据 manifest、hash 和受控归档位置必须可追踪。

## 10. 指标与统计约束

### 10.1 指标

协议必须唯一指定：

- 中间位置范围及敏感性区间；
- 端点/极端计数；
- 方差比 `V_T/V_0`；
- 组内/组间方差分量与 ICC；
- 平均立场变化；
- 连续 K 轮稳定的收敛规则；
- 理由 embedding 分散度；
- 预注册理由类别的 Shannon entropy/有效类别数；
- Self-BLEU 仅作为次要指标。

### 10.2 分析单位

- run/seed 是主要独立重复单位；
- 相同 seed 跨条件使用 matched/block 分析；
- 比例结局优先使用 binomial 模型、随机化检验或合适的区组对比；
- 轨迹模型考虑 run 随机效应与时间相关结构；
- 未收敛属于右删失，不得直接删除后做普通 ANOVA；
- 优先报告效应量与 95% CI，并进行阈值敏感性分析。

## 11. 测试与验收

### 11.1 自动化测试

最低测试集必须覆盖：

- 任意 N 人口生成且满足平衡约束；
- persona 因素只改变允许改变的 prompt 部分；
- 同步更新中同轮 Agent 不读取新状态；
- exposure record 与实际 prompt 输入一致；
- 每 Agent/round RNG 稳定且互不污染；
- parser 对合法、多个标签、缺失标签和越界值的行为；
- 可恢复/不可恢复错误分类；
- checkpoint 中断与幂等恢复；
- 不完整 run 被分析拒绝；
- 协议、配置与指标定义一致；
- mock N=1000 性能与内存基线。

### 11.2 分级验收

1. mock N=20 完整流程；
2. mock N=100/1000 规模验证；
3. 真实 API N=20 校准；
4. 真实 API N=50/100 成本与吞吐校准；
5. pilot-3.0 N=20 行为方向复现，仅作为迁移验收；
6. Paper 1 Phase 0 manipulation check；
7. 正式实验前 protocol freeze 和分析 dry run；
8. 正式数据冻结后才允许论文主分析。

## 12. 实施阶段

### Phase A：知识归档

建立 README、AGENTS、overview、research-program、research-qa、decisions、reproducibility 和 archive-index；修正已知错误路径和过期设计；将历史 RLHF 方案明确路由到 Paper 2。

### Phase B：Paper 1 协议

完成构念、2×2 起始设计、社会暴露对照、群体定义、指标、统计、排除和停止规则。机器配置在协议确认后创建。

### Phase C：平台基础

创建 package、schemas、mock adapter、引擎、storage、validation 和最低测试集。

### Phase D：迁移与校准

复用 pilot 中经过验证的同步更新骨架和 API adapter，但不复制旧双实现；完成 mock 规模测试、pilot 行为方向复现和 API 成本校准。

### Phase E：Paper 1 正式实验

完成 Phase 0 后冻结矩阵；运行正式实验；执行完整性校验、数据冻结、主分析和敏感性分析。

### Phase F：交付与复用

形成 Paper 1 可复现包，并记录 Paper 2/GLM benchmark 需要新增的协议与 adapter，不复制平台核心。

## 13. 反模式保护

- 不把 `n_agents` 直接改成 1000 后运行；
- 不继续在旧 Notebook 增加正式能力；
- 不保留 Notebook/src 双实现；
- 不把复合 prompt 效应简称为 persona 强度效应；
- 不把预测判断与规范态度混成一个量表；
- 不把 N 当作实验重复数；
- 不使用结局聚类定义群体再证明组间差异；
- 不报告未实际传入的生成参数；
- 不让未完成 run 进入分析；
- 不用普通 ANOVA 处理右删失收敛时间；
- 不把基金愿景描述成已实现能力或已有实验发现。

## 14. 完成标准

本设计完成的判据是：

1. 新接手者能在五分钟内区分历史证据、当前协议与未来愿景；
2. Paper 1 的人类协议和机器配置无冲突；
3. 核心实验逻辑只有一套；
4. mock 模型可验证 N=1000，而无需真实 API；
5. 真实 run 可以中断恢复且完整性可自动证明；
6. 所有正式结果可追溯到协议、配置、代码、prompt、模型和原始事件；
7. Paper 2 和 benchmark 可通过新增配置/adapter 扩展，而不复制引擎。
