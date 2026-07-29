# Agent-EX Paper 1 平台实施计划

**日期：** 2026-07-14
**状态：** Phase 1–3A历史实施记录；Phase 4部分已被07-29事件级设计取代
**目标分支：** `codex/paper1-platform`
**实施原则：** 协议先行、测试先行、分级放大、旧 pilot 原地冻结

> 本计划只继续证明Phase 3A已经完成的工作。第4阶段及后续仍含旧同步语义，不得直接
> 执行；待07-29完成规格通过整份书面复核后，另写Phase 4B实施计划。

## 0. 已确认目标

Paper 1 的正式设计为：

- `identity information 2 × continuity requirement 2 × social exposure 3`，共12 cells；
- 唯一 primary outcome：`ΔS_T = Δlog((B+ε)/(W+ε))`；
- 唯一 primary estimand：continuity 对 `WS - shuffled` 网络效应的 matched-seed DiD 调节；
- 正式规模：N=1000、T=50，首批10个 matched seeds，按预注册盲态规则最多扩展至20个；
- Phase 0 与 N=200/500/1000 有限规模检验通过后才允许正式运行。

权威来源：

- `docs/superpowers/specs/2026-07-14-paper1-focused-research-design.md`
- `docs/superpowers/specs/2026-07-14-agent-ex-paper1-platform-design.md`

## Phase 0A：本地文档与 API 发现（已完成）

### 发现来源

- `pilot-1.0/src/agent.py:6-27`：轻量 Agent/OpinionRecord；
- `pilot-1.0/src/network.py:51-99`：邻居抽样与历史上下文；
- `pilot-1.0/src/llm_client.py:10-79`：OpenAI-compatible adapter 与评分解析；
- `pilot-1.0/src/simulator.py:63-107`：Semaphore、gather、统一提交；
- `pilot-2.0/src/simulate.py:334-424`：按 epoch checkpoint 概念；
- `pilot-3.0/run.ipynb` Cell 10：实际人口、网络、prompt、parser 和指标；
- `pilot-3.0/run.ipynb` Cell 18：正式 pilot 的同步快照主循环；
- `pilot-3.0/run.ipynb` Cell 28：旧分析入口及其完整性缺口。

### 已验证可用 API

- Python：`dataclass`、`Path`、`random.Random`、`asyncio.Semaphore/to_thread/gather`、JSON/CSV；
- NetworkX：BA/WS graph factory、neighbors/degree、density、average_clustering；
- NumPy/Pandas：数组、分组、表格落盘；
- OpenAI-compatible：`OpenAI(api_key, base_url, timeout)` 与 `chat.completions.create(model,messages,temperature,max_tokens,extra_body)`；
- 现有本地 adapter 未实现 `top_p`、request seed、structured output、usage/request-id 元数据，不得假设它们已支持。

### Phase 0 结论

- `platform/` 在 2026-07-14 发现阶段尚不存在；Phase 3A 已于 2026-07-29 建立；
- `pilot-3.0/run.ipynb` 是实际正式 pilot 实现，`pilot-3.0/src` 与 pilot-1.0 逐字节相同；
- 迁移同步语义、记录契约和测试样例，不复制任何旧主循环；
- 当前环境未安装 pytest、PyYAML、NetworkX、SciPy、statsmodels、openai，实施前需建立隔离环境与锁定依赖。

## Phase 0B：运行时与官方 API 发现（平台代码前强制 gate）

### 用户决策

在创建 `pyproject.toml` 和真实 model adapter 前，必须确认：

- `MODEL_PROVIDER_ID`：正式模型提供方；
- `MODEL_ID` 与可固定的 revision/version；
- `INFERENCE_RUNTIME`：远程 OpenAI-compatible API、vLLM 本地服务或二者；
- 正式 N=1000 是否使用同一 runtime，Phase 0 是否允许使用兼容但不同的校准 provider。

未确认时允许实施 mock-only domain/engine 设计，但禁止实现或锁定真实 adapter。

### 官方文档发现

由独立文档代理读取所选 provider/runtime 的一手文档，并输出：

- 文档 URL、读取日期、SDK/runtime 版本；
- Python 客户端构造与请求的精确签名；
- 模型身份、revision 和上下文限制；
- `temperature`、`top_p`、seed、max tokens、thinking/structured output 支持；
- usage、finish reason、request ID 和错误/Retry-After 的返回位置；
- vLLM 的启动、并发、batch 和 OpenAI-compatible 限制；
- 明确不存在或未验证的 API。

### 依赖环境发现

- 固定 Python minor version；
- 在隔离环境中解析并锁定 pytest、Pydantic/schema validator、PyYAML、NetworkX、NumPy/Pandas、SciPy、OpenAI SDK 或所选 provider SDK；
- 使用安装后的 `inspect.signature`/最小离线 import 检查核对计划中的 API；
- 将结果写入计划附录“Allowed APIs v1”，并引用官方来源和版本。

### 验证清单

- 未确认 provider/runtime 时真实 adapter 阶段处于 blocked；
- 所有记录参数都能映射到已验证请求签名；
- 所有响应元数据都能映射到已验证响应字段；
- `pyproject.toml` 不含“可能需要”的猜测性依赖。

### 反模式

- 不以旧 pilot 签名代替当前官方文档；
- 不因为 API “OpenAI-compatible”就假定支持 seed、structured output 或完整元数据；
- 不在 Phase 5 才第一次发现核心 SDK 不兼容。

## Phase 1：隔离工作区与知识基线

### 1.1 建立 worktree

待用户选择项目内 `.worktrees/` 或用户全局目录后：

- 从当前 `main` HEAD 创建 `codex/paper1-platform`；
- 若使用项目内目录，先验证其已被 Git 忽略；
- 不携带或覆盖当前用户未提交的 `README.md` 删除项；
- 不提交 `.codex/config.toml`。

### 1.2 创建/更新文档

创建：

- `AGENTS.md`
- `docs/project-overview.md`
- `docs/research-program.md`
- `docs/paper1-protocol.md`
- `docs/research-qa.md`
- `docs/decisions.md`
- `docs/reproducibility.md`
- `docs/archive-index.md`
- `logs/2026-07-14.md`

小块更新：

- `README.md`：只更新过时导航和当前主线，保留用户工作区已有删除意图；
- 平台设计 §5.5：以最终 N=1000 方案替换旧 N≈200 表述；
- `design/*.md` 暂不改正文，由 archive-index 标记其历史地位。

### 文档参考

- focused spec §1、§4、§11–13；
- platform spec §3–4、§7–10；
- `logs/notion-2026-05-31.md` §0、§4–7；
- README 当前 working-tree 内容，而不是 HEAD 版本。

### 验证清单

- 每个新文档含 `status/authority/supersedes/last-verified`；
- README 不再称05-31为最新设计；
- 全仓搜索确认当前文档不把 RLHF、动态重连或 weak/lifelong 写成 Paper 1 主矩阵；
- `git diff -- README.md` 保留用户原删除项；
- `.codex/` 未被跟踪。

### 反模式

- 不把 focused spec 全文复制进多个文档；
- 不把 Notion 或 README 设为执行参数真相；
- 不把未决参数伪装为已冻结值。

## Phase 2：Paper 1 协议草案与决策冻结

### 2.1 先写人类协议草案

`docs/paper1-protocol.md` 必须包含：

- 协议身份、版本、状态；
- 12-cell 稳定 cell IDs；
- identity、continuity、exposure 的允许差异和禁止文本；
- matched-seed 共享对象；
- Agent、WS、同步更新和三类 exposure 合同；
- primary outcome/estimand；
- Phase 0、有限规模和正式 N=1000 gates；
- 完整性、失败、排除和停止规则；
- 证据边界。

### 2.2 显式保留待冻结字段

以下字段进入 `docs/research-qa.md`，不得由 coder 决定：

- 主议题与单一态度构念；
- 立场量表和初始组切点；
- `T*`、自然对数、`ε`；
- B/W 精确总体权重公式、ddof 和缺组规则；
- `δ_min`；
- 正式 seed 列表；
- 形态阈值、连续窗口和敏感性区间；
- continuity manipulation check 评分方式及锁死/拒答/失败门槛；
- primary matched contrast 的最终推断检验。

执行所需但当前同样未冻结的字段：

- `POPULATION_SOURCE`、人口字段、联合/边际平衡规则、恰好 N 的生成方法；
- `INITIAL_STANCE_GENERATOR`、初始理由来源、跨 cell 匹配与最小组样本规则；
- `WS_K`、`WS_P`、无向/有向、连通性要求和非法参数处理；
- `ACTIVATION_MODE`、每轮激活数、`MAX_NEIGHBORS`、`MEMORY_WINDOW` 和社会 exposure 数；
- `MODEL_PROVIDER_ID`、`MODEL_ID/REVISION`、`INFERENCE_RUNTIME`；
- temperature、top_p、max tokens、request seed、thinking、timeout、retry、concurrency/rate budget；
- N=200/500/1000 有限规模检验的 cells、matched seed 数和 seed 列表；
- 有限规模 gate 的 `ΔS_T` 稳定容差、最大失败/解析失败率、最小吞吐、最大内存和最大预计总时长；
- formal gate 的恢复演练次数、允许失败终态和矩阵完整性阈值。

每个 unresolved 字段必须具有：稳定 ID、说明、候选值、推荐值、决策者、最迟 gate 和影响的 schema paths。Phase 3 schema 必须标记哪些字段是 `formal_required`，formal config 存在任何未冻结字段时验证失败。

### 2.3 决策会审

在创建正式机器 YAML 之前，逐项向用户提交候选方案、方法理由和推荐值。用户确认后：

- 更新 `docs/decisions.md`；
- 将 protocol 标记为 `confirmed`；
- 计算 protocol version；
- 才进入 Phase 3。

机器 schema 可以先定义字段形状和 `formal_required` 约束，但不得用 coder 默认值填补决策。

### 验证清单

- 协议中所有未决项都有稳定 ID、owner、截止 gate；
- 没有裸 `TBD`，统一使用结构化 `UNRESOLVED[FIELD_ID]`；
- primary outcome/estimand 与 focused spec 逐字义一致；
- 12 cells 可机械枚举且没有复合 prompt；
- 用户确认记录进入 decisions。

## Phase 3：项目骨架、schema 与领域模型（TDD）

### 3.1 文件结构

创建：

```text
platform/
├── pyproject.toml
├── src/agent_ex/
│   ├── __init__.py
│   ├── domain.py
│   ├── protocol.py
│   └── validation.py
├── protocols/paper1.schema.json
├── configs/paper1/protocol.yaml
└── tests/
```

### 3.2 RED 测试

先写并确认失败：

- schema 拒绝缺失 primary IDs、非12 cells 和非法 factor level；
- protocol 中出现方向性 persona/抗从众/步长限制时失败；
- protocol version/hash 对执行字段变化敏感；
- domain IDs、状态和事件不可变；
- 人类协议生成区与 YAML 不一致时失败。

### 3.3 GREEN 实现

- `domain.py`：不可变 AgentState、OpinionRecord、ExposureRecord、GenerationAttempt、GenerationEvent、RunManifest；
- `protocol.py`：加载、规范化、schema 验证、稳定 hash；
- `validation.py`：协议引用和 source-of-truth 检查；
- 机器协议只填入 Phase 2 已确认字段。

### 文档参考

- focused spec §5–12；
- platform spec §3.2、§7–9；
- `pilot-1.0/src/agent.py:6-27` 仅作轻量状态模式参考。

### 验证清单

- 每个测试均先出现预期 RED，再 GREEN；
- `pytest` 全绿；
- schema/YAML/Markdown 无差异检查通过；
- 无 mutable default、globals config 或 Notebook 业务逻辑。

## Phase 4：Population、Persona、Network 与 Exposure（TDD）

### 4.1 公开接口

- `PopulationFactory.create(spec, seed) -> Population`
- `PersonaPolicy.render(agent, factor_levels) -> PersonaBlocks`
- `NetworkFactory.ws(spec, seed) -> GraphRecord`
- `ExposurePlanner.plan(snapshot, graph, cell, rng_key) -> ExposureBatch`

### 4.2 RED 测试

- 任意 N 精确生成 N 个唯一 Agent，N=1000 不截断；
- 人口、初始立场、初始理由跨12 cells完全匹配；
- identity 只改变身份块，continuity 只改变连续性句；
- WS graph 节点集等于 Agent IDs；
- shuffled 置换保持接收数量、禁止自环/真实邻边、不跨 cell 复制内容；
- exposure record 的 sampled IDs 与渲染输入一致；
- 每 `(seed,round,agent,component)` RNG 独立且不受并发顺序影响。

### 4.3 GREEN 参考

- Graph factory 参考 `pilot-3.0/run.ipynb` Cell 10 `build_network`；
- 加权邻居抽样参考 `pilot-1.0/src/network.py:51-78`；
- 不复制 `roles[:n_agents]`、`stubbornness` 或 lifelong prompt。

### 验证清单

- N=20/100/1000 mock 人口与图约束全过；
- 12-cell prompt block 自动 diff 只出现允许差异；
- 置换 exposure 可序列化和重放；
- 同 seed 重跑 hash 一致。

## Phase 5：Model Adapter、Engine 与 Storage（TDD）

### 5.1 Phase 0B 复核

只有 Phase 0B 已产生带版本与一手来源的 Allowed APIs v1 才能实施真实 adapter。实施代理首先复核：

- 当前模型身份与版本策略；
- OpenAI-compatible 参数签名；
- `top_p`、seed、usage、finish reason、request ID、Retry-After；
- vLLM 批处理/并发能力。

未经官方文档确认的参数不得进入 Allowed APIs；provider 仍未决定时本阶段只实现 MockAdapter 和 adapter protocol。

### 5.2 RED 测试

- mock adapter 返回结构化响应和请求元数据；
- adapter 实际传递每个被记录的生成参数；
- 4xx 不盲重试，429/可恢复5xx遵守重试策略；
- 同步引擎同轮不读取新状态；
- 单 Agent 失败被记录为事件，不使已完成任务丢失；
- 每个 event/attempt ID 稳定且重试不覆盖；
- 中断后只恢复非终态事件；
- 同 run 幂等恢复，不重复请求或写入；
- 不完整 run 无法标记为主分析 eligible。

### 5.3 GREEN 实现

- `models.py`：MockAdapter、OpenAICompatibleAdapter、typed request/response/error；
- `prompts.py`：结构化输入到 chat messages，不读取 globals；
- `engine.py`：轻量 snapshot、Semaphore、per-agent task outcome、同步 commit；
- `storage.py`：append-only events、attempts、round checkpoint、manifest、原子写入与恢复。

### 参考

- adapter：`pilot-1.0/src/llm_client.py:10-65`；
- 同步边界：`pilot-3.0/run.ipynb` Cell 18 行123-168；
- checkpoint 概念：`pilot-2.0/src/simulate.py:334-424`，不复制其 IO 写法。

### 验证清单

- 故障注入测试覆盖中断、429、解析失败和重启；
- raw prompt/response、exposure、参数与 hash 可逐请求追溯；
- mock N=1000 不需要网络或 API key；
- 无每轮 deepcopy 完整 history、无 run 末尾一次性落盘。

## Phase 6：Metrics、Analysis 与盲态 SSR（TDD）

### 6.1 公开接口候选

- `compute_variance_components(scores, prereg_group, spec)`
- `compute_delta_log_bw(round_metrics, t0, t_star, epsilon)`
- `compute_seed_primary_contrast(matched_cell_metrics, spec)`
- `blind_reestimate_seed_count(centered_z, sample_size_spec)`
- `classify_shapes(trajectory, frozen_thresholds)`

这些接口在 Phase 2 决策后冻结，不能由实现者自行改变公式。

### 6.2 RED 测试

- 已知 fixture 满足 `V=B+W`；
- `ΔS_T` 同时保留 B、W、S 和 delta；
- primary z_s 使用正确四 cells、matched seed、identity 等权；
- 缺 cell/round/seed/hash 时拒绝分析；
- SSR 直接使用 z_s 配对方差，不拼 cell 方差；
- SSR 对研究者输出隐藏 mean/sign/CI/p/cell means；
- 10→20 规则、ceiling、cap 和首10纳入规则与协议一致；
- 形态 flags 非互斥，单向漂移不被判成极化；
- failed/imputed/fallback run 按协议限制进入分析。

### 6.3 GREEN 实现

- `metrics.py`：run×round 的总体和组内/组间分量；
- `analysis.py`：matched contrasts、轨迹表和形态 flags；
- `sample_size.py`：单次盲态 nuisance-variance 重估；
- 统计依赖必须在 `pyproject.toml` 锁定并记录版本。

### 验证清单

- synthetic fixtures 覆盖均质化、单向集中、极化、双层结构、停滞；
- primary estimate 与手算 fixture 一致；
- 分析入口拒绝 pilot 式“最新目录但不完整”的 run；
- 不使用 pilot Cell 28 普通 OLS ANOVA 代替 matched design。

## Phase 7：CLI、Notebook 与 Phase 0 工作流

### 7.1 创建

- `platform/scripts/validate_protocol.py`
- `platform/scripts/run_experiment.py`
- `platform/scripts/resume_run.py`
- `platform/scripts/validate_run.py`
- `platform/scripts/build_analysis_dataset.py`
- `platform/notebooks/paper1_phase0.ipynb`
- `platform/notebooks/paper1_results.ipynb`

Notebook 只能调用 package 公共接口并展示结果。

### 7.2 Phase 0A

- 自动 prompt diff；
- continuity coherence/lock check；
- cell non-degeneracy；
- 单一构念、方向偏置、拒答和解析失败检查；
- 输出 `pass|revise|abort`，失败不得进入下一 gate。

### 7.3 Phase 0B

- mock N=20/100/1000；
- real N=20/50/100；
- shape dry-run confusion fixtures；
- primary z_s 方差和成本/吞吐诊断。

### 验证清单

- CLI `--help`、错误配置和恢复路径测试；
- Notebook 中不存在 class/主循环/指标定义；
- Phase 0 决策文件引用 protocol/hash/model identity；
- pilot-3.0 N=20 行为方向只作迁移回归检查。

## Phase 8：矩阵调度与盲态扩样编排（TDD）

### 8.1 创建

- `platform/src/agent_ex/orchestration.py`：不可变 Schedule、RunTask、Stage 定义；
- `platform/src/agent_ex/registry.py`：任务注册、原子认领、lease/heartbeat、完成与失败终态；
- `platform/scripts/create_schedule.py`：从 frozen protocol 生成完整矩阵；
- `platform/scripts/run_worker.py`：按并发/速率预算认领并恢复单 run；
- `platform/scripts/audit_matrix.py`：验证 cell×seed 配对、重复/遗漏、hash 和 eligibility；
- `platform/scripts/freeze_stage1.py`：冻结首10 seeds 的完整事件集；
- `platform/scripts/run_blinded_ssr.py`：受限读取 z_s 中心化方差，输出扩样决定；
- `platform/scripts/append_stage2_schedule.py`：只按 SSR 决定追加 seeds 11–n，不改写 Stage 1；
- `platform/scripts/freeze_formal_dataset.py`：全矩阵完成后冻结分析数据集。

### 8.2 RED 测试

- 相同 protocol/hash/seed list 生成字节一致 schedule；
- 重复 worker 不能同时认领同一 task；lease 过期后可安全恢复；
- 重复启动不产生第二个逻辑 run；
- 单 run 中断后从非终态 event 恢复；
- 漏 cell、重复 cell、错误 seed、错误 protocol/hash 均使矩阵审计失败；
- Stage 1 未达到120个 eligible runs时禁止 SSR；
- SSR 不能输出 mean/sign/CI/p/cell means；
- Stage 2 只能 append 预先列出的 seed，不能修改/删除 Stage 1；
- n_req≤10、11–20、>20 三条路径均有小型故障注入矩阵测试；
- worker 崩溃、registry 重启和网络错误后 exactly-once 逻辑事件仍成立。

### 8.3 并发与预算

- schedule 固定 expected events/runs；
- worker concurrency、provider rate budget、GPU batch budget 和重试预算来自 frozen runtime config；
- registry 与 event store 分离：任务可以重新认领，已完成 event 不重复生成；
- 每个 stage 输出完成计数、失败计数、预计剩余时间和成本，但正式阶段不显示条件效应。

### 验证清单

- 用 N=5、T=3、12 cells、2 seeds 的故障注入矩阵完整演练 schedule→worker→freeze→SSR→append→final freeze；
- 矩阵级 expected/actual 数完全一致；
- 跨进程重启后无重复模型请求；
- 盲态边界经独立反模式代理检查。

## Phase 9：有限规模验证与 N=1000 正式准备

### 9.1 有限规模

- 按 Phase 2 冻结的 cells 和 matched seeds，在 primary contrast 上依次运行 N=200/500/1000；
- 比较 `ΔS_T`、失败率、吞吐、内存和稳定时间；
- N=200/500 不进入正式主结论。

准入报告必须逐项比较 frozen gate：`ΔS_T` 稳定容差、失败/解析失败上限、吞吐下限、内存上限、预计总时长上限。任一 gate 未过即停止，不允许用文字判断“看起来稳定”。

### 9.2 正式运行 gate

必须同时满足：

- protocol 状态 `frozen`；
- 主议题、量表、切点、T*、ε、δ_min、seed 列表和形态阈值已确认；
- 依赖锁、Git SHA、模型身份和数据归档位置已记录；
- mock N=1000、真实校准、恢复测试、分析 dry run 和有限规模检验通过；
- 成本/吞吐能支持约600万次首阶段生成；
- 10个 matched seeds 的全部12 cells不可变 Stage 1 schedule 已生成并通过矩阵审计；
- registry/worker/lease/heartbeat/跨进程恢复与 Stage 1→SSR→Stage 2 演练通过。

### 验证清单

- 启动器拒绝任何未过 gate 的 formal config；
- 运行前 dry-run 输出 expected events = `1000×50×12×10`；
- 研究者不可见 SSR 效应方向；
- 正式数据目录具备受控归档、hash 和恢复演练。

## Phase 10：最终验证与交付

### 全面验证

- 运行全部单元、集成、属性、故障注入和规模测试；
- 搜索禁止模式：Notebook 主循环、globals CONFIG、stubbornness、lifelong、未传递 top_p、latest-run 自动选择、mutable defaults；
- 验证 README/AGENTS/protocol/config/manifest 权威关系；
- 对照官方 provider 文档检查所有请求参数；
- 由独立代理完成验证、反模式、代码质量审查后才提交阶段成果。

### 完成定义

平台“完成”不等于已经跑完 N=1000。代码交付完成需证明：

- 协议可验证、运行可恢复、结果可追溯；
- mock N=1000 通过；
- Phase 0 和有限规模 gate 可机械执行；
- formal launcher 在未冻结参数时会拒绝启动；
- Paper 2 可通过新增协议/adapter 扩展而不复制引擎。
