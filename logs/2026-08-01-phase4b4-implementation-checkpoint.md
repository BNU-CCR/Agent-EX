---
status: complete / independently reviewed
date: 2026-08-01
branch: codex/paper1-phase4b
baseline: 728198a
phase: Phase 4B-4 implementation checkpoint
---

## 完成收口（2026-08-01）

- 独立规格审查、反模式审查与代码质量审查最终均为`APPROVED`，没有开放审查项。
- 最终network专项为`43 passed`，protocol/schema gates为`143 passed`；连续fresh全套为
  `318 passed in 31.25s`，无skip/xfail；fresh coverage为`318 passed in 97.43s`，
  `2237 statements / 323 missed / 86%`，`network.py`为`84%`。
- N=1000锚点独立复算通过：WS output hash为
  `d2a9874c648486ef7c8dc6d8148862400ec927d36e82bea461ce832238a5188c`，shadow output
  hash为`221140fc49b6a1f9fc521d9108e295540e03a53477f6cd18113c1ea48d3eaa8e`，D-07
  structure-gate output hash为
  `3e4d5387aa2e5dcffc5e2312c6d3ff20329dc9fd909b5338755191d0b2834863`；绑定同seed
  population、round-0 initialization和WS的Agent-node mapping亦通过重算验证，output hash为
  `ee62915b5fa2476abbab9a7eb2181819686bda68cfb2dc0d9e6cf27adae4c52b`。
- shadow hash相较早期checkpoint的变化仅来自新增完整multi-attempt audit；图结构和交换计数
  未变。所有上述制品与hash都只是`mock_only / not_frozen`工程回归证据。NetworkX版本、
  WS/shadow算法、预算、D-07 null规则及全部精确`P1_*`机器值仍保持
  `UNRESOLVED[...]`，不构成formal freeze。
- 完成文档更新前的已验证代码/测试工作树快照SHA-256为
  `B19E18908FEA12EC605310A096CCFC9A0A58FB3CEF9A9F6DED4766B55A1661DB`。这是
  pre-documentation verification hash；文档更新后最终release verifier会产生新快照，
  它不是提交hash。
- Phase 4B-4现为`complete / independently reviewed`；尚未提交，Phase 4B-5尚未开始。

## 2026-08-01 multi-attempt audit fix（复审已关闭）

- 新增严格TDD回归：`n=10,k=2,p=.05,seed=15,max_attempts=10,trial_budget_per_edge=1`
  的构造在第9次attempt成功。旧artifact只保留第9次审计并遗漏前8次失败消耗，新测试先因
  不存在`attempt_audits`按预期RED失败。
- `_try_shadow_attempt`现在无论成功或失败均返回该attempt的交换、连通性检查、候选trial与
  剩余禁边审计；`_replay_shadow_construction`保存按序的全部attempt，并把顶层三个消耗计数
  定义为所有已用attempt的累计值。失败attempt从新的WS副本开始，但其已消耗预算不再丢失。
- validator要求attempt列表长度等于`attempts_used`、index连续、仅最后一次成功、完成状态与
  剩余禁边一致、每次及累计trial均在冻结预算内，且累计值等于per-attempt之和；随后仍以
  WS input、derived seed和预算精确重放并比较完整图与完整audit。
- GREEN证据：多-attempt及相关回归`3 passed`；network完整`43 passed in 19.98s`；连续
  fresh full `318 passed in 32.92s`。fresh coverage full为`318 passed in 91.50s`，总覆盖率
  `86%`（2237 statements / 323 missed），`network.py`为`84%`。
- N=1000测试包含在network/full中，network durations记录call `17.72s`，未见性能回退。
  `ruff check platform`、`ruff format --check platform`、`pip check`与`git diff --check`
  最终均通过。
- shadow图结构与交换计数没有变化；output hash因新增完整attempt audit而按证据合同预期变化，
  下文三seed hash已更新。它们仍是`mock_only / not_frozen`回归证据，不是formal冻结值。

## 2026-08-01 code-quality fixes（复审已关闭）

- 严格TDD先新增三项回归测试并观察到预期RED：hash-consistent但使用错误seed生成的
  WS图未被拒绝；shadow的合法范围audit计数可被置零；含连通性回滚的合法shadow构造
  会因`connectivity_checks != accepted_swaps`被自身validator错误拒绝。
- WS validator现在按锁定的NetworkX算法、声明参数与RNG derived seed确定性重放，并精确
  比较canonical edges，不能再用另一seed的合法WS图伪装原provenance。
- shadow构造与validator共用单一、版本锁定的有界重放路径；公开validator从WS input、
  derived seed与预算重放并精确比较canonical edges及完整construction audit。builder复用其
  已执行的同一重放结果进行自校验，避免N=1000构建时无意义地重复执行昂贵算法。
- audit范围允许`accepted_swaps <= connectivity_checks <= candidate_trials`，因此断连候选的
  回滚检查可被忠实记录；精确重放仍拒绝任何hash-consistent audit伪造。
- GREEN证据：新增3项`3 passed`；network完整`42 passed in 20.26s`；连续fresh full
  `317 passed in 31.24s`。fresh coverage full为`317 passed in 92.38s`，总覆盖率`86%`
  （2212 statements / 316 missed），`network.py`为`85%`。
- N=1000 WS+shadow构造与自校验压力测试单独为`1 passed in 18.89s`（call 18.37s）；
  builder复用已执行重放结果后未引入第二次同量级shadow构造。
- `ruff check platform`、`ruff format --check platform`、`pip check`与`git diff --check`
  均通过。该阶段性结果当时仍未提交、未进入4B-5，状态为
  `quality fixes pending re-review`；后续复审关闭状态见上方“完成收口”。

## 2026-08-01 review-fix checkpoint（复审已关闭）

- A：`build_agent_node_mapping`现在强制绑定同一matched seed的population、round-0
  initialization和WS三个`ArtifactEnvelope`；Agent ID只从population导出并与round-0逐条一致，
  三个source ID/hash/seed均进入payload与input-hash证据。
- B：删除旧工程ID旁路。NetworkX版本、WS/shadow构图算法、shadow attempt/trial预算以及
  D-07规则环格/随机null算法与重复数已进入canonical+packaged schema、draft YAML和
  research-QA的正式`P1_*`决策集合；draft全部保持`UNRESOLVED[P1_*]`，formal继续fail closed。
  human summary由公开renderer输出更新，mock artifact仍只记录实际3.6.1与候选算法。
- C：新增纯结构D-07 gate：同N/同边数规则环格与随机图null使用独立RNG namespace，记录
  relative clustering、relative path和small-world coefficient；不接受任何意见输入，null断连
  按当前冻结`on_invalid=fail`语义fail closed。
- D/E：WS拒绝bool节点/端点并严格校验library、algorithm、RNG implementation/coordinates/hash；
  shadow严格校验library/RNG/budget/WS link以及整数audit范围和真实trial上界。
- 严格TDD的新增RED均先因缺失接口或未拒绝漂移而失败，随后network定向达到`39 passed`；
  protocol完整为`139 passed`。分拆fresh全套为`64 + 4 + 107 + 139 = 314 passed`。
- 单进程全套在本桌面宿主两次无pytest traceback地被终止；首次另发现系统Temp目录权限错误。
  使用workspace basetemp逐文件分拆均exit 0，因此记录为宿主/资源限制，不解释为单进程通过证据。
- coverage分拆（排除旧的N=1000 shadow压力测试；该测试已在非coverage network套件通过）为
  `2198 statements / 315 missed / 86%`，`network.py`为`85%`。
- N=1000结构anchor（seed 2026072901, k=10, p=.05, null=1）通过重算validator：WS hash
  `d2a9874c648486ef7c8dc6d8148862400ec927d36e82bea461ce832238a5188c`，gate hash
  `3e4d5387aa2e5dcffc5e2312c6d3ff20329dc9fd909b5338755191d0b2834863`。
- 该阶段性checkpoint当时为`in_progress / review fixes pending re-review`；未提交、未进入
  4B-5。后续复审关闭状态见上方“完成收口”。

# Phase 4B-4 实现检查点

本检查点记录WS、degree-preserving shadow graph与Agent-node mapping的首轮实现、后续
TDD审查修复及纯结构工程gate。以下各节保留实现过程证据；最终审查与验证状态以上方
“完成收口”为准。Phase 4B-4现为`complete / independently reviewed`；未提交，
Phase 4B-5未开始。

## 工程gate与未冻结边界

- Python为3.12.13；项目依赖候选锁定并实装`networkx==3.6.1`。
- WS显式调用
  `networkx.generators.random_graphs.watts_strogatz_graph(n,k,p,seed,create_using=nx.Graph)`；
  不使用connected包装器、默认seed或隐藏重抽。
- 初稿曾尝试使用不进入schema的独立工程ID；审查已判定该旁路无效并迁移为正式
  `P1_*`研究决策ID，由schema、YAML、research-QA与human summary共同约束。
- NetworkX 3.6.1、`k=10,p=.05`、三个mock seeds与shadow预算只属于
  `mock_only / not_frozen`工程候选。formal机器值分别继续标记为对应
  `UNRESOLVED[P1_*]`，没有把mock候选写成formal值或决定卡。
- 结构gate未读取任何意见、对比、效应、显著性或LLM输出。

## 实现合同

- `build_ws_artifact`：严格校验N/k/p，使用`ws_graph`独立RNG namespace；节点固定
  `0..N-1`，edge tuple逐端点规范化并全局排序；无向、简单、全连通、边数
  `N*k/2`，任一失败立即拒绝。
- `validate_ws_artifact`：重算节点、边、结构报告、库身份、构图参数input hash、
  output hash/envelope identity与RNG provenance；hash一致但参数或结构漂移仍失败关闭。
- `build_shadow_artifact`：算法ID为
  `paper1.mock_forbidden_edge_connected_double_swap@1.0.0`。从WS副本开始，每次以
  double-edge swap消除至少一条原WS边，禁止生成自环、重边或任何WS边；每个接受交换
  即时运行连通检查，始终保持逐节点度数。attempt与每条禁边trial均有显式预算，耗尽
  后fail closed，不在run中修图、降级或重抽。
- `validate_shadow_artifact`：验证WS input hash/source identity、逐节点度数、边集合完全
  不相交、简单性、连通性、构图预算hash、审计计数与`shadow_graph` RNG provenance。
- `build_agent_node_mapping`：强制绑定已完整验证且matched-seed一致的population、round-0
  initialization与WS三个制品；Agent ID从population导出并与round-0逐条一致。使用
  `agent_node_mapping`独立namespace做Fisher–Yates shuffle，不读取身份、立场或cell；
  同seed可跨12 cells复用。
- 全部制品使用`ArtifactEnvelope`，包含稳定类型/schema、算法ID/版本、input/output
  hash、独立RNG provenance及`mock_only / not_frozen`元数据。

## TDD证据

- 首组RED：`ModuleNotFoundError: No module named 'agent_ex.network'`。
- WS最小GREEN：`13 passed, 6 deselected`。
- 首轮network专项：`19 passed in 25.27s`。
- 公开API先`1 failed`，导出五个接口后`1 passed`。
- 参数/budget input hash与mapping位置框架三项补强先`3 failed`，最小修复后`3 passed`。
- downstream绕过完整WS验证先`1 failed`，统一调用完整验证后`1 passed`。
- matched-seed混搭先`1 failed`；shadow/mapping绑定WS seed后相关`4 passed`。
- 首次完整套件`285 passed, 12 failed`。根因为旧公开API集合及`P1_`工程ID污染决策
  registry；迁移后protocol/wheel/API定向`144 passed`。

## N=1000纯结构gate

mock seeds固定为`2026072901/02/03`，只作为本实现回归输入。

- 27/27张WS图全连通，无失败seed；`k=6/10/20`边数分别严格为
  `3000/5000/10000`。
- 单张WS构图、完整结构报告、hash与序列化耗时1.31至2.41秒；JSON约36.7KB、
  57.1KB、106.2KB（随k增长）。
- 锚点`k=10,p=.05`三seed：平均聚类
  `.562034/.562089/.574100`；平均最短路`5.086326/5.058811/5.247211`；直径均9。
- 锚点WS output hashes：
  `d2a9874c648486ef7c8dc6d8148862400ec927d36e82bea461ce832238a5188c`、
  `6d6fe8e342f9130d3673fe00d51e8db31bbc20f55a585aa73d7992cd61ee0150`、
  `35a0812e94e806dfb432b774850ccf84b52dd64ad5f2c298e973d5267f6d2aaa`。
- 三张shadow均首次attempt成功；接受交换3467/3469/3465次，candidate trials
  3622/3591/3595次，耗时20.85/20.77/21.80秒；全部全连通、逐节点度数一致、
  WS边交集为0。
- shadow output hashes：
  `221140fc49b6a1f9fc521d9108e295540e03a53477f6cd18113c1ea48d3eaa8e`、
  `e877f08e7e2e5998d1b8ea1f20d9f2be12143610cf8d0b828e57d83bfee9553d`、
  `15bb7e460ded47de8d4ea0e66562ed2ab68096cc2e1b3abc2768e83c63c1cffa`。

这些hash仅证明mock算法与候选版本在本checkpoint的输出，不是formal图冻结。

## 验证证据

- fresh完整套件：格式化与文档checkpoint写入后的最终复验为
  `299 passed in 42.91s`，无skip/xfail。
- fresh coverage：`299 passed in 113.82s`；`2081 statements / 297 missed / 86%`；
  `network.py`为`263 statements / 40 missed / 85%`。
- protocol/schema/draft/formal/human-summary定向gate：`5 passed`。
- Ruff check通过；Ruff format check为`21 files already formatted`。
- `pip check`：`No broken requirements found.`。
- `git diff --check`退出0，仅有Windows未来LF/CRLF转换提示。
- Python/NetworkX实装：`3.12.13 / 3.6.1`；当前lock SHA-256为
  `C51AAD1B9E4BBFE4F560A30776C60CE643C1D747A63CABEC86C316C854F0E684`。

## 文件边界

- 实现：`platform/src/agent_ex/network.py`及`agent_ex.__init__`公开导出。
- 测试：`platform/tests/test_network.py`、公开API安装/领域集合迁移。
- 依赖：`platform/pyproject.toml`、`platform/requirements-dev.lock`。
- 工程登记与未决项：`docs/research-qa.md`、canonical/packaged schema、draft formal YAML与
  generated human summary；状态：`task_plan.md`、`progress.md`与本检查点。所有新增正式
  `P1_*`字段仍为`UNRESOLVED[...]`并fail closed。
- 未修改决定卡；未实现schedule/attention/expression等4B-5能力。

## 下一步

Phase 4B-4三类独立审查已经全部关闭，下一步仅是对文档更新后的完整工作树执行最终release
复验并提交/同步本阶段。Phase 4B-5在该收口完成前仍未开始；任何mock候选都不得提升为
formal值。
