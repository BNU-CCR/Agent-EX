---
status: active unresolved-register
authority: canonical register of unresolved research and runtime decisions until each is moved to docs/decisions.md
supersedes: scattered open questions in design/todo.md, README.md and historical Notion handoffs for Paper 1 implementation
last-verified: 2026-07-16
---

# Paper 1 研究问答与未决项

规则：每个未决项必须保留稳定 ID。推荐值只是会审输入，不是执行默认值；在决策进入 `docs/decisions.md` 前，配置必须保留对应的 `UNRESOLVED[ID]` 并拒绝 formal run。

## 构念、指标与推断

| ID | 问题 | 候选 / 推荐 | 决策者 | 最迟 gate | Schema paths |
|---|---|---|---|---|---|
| P1_TOPIC_PRIMARY | 主议题与单一态度构念 | AI劳动议题；推荐把预测判断与规范支持二选一 | 用户+方法会审 | Phase 0A 前 | topic.id, topic.statement, topic.statement_sha256, stance.construct |
| P1_STANCE_SCALE | 立场量表 | Likert/连续刻度；推荐先做认知访谈式 prompt 校准 | 用户+方法会审 | Phase 0A 前 | stance.scale |
| P1_INITIAL_GROUP_CUTS | 初始组切点 | 三组/分位组；推荐保证预注册且每组足量 | 方法会审 | Phase 0B 前 | groups.cuts |
| P1_ENDPOINT_TSTAR | primary 终点 T* | T=50 内预注册终点；不自动等同最后一轮 | 用户+方法会审 | Phase 0B 前 | outcomes.primary.t_star |
| P1_LOG_EPSILON | log 比值 ε | 数值稳定常数；推荐用合成 fixture 做敏感性检查 | 方法会审 | Phase 0B 前 | outcomes.primary.epsilon |
| P1_BW_FORMULA | B/W 精确公式 | 总体加权/ANOVA 分解；推荐满足可测试分解恒等式 | 方法会审 | Phase 0B 前 | metrics.variance_components |
| P1_BW_DDOF | 方差 ddof | 0/1；须与公式和 fixture 一致 | 方法会审 | Phase 0B 前 | metrics.ddof |
| P1_MISSING_GROUP_RULE | 缺组处理 | fail/exclude；推荐运行前 fail | 方法会审 | Phase 0B 前 | metrics.missing_group |
| P1_DELTA_MIN | 最小重要效应 | 由理论/模拟精度定义，不从正式结果反推 | 用户+方法会审 | formal freeze | sample_size.delta_min |
| P1_FORMAL_SEEDS | 10+10 seed 列表 | 预生成固定列表；推荐与其他 RNG namespace 分离 | 用户+实现会审 | formal freeze | sampling.formal_seeds, sampling.blind_ssr |
| P1_SHAPE_THRESHOLDS | 形态阈值 | 均质化/漂移/极化/双层/停滞阈值 | 方法会审 | Phase 0B 前 | shapes.thresholds |
| P1_SHAPE_WINDOW | 连续窗口 | K轮；用合成轨迹校准 | 方法会审 | Phase 0B 前 | shapes.window |
| P1_SHAPE_SENSITIVITY | 敏感性区间 | 预注册上下界 | 方法会审 | formal freeze | shapes.sensitivity |
| P1_CONTINUITY_MC_SCORING | 连续性 manipulation check | 人工盲评/模型评审/规则；推荐双方法一致性 | 用户+方法会审 | Phase 0A 前 | gates.continuity.scoring |
| P1_CONTINUITY_LOCK_THRESHOLD | 锁死门槛 | 近零变化率阈值 | 方法会审 | Phase 0A 前 | gates.continuity.lock_max |
| P1_REFUSAL_THRESHOLD | 拒答门槛 | 最大率 | 方法+运行时会审 | Phase 0A 前 | gates.quality.refusal_max |
| P1_PARSE_FAILURE_THRESHOLD | 解析失败门槛 | 最大率 | 方法+运行时会审 | Phase 0A 前 | gates.quality.parse_failure_max |
| P1_PRIMARY_INFERENCE | 主对比推断 | 配对单样本对比/置换/层级模型；推荐与 matched-seed 设计一致 | 方法会审 | analysis freeze | analysis.primary_test |

## 人口、网络与暴露

| ID | 问题 | 候选 / 推荐 | 决策者 | 最迟 gate | Schema paths |
|---|---|---|---|---|---|
| P1_POPULATION_SOURCE | 人口来源 | 合成人口/调查边际；推荐可审计且无立场泄漏 | 用户+方法会审 | Phase 4 前 | population.source |
| P1_POPULATION_FIELDS | 身份字段 | 人口学与议题经历清单 | 用户+方法会审 | Phase 4 前 | population.fields |
| P1_POPULATION_BALANCE | 联合/边际平衡 | 独立/配额/联合分布 | 方法会审 | Phase 4 前 | population.balance |
| P1_POPULATION_EXACT_N | 恰好 N 的生成规则 | 配额余数/受控抽样；推荐确定性算法 | 方法+实现会审 | Phase 4 前 | population.exact_n |
| P1_INITIAL_STANCE_GENERATOR | 初始立场生成 | 固定分布/外部数据/模型生成 | 用户+方法会审 | Phase 4 前 | initialization.stance |
| P1_INITIAL_REASON_SOURCE | 初始理由来源 | 模板/模型/语料；推荐跨 cell 完全匹配 | 用户+方法会审 | Phase 4 前 | initialization.reason |
| P1_PERSONA_TEMPLATES | 四个 persona 模板制品 | identity×continuity 四组合；只登记稳定 template ID 与 SHA-256，不在协议中保存自由文本 | 用户+方法会审 | Phase 0A 前 | persona.identity_absent_continuity_absent.template_id, persona.identity_absent_continuity_absent.template_sha256, persona.identity_absent_continuity_present.template_id, persona.identity_absent_continuity_present.template_sha256, persona.identity_present_continuity_absent.template_id, persona.identity_present_continuity_absent.template_sha256, persona.identity_present_continuity_present.template_id, persona.identity_present_continuity_present.template_sha256 |
| P1_MIN_GROUP_SIZE | 最小组样本 | 绝对数/比例 | 方法会审 | Phase 4 前 | groups.min_size |
| P1_WS_K | WS 邻居数 k | Phase 0 候选网格；不沿用 pilot 默认 | 方法会审 | Phase 4 前 | network.ws.k |
| P1_WS_P | WS 重连概率 p | Phase 0 候选网格；不沿用 pilot 冲突值 | 方法会审 | Phase 4 前 | network.ws.p |
| P1_GRAPH_DIRECTION | 图方向 | 无向/有向；推荐与暴露语义一致 | 方法会审 | Phase 4 前 | network.directed |
| P1_GRAPH_CONNECTIVITY | 连通要求 | connected/giant component | 方法会审 | Phase 4 前 | network.connectivity |
| P1_INVALID_GRAPH_RULE | 非法参数/图处理 | 运行前 fail；推荐不静默修复 | 实现+方法会审 | Phase 4 前 | network.on_invalid |
| P1_ACTIVATION_MODE | 激活方式 | 全体同步/子集同步 | 用户+方法会审 | Phase 4 前 | dynamics.activation_mode |
| P1_ACTIVATION_COUNT | 每轮激活数 | N/固定数/比例 | 方法会审 | Phase 4 前 | dynamics.activation_count |
| P1_MAX_NEIGHBORS | 最大邻居输入数 | 全邻居/抽样上限 | 方法+成本会审 | Phase 4 前 | exposure.max_neighbors |
| P1_MEMORY_WINDOW | 历史窗口 | 全历史/固定K轮窗口/摘要 | 用户+方法会审 | Phase 4 前 | memory.window |
| P1_SOCIAL_EXPOSURE_COUNT | 社会消息数 | degree/固定上限；必须匹配 E1/E2 | 方法会审 | Phase 4 前 | exposure.social_count |

## 模型、API 与运行时

| ID | 问题 | 候选 / 推荐 | 决策者 | 最迟 gate | Schema paths |
|---|---|---|---|---|---|
| P1_MODEL_REVISION | Qwen3-8B 权重 revision | 候选 `b968826d9c46dd6066d109eabc6255188de91218`；artifact/runtime smoke 后固定 | 用户+运行时会审 | Phase 0B 结束 | model.revision |
| P1_VLLM_VERSION | vLLM 版本/镜像 | 候选 `0.23.0`；runtime smoke 后固定版本与镜像 digest | 运行时会审 | adapter 实现前 | runtime.vllm.version |
| P1_TEMPERATURE | temperature | Phase 0 候选；主矩阵固定 | 用户+方法会审 | Phase 0A 前 | generation.temperature |
| P1_TOP_P | top_p | Phase 0 候选；须验证实际传递 | 用户+方法会审 | Phase 0A 前 | generation.top_p |
| P1_MAX_TOKENS | max tokens | 按结构化理由长度校准 | 方法+成本会审 | Phase 0B 前 | generation.max_tokens |
| P1_REQUEST_SEED | 模型采样 seed | vLLM 支持性实测；不支持则标记非确定 | 运行时会审 | adapter 实现前 | generation.seed |
| P1_TIMEOUT_RETRY | timeout/retry | 按错误分类和 Retry-After 冻结 | 运行时会审 | adapter 实现前 | runtime.timeout, runtime.retry |
| P1_CONCURRENCY_BUDGET | 并发/显存/速率预算 | 由真实 benchmark 冻结 | 运行时+成本会审 | Phase 0B 结束 | runtime.concurrency, runtime.rate_budget |
| P1_API_PROVIDER | API 稳健性提供方 | DashScope/其他；推荐固定 snapshot 可用者 | 用户+方法会审 | 稳健性预注册前 | robustness.api.provider |
| P1_API_SNAPSHOT | API 精确 snapshot | 禁止 rolling alias | 用户+运行时会审 | 稳健性预注册前 | robustness.api.model_snapshot |
| P1_API_ROBUSTNESS_CELLS | API 核心8 cells | `P1-I0-C0-E1/E2`、`P1-I0-C1-E1/E2`、`P1-I1-C0-E1/E2`、`P1-I1-C1-E1/E2`，即全部 identity×continuity 下的 shuffled 与 WS | 用户+方法会审 | 稳健性预注册前 | robustness.api.cells |
| P1_API_ROBUSTNESS_SCALE_FREEZE | API 子集最终 N/T/seeds | 暂拟 N=200/T=50/5 matched seeds；不定义 cells | 用户+成本会审 | 稳健性预注册前 | robustness.api.scale |

## 规模与运行 gates

| ID | 问题 | 候选 / 推荐 | 决策者 | 最迟 gate | Schema paths |
|---|---|---|---|---|---|
| P1_SCALE_GATE_DESIGN | N=200/500/1000 的 cells/seeds | primary contrast cells；matched seeds | 用户+方法会审 | Phase 9 前 | gates.scale.design |
| P1_GATE_DELTA_STABILITY | ΔS 稳定容差 | 预注册绝对/相对容差 | 方法会审 | Phase 9 前 | gates.scale.delta_tolerance |
| P1_GATE_FAILURE_MAX | 最大生成失败率 | 固定上限 | 方法+运行时会审 | Phase 9 前 | gates.scale.failure_max |
| P1_GATE_THROUGHPUT_MIN | 最小吞吐 | calls/tokens per second | 运行时+成本会审 | Phase 9 前 | gates.scale.throughput_min |
| P1_GATE_MEMORY_MAX | 最大内存/显存 | benchmark 后冻结 | 运行时会审 | Phase 9 前 | gates.scale.memory_max |
| P1_GATE_DURATION_MAX | 最大预计总时长 | 预算约束 | 用户+成本会审 | formal freeze | gates.formal.duration_max |
| P1_RECOVERY_DRILLS | 恢复演练次数 | 固定次数与故障场景 | 实现会审 | formal freeze | gates.formal.recovery_drills |
| P1_ANALYSIS_ELIGIBILITY | 允许终态/排除阈值 | 主分析默认零 failed/imputed/fallback | 用户+方法会审 | analysis freeze | quality.eligibility, quality.exclusion |
| P1_MATRIX_COMPLETENESS | 矩阵完整性阈值 | 推荐100% expected terminal + 配对完整 | 方法+实现会审 | formal freeze | gates.formal.matrix_complete |
| P1_PROTOCOL_VERSION | 首个冻结版本 | 语义化/内容 hash；推荐二者同时记录 | 实现+方法会审 | protocol freeze | protocol.version |
| P1_DATA_ARCHIVE_URI | 正式数据归档位置 | 对象存储/受控卷；推荐不可变版本与校验 hash | 用户+运行时会审 | formal freeze | storage.archive_uri |
| P1_ARCHIVE_PROVENANCE_MAP | pilot/Notion/Git/原始数据映射 | 建立逐项 URI、commit 与完整性状态 | 用户+归档会审 | Paper 1 发布前 | provenance.archive_map |
