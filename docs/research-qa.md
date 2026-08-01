---
status: active unresolved-register
authority: canonical register of unresolved research and runtime decisions until each is moved to docs/decisions.md
supersedes: scattered open questions in design/todo.md, README.md and historical Notion handoffs for Paper 1 implementation
last-verified: 2026-07-29
---

# Paper 1 研究问答与未决项

规则：每个未决项必须保留稳定 ID。推荐值只是会审输入，不是执行默认值；在决策进入
`docs/decisions.md` 的 fenced YAML 审批记录前，配置必须保留对应的
`UNRESOLVED[ID]` 并拒绝 formal run。审批记录中的 `approvers` 至少要包含本表“决策者”
列的完整 owner 角色字符串；模糊匹配、子串或自由改写不算授权。

## 构念、指标与推断

| ID | 问题 | 候选 / 推荐 | 决策者 | 最迟 gate | Schema paths |
|---|---|---|---|---|---|
| P1_TOPIC_PRIMARY | 主议题与单一态度构念 | 已确认延迟退休、转基因食品、AI就业替代三包全部进入Phase 0 probe；若多个通过，优先级为延迟退休>转基因>AI就业，主议题取最高优先通过者，其余通过者按预注册预算进入稳健性；最终机器原文与hash仍须probe冻结，见`D-2026-07-29-02`、`D-2026-07-29-15`、`DR-P1-045`至`DR-P1-047`、`DR-P1-084` | 用户+方法会审 | Phase 0A 前 | topic.id, topic.statement, topic.statement_sha256, stance.construct |
| P1_STANCE_SCALE | 立场量表 | 已确认首选1–7全标签有序量表、真实中点及独立1–5审计型confidence；须按`DR-P1-048`与0–10挑战者及字段顺序一起probe后冻结实际机器值 | 用户+方法会审 | Phase 0A 前 | stance.scale |
| P1_INITIAL_GROUP_CUTS | 初始组切点 | 已确认按round 0固定为1–3/4/5–7三组，不按终点重分；见`D-2026-07-29-05`、`DR-P1-057` | 用户+方法会审 | Phase 4 前 | groups.cuts |
| P1_PRIMARY_OUTCOME | 单一primary outcome | 旧`Δlog(B/W)`只保留为候选组际结构指标；须依据动力学总问题、round-0机械基线和形态区分，在不读取正式结果的统计规格中冻结一个单一endpoint，见`D-2026-07-29-20`、`DR-P1-089` | 用户+方法会审 | analysis freeze | outcomes.primary.id, outcomes.primary.definition |
| P1_ENDPOINT_TSTAR | 候选组际结构指标终点 T* | T=50 内预注册终点；不自动等同最后一轮，也不自动获得primary地位 | 用户+方法会审 | Phase 0B 前 | outcomes.group_structure.t_star |
| P1_LOG_EPSILON | 候选组际结构log比值 ε | 数值稳定常数；推荐用合成fixture做敏感性检查，不得自动绑定新primary outcome | 方法会审 | Phase 0B 前 | outcomes.group_structure.epsilon |
| P1_BW_FORMULA | B/W 精确公式 | 总体加权/ANOVA 分解；推荐满足可测试分解恒等式 | 方法会审 | Phase 0B 前 | metrics.variance_components |
| P1_BW_DDOF | 方差 ddof | 0/1；须与公式和 fixture 一致 | 方法会审 | Phase 0B 前 | metrics.ddof |
| P1_MISSING_GROUP_RULE | 缺组处理 | fail/exclude；推荐运行前 fail | 方法会审 | Phase 0B 前 | metrics.missing_group |
| P1_DELTA_MIN | 最小重要效应 | 由理论/模拟精度定义，不从正式结果反推 | 用户+方法会审 | formal freeze | sample_size.delta_min |
| P1_FORMAL_SEEDS | 10+10 seed 列表 | 预生成固定列表；推荐与其他 RNG namespace 分离 | 用户+实现会审 | formal freeze | sampling.formal_seeds, sampling.blind_ssr |
| P1_SHAPE_THRESHOLDS | 形态阈值 | 均质化/漂移/极化/双层/停滞阈值 | 方法会审 | Phase 0B 前 | shapes.thresholds |
| P1_SHAPE_WINDOW | 连续窗口 | K轮；用合成轨迹校准 | 方法会审 | Phase 0B 前 | shapes.window |
| P1_SHAPE_SENSITIVITY | 敏感性区间 | 预注册上下界 | 方法会审 | formal freeze | shapes.sensitivity |
| P1_CONTINUITY_MC_SCORING | 连续性 manipulation check | 已确认采用规则+独立模型judge+分层盲态人工编码，平衡“合理保持/充分信息后改变/信息不足”情境；精确量表与阈值待Phase 0冻结，见`D-2026-07-29-06`、`DR-P1-064` | 用户+方法会审 | Phase 0A 前 | gates.continuity.scoring |
| P1_CONTINUITY_LOCK_THRESHOLD | 锁死门槛 | 已确认C1须提高历史解释连贯性但在强而非欺骗性反向信息下仍能可解释改变；精确上限保持`UNRESOLVED`，见`D-2026-07-29-06`、`DR-P1-063`、`DR-P1-064` | 方法会审 | Phase 0A 前 | gates.continuity.lock_max |
| P1_REFUSAL_THRESHOLD | 拒答门槛 | Phase 0题干probe已确认实质拒答率不高于1%；formal runtime门槛和canonical值仍须冻结 | 方法+运行时会审 | Phase 0A 前 | gates.quality.refusal_max |
| P1_PARSE_FAILURE_THRESHOLD | 解析失败门槛 | Phase 0题干probe已确认至多一次格式重试后有效解析率不低于99%；formal runtime门槛和canonical值仍须冻结 | 方法+运行时会审 | Phase 0A 前 | gates.quality.parse_failure_max |
| P1_PRIMARY_INFERENCE | 主对比推断 | 对四个persona条件等权平均的matched-seed `WS-shadow`差异采用配对单样本对比/置换/层级模型；精确方法待盲态冻结，见`D-2026-07-29-20`、`DR-P1-089` | 方法会审 | analysis freeze | analysis.primary_test |

## 人口、网络与暴露

| ID | 问题 | 候选 / 推荐 | 决策者 | 最迟 gate | Schema paths |
|---|---|---|---|---|---|
| P1_POPULATION_SOURCE | 人口来源 | 已确认目标总体为中国大陆18岁以上、过去半年上网的家庭/社区居民，并采用NBS2025+Census2020+CNNIC57+CFPS2022分层来源；实际文件版本、筛选变量和hash待冻结，见`D-2026-07-29-03`、`DR-P1-049`至`DR-P1-051` | 方法会审+机器冻结 | Phase 4 前 | population.source |
| P1_POPULATION_FIELDS | 身份字段 | 已确认采用校准、身份可见、分析审计、议题扩展四类用途；共同身份卡限年龄段、调查记录性别、教育、当前城乡、主要活动及就业者宽职业组；精确crosswalk、机器标签和模板仍待冻结，见`D-2026-07-29-04`、`DR-P1-003`、`DR-P1-052`至`DR-P1-055` | 方法会审+机器冻结 | Phase 4 前 | population.fields |
| P1_POPULATION_BALANCE | 联合/边际平衡 | 已确认加权CFPS2022成年网民作首选联合供体，以2025总体边际、2020详细交叉结构和CNNIC网民边际透明校准；精确字段/约束/容差仍未决，见`D-2026-07-29-03`、`DR-P1-050`、`DR-P1-051` | 方法会审 | Phase 4 前 | population.balance |
| P1_POPULATION_EXACT_N | 恰好 N 的生成规则 | 已确认以校准权重为输入的TRS整数化生成恰好N人；每个matched seed重新抽取一份人口，同seed的12 cells逐Agent共用，seed间不得复用同一人口；精确排序/tie-break/RNG与输入制品待机器冻结，见`D-2026-07-29-16`、`DR-P1-085` | 方法+实现会审 | Phase 4 前 | population.exact_n |
| P1_INITIAL_STANCE_GENERATOR | 初始立场生成 | 已确认采用七档人数`[50,100,200,300,200,100,50]`的受控对称单峰分布；人口—立场约束正交，同matched seed跨12 cells逐Agent匹配；精确算法/容差/RNG待机器冻结，见`D-2026-07-29-05`、`DR-P1-056`、`DR-P1-057` | 用户+方法会审 | Phase 4 前 | initialization.stance |
| P1_INITIAL_REASON_SOURCE | 初始理由来源 | 已确认采用“来源支持的论据家族+冻结模型受控改写+机器/人工审计”的离线理由库；每Agent一条round-0理由，同matched seed跨cell完全匹配；理由制品和阈值待机器冻结，见`D-2026-07-29-05`、`DR-P1-058`至`DR-P1-060` | 用户+方法会审 | Phase 4 前 | initialization.reason |
| P1_PERSONA_TEMPLATES | 四个 persona 模板制品 | 已确认由共同骨架确定性插入最小identity块和非锁死continuity块；absent条件真省略，不使用中立Persona/placebo；模板原文、顺序挑战、ID与hash经Phase 0冻结，见`D-2026-07-29-06`、`DR-P1-061`至`DR-P1-065` | 用户+方法会审 | Phase 0A 前 | persona.identity_absent_continuity_absent.template_id, persona.identity_absent_continuity_absent.template_sha256, persona.identity_absent_continuity_present.template_id, persona.identity_absent_continuity_present.template_sha256, persona.identity_present_continuity_absent.template_id, persona.identity_present_continuity_absent.template_sha256, persona.identity_present_continuity_present.template_id, persona.identity_present_continuity_present.template_sha256 |
| P1_MIN_GROUP_SIZE | 最小组样本 | 已确认主分布三组为350/300/350并以300作运行前硬门槛；分布改变时必须联动重审，见`D-2026-07-29-05`、`DR-P1-057` | 用户+方法会审 | Phase 4 前 | groups.min_size |
| P1_WS_K | WS 邻居数 k | 已确认N=1000首选`k=10`，以`{6,10,20}`做不调用LLM的结构挑战；精确值经锁定NetworkX和正式seeds复算后冻结，见`D-2026-07-29-07`、`DR-P1-067`、`DR-P1-070` | 用户+方法会审 | Phase 4 前 | network.ws.k |
| P1_WS_P | WS 重连概率 p | 已确认首选`p=0.05`，以`{.02,.05,.10}`做纯结构挑战；不得按意见结果方向选值，见`D-2026-07-29-07`、`DR-P1-068`、`DR-P1-070` | 用户+方法会审 | Phase 4 前 | network.ws.p |
| P1_GRAPH_DIRECTION | 图方向 | 已确认标准WS无向简单图，边解释为稳定的相互可见接触，不代表真实关注关系，见`D-2026-07-29-07`、`DR-P1-066` | 用户+方法会审 | Phase 4 前 | network.directed |
| P1_GRAPH_CONNECTIVITY | 连通要求 | 已确认N个节点全连通，不采用giant component加小分量，见`D-2026-07-29-07`、`DR-P1-066`、`DR-P1-069` | 用户+方法会审 | Phase 4 前 | network.connectivity |
| P1_INVALID_GRAPH_RULE | 非法参数/图处理 | 已确认运行时`fail`且不得修边/取巨分量/重抽；冻结前只按预注册确定性候选seed序列筛选并保存失败attempt，见`D-2026-07-29-07`、`DR-P1-069` | 用户+实现+方法会审 | Phase 4 前 | network.on_invalid |
| P1_NETWORK_LIBRARY_VERSION | 网络图库精确版本 | Phase 4B-4 mock实际记录`networkx==3.6.1`，但formal机器值保持`UNRESOLVED[P1_NETWORK_LIBRARY_VERSION]`，须经实现+方法会审冻结；mock候选不得反向升级为formal值 | 实现+方法会审 | formal graph freeze | network.library.version |
| P1_WS_BUILDER_ALGORITHM | WS精确构图器 | Phase 4B-4 mock实际记录`paper1.mock_networkx_watts_strogatz@1.0.0`并显式传入派生seed和`nx.Graph`；formal机器值保持`UNRESOLVED[P1_WS_BUILDER_ALGORITHM]` | 实现+方法会审 | formal graph freeze | network.ws.builder_algorithm |
| P1_SHADOW_BUILDER_ALGORITHM | shadow精确构图器 | Phase 4B-4 mock实际记录有界、连通、禁WS边的逐步双边交换候选；formal机器值保持`UNRESOLVED[P1_SHADOW_BUILDER_ALGORITHM]` | 实现+方法会审 | formal graph freeze | network.shadow.builder_algorithm |
| P1_SHADOW_MAX_ATTEMPTS | shadow最大构图attempt数 | Phase 4B-4 mock可显式使用候选预算，但formal机器值保持`UNRESOLVED[P1_SHADOW_MAX_ATTEMPTS]`且预算耗尽fail closed | 实现+方法会审 | formal graph freeze | network.shadow.max_attempts |
| P1_SHADOW_TRIAL_BUDGET_PER_EDGE | shadow每条禁边trial预算 | Phase 4B-4 mock可显式使用候选预算，但formal机器值保持`UNRESOLVED[P1_SHADOW_TRIAL_BUDGET_PER_EDGE]`且不得运行中放宽 | 实现+方法会审 | formal graph freeze | network.shadow.trial_budget_per_edge |
| P1_STRUCTURE_GATE_ALGORITHM_VERSION | D-07纯结构gate算法版本 | relative clustering、relative path与small-world系数的精确计算合同须在formal graph freeze冻结；当前draft保持`UNRESOLVED[P1_STRUCTURE_GATE_ALGORITHM_VERSION]` | 实现+方法会审 | formal graph freeze | network.structure_gate.algorithm_version |
| P1_RING_LATTICE_BASELINE_ALGORITHM | 规则环格结构baseline算法 | 同N且与WS一致k的规则环格只读结构，不读意见；精确算法在formal graph freeze前保持`UNRESOLVED[P1_RING_LATTICE_BASELINE_ALGORITHM]` | 实现+方法会审 | formal graph freeze | network.structure_gate.ring_lattice_algorithm |
| P1_RANDOM_GRAPH_NULL_ALGORITHM | 同规模随机图null算法 | 随机null须与WS同N、同边数、独立RNG且断连按冻结规则fail closed；精确算法保持`UNRESOLVED[P1_RANDOM_GRAPH_NULL_ALGORITHM]` | 实现+方法会审 | formal graph freeze | network.structure_gate.random_null_algorithm |
| P1_RANDOM_GRAPH_NULL_REPLICATES | 同规模随机图null重复数 | 精确重复数影响结构baseline，必须formal冻结；当前draft保持`UNRESOLVED[P1_RANDOM_GRAPH_NULL_REPLICATES]`，不得用mock候选冒充研究默认 | 实现+方法会审 | formal graph freeze | network.structure_gate.random_null_replicates |
| P1_ACTIVATION_MODE | 激活方式 | 已确认固定WS上的异质加权随机顺序激活；事件严格串行读取前一成功提交状态，失败事件不得改变状态或游标，恢复时重放同一事件；当前schema枚举不兼容，正式修订前继续fail closed，见`D-2026-07-29-08`、`D-2026-07-29-18`、`DR-P1-071`、`DR-P1-087` | 用户+方法会审 | Phase 4 前 | dynamics.activation_mode |
| P1_ACTIVATION_COUNT | 每轮激活数 | 已确认T=50 sweeps、每sweep当前N次有放回事件；正式N=1000即每run 50,000事件，见`D-2026-07-29-08`、`DR-P1-072` | 方法会审 | Phase 4 前 | dynamics.activation_count |
| P1_ACTIVITY_WEIGHT_DISTRIBUTION | 长期活跃权重分布 | 已确认主模型为正截断对数正态并归一化`sum(w_i)=N`；截断Pareto为重尾敏感性、等权为机制基线；精确参数待Phase 0冻结，见`D-2026-07-29-12`、`DR-P1-081` | 用户+方法会审 | Phase 0 前 | dynamics.activity_weights.parameters |
| P1_ACTIVITY_CALIBRATION_TARGETS | 活跃过程校准目标 | 已确认按权重/实现激活Gini、top 1%/10%份额、最大个体份额、有限T零激活比例、跨sweep波动和跨N稳定性做非结果导向校准；目标区间/容差/算法待冻结，见`D-2026-07-29-12`、`DR-P1-081` | 方法+成本会审 | Phase 0 前 | dynamics.activity_weights.calibration_targets |
| P1_PRIVATE_UPDATE_SEMANTICS | 私人更新与公开表达关系 | 已确认每次激活先更新私人状态，是否替换最近公开帖子由预生成`publish_flag`决定；社会曝光只读公开帖子，见`D-2026-07-29-09`、`DR-P1-078` | 用户+方法会审 | Phase 4 前 | state_model.private_update_semantics |
| P1_PUBLISH_PROCESS | 公开表达过程 | 已确认hurdle–Beta结构：潜水者后续q=0，非潜水者q来自Beta；精确潜水比例/Beta参数待校准，见`D-2026-07-29-11`、`DR-P1-080` | 用户+方法会审 | Phase 0 前 | expression.publish_process.parameters |
| P1_ATTENTION_EXPRESSION_CORRELATION | 注意与表达倾向关系 | 已确认主模型独立；正相关为预注册敏感性，具体构造/强度待冻结，见`D-2026-07-29-11`、`DR-P1-080` | 用户+方法会审 | Phase 0 前 | expression.attention_expression_correlation.main, expression.attention_expression_correlation.sensitivity |
| P1_PRIVATE_PUBLIC_OUTCOME_PRIORITY | 私人/公开分布的分析排序 | 已确认私人状态为唯一primary；公开存量、公开流量和表达偏差为强制预注册secondary，见`D-2026-07-29-10`、`DR-P1-079` | 用户+统计会审 | Phase 0 前 | analysis.outcome_priority |
| P1_MAX_NEIGHBORS | feed消息容量B（稳定旧ID，非邻居/来源数量） | 已确认有限未读feed及Phase 0候选程序：主候选B=6、挑战`{4,6,8}`；B限制消息条数且允许同一发送者多帖，不限制邻居/来源数。精确B与制品hash须在Phase 0B冻结；Phase 4B将schema路径迁移为`exposure.feed_message_capacity`并保留旧ID作provenance，见`D-2026-07-29-14`、`D-2026-07-29-19`、`DR-P1-083`、`DR-P1-088` | 方法+成本会审 | Phase 0B 结束 | exposure.feed_message_capacity |
| P1_MEMORY_WINDOW | 私人更新记忆窗口K | 已确认模型只见最近K次成功私人更新，主候选K=3、挑战`{1,3,5}`；round-0不永久保留且不使用LLM摘要，完整历史只进入证据链；精确K与制品hash须在Phase 0B冻结，见`D-2026-07-29-17`、`DR-P1-086` | 用户+方法会审 | Phase 0B 结束 | memory.window |
| P1_SOCIAL_EXPOSURE_COUNT | 社会消息数 | 已确认E1固定shadow graph、E2原WS；首激活可读取邻居round-0公开帖，之后只读游标后最新至多B条；允许同一发送者多帖，不足不回填、超量过期、空feed显式记录，见`D-2026-07-29-13`至`15`、`D-2026-07-29-19`、`DR-P1-082`至`DR-P1-084`、`DR-P1-088` | 方法会审 | Phase 4 前 | exposure.social_count |

## 模型、API 与运行时

| ID | 问题 | 候选 / 推荐 | 决策者 | 最迟 gate | Schema paths |
|---|---|---|---|---|---|
| P1_MODEL_REVISION | Qwen3-8B 权重 revision | 候选 `b968826d9c46dd6066d109eabc6255188de91218`；artifact/runtime smoke 后固定 | 用户+运行时会审 | Phase 0B 结束 | model.revision |
| P1_VLLM_VERSION | vLLM 版本/镜像 | 候选 `0.23.0`；runtime smoke 后固定版本与镜像 digest | 运行时会审 | adapter 实现前 | runtime.vllm.version |
| P1_TEMPERATURE | temperature | Phase 0 候选；主矩阵固定 | 用户+方法会审 | Phase 0A 前 | generation.temperature |
| P1_TOP_P | top_p | Phase 0 候选；须验证实际传递 | 用户+方法会审 | Phase 0A 前 | generation.top_p |
| P1_MAX_TOKENS | max tokens | 按结构化理由长度校准 | 方法+成本会审 | Phase 0B 前 | generation.max_tokens |
| P1_REQUEST_SEED | 模型采样 seed | vLLM 支持性实测；不支持则标记非确定 | 运行时会审 | adapter 实现前 | generation.seed |
| P1_MODEL_SEED_PAIRING | 模型采样seed的cell/attempt配对语义 | 明确决定是否在同matched seed的12 cells按event ordinal配对模型采样seed，以及同一event重试是否复用seed；未冻结前实现必须fail closed，不得隐式继承旧`round+agent`键 | 用户+方法+运行时会审 | adapter 实现前 | generation.seed_pairing |
| P1_TIMEOUT_RETRY | timeout/retry | 已确认失败事件不提交私人状态、公开帖、游标或RNG进度；重试与恢复必须保持相同event identity和预生成输入。精确timeout、错误分类、次数与Retry-After仍待运行时冻结，见`D-2026-07-29-18`、`DR-P1-087` | 运行时会审 | adapter 实现前 | runtime.timeout, runtime.retry |
| P1_CONCURRENCY_BUDGET | 并发/显存/速率预算 | 由真实 benchmark 冻结 | 运行时+成本会审 | Phase 0B 结束 | runtime.concurrency, runtime.rate_budget |
| P1_API_PROVIDER | API 稳健性提供方 | DashScope/其他；推荐固定 snapshot 可用者 | 用户+方法会审 | 稳健性预注册前 | robustness.api.provider |
| P1_API_SNAPSHOT | API 精确 snapshot | 禁止 rolling alias | 用户+运行时会审 | 稳健性预注册前 | robustness.api.model_snapshot |
| P1_API_ROBUSTNESS_CELLS | API 稳健性 cells | 从12个 canonical cell IDs 中审批1至12个不重复 cells；推荐核心8 cells 为 `P1-I0-C0-E1/E2`、`P1-I0-C1-E1/E2`、`P1-I1-C0-E1/E2`、`P1-I1-C1-E1/E2`，即全部 identity×continuity 下的 shuffled 与 WS | 用户+方法会审 | 稳健性预注册前 | robustness.api.cells |
| P1_API_ROBUSTNESS_SCALE_FREEZE | API 子集最终 N/T/seeds | 暂拟 N=200/T=50/5 matched seeds；不定义 cells | 用户+成本会审 | 稳健性预注册前 | robustness.api.scale |

## 规模与运行 gates

| ID | 问题 | 候选 / 推荐 | 决策者 | 最迟 gate | Schema paths |
|---|---|---|---|---|---|
| P1_SCALE_GATE_DESIGN | N=200/500/1000 的 cells/seeds | primary contrast cells；matched seeds | 用户+方法会审 | Phase 9 前 | gates.scale.design |
| P1_GATE_PRIMARY_OUTCOME_STABILITY | 新primary outcome稳定容差 | 在`P1_PRIMARY_OUTCOME`冻结后，为其四persona等权`WS-shadow`主对比预注册绝对/相对容差，见`D-2026-07-29-20` | 方法会审 | Phase 9 前 | gates.scale.primary_outcome_tolerance |
| P1_GATE_DELTA_STABILITY | 候选组际结构ΔS稳定容差 | 旧primary gate已由`P1_GATE_PRIMARY_OUTCOME_STABILITY`取代；若保留，只作candidate/secondary诊断，不得控制主实验准入 | 方法会审 | Phase 9 前 | gates.scale.group_structure_delta_tolerance |
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
