---
status: approved implementation plan; executing; Phase 4B-0 through 4B-6 complete / independently reviewed; Phase 4B-7 review repairs implemented / pending independent re-review
authority: Phase 4B implementation sequence
date: 2026-07-29
inputs:
  - docs/superpowers/specs/2026-07-29-paper1-phase4a-completion-design.md
  - docs/superpowers/specs/2026-07-29-paper1-phase4a1-methodological-reframing-design.md
  - docs/paper1-protocol.md
  - docs/research-qa.md
supersedes: Phase 4 and later implementation steps in the 2026-07-14 platform implementation plan
does-not-freeze: unresolved research parameters, formal protocol values, model/runtime versions or analysis thresholds
---

# Paper 1 Phase 4B 实施计划

## 1. 目标与完成边界

Phase 4B把现有“协议验证与证据记录地基”升级为一个**可用mock完整运行、可恢复、
可审计，但仍禁止formal run**的Paper 1实验平台。

本阶段完成时应具备：

- 与Phase 4A事件语义一致的schema、draft YAML、人类协议摘要和domain records；
- 版本化topic/persona/population/initialization/network/schedule制品；
- 非公开Agent状态、公开帖子、feed游标、有限未读曝光和自身记忆；
- mock adapter、严格串行事件引擎、事务存储、checkpoint与同事件恢复；
- N=20/100/1000 mock确定性与不变量测试；
- 新primary estimand/outcome层级及过程诊断接口；
- 全部未决研究值继续以`UNRESOLVED[...]`阻断formal run。

Phase 4B不包括：

- 获取或冻结正式CFPS/NBS/CNNIC数据文件；
- 冻结三议题中的最终主议题、B/K、注意/表达精确参数或primary endpoint；
- 真实Qwen/vLLM调用、API稳健性或云端正式运行；
- N=1000真实模型矩阵；
- 真人、真实平台、动态重连、推荐算法或跨模型主矩阵；
- 把mock fixture常量提升为正式研究参数。

## 2. Phase 0：文档发现结论

### 2.1 当前允许复用的真实API

以下API已经存在，可继续保持或按明确迁移规则升级：

- `load_protocol(path)`、`validate_protocol(...)`：
  `platform/src/agent_ex/protocol.py:104,398`；
- `execution_projection(protocol)`、`canonical_protocol_hash(protocol)`：
  `platform/src/agent_ex/protocol.py:448,455`；
- `render_human_protocol_summary(...)`、
  `update_human_protocol_summary(...)`和`validate_human_protocol_sync(...)`：
  `platform/src/agent_ex/validation.py:71-104`；
- `canonical_payload_hash(...)`及深不可变JSON payload模式：
  `platform/src/agent_ex/domain.py:98-169`；
- `GenerationAttempt`的状态、请求/响应、usage和hash合同：
  `platform/src/agent_ex/domain.py:352-535`；
- 显式`to_payload/from_payload`版本合同：
  `platform/src/agent_ex/domain.py:636-694,1005-1120`；
- formal fail-closed、decision provenance和schema镜像测试模式：
  `platform/tests/test_protocol.py:273-999`。

### 2.2 当前不存在的API

仓库中不存在可直接调用的Population、TopicPackage、Persona、Network、Feed、Memory、
Adapter、EventStore、CheckpointStore或Engine。旧计划中的`PopulationFactory.create`、
`PersonaPolicy.render`、`NetworkFactory.ws`和`ExposurePlanner.plan`只是文档示意，
不是现有代码。

因此后续阶段必须明确“创建新接口”，不能假装调用已有实现。

### 2.3 当前必须先修的结构冲突

- `derive_event_id(run_id, round_index, agent_id)`无法表示同一Agent同一sweep多次激活：
  `domain.py:213-225`；
- `FrozenSchedule`按`(round_index, agent_id)`去重：
  `domain.py:636-649`；
- `AgentState`要求历史round严格递增：
  `domain.py:266-306`；
- `ExposureRecord`禁止同一发送者多帖且拒绝空社会feed：
  `domain.py:310-337`；
- evidence graph要求社会来源恰好来自上一轮：
  `domain.py:1217-1230`；
- recovery cursor仍是`{round_index,event_index}`，没有事件链或状态内容：
  `domain.py:906-929`；
- schema仍固定同步更新、旧primary outcome/estimand和旧scale gate：
  `platform/protocols/paper1.schema.json:130-177,221-226`。

### 2.4 当前验证基线

使用旧Phase 3A Python 3.12.13环境进行只读基线验证：

- `342 passed, 11 failed`；
- Ruff check通过；
- Ruff format check通过。

11项失败均来自已批准文档/研究问答与尚未迁移schema之间的已知不一致，包括新
primary ID、group-structure路径、feed容量路径和新scale gate。Phase 4B第一个代码
工作包必须恢复全绿，不能在红色协议基线上叠加engine。

本机默认Python为3.14.3且没有pytest/ruff；执行Phase 4B前必须建立项目本地、可移植的
Python 3.12环境。不得把旧worktree虚拟环境路径写入脚本或文档。

## 3. 总体架构与提交顺序

```text
协议/schema断代
    ↓
event-ordinal领域记录与artifact/RNG基础
    ↓
topic + population + initialization + persona
    ↓
WS/shadow网络 + attention/expression + frozen schedule
    ↓
private/public状态 + feed + memory + prompt view
    ↓
mock adapter + SQLite事务存储 + 严格串行engine
    ↓
checkpoint/recovery + N=20/100/1000整体验证
```

建议每个阶段独立提交。任何阶段红灯都不进入下一阶段。

## 4. Phase 4B-0：可移植开发环境与基线护栏

### 实现内容

1. 使用Python 3.12创建`platform/.venv`，从`requirements-dev.lock`安装锁定依赖。
2. 记录标准命令：

   ```powershell
   .\.venv\Scripts\python.exe -m pytest -q
   .\.venv\Scripts\python.exe -m ruff check .
   .\.venv\Scripts\python.exe -m ruff format --check .
   ```

3. 在`platform/tests/`保留当前11个预期RED作为Phase 4B-1迁移输入，不使用
   `xfail`、skip或删测试制造绿色。
4. 将Phase 4A.1状态改为用户已书面确认，并在进度日志记录基线失败原因。

### 参考

- Python边界：`platform/pyproject.toml:9`；
- 依赖锁：`platform/requirements-dev.lock`；
- 安装来源测试：`platform/tests/test_installation.py:17-155`。

### 验证

- `python --version`必须为3.12.x；
- `pip check`通过；
- pytest确切复现已知协议漂移失败，不出现导入或依赖失败；
- `.venv/`和`.pytest-tmp/`不进入Git。

### 反模式

- 不复用旧worktree虚拟环境作为正式入口；
- 不放宽`requires-python`到3.14；
- 不通过跳过formal测试掩盖schema漂移。

## 5. Phase 4B-1：协议、schema与分析层级断代迁移

### RED测试

先在`platform/tests/test_protocol.py`新增或改写测试，要求：

- primary estimand常量为
  `P1_PRIMARY_WS_SHADOW_AVERAGE_EFFECT`；
- primary outcome保持`UNRESOLVED[P1_PRIMARY_OUTCOME]`；
- continuity DiD登记为关键secondary；
- `outcomes.group_structure`保存旧`Δlog(B/W)`、T*和epsilon；
- `gates.scale.primary_outcome_tolerance`使用
  `P1_GATE_PRIMARY_OUTCOME_STABILITY`；
- 旧`P1_GATE_DELTA_STABILITY`只绑定
  `gates.scale.group_structure_delta_tolerance`；
- `dynamics.activation_mode`支持且只接受已批准的严格串行、有放回加权语义；
- `exposure.feed_message_capacity`继续以稳定旧ID
  `P1_MAX_NEIGHBORS`记录provenance；
- 两份schema字节一致；
- draft允许注册的`UNRESOLVED[...]`，formal继续拒绝。

### 实现内容

同步修改：

- `platform/protocols/paper1.schema.json`；
- `platform/src/agent_ex/schemas/paper1.schema.json`；
- `platform/configs/paper1/protocol.yaml`；
- `platform/tests/test_protocol.py`；
- `platform/tests/test_installation.py`；
- 必要时修改`platform/src/agent_ex/validation.py`中的summary projection。

新增/迁移的schema块至少包括：

- primary/secondary/exploratory分析层级；
- group-structure候选指标；
- attention weight、expression propensity、publish process；
- private/public状态语义；
- event-ordinal激活语义；
- feed容量、cursor、memory window；
- process diagnostics、术语映射和robustness标签；
- 新旧scale gate各自的稳定ID与路径。

使用`update_human_protocol_summary(...)`从draft YAML重新生成
`docs/paper1-protocol.md`页首摘要，不手工编辑生成区。

### 参考

- packaged canonical schema加载：`protocol.py:91-101`；
- 附加schema不得放宽canonical schema：`protocol.py:383-427`；
- summary生成：`validation.py:43-104`；
- schema/QA精确路径测试：`test_protocol.py:182-234,526-530`；
- Phase 4A.1迁移要求：
  `docs/superpowers/specs/2026-07-29-paper1-phase4a1-methodological-reframing-design.md:227-246`。

### 验证

- `test_protocol.py`和`test_installation.py`全绿；
- schema镜像SHA-256完全一致；
- 人类协议generated summary与draft YAML一致；
- draft config仍因未决字段不能进入formal；
- 全套测试恢复全绿后才进入4B-2。

### 反模式

- 不静默改变稳定旧ID语义；
- 不手改generated summary；
- 不把B=6、K=3或任何fixture值填入formal字段；
- 不在schema override中绕过packaged canonical schema。

## 6. Phase 4B-2：event ordinal、领域记录v2与artifact/RNG基础

**状态（2026-08-01）：** complete / independently reviewed。独立规格/反模式审查与
代码质量复审均为`APPROVED`；最终fresh全套为`194 passed`，独立全量覆盖率为`85%`
（1245 statements / 187 missed）。在Phase 4B-2收口时，Phase 4B-3尚未开始。

### RED测试

在`platform/tests/test_domain.py`先增加：

- 同一Agent同一sweep可出现多次且event ID不同；
- `event_ordinal`从0连续到`N×T-1`，不可重复或缺口；
- `derive_event_id(run_id, event_ordinal)`稳定且不读取agent/sweep；
- schedule v2 JSON round-trip与v1明确拒绝/迁移错误；
- recovery cursor只保存`next_event_ordinal`和当前event identity；
- main-path complete要求所有预期event均`succeeded`；
- `excluded`只属于分析标记；imputed/fallback不得进入Paper 1主状态链。

### 实现内容

修改`platform/src/agent_ex/domain.py`：

- `derive_event_id(run_id, event_ordinal)`；
- `ScheduleSlot(event_ordinal, sweep_index, draw_index, agent_id, publish_flag)`；
- `FrozenSchedule`v2；
- `GenerationEvent`以ordinal为身份、sweep/agent为属性；
- `RunManifest`以连续event前缀和`next_event_ordinal`表达进度；
- `validate_evidence_graph`按ordinal因果先后校验，不再要求“恰好上一轮”；
- formal Paper 1完整性要求全部succeeded。

创建`platform/src/agent_ex/artifacts.py`：

- `ArtifactEnvelope`：stable ID、schema version、algorithm version、input hashes、
  output hash和RNG provenance；
- 显式`to_payload/from_payload`；
- artifact内容与envelope hash绑定。

创建`platform/src/agent_ex/rng.py`：

- 统一namespace注册；
- 从`matched_seed × namespace × coordinates`确定性派生局部seed；
- 事件级namespace必须包含`event_ordinal`；
- 禁止共享可变全局RNG。

需要登记但不得伪造数值的新工程ID应先进入`docs/research-qa.md`，例如网络库/构图器
版本、artifact schema版本和存储格式版本。

### 参考

- canonical hash与freeze模式：`domain.py:98-169`；
- artifact round-trip模式：`domain.py:636-694`；
- evidence graph唯一索引框架：`domain.py:1148-1306`；
- Phase 4A event/RNG合同：completion spec `:132-161,215-250`。

### 验证

- domain测试全绿；
- fixture N=1000、T=50可构造50,000个轻量schedule slots；
- 同一Agent同一sweep重复激活测试通过；
- 任意ordinal缺口、重复、伪造ID或未来来源均fail closed；
- `__init__.py`只导出经过测试的稳定公开类型。

### 反模式

- 不保留`round+agent`作为事件或RNG唯一键；
- 不用`event_index`冒充全局ordinal；
- 不为旧schedule提供会静默改变语义的兼容转换；
- 不让main engine产生excluded/imputed/fallback。

## 7. Phase 4B-3：topic、population、initialization与persona制品

**状态（2026-08-01）：** complete / independently reviewed。独立规格审查、反模式审查
与代码质量复审均为`APPROVED`；质量定向回归为`72 passed`，最终fresh全套为
`274 passed`且无skip/xfail，独立全量覆盖率为`86%`
（1817 statements / 257 missed）。schema、draft、formal与human-summary gate均通过；
mock fixture保持`mock_only / not_frozen`，未填补`UNRESOLVED[...]`。Phase 4B-4尚未开始。

### 新文件

- `platform/src/agent_ex/topic.py`
- `platform/src/agent_ex/population.py`
- `platform/src/agent_ex/initialization.py`
- `platform/src/agent_ex/persona.py`
- 对应`platform/tests/test_*.py`
- `platform/tests/fixtures/paper1/`下的明确mock制品

### 接口边界

创建经过测试的最小接口：

- `TopicPackage.from_payload(...)`与`to_payload()`；
- `trs_integerize(donors, weights, n, rng_seed)`；
- `build_population_artifact(...)`；
- `assign_initial_stances(...)`；
- `assign_initial_reasons(...)`；
- `render_persona(template_artifact, population_member, condition)`；
- `validate_persona_factor_diff(rendered_templates)`。

实际签名在RED测试中冻结，不能在实现中临时扩张。

### 实现要求

- topic package只承载议题制品，不把题干写进engine/network/feed；
- TRS输出恰好N，报告边际/联合误差、克隆、结构零和缺失；
- 每个matched seed独立人口，同seed 12 cells逐Agent复用；
- mock初始化严格产生`[50,100,200,300,200,100,50]`；
- population字段与初始立场受约束正交；
- round 0同时产生非公开初始状态和一条公开初始帖；
- persona由共同骨架确定性插入identity/continuity块；
- absent条件真省略，自动diff只允许已批准因素块变化；
- 所有制品使用`ArtifactEnvelope`和独立RNG namespace。

### 参考

- completion spec `:36-110`；
- TRS与matched seed依据：`DR-P1-085`；
- Persona边界：`DR-P1-061`至`065`；
- Phase3A不可变payload模式：`domain.py:98-169,636-694`。

### 验证

- N=20/100/1000 fixture均恰好N；
- 同seed跨12 cells的population、initial stance/reason完全一致；
- seed间人口重新抽样；
- 结构零、非法权重、不可实现约束、超容差均fail；
- persona四模板自动diff不出现额外文字；
- fixture文件名和metadata显式标记`mock_only`。

### 反模式

- 不下载或假装冻结正式CFPS数据；
- 不把fixture容差/标签提升为formal默认；
- 不由目标模型在正式run中自由生成round-0理由；
- 不用中性persona填充absent条件。

## 8. Phase 4B-4：WS/shadow网络与node mapping

**状态（2026-08-01）：** complete / independently reviewed。独立规格、反模式与代码质量
审查均为`APPROVED`；最终连续fresh全套为`318 passed in 31.25s`，coverage为
`318 passed in 97.43s`（`2237 statements / 323 missed / 86%`，`network.py`为`84%`）。
network专项`43 passed`，protocol/schema gates为`143 passed`。N=1000纯结构锚点及
population/round-0/WS三制品绑定的node mapping均通过独立复算。NetworkX、构图算法、预算、
结构gate规则及全部精确`P1_*`机器值仍为`UNRESOLVED[...]`；现有制品和hash仅为
`mock_only / not_frozen`工程证据，不构成formal freeze。Phase 4B-5尚未开始。

### 前置工程gate

在写网络实现前：

1. 在`docs/research-qa.md`登记精确图生成库/版本与构图器算法ID；
2. 选择并锁定一个NetworkX候选版本；
3. 只读取结构、连通与资源指标运行候选seed回归；
4. 记录决定与lock hash，不读取任何意见动力学结果。

### 新文件与接口

- `platform/src/agent_ex/network.py`
- `platform/tests/test_network.py`

创建：

- `build_ws_artifact(...)`
- `build_shadow_artifact(ws_artifact, ...)`
- `build_agent_node_mapping(...)`
- `validate_ws_artifact(...)`
- `validate_shadow_artifact(...)`

图生成与图验证必须分离。

### 实现要求

- WS无向、简单、全连通；
- shadow逐节点保持对应WS度数；
- shadow禁止自环、重边和任何真实WS边，并要求全连通；
- 同matched seed的E2 cells复用WS，E1 cells复用shadow；
- Agent—node mapping跨12 cells固定；
- 构图失败立即fail，不在run中修图或重抽；
- edge list、结构报告、input/output hash与RNG provenance完整保存。

### 参考

- completion spec `:111-130`；
- D-2026-07-29-07、13；
- NetworkX候选依据：`paper1-design-rationale.md:1621-1715,2373`。

### 验证

- 度序列逐节点完全相等；
- WS与shadow边集合不相交；
- 两图均简单、无向、全连通；
- 同seed确定性、不同seed可变；
- k/p非法、构图失败、hash漂移均fail closed；
- N=1000结构测试不调用LLM。

### 反模式

- 不只匹配平均度；
- 不按意见结果挑graph seed；
- 不逐sweep或逐event重抽shadow；
- 不把NetworkX默认行为当作未记录的研究参数。

## 9. Phase 4B-5：attention、expression与完整冻结schedule

**状态（2026-08-18）：** `complete / independently reviewed`。独立规格/反模式审查与
代码质量复审均为`APPROVED`，独立release verification为`PASS`。最终连续fresh全套为
`402 passed in 69.92s`；coverage为`402 passed in 204.17s`、
`2876 statements / 419 missed / 85%`（`schedule.py`为
`638 statements / 96 missed / 85%`），定向验证为`275 passed`。N=1000/T=50显式mock
构造耗时23.765秒，activation/publish JSON为4,110,564/5,132,825 bytes，ledger一次可信
验证为3.193秒、验证后单ordinal读取约47微秒。两份schema镜像SHA-256一致；draft中仍有
88个`UNRESOLVED[...]`，所有制品继续为`mock_only / not_frozen`，因此这些结果不构成
formal freeze。完成文档更新前的已验证代码/测试候选canonical snapshot为
`dc1b81a27919ec9e606c58342fb8771ba6e5ba962bf6c20006ba8f3168d6ea2c`，schema镜像为
`3db603ea0c8303a061838cd962db687a6d5ab616bacc78dd1876b007d7a5783e`；文档后release将生成
新的最终snapshot。Phase 4B-6尚未开始。

### 新文件

- `platform/src/agent_ex/schedule.py`
- `platform/tests/test_schedule.py`

### 创建接口

- `build_attention_artifact(...)`
- `build_expression_artifact(...)`
- `build_activation_schedule(...)`
- `build_publish_schedule(...)`
- `validate_matched_schedule_reuse(...)`

### 实现要求

- attention权重严格为正并归一化`sum(w_i)=N`；
- 支持截断对数正态、截断Pareto和`w_i=1`能力，但精确参数保持未决；
- expression hurdle与Beta倾向和attention独立生成；
- 每sweep有放回抽N次，生成连续全局event ordinal；
- publish flag预生成并绑定每个event；
- 同matched seed 12 cells复用attention、expression、activation和publish制品；
- RNG namespaces严格分开；
- schedule artifact不调用模型、不读取意见结果。

### 参考

- completion spec `:132-161`；
- D-2026-07-29-08、11、12、18；
- schedule v2基础：Phase 4B-2。

### 验证

- 每sweep恰好N个事件，总数N×T；
- 重复Agent合法；
- 权重归一化、潜水者和publish统计可审计；
- 同seed跨cell schedule hash一致；
- equal-weight基线仍使用严格串行事件；
- 任何精确参数未冻结时formal config继续失败。

### 反模式

- 不恢复同步更新；
- 不让attention和expression共用同一随机变量；
- 不按意见方向校准权重或发帖率；
- 不在运行中重新抽publish flag。

## 10. Phase 4B-6：private/public状态、有限未读feed与memory

**状态（2026-08-18）：** `complete / independently reviewed`。首轮及最终复审的来源重放、
selection重放、round-0证据、latest-public pointer、邻居集合规范化、末次成功attempt、
全candidate hash与累计日志性能缺口均已先RED后修复。独立规格/反模式与代码质量复审均为
`APPROVED`，release verification为`PASS`；最终连续fresh全套为
`459 passed in 68.59s`，coverage为`459 passed in 218.13s`、
`3922 statements / 566 missed / 86%`（feed 84%、memory 87%、state 88%、domain 81%）。
定向回归为121 passed，补充攻击套件为18 passed及2 passed，protocol/installation为
144 passed；N=1000/T=50增量调用形态为`1 passed in 12.99s`。Ruff/format/pip/diff及
schema/draft/formal/human-summary门禁通过。完成文档更新前的已验证候选canonical snapshot
SHA-256为`3563f328c7f749b423b7e8bb01aa99d7bf20ffe92d458c454f9f6a67ccf9fe36`；文档更新后
release会产生新snapshot。两份schema镜像SHA-256均为
`3db603ea0c8303a061838cd962db687a6d5ab616bacc78dd1876b007d7a5783e`。draft仍含88个
`UNRESOLVED[...]`，全部产物保持`mock_only / not_frozen`；B/K仍为调用者显式提供的mock
挑战输入而非formal冻结值。Phase 4B-7未开始。

### 新文件

- `platform/src/agent_ex/state.py`
- `platform/src/agent_ex/feed.py`
- `platform/src/agent_ex/memory.py`
- `platform/tests/test_state.py`
- `platform/tests/test_feed.py`
- `platform/tests/test_memory.py`

### 领域记录

创建并版本化：

- `PrivateState`与`PrivateUpdate`；
- `PublicPost`及latest-public pointer；
- `FeedCursor`；
- `FeedCandidate`、`ExposureSelection`与扩展后的`ExposureRecord`；
- `MemoryItem`与只读`MemoryView`。

### Feed算法

1. 从曝光图邻居中读取接收者cursor之后的新公开帖；
2. 首次激活允许round-0公开帖；
3. 超过B取事件序最新B条，其余标记expired；
4. 不足B不回填已读旧帖，空feed合法；
5. 同一发送者多帖合法；
6. cursor推进到候选扫描边界；
7. 入选后按独立slot RNG排列；
8. E1/E2复用slot位置seed而不复制内容。

Exposure证据必须记录候选、入选、过期、post/event/source ID、消息年龄、原始顺序、
显示槽位、渲染文本和hash。

### Memory算法

- 只取最近K次成功私人更新，不因是否公开而过滤；
- 每条含文字立场、理由、confidence和是否公开；
- 按旧到新排列；
- round 0不永久置顶；
- 不调用LLM摘要。

### 参考

- completion spec `:164-198`；
- D-2026-07-29-14、17；
- 方法过程诊断要求：Phase 4A.1 `:224-246`。

### 验证

- 空feed、同源多帖、同sweep前序公开帖均合法；
- future post、private泄漏、已读回填、cursor倒退均fail；
- B={4,6,8}、K={1,3,5}只作为mock挑战输入；
- 过程诊断可计算消息数、年龄、来源覆盖、重复来源、空feed和发送者活跃度；
- memory不受是否公开影响。

### 反模式

- 不把latest public stock当成唯一历史事件；
- 不把private reason暴露给其他Agent；
- 不强制social exposure非空；
- 不按立场、相似性、热度或LLM相关性排序。

## 11. Phase 4B-7：prompt view、parser与mock adapter

**状态（2026-08-18）：** `in_progress / review repairs implemented / pending independent
re-review`。已按严格TDD实现hash绑定的`PromptView`、只渲染授权内容的两消息视图、严格
`stance → confidence → public_reason`解析证据、provider-neutral adapter合同和确定性脚本
`MockAdapter`。Prompt输入由typed `GenerationEvent`绑定event/attempt上下文，并同时绑定
matched seed、canonical cell、topic、rendered persona、当前private state、最近K次memory、
ExposureRecord及模板版本；社会消息只使用4B-6已经冻结的display-slot顺序，不重新抽样。
parser不修补JSON、不强制类型转换、不填默认值，数字/未知立场、bool/nonfinite confidence、
空理由、重复/额外字段、代码围栏、尾随文本和`publish_flag`均作为带raw hash的失败证据返回。
adapter request只能从PromptView派生；response绑定event/attempt、request、script、显式mock
seed、mock model/runtime identity和全部hash，单次调用返回response或timeout，不实现retry、
状态提交、SQLite或真实模型。

前两轮独立审查发现的event/exposure跨域、截断memory、自洽persona注入、文本边界、request/
response自述、parser Unicode/depth及evidence重封装问题，已逐组先RED后GREEN修复。Prompt
现重放完整event、population/template/persona及successful history，所有自然文本作为单一
deterministic JSON data payload；request采用factory-sealed capability，response与parse
evidence均有trusted replay validator；反序列化view/response必须完整重放后重新签章；system
role固定且全部persona自然文本只进入user JSON；prompt/parser资源预算由调用者显式传入、
hash绑定并在复制/序列化前preflight。2026-08-27恢复后继续以RED→GREEN补齐typed
RunManifest、canonical cell、recovery cursor、当前及所有非round-0来源的冻结schedule slot/
同run成功前缀/final successful attempt重放。修复后prompt/parser/mock定向为52 passed，最终
连续fresh全套为`511 passed in 73.83s`；production-source coverage为
`511 passed in 234.59s`、`4898 statements / 710 missed / 86%`，新增
base/mock/parser/prompt分别为90%/87%/87%/80%。N=1000的PromptView+render工程基准为
8.9075秒。Ruff、format、pip与diff门禁已通过；两份schema继续保持相同
SHA-256 `3db603ea0c8303a061838cd962db687a6d5ab616bacc78dd1876b007d7a5783e`，draft仍有
88个`UNRESOLVED[...]`。全部新增记录保持`mock_only / not_frozen`；本阶段未调用网络、
vLLM/OpenAI、未读取研究结果、未冻结model seed pairing/timeout/retry或其他formal参数，
也未进入Phase 4B-8。实现完成不等于阶段关闭，须等待独立规格/反模式、代码质量和release
re-review与release verification。

最终review repairs继续按RED→GREEN修复三项边界：四cell现在使用完全相同的静态system
合同，I0/C0是真省略且C0仍接收相同memory，版本化可信控制布尔由cell与persona重放产生；
全部非round-0 own/social更新严格绑定final成功attempt的stance/confidence/public_reason；
raw manifest只在`ValidatedPromptRunContext`创建时验证/hash并预建schedule/event/attempt索引，
后续prompt不再复制或扫描完整prefix。seal仅是同进程完整性哨兵而非安全/授权边界。最新
focused为118 passed，fresh full为514 passed in 80.54s，production coverage为514 passed in
248.34s、4981 statements / 729 missed / 85%；N=1000 prompt+render为8.827秒，N=50000
context验证0.317秒且后续event membership为O(1)。protocol/install 144 passed，Ruff/format/
pip/diff、schema镜像与88个UNRESOLVED gate通过。状态仍为pending independent re-review，
未提交、未推送、未进入4B-8。

2026-08-27复审追加三项P1也已逐项RED→GREEN：`ValidatedPromptRunContext`改为对全部
可见语义字段及schedule/event/attempt索引做canonical摘要并使用closure-held HMAC完整性
哨兵，所有消费者按当前内容复验；`P1_MODEL_SEED_PAIRING`仍未决，因此domain graph与prompt
只校验/记录每次attempt的显式整数`model_seed`，不再擅自要求同event retries相等；prompt以
单次线性遍历重放全部candidate的typed `PublicPost`/`PrivateUpdate`，包括未被选择的过期
round-0内容。最终fresh full为522 passed in 75.45s；production coverage为522 passed in
232.90s、5004 statements / 728 missed / 85%，prompt覆盖81%；N=1000 prompt+render为
10.001秒，N=50000含content-bound sentinel的context验证0.903秒、三次lookup约3.1微秒。
状态继续为pending independent re-review；未提交、未推送、未进入4B-8。

2026-08-28最终2 P1 + 2 P2收尾替换了上述逐consumer全量HMAC复验：context创建时独立
typed replay `FrozenSchedule`、manifest、events与attempts，并把immutable snapshot登记到
`id + weakref exact owner` registry；consumer只做O(1) owner查找并只读snapshot，复制/
replace/跨cell句柄失败关闭，weakref清理防止陈旧entry与迟到callback污染ID复用。公共RNG
registry移除`model_sampling`，在`P1_MODEL_SEED_PAIRING`冻结前派生明确失败；attempt仍只记录
显式`model_seed`证据。parser在response seal/hash之前完成严格string、character和单次有界
UTF-8/byte gate，超限明确抛出fail-closed异常，普通malformed/depth证据合同不变。四项回归
先得到预期`4 failed`，最小GREEN后prompt/parser/mock/domain/feed focused为
`151 passed in 16.29s`。此前522/full/coverage数据仅属上一snapshot历史证据；当前snapshot待
独立复审后只运行一次最终full+coverage。未提交、未推送、未进入4B-8。

2026-08-28生命周期复审追加的3 P1 + 1 P2已按TDD修复。公共
`ValidatedPromptRunContext`现在只暴露不可嵌套篡改的scalar identity/metadata；完整schedule、
event、attempt及索引仅存在validator registry snapshot。新增
`advance_validated_prompt_run_context`以同一owner identity原子校验并追加连续成功event及其
failed-then-successful attempt chain，失败不推进cursor/prefix，成功仅做每event attempts数目的
工作；恢复时的初始event/attempt索引必须exact-cover manifest完整成功前缀，避免后续prompt
需要此前被省略的旧source；prompt同时绑定baseline manifest hash、logical context identity与当前增量prefix
commitment。每个prompt的source evidence exact-cover检查改为`len + expected-ID point lookup`，
不再遍历整张调用者map。parser在UTF-8编码前同时执行character与保守byte-count preflight，
随后只做一次受byte budget约束的严格编码。50,000-slot结构回归确认context创建后连续三次
advance不再重放schedule，且三个event使用不同显式`model_seed`仍合法，不冻结未决pairing。
随后新增两项恢复一致性RED，稳定得到`2 failed`：live advance与checkpoint恢复的prefix算法
不同，且恢复注册不绑定attempt内容。现已统一为稳定run/seed/cell/schedule genesis，再按ordinal
fold canonical event hash与ordered canonical attempt hashes；同一完整证据恢复得到相同logical
context ID与prefix hash，任一合法event/attempt内容漂移则改变prefix，但不规定model-seed
pairing。两项GREEN为`2 passed in 0.55s`，context focused为`15 passed in 1.44s`；当前prompt/
parser/mock/domain/feed focused为`159 passed in 18.42s`，Ruff/format通过；按收尾
策略未重复运行full/coverage，须待独立复审批准同一snapshot后各运行一次。未提交、未推送、
未进入4B-8。

并发一致性P2也已按确定性RED→GREEN收口：使用`threading.Event`协调而非sleep的回归先证明
prompt reader可把旧event cursor与advance后的新prefix混合，metadata也缺少统一原子版本捕获。
现由每个context自己的writer lock串行advance，完整校验后先追加新event/attempt键，最后一次
替换不可变`cursor + prefix`版本；metadata和每次prompt build只捕获一次该版本。旧版本reader
无法越过其cursor访问新增索引，且无需逐prompt/advance复制prefix，也不持有全局跨run长锁。
两项新增GREEN为`2 passed in 0.61s`，context focused为`17 passed in 1.41s`，扩展focused为
`161 passed in 18.74s`；Ruff check、format check和diff check通过。未跑full/coverage，未提交、
未推送、未进入4B-8。

### 新文件

- `platform/src/agent_ex/prompt.py`
- `platform/src/agent_ex/parser.py`
- `platform/src/agent_ex/adapters/base.py`
- `platform/src/agent_ex/adapters/mock.py`
- 对应测试文件。

### 创建接口

- `build_prompt_view(topic, persona, memory, exposure)`;
- `render_messages(prompt_view)`;
- `parse_agent_update(raw_response)`;
- `ModelAdapter.generate(request) -> AdapterResponse`;
- `MockAdapter`的脚本化成功、格式失败、timeout和重试响应。

这里的`ModelAdapter`是Phase 4B新建接口，不得声称当前已有。

### 实现要求

- 每次event只对应一次主生成调用；
- 固定JSON输出包含stance、reason、confidence；
- parser最多一次格式重试的策略仍由后续runtime gate注入；
- attempt保留rendered messages、raw response、parsed result和全部hash；
- mock响应由event ID/fixture脚本确定，不读取cell结果；
- 真实vLLM/OpenAI-compatible adapter留到Phase 0B。

### 参考

- `GenerationAttempt`证据合同：`domain.py:352-535`；
- topic/persona/feed/memory payload限制：completion spec `:36-64,98-110,164-198`；
- adapter实现前未决项：`docs/research-qa.md:68-84`。

### 验证

- 正常、拒答、非法JSON、越界分数、空理由、重试耗尽均覆盖；
- 同event重试保持request/exposure/model-seed语义；
- mock adapter不需要网络；
- prompt中不存在private-state泄漏、数字邻居分数或条件标签。

### 反模式

- 不直接依赖某个vLLM客户端的假想方法；
- 不在parser中修补实质内容；
- 不用第二模型总结memory；
- 不把mock确定性解释为真实模型确定性。

## 12. Phase 4B-8：SQLite事务存储、严格串行engine与checkpoint

### 存储选择

每个run使用独立SQLite数据库作为执行期事务存储，使用Python标准库`sqlite3`：

- schedule/artifact只读绑定；
- attempt append-only；
- event成功、private update、可选public post、cursor和事件链头在一个事务中提交；
- 原始大响应可外置文件/对象存储，数据库只保存URI与hash；
- 完成后导出不可变manifest和证据索引。

选择SQLite是因为单run严格串行、不需要多写者，同时需要原子提交和崩溃恢复。
若云端文件系统不支持安全本地WAL，则运行目录必须放本地scratch，完成后再归档；
不得把数据库放Git。

### 新文件

- `platform/src/agent_ex/storage.py`
- `platform/src/agent_ex/checkpoint.py`
- `platform/src/agent_ex/engine.py`
- `platform/tests/test_storage.py`
- `platform/tests/test_checkpoint.py`
- `platform/tests/test_engine.py`

### Engine事件流程

1. 校验下一个`event_ordinal`及schedule hash；
2. 从最后成功提交读取private/public/cursor状态；
3. 构建feed、memory和prompt；
4. 记录pending/in-progress attempt；
5. 调用adapter并解析；
6. 失败则append attempt，但不修改任何研究状态；
7. 成功则在单一事务中提交private update；
8. 读取预生成publish flag，必要时追加public post并更新latest pointer；
9. 提交cursor、event chain hash、event和manifest进度；
10. 进入下一个ordinal。

单run不提供并发commit入口；并行只能发生在run/cell调度层。

### Checkpoint

checkpoint至少绑定：

- protocol/run/schedule/artifact hashes；
- `next_event_ordinal`和当前event ID；
- 全部private/public/cursor状态hash；
- event chain head；
- 当前event的attempt前缀；
- manifest hash和存储schema版本。

恢复时先验证连续、无缺口、全部succeeded的前缀；若当前event只有failed attempts，
仍以相同event ID和冻结输入继续下一attempt。hash或前缀不一致立即停止。

### 参考

- 现有manifest外部artifact绑定：`domain.py:698-1120`；
- 现有attempt合同：`domain.py:352-535`；
- Phase 4A失败/恢复：completion spec `:201-214`；
- `docs/reproducibility.md:70-73`。

### 验证

- 故障注入覆盖：调用前、响应后解析前、private提交中、public提交中、checkpoint写入中；
- 每种失败恢复后与不间断run得到相同最终hash；
- failed attempt不推进cursor/private/public/publish/RNG；
- 重试耗尽后run停在同一event并保持可恢复；
- SQLite事务回滚后无半提交；
- main-path complete只接受所有预期event succeeded。

### 反模式

- 不把manifest中的URI/hash字段当作已实现checkpoint；
- 不跨shell或用临时脚本拼接删除/移动结果目录；
- 不跳过、插补或fallback；
- 不在单run内并发写入。

## 13. Phase 4B-9：整合mock矩阵、规模测试与文档交付

### 整合fixtures

提供三档明确`mock_only`配置：

- N=20：快速单元/故障矩阵；
- N=100：完整12-cell集成；
- N=1000：不调用真实模型的确定性、复杂度、存储和恢复测试。

T可在快速测试中缩小，但正式规模fixture必须能生成N=1000、T=50的schedule和制品；
不得运行600万次真实生成。

### 跨cell不变量

同matched seed验证：

- population、initial stance/reason逐Agent一致；
- Agent—node mapping一致；
- E1/E2分别复用shadow/WS图；
- attention/expression/activation/publish schedule一致；
- 只有协议允许的persona因素块、exposure图和由其产生的状态链不同。

### 分析与过程接口

输出但不选择结果：

- private state和public stock/flow快照；
- 实际消息数、年龄、来源覆盖、重复来源、空feed和发送者活跃度；
- round-0基线和相对变化；
- primary/secondary/exploratory标签；
- 术语映射与model/prompt/topic/robustness provenance。

该阶段只验证能计算和追溯，不读取极化方向、显著性或“哪个议题更有趣”。

### 文档

更新：

- `docs/paper1-protocol.md`
- `docs/reproducibility.md`
- `docs/project-overview.md`
- `logs/<date>-phase4b-handoff.md`
- `task_plan.md`、`progress.md`、`findings.md`

### 最终验证

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest --cov=agent_ex --cov-report=term-missing
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

另需验证：

- 两份schema字节一致；
- generated human summary同步；
- draft config可验证，formal config因未决项失败；
- wheel隔离安装与formal fail-closed smoke通过；
- N=1000/T=50 schedule为50,000个连续ordinal；
- N=20/100/1000 mock恢复前后最终hash一致；
- Git不包含原始大结果、SQLite数据库、checkpoint、缓存或`.codex/`。

## 14. Phase 4B完成定义

只有同时满足以下条件才标记Phase 4B完成：

1. 全套测试、Ruff、format、pip check和diff check通过；
2. schema、YAML、人类协议和research-QA路径一致；
3. 旧同步/round+agent/previous-round曝光语义已从formal路径清除；
4. mock 12-cell可以严格串行运行并原位恢复；
5. private/public/feed/memory全链路可追溯；
6. 所有artifact含版本、hash和RNG provenance；
7. formal run仍因未冻结研究参数失败关闭；
8. 没有真实模型调用、正式结果选择或大结果入Git；
9. 新增公开API在`__init__.py`有导入测试；
10. 形成换机/上云可恢复的Phase 4B handoff。

## 15. 后续阶段

Phase 4B完成后才进入：

- Phase 0A：议题、量表、persona与理由库probe；
- Phase 0B：模型revision、NetworkX/运行时、B/K、注意/表达和吞吐校准；
- 真实Qwen N=20/50/100 smoke；
- N=200/500/1000有限规模gate；
- N=1000、T=50正式12-cell实验。

执行Phase 4B时应使用`do`/subagent-driven workflow，并按阶段4B-0至4B-9逐项提交；
不得一次性重写全部`domain.py`后再补测试。
