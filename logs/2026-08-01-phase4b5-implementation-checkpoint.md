---
status: complete / independently reviewed
date: 2026-08-01
last-verified: 2026-08-18
branch: codex/paper1-phase4b
baseline: b2fe2d69
phase: Phase 4B-5 implementation checkpoint
---

# Phase 4B-5 实现检查点

本检查点只记录attention、expression、activation与预生成publish schedule的mock工程能力。
当前实现及最终三个P1审查修复已经独立规格/反模式、代码质量与release三路复审关闭，
Phase 4B-5状态为`complete / independently reviewed`。本检查点不启动或实现Phase 4B-6。

## 实现边界

- `build_attention_artifact`支持正截断lognormal、正截断Pareto和equal-weight三种显式mock
  family；所有权重严格为正并归一化到`sum(w_i)=N`，保存逐Agent值、分布参数、诊断、
  input/output hash及`attention` RNG provenance。lognormal使用每attempt固定两次primitive
  uniform的版本化Box–Muller，Pareto使用每attempt一次uniform的显式inverse CDF；两者均不
  调用stdlib内部可能含隐藏循环的distribution helper，非有限、溢出、边界值与预算耗尽均
  fail closed。
- `build_expression_artifact`实现hurdle–Beta：结构性潜水者的后续publish probability为0，
  非潜水者为连续Beta倾向。主路径只接受`independent`，不读取attention、人口、网络、初始
  立场、cell或意见结果；非潜水者采用v2自有bounded gamma-ratio Beta，每attempt至多两个gamma
  candidate、两次gauss和四次显式uniform。溢出、下溢、非有限或边界candidate均拒绝，显式
  attempt budget耗尽fail closed；不调用内部含无界循环的stdlib `betavariate`。
- `build_activation_schedule`按固定attention权重每sweep有放回抽N次，产生N×T个连续
  零基全局`event_ordinal`；sweep/draw/agent只作为属性。完整序列在运行前生成并绑定attention
  output hash与独立`activation` RNG ledger。平台能力硬上限为N≤1000、T≤50、events≤50,000，
  不把N=1000当调用默认或研究参数。
- `build_publish_schedule`将独立`publish` RNG按逐Agent表达倾向生成的flags绑定到每个activation
  slot，并封装为`paper1.schedule.v2`的完整`FrozenSchedule`；结构性潜水者所有后续flag均为false。
  activation/publish均以版本化common-coordinates+ordinal range/count+逐event key digest ledger压缩
  重复provenance；每个event key仍逐ordinal独立重建和审计。raw mapping必须先与可信source/common
  coordinates及root核验并扫描digest一次，得到immutable validated ledger；其单ordinal读取为O(1)。
  `ValidatedEventRNGLedger`的普通公开构造会拒绝，只有模块内可信构造或
  `validate_event_rng_ledger`核验后才签发sealed capability；Python同进程反射不被误述为安全沙箱。
- `validate_matched_schedule_reuse`要求同matched seed的12 cells逐字复用四类制品，并重算
  attention、expression、activation、publish与最终schedule hash；跨seed、伪造payload、RNG或
  hash漂移均fail closed。
- 所有产物显式`mock_only: true`及`research_parameter_status: not_frozen`；未调用模型，未读取
  私人/公开意见，未实现event engine、state/feed/memory或Phase 4B-6能力。

## 严格TDD证据

- 首个RED：`ModuleNotFoundError: No module named 'agent_ex.schedule'`；最小attention GREEN为
  `1 passed`。
- Pareto/equal-weight能力先得到`2 failed, 2 passed`，最小GREEN后attention范围为`4 passed`。
- expression、activation和publish/复用接口分别先因公开接口缺失进入RED；GREEN依次达到
  `6 passed`、`8 passed`和`11 passed`。
- 完整FrozenSchedule首次GREEN后暴露ArtifactEnvelope深冻结对象不能绕过JSON transport；
  修正为公开`to_payload`传输合同后schedule专项为`11 passed`。
- 公开API导出测试先因`agent_ex`无五个新接口得到`1 failed`，导出及精确集合迁移后为
  `2 passed`。
- 可审计诊断先得到`3 failed, 16 passed`，补充weight/lurker/activation诊断后为`19 passed`。
- hash-consistent伪造attention权重最初未被拒绝，回归先得到`1 failed`；完整确定性重算后攻击
  测试GREEN。
- lognormal对数location最初由实现隐式固定为0；mock缺失`log_location`的回归先得到
  `1 failed`（未按预期拒绝），formal schema缺少required字段的回归也先得到`1 failed`。
  最小修复要求调用者显式传入有限`log_location`，将其传入真实截断采样并绑定payload、input
  hash与RNG coordinates；删改后hash-consistent重封装会被确定性重放拒绝。schema只要求显式
  number且无default，draft仍为`UNRESOLVED[P1_ACTIVITY_WEIGHT_DISTRIBUTION]`，未冻结0。
- 极端`alpha=1e-300,beta=1.0`的非潜水者Beta边界回归先得到`1 failed`；sweep_count=51能力
  边界和旧逐event provenance tuple也分别先得到RED。最小修复增加显式版本化Beta attempt budget、
  N/T/event能力上限及紧凑event RNG ledger；budget、ledger或ordinal重封装漂移均fail closed。
- N=1000/T=50旧格式实测activation/publish JSON分别为35,117,393/49,989,024 bytes；紧凑格式
  将其降到4,125,549/5,132,258 bytes。5/6MiB阈值只约束固定`agent-%04d` mock benchmark，
  明确不是任意合法长Agent ID的输入有效性规则。
- 终审进一步以monkeypatch禁止`betavariate`并计数primitive RNG；旧实现先因调用无界stdlib得到
  RED。`alpha=beta=1e308`、attempt budget 2在新实现中快速耗尽，且primitive调用不超过结构
  上限。旧public raw-ledger单点入口、篡改common后重算digest及event_count边界也先得到RED；
  迁移为trusted validation→typed ledger后全部GREEN，bool和>50,000在digest扫描前拒绝。
- 最终三个P1继续按严格TDD关闭：公开`ValidatedEventRNGLedger(...)`原本可伪造、stdlib
  lognormal/Pareto helper仍被调用（且uniform=0会卡在其内部循环）、N=1001会在sampling或
  deterministic replay后才拒绝，分别先得到可归因RED。最小GREEN引入sealed ledger capability、
  显式有限primitive采样和统一N≤1000预检；attention/expression builder及activation/publish
  source在逐record sampling/replay前fail fast。Beta分布sanity样本同步降至N=1000能力边界内。
- postfix代码质量复审的两个P1同样先RED：自报`len=1001`且任一元素访问即抛错的Sequence证明
  `_agent_ids`曾在容量门禁前物化；12组hash-consistent oversized/bool envelope攻击证明matched
  reuse validator曾在全cell资源预检前进入source replay。最小GREEN先读取Sequence长度并执行
  N门禁，再物化合法输入；同时对全部12 cells的attention/expression record count、activation与
  publish的population/sweep/event声明执行共享raw-envelope preflight，之后才允许完整语义验证和
  deterministic replay。preflight只承担资源边界，不替代后续hash/RNG/绑定校验。
- 本轮1P1+1P1+P2再以严格TDD关闭三类Python宽松语义：ledger的int→float/bool与nested
  common伪造在raw type check前进入capability rebuild，len=1000的Sequence被tuple额外探测
  index 1000，删除10类容量必需字段会落入replay。GREEN要求raw ledger顶层严格int/ordinal=0、
  common及ledger/root使用strict-JSON递归与canonical hash作类型敏感比较；Sequence仅按已验证
  `range(len)`索引物化；matched preflight要求records、N、T、slots和ledger event_count全部存在，
  且`N×T == len(slots) == ledger event_count`，同时覆盖publish sweep/ledger bool。

## 验证证据

- strict-JSON/lying-Sequence/required-preflight修复后的schedule专项：`83 passed in 31.79s`；
  domain+protocol为`192 passed in 6.56s`；formal unresolved与schema镜像定向为
  `3 passed in 0.58s`。
- 独立连续fresh全套：`402 passed in 69.92s`，无失败、skip或xfail。
- 独立fresh coverage：`402 passed in 204.17s`；`2876 statements / 419 missed / 85%`，
  `schedule.py`为`638 statements / 96 missed / 85%`。
- 独立定向验证：`275 passed`。
- N=1000/T=50显式mock构造并JSON恢复为50,000个连续ordinal；首ordinal为0、末ordinal为
  49,999；equal-weight与Beta attempt budget 100的显式mock候选构造耗时23.765秒，
  activation ledger可信验证为3.193秒，validated ordinal 49,999单点读取约47微秒；以
  monkeypatch禁止event digest重扫后仍成功。activation/publish JSON为
  4,110,564/5,132,825 bytes，JSON round-trip与schedule hash相等。该规模只是无模型工程
  测试，不是formal run或研究结果。
- 本轮后N=1000/T=50 formal-scale mock gate再次通过：`1 passed in 28.18s`；继续覆盖
  50,000连续ordinal、JSON尺寸/round-trip、trusted ledger与禁digest重扫的O(1)读取。
- 最终Ruff check与清理临时目录后的23-file format check通过；`pip check`为`No broken requirements found.`，
  `git diff --check`退出0，tracked hygiene无`.codex/`、pytest缓存、数据库或`__pycache__`。
- draft配置中的`P1_ACTIVITY_WEIGHT_DISTRIBUTION`、`P1_ACTIVITY_CALIBRATION_TARGETS`、
  `P1_PUBLISH_PROCESS`与`P1_ATTENTION_EXPRESSION_CORRELATION`仍为对应`UNRESOLVED[...]`；
  既有formal fail-closed测试继续通过。两份schema仅新增显式`log_location`必填数值属性且无
  default；本阶段没有修改draft YAML或决定卡，也未将mock候选0提升为formal参数。

## 独立复审结论

- 独立规格/反模式复审：`APPROVED`；四制品绑定、独立逐event RNG、运行前publish freeze、
  canonical 12-cell/expected-seed复用语义及formal fail-closed边界均已关闭。
- 独立代码质量复审：`APPROVED`；有限预算采样、Beta严格内点、sealed typed ledger、
  严格JSON类型、容量预检、确定性重算和N=1000/T=50资源边界均无开放项。
- 独立release verification：`PASS`；连续full、coverage、定向攻击、schema镜像、
  88个`UNRESOLVED[...]`、Ruff/format、依赖、diff与Git hygiene均通过。
- 完成文档更新前的已验证代码/测试候选canonical snapshot SHA-256为
  `dc1b81a27919ec9e606c58342fb8771ba6e5ba962bf6c20006ba8f3168d6ea2c`；文档更新后的
  release verification将产生新的最终snapshot。两份schema镜像SHA-256均为
  `3db603ea0c8303a061838cd962db687a6d5ab616bacc78dd1876b007d7a5783e`。这些是工程验证
  标识，不是formal protocol freeze或提交hash。

## 完成边界

- Phase 4B-5已关闭为`complete / independently reviewed`，没有开放审查项。
- draft仍含88个`UNRESOLVED[...]`；所有mock参数必须由调用者显式传入，所有制品仍为
  `mock_only / not_frozen`，formal继续fail closed。
- 本阶段未调用真实模型、未产生研究结果、未冻结formal参数，也未开始Phase 4B-6。
