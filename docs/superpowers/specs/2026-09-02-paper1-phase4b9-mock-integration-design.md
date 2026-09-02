---
status: approved implementation design; independently reviewed with no P0-P3 on 2026-09-02
authority: Phase 4B-9 engineering design; subordinate to frozen protocol, 2026-07-29 Phase 4A completion design, and approved 2026-07-29 Phase 4B plan
date: 2026-09-02
---

# Paper 1 Phase 4B-9｜Mock矩阵整合、规模门禁与交接设计

## 1. 目的与完成边界

Phase 4B-9把已经独立实现的population、initialization、persona、network、schedule、
private/public/feed/memory、prompt/parser/mock adapter、v6 storage、strict lifecycle engine和
checkpoint/recovery组合成可重复的mock-only矩阵。它证明平台能够在不连接真实模型的前提下
机械生成12个canonical cells、严格串行执行、重开恢复、审计跨cell复用边界并输出不含结果
选择的过程证据。

本阶段不冻结任何仍为`UNRESOLVED[...]`的研究或运行参数，不接入Qwen/vLLM，不执行真实
API，不产生论文结果，也不把N=200/500/1000有限规模gate或正式N=1000/T=50/10 matched
seeds主实验提前塞入Phase 4B。Phase 4B-9通过后，代码达到“进入Phase 0A/0B前的平台
工程就绪边界”，不等于“正式实验参数已经冻结”或“可以直接启动主实验”。

## 2. 约束来源

本设计细化已整包批准的`D-2026-07-29-21`和
`docs/superpowers/plans/2026-07-29-paper1-phase4b-implementation-plan.md`第13–14节，
不重新决定研究设计。以下边界不可更改：

- canonical matrix固定为`identity 2 × continuity 2 × exposure 3 = 12 cells`；
- 每个run严格串行事件提交；失败不得推进private/public/cursor/RNG progress；
- 同matched seed跨12 cells复用population、initial stance/reason、Agent—node mapping、
  attention/expression、activation/publish schedule；
- E0不读社会feed，E1使用固定shadow graph，E2使用固定WS graph；
- `private_state`唯一primary，`public_stock`、`public_flow`、`expression_gap`为预注册
  required secondary，但`expression_gap`精确距离仍未冻结；
- B、K、timeout、retry limit、model seed pairing、checkpoint cadence及正式性能阈值没有
  coder default；
- formal config只要含未决值就继续fail closed；
- 所有新增fixture、run和报告必须明确`mock_only / not_frozen`；
- 原始SQLite、checkpoint、模型响应与大规模输出不进入Git。

## 3. 架构选择

采用“薄矩阵编排 + 已有单事件pipeline + 只读审计”三层结构。

### 3.1 `mock_matrix.py`：矩阵与规模制品

该模块只负责构造和验证mock运行计划，不执行事件：

- `MockScaleCase`从显式artifact payload读取`N`、`T`、用途和执行模式；所有字段必填，
  没有默认值；
- `MockCellBinding`把canonical cell ID机械拆为identity、continuity和exposure，并绑定
  population/initialization/persona/WS/shadow/mapping/schedule的typed artifact IDs/hashes；
- `MockMatchedSeedMatrix`包含同一matched seed的恰好12个cell bindings，并以canonical
  cell顺序固定序列；
- `build_mock_matched_seed_matrix(...)`只接受调用方已经构建并验证的typed artifacts，
  不自行选择k/p、B/K、seed或model参数；
- `validate_mock_matched_seed_matrix(...)`机械检查共享与允许差异，不读取任何stance结果方向。

该层不得创建另一种cell命名、旧同步schedule或previous-round exposure兼容路径。RunManifest
仍由现有v2 domain contract创建；每个cell因run spec/cell不同拥有独立run ID和SQLite，
共享artifact hash不意味着共享可变storage。

### 3.2 `mock_run.py`：严格串行外层harness

该模块只在run级重复调用现有`MockEventPipeline.execute()`。它不复制prepare/invoke/finalize、
retry、reconciliation、commit或checkpoint验证逻辑：

- `MockEventInvocation`为每个event显式携带feed capacity、memory window、parser/prompt limits、
  attempt policy、model identity、request parameters、model seed、HTTP/provider/usage/
  finish证据以及可选reconciliation；它不携带另一条timestamp通道；
- 每个pipeline由调用方在构造时注入run级确定性`clock`。版本化mock fixture提供有序、可重放的
  clock sequence并由matrix fixture assembly绑定其identity/hash；harness只接收已构造pipeline，
  不直接消费或写入时间。现有pipeline独占消费时钟，状态表固定为：fresh/retry/
  pending-resume成功消费started、finished两项；对应失败再消费failure `recorded_at`；
  IN_PROGRESS reconciliation或rehydration成功只重放/消费已持久化的started项，并沿用typed或
  persisted finished值，若失败再消费failure `recorded_at`；landed-success和already-complete均
  消费零项。重开定位不能只取未用suffix：IN_PROGRESS必须先返回已持久化started值再进入剩余
  序列。测试必须逐状态证明timestamp evidence/hash相同；
- `MockRunControl`显式携带目标event ordinal与checkpoint ordinals；空checkpoint tuple表示
  调用方明确选择本次不写checkpoint，而不是隐藏cadence；
- `execute_mock_run(...)`要求invocation sequence exact-cover目标ordinal prefix，逐项核对
  event ordinal/identity后调用pipeline；只接受`committed`或最终`complete`继续循环；任何
  FAILED、缺失授权、reconciliation需求或异常都原样停止，不自动重试、不跳过、不fallback；
- checkpoint只调用包级公开`build_checkpoint`、`write_checkpoint_atomic`和
  `validate_checkpoint`接口；恢复只从`RunStorage.open`、checkpoint验证和重新构造的
  `MockEventPipeline`进入；
- `MockRunReport`只记录实际执行/恢复事实、最终checkpoint/storage roots、耗时与峰值内存，
  不给阈值判定。正式阈值仍由Phase 0B冻结输入决定。

这里的for-loop只是已批准的run orchestrator，不是第二套event engine。它不能直接写SQLite、
构造terminal attempt或推进状态。

### 3.3 `process_audit.py`：只读过程与结果可计算性接口

该模块在显式sweep边界从v6 SQLite公开读接口构建immutable、hash-bound审计制品：

- `RoundZeroBaseline`：N个Agent的初始private state与初始public post有序分布及root；
- `PrivateStateSnapshot`：每个Agent在本sweep边界的private state有序payload/hash；标签为primary；
- `PublicStockSnapshot`：每个Agent截至本sweep边界最近一条公开帖的等权有序集合；标签为
  required secondary；
- `PublicFlowSnapshot`：本sweep新公开帖的消息加权有序集合，允许同一Agent重复；标签为
  required secondary；
- `ExposureProcessSummary`：逐event实际选中消息数、event-backed消息年龄、round-0消息数、
  unique source数、重复来源消息数、空feed数、过期数及sender activity counts；整体固定标为
  `exploratory/process_diagnostic`；
- `SweepProcessAudit`：一个完整sweep的三类snapshot、process summary、相对round-0的七档
  label-count delta及边界root；机械label-count delta同样固定标为
  `exploratory/process_diagnostic`，不得升格为outcome；
- `MockProcessAudit`：一个round-0 baseline和从sweep 1到当前边界的连续
  `SweepProcessAudit`序列，以及run/cell/model/prompt/topic/robustness provenance、边界
  checkpoint/storage roots、版本化术语映射及canonical payload hash。术语映射必须以
  `terminology_map_id`、`terminology_map_hash`和canonical payload三者共同绑定，至少覆盖
  `identity`、`continuity`、`private_state`、`public_post`到07-29 Phase 4A.1批准论文术语的
  对应；本阶段只引用/复制该批准映射，不得发明结果导向命名。

消息年龄只对event-backed post定义为
`receiver_event_ordinal - source_event_ordinal`，必须为正整数；round-0候选单独计数，不伪造
数值年龄。来源覆盖保留原始`selected_source_agent_ids`与计数，暂不冻结比例或阈值。
`expression_gap`只登记为“required secondary / definition unresolved”，并输出计算它所需的
private/public ordered distributions；本阶段不得选择距离函数或根据结果交换primary/secondary。
相对变化只机械输出每个七档label在当前snapshot与round-0 baseline之间的整数count delta；
不把该delta命名为效应、极化或显著性，也不据此设置gate。

审计构建只读取成功提交前缀，并允许两种权威执行态：(a) 请求边界上的合法`RUNNING`前缀，
且该边界不存在未解决或非terminal attempt；(b) 精确覆盖完整schedule、已由storage完整性
验证的`COMPLETE`前缀。`FAILED`、不完整/被篡改前缀、边界不在已提交范围、边界不是
population size的整数倍、sweep序列不从1连续覆盖、证据缺失/额外/错序或checkpoint与
SQLite冲突均必须失败关闭。审计事务不得跨adapter调用持有。

## 4. 三档mock规模

三档值由版本化`paper1.mock-scale-cases.v2`测试制品显式记录；该制品必须继续标记
`mock_only: true`和`research_parameter_status: not_frozen`。这里的T和执行模式是工程测试
输入，不成为formal protocol值。

### 4.1 N=20：故障与恢复矩阵

- 构造12 cells及共享artifact审计；
- 使用显式的小T执行成功、失败、重试、checkpoint和重开恢复测试；
- 在调用前、IN_PROGRESS、invocation后、terminal success后、SQLite commit后等4B-8C-3
  已定义prefix上做组合恢复；
- 比较不间断run与重开run的最终storage/checkpoint/audit hashes；
- 运行在普通测试套件内。

### 4.2 N=100：完整12-cell集成

- 对同一matched seed机械构造并执行全部12 cells；
- T使用fixture中的显式缩小值，不把它称为正式T=50；
- 每个cell拥有独立SQLite并严格串行完成；
- 验证E0/E1/E2 feed边界、四persona条件差异、跨cell共享hash及允许的后续状态链差异；
- 生成每cell的过程审计hash与matrix-level completion report；
- 测试不比较stance方向、效应大小、极化或显著性。

### 4.3 N=1000：正式形状与50,000-event工程门禁

分成两个不同证据，避免把schedule构造冒充完整执行：

1. **形状门禁**：为12 cells构造N=1000/T=50的50,000连续ordinal schedule、共享制品、
   manifests和跨cell审计；不执行12×50,000 events。
2. **执行门禁**：预先固定一个仅用于工程压力的社会cell，在单matched seed上用deterministic
   mock完整执行50,000 events，生成显式sweep checkpoint、重开验证、过程审计、总耗时、
   SQLite/不可变导出字节数和峰值内存。工程stress cell ID写入fixture，不按结果选择；它不
   获得研究优先级。

恢复hash等价性另以N=1000的显式缩小T fixture完成，避免默认release测试必须重复执行两条
50,000-event完整run。50,000-event门禁仍必须至少有一次真实逐事件pipeline执行；禁止用
空state checkpoint、只生成schedule、批量SQL伪提交或绕过prompt/parser/adapter来替代。

50,000-event测试标记为release/slow，普通单元回归不隐式触发。最终Phase 4B release必须显式
运行并记录一次；测试只报告观测值，除非调用方显式提供已冻结的性能阈值，否则不判定
“够快/够省内存”。

## 5. 跨cell不变量

`validate_mock_matched_seed_matrix`至少检查：

1. 恰好12个唯一canonical cell IDs，identity/continuity/exposure笛卡尔积exact-cover；
2. matched seed、topic package、population、initial stance/reason逐Agenthash一致；
3. WS、shadow、Agent—node mapping及结构gate均来自同一matched-seed artifact family；
4. 全部cell复用相同attention、expression、activation、publish及完整FrozenSchedule hash；
5. E0的exposure graph hash为None，E1精确绑定shadow，E2精确绑定WS；
6. 四个persona条件只在批准的identity/continuity块出现机械差异；exposure不得改变persona；
7. 每cell RunManifest、storage binding、adapter execution binding和mock script彼此一致；
8. run ID、cell-specific run spec、exposure graph和由执行产生的状态/evidence chain允许不同，
   不能错误要求跨cell输出相等；
9. 任何单一cell伪造共享hash、交换E1/E2图、改变Agent mapping、schedule slot、publish flag、
   mock runtime/script或manifest后，矩阵在执行前失败关闭。

验证器返回成功或抛出错误，不产生“哪个cell更好”的排序和分数。

## 6. 恢复与确定性比较

每档恢复测试建立两个独立run identity但共享同一明确fixture输入：

- uninterrupted run连续执行到目标边界；
- interrupted run在fixture列出的checkpoint/prefix关闭storage，重新打开数据库、验证checkpoint，
  重建pipeline后继续；
- 比较时不能直接要求run_id-dependent hashes相等。必须用版本化
  `MockComparableRunProjection`去除仅由launch nonce/run ID/URI/时间路径导致的身份字段，
  同时保留cell、matched seed、schedule、event ordinals、agent states、public posts、feed
  cursors、attempt outcomes、prompt/response/parse及过程审计的语义hash；
- projection schema和排除字段写死并测试，不能由调用方任意传“忽略字段”；
- 原始run级evidence仍各自完整保存，projection只用于mock deterministic equivalence gate，
  不覆盖manifest或SQLite truth。

如果恢复需要真实provider reconciliation，本阶段只使用4B-8C-3已验证的显式mock
reconciliation输入。不得把“重开后重新调用mock adapter但输出碰巧相同”当作zero-resend证据。

## 7. 资源与文件卫生

- 每个测试run使用系统临时目录下独立SQLite/checkpoint/export路径；
- 正常和异常路径都显式关闭pipeline/storage并释放lease；
- N=100完整矩阵和N=1000/T=50 release gate结束后清理临时运行文件；
- Git hygiene测试拒绝`.sqlite*`、checkpoint、raw response、coverage/cache、`.codex/`和大结果；
- 交接只提交设计/计划/代码/测试、小型mock fixture、manifest/hash示例与归档定位规则；
- 不提交由性能run生成的原始数据库或全量审计payload。

## 8. 测试与发布顺序

所有实现使用TDD，按以下顺序提交：

1. scale fixture v2与canonical matrix plan；
2. cross-cell exact-cover/shared-artifact validator；
3. thin strict-serial mock run harness；
4. process audit与comparable recovery projection；
5. N=20故障/恢复矩阵；
6. N=100完整12-cell集成；
7. N=1000/T=50 shape与真实50,000-event release gate；
8. protocol/reproducibility/overview/handoff与最终release review。

每项先加入可观察的RED，再做最小GREEN；P0-P2复审问题必须新增RED/GREEN回归。最终同时
运行full suite、coverage、Ruff check/format、pip check、diff check、schema镜像、human summary、
draft/formal、wheel安装和Git hygiene gates。

## 9. 拒绝方案

### 9.1 在测试中复制完整event loop

它会形成与`MockEventPipeline`/`StrictSerialLifecycleEngine`竞争的恢复语义，拒绝。测试fixture
只能构造显式输入，run harness只能调用公开pipeline。

### 9.2 给B/K、timeout、retry、model seed或checkpoint cadence加方便默认值

这会把mock工程值偷渡为研究配置，拒绝。所有值进入版本化mock fixture或调用参数并明确
not_frozen。

### 9.3 用N=1000/T=50 schedule构造代替50,000-event执行

它不能证明累计SQLite、prompt context、feed、checkpoint、内存或吞吐，拒绝。shape gate与
execution gate必须分开命名和记录。

### 9.4 为了让测试快而批量写最终state

它绕过严格串行因果链、失败原子性与证据重放，拒绝。性能问题应通过消除不必要的全历史
扫描修复，不能改变事件语义。

### 9.5 在4B-9计算/选择论文结果

本阶段只证明输出可计算、可追溯。不得查看哪个cell更极化、按效应方向挑stress cell、冻结
expression-gap距离或设显著性规则。

## 10. 完成标准

Phase 4B-9及整个Phase 4B只有在以下证据全部存在时才完成：

- 4B-8C-3最终三路release复核补齐且无P0-P2；
- N=20/100/1000 mock fixture均严格typed、deterministic、mock-only/not-frozen；
- N=100完整12-cell严格串行完成并通过跨cell不变量；
- N=1000/T=50的12-cell shape gate和单run 50,000-event真实mock execution gate均通过；
- N=20/100/1000缩小T恢复前后comparable final hashes一致；
- process audit可输出private/public stock/flow与全部指定曝光过程量，不选择结果；过程量与
  机械label-count delta均带`exploratory/process_diagnostic`标签；
- `MockProcessAudit`包含hash-bound版本化术语映射ID/hash/payload及
  model/prompt/topic/robustness provenance；
- schema/YAML/human protocol/research-QA路径同步，formal继续因未决项fail closed；
- full/coverage/static/format/dependency/diff/wheel/Git hygiene gates通过；
- 形成换机/上云可恢复handoff，记录commit、测试计数、运行环境、观测资源、限制和下一阶段；
- Git不含原始大结果、SQLite、checkpoint、cache或`.codex/`。

满足这些条件后，下一步是Phase 0A/0B与真实模型小规模校准，而不是直接开始正式主实验。
