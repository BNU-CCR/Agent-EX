---
status: review repairs implemented; pending independent re-review and commit
authority: implementation evidence for Phase 4B-8C-1; subordinate to frozen protocol/specification chain
date: 2026-08-30
---

# Phase 4B-8C-1｜存储侧 engine readiness

## 边界

本工作包只补齐严格串行 engine 所需的存储接口，不实现 engine、adapter 调用、网络、
真实模型、重试上限、timeout 分类、checkpoint 频率或正式研究参数。

现有 `RunManifest` 不能忠实承担执行期动态状态：其 complete 语义要求 frozen archive，
而 recovery cursor 又要求外部 checkpoint URI/hash。因此本工作包不修改 baseline
manifest，也不把执行期投影伪称为完整 `RunManifest`；新增独立、typed、canonical、
hash-bound 的 `ExecutionState`。

## TDD 证据

### RED

先新增最小测试，再运行：

```text
platform/.venv/Scripts/python.exe -m pytest -q tests/test_storage.py
  -k "private_updates_for_agent or current_event_journal or execution_state_is_separate
      or terminal_halt or run_lease"
```

实际在 collection 阶段失败：`ImportError: cannot import name 'EventJournalState'`，证明
测试先于实现且目标接口尚不存在。

独立审查提出的恢复授权、全写路径lease和checkpoint绑定修复继续按RED→GREEN推进：

- 新增恢复授权/lease/不可变测试后，collection按预期因缺少
  `ResumeAuthorizationEvidence`失败；
- 新接口最小实现后，focused为`3 passed`；
- lease门禁第一次storage全跑为`98 passed, 1 failed`，唯一失败准确定位到reopen后
  `commit_success` fixture未显式持lease；修正fixture后storage为`100 passed`；
- checkpoint v2接线第一次为`60 passed, 10 failed`，失败集中在合法旧execution/
  attempt前缀的stale分类；加入候选自身结构自洽校验和append-only prefix替换后为
  `70 passed`，再加入halt/auth与单snapshot测试后为`72 passed`；
- 授权删除、row event篡改、payload篡改、错event、重复及分叉授权均有fail-closed
  回归；第二进程不持lease直接调用mutator被拒绝，持lease进程`os._exit`后新owner可写。
- 补充“授权后真正开始下一attempt”的回归后，首次按预期RED于integrity仍把历史halt
  当当前FAILED；根因修复为按event/attempt有序保存完整failure/authorization前缀，
  仅最后未授权failure阻断。测试覆盖同一event两轮halt→authorize，checkpoint绑定完整
  payload前缀及其root hash。
- 第二轮审查将根因收敛到两张表各自依赖`rowid`、缺乏跨failure/authorization的统一
  因果顺序。新增反例先分别RED于缺少canonical sequence字段、授权后仍保留current
  failure，以及checkpoint可保留完整FAILED attempt却截短授权证据并被判stale。修复后
  每条证据带连续1-based sequence、跨类型previous hash、kind、run/event/ordinal；failure
  还精确绑定attempt ID/index及terminal transition hash。完整链只能严格交替
  failure→authorization，末端可为未授权failure。
- SQLite篡改矩阵覆盖删除failure、删除authorization、跳sequence、错event、分叉previous
  hash、错attempt及恶意reinsert；checkpoint矩阵覆盖重复、反排、跳sequence、错event、
  分叉、跨ordinal和重hash伪造execution，全部fail closed。同一attempt二次halt亦被拒绝。
- 第三轮审查的跨event反例先RED：event 0 已完成halt→authorize→success后，event 1的
  新FAILED attempt错误复用了event 0授权并返回`retry_same_event`。修复后journal只接受
  当前event ID/ordinal/latest attempt精确绑定的failure及authorization，close/reopen一致。
- checkpoint阶段反例先RED：FAILED transition后、halt写入前的合法checkpoint在后写halt
  后被误判conflict。修复改为逐attempt周期重放：只有出现下一attempt时，前一FAILED
  attempt才强制要求exact failure+authorization pair；最后FAILED允许pre-halt、halted、
  authorized三个阶段，execution由候选阶段重放。测试覆盖两轮retry全阶段、跨ordinal，
  并保留“已有后续attempt却截短历史pair”的fail-closed门禁。
- hardlink反例先以`2 failed`确认：同进程两个预打开实例和持lease实例均可在数据库新增
  硬链接后继续获取lease/写入。修复后create/open捕获实际regular-file identity，要求
  `st_nlink == 1`；lease获取前后及每个mutator事务内复检。跨目录alias、真实第二进程、
  持锁后新增alias均拒绝；删除alias且文件identity未变后允许安全继续。
- R4继续以精确反例推进：FAILED attempt 后未写terminal failure与外部resume authorization
  就创建attempt 2、事务入口检查后首个INSERT瞬间创建hardlink、retry attempt存在但删除
  causal pair，以及已提交event删除既有完整因果历史，分别先RED。修复后下一attempt只在
  同一`BEGIN IMMEDIATE`事务中接受紧邻前一FAILED attempt的唯一failure→authorization
  exact pair；完整integrity与checkpoint `from_payload`/`validate`都逐attempt重放同一规则。
  最后FAILED仍允许pre-halt、halted、authorized三个合法阶段，已提交ordinal之前的既有
  因果证据则不可删除后重hash伪装成旧checkpoint。
- 所有运行时写mutator统一通过`_begin_write`/`_commit_write`事务边界：BEGIN之后验证
  lease、数据库identity与`nlink == 1`，COMMIT前最后一次复检，失败统一ROLLBACK。静态
  枚举覆盖`append_attempt`、`initialize_agent`、`seal_initial_state`、`commit_success`、
  `record_terminal_failure`和`authorize_resume`，以及它们调用的insert/update helper。
  仅新文件的schema/binding/progress/execution初始化发生在`RunStorage`对象和lease存在前，
  作为独占create路径单列，不是运行时mutator。

### GREEN

- 新增 focused readiness：`6 passed, 90 deselected`（首轮实现证据）。
- 审查修复后storage + checkpoint + domain最终fresh：`241 passed in 24.09s`。
- 前一轮239项定向coverage：storage与checkpoint合计`1935 statements / 297 missed / 85%`；
  多周期前缀修复后的最终coverage留给独立发布复审重跑。
- 审查修复后最终fresh平台全套：`713 passed in 86.15s`；独立发布门禁待复审。
- 第二轮因果链修复后storage + checkpoint最终fresh（含完整授权后生命周期）为
  `194 passed in 18.20s`。
- 第三轮三个P1的新RED/GREEN定向为`5 passed`；首次storage+checkpoint回归为
  `198 passed, 2 failed`，两项旧fixture分别保留了后续retry却截短历史pair、以及FAILED
  attempt后无halt/auth直接创建下一attempt，与新冻结因果规则冲突；fixture按exact pair
  修订后定向`2 passed`。最终fresh storage+checkpoint为`200 passed in 31.66s`，仓库根
  cwd的storage+checkpoint+domain+state+feed为`299 passed in 38.12s`，完整平台为
  `736 passed in 110.34s`；Ruff、format check、pip check和diff check全部通过。
- 同一storage/checkpoint/domain/state/feed组合从`platform/`与仓库根分别运行，均为
  `292 passed`（32.17s / 37.52s），跨进程helper不再依赖调用cwd。
- 本轮完整平台最终fresh：`730 passed in 86.94s`；storage + checkpoint定向coverage为
  `2146 statements / 328 missed / 85%`，193项全部通过。
- R4核心RED→GREEN为`5 passed`；补充已提交因果历史反例再次先RED后GREEN。最终
  storage+checkpoint（含格式化后复跑）为`207 passed in 27.00s`，仓库根核心为
  `306 passed in 46.42s`，完整平台为`743 passed in 125.61s`。Windows真实lease/
  hardlink/跨进程/crash路径定向通过；POSIX分支在Windows仅作受控结构探针，不冒充
  真实`fcntl`运行证据。Ruff check/format check、pip check与diff check全部通过。
- R5 foreign identity四组反例首先为`4 failed`：foreign failure run、foreign
  authorization run、二者self-consistent重hash后的foreign run均被journal误报为
  `retry_same_event`，foreign ordinal pair则可错误追加attempt 2。修复后causal typed
  replay、journal和同一`BEGIN IMMEDIATE`内的retry gate均重复验证binding run、当前
  ordinal、派生event ID、failure/auth彼此identity及既有attempt/hash闭包；四组均GREEN，
  attempt 2无落行且integrity fail closed。
- R5 create/open反例首先为`2 failed, 2 skipped`：旧create未走no-replace安装，受控
  竞态可绕过钩子；旧open在identity检查与SQLite连接之间交换路径后仍错误成功。修复后
  create只在同目录唯一`O_EXCL`临时regular file上初始化完整SQLite，关闭后用hard-link
  no-replace原子安装，再删除自己的临时目录项并进入统一hardened open；任何已有目录项
  与并发获胜者都不覆盖，失败只清理自己的temp。open先以POSIX `O_NOFOLLOW`或Windows
  稳定`r+b` handle捕获regular/`nlink == 1` identity，再以SQLite URI `mode=rw`连接，
  连接前后比较handle/path identity并把handle保留到`RunStorage.close()`；所有write仍在
  事务入口与commit前复检。Windows受控交换由稳定handle直接阻止，连续失败open后仍可
  replace/unlink，证明connection与identity handle异常路径均释放。
- 最终identity审计又发现安装成功到统一hardened open之间仍需携带create所安装inode的
  闭包；受控替换反例先`1 failed`，证明仅由open重新捕获identity会接受一份内容相同但
  inode不同的替换文件。修复后create在temp→target link期间验证两路径同inode/`nlink=2`，
  删除temp后验证target `nlink=1`，并把该expected identity传入hardened open；连接前若
  inode已变立即关闭handle并拒绝。定向create/open组为`5 passed`。
- R5最终fresh：storage `126 passed, 2 skipped`；storage+checkpoint
  最终`214 passed, 2 skipped`；仓库根核心`313 passed, 2 skipped`；完整平台最终
  `750 passed, 2 skipped in 120.74s`。storage+checkpoint定向coverage为
  `2351 statements / 362 missed / 85%`（storage 84%，checkpoint 85%），214项通过。
  Ruff check、format check、pip check与diff check均通过。两个skip仅为当前Windows
  环境无法创建dangling symlink及真实POSIX smoke，不能解释为Linux验证。
- R5交付前独立fresh复跑：foreign/create/open identity专项`10 passed, 1 skipped`；
  storage+checkpoint `214 passed, 2 skipped in 36.02s`；仓库根核心
  `313 passed, 2 skipped in 54.53s`；完整平台`750 passed, 2 skipped in 132.19s`。
  定向coverage再次得到`2351 statements / 362 missed / 85%`（storage 84%，
  checkpoint 85%），且Ruff check、format check、pip check与diff check再次全部通过。
  所有本轮pytest cache、basetemp与coverage data均使用唯一系统临时目录并已清理；Git
  工作树仍严格只有本工作包既定7个文件。

所有测试使用系统临时目录作为 `basetemp` 与 pytest cache，未把运行数据库、lease、
checkpoint 或原始响应写入 Git。

## 已实现能力

1. `private_updates_for_agent(agent_id)` 从 round 0 开始，按 sequence 严格连续地进行
   typed/hash/event provenance 重放，并返回不可变 tuple；最终结果必须重放至 current
   private state。
2. `current_event_journal()` 返回 typed `EventJournalState`：current event identity、
   ordinal、next attempt index、latest typed transition 和证据导向 resume state；不包含
   max retries 或 timeout 默认。
3. SQLite `execution_state` 是执行真相的动态投影，表达 RUNNING/FAILED/COMPLETE、
   event IDs、status counts、failed IDs、next/current event，并保存 canonical payload/hash。
   attempt 生命周期随 attempt 事务更新；成功事件投影与 event/private/public/cursor/
   progress/chain 在同一事务中更新。baseline manifest payload/hash 保持不变。
4. `record_terminal_failure(...)` 只接受调用方显式给出的 reason、policy ID/hash 和
   timestamp。halt后所有事件写fail closed；只有调用方显式追加canonical/hash-bound
   `ResumeAuthorizationEvidence`才能把FAILED恢复为RUNNING。授权绑定稳定ID、run/event/
   ordinal、前一terminal failure hash、外部policy ID/hash和timestamp；不推进ordinal，
   不修改private/public/cursor/progress/chain，也不决定重试上限、timeout或model seed。
5. `RunLease` 使用标准库跨平台 advisory file lock：POSIX直接以`O_NOFOLLOW`打开真实
   SQLite数据库inode，验证regular/identity/`nlink == 1`后使用`fcntl.flock`，使路径别名
   不能转成独立sidecar锁域；Windows保留sidecar，但拒绝reparse point，并把OS锁绑定到
   经handle/path identity与link count核验的稳定打开句柄。`msvcrt.locking`与进程内
   registry共同封闭同进程第二实例竞态。context exit、
   storage close 和进程崩溃均释放 OS lease。所有实例写mutator在`BEGIN IMMEDIATE`内
   验证当前实例持有lease；只读接口无需lease，且不会默认自动获取。测试覆盖同进程、
   第二进程直接mutator拒绝及crash后新owner写入。数据库自身另绑定稳定文件identity并
   要求link count恰为1；不可靠或多硬链接环境fail closed，防止不同alias绕过lease路径。
   Windows真实测试确认持有句柄期间sidecar不能被unlink/recreate。POSIX的真实`fcntl`
   行为仍需Linux发布门禁复跑；当前Windows测试只证明该分支打开并键控数据库自身inode。
   对同权限恶意进程在入口与提交前两次检查之间瞬时create-delete hardlink的极窄窗口，
   标准库跨平台接口无法给出持续内核通知，因此仍是明确OS边界，不将双复检夸大为完全消除。
   同理，POSIX上同权限攻击者若能在两次路径检查之间swap并restore，stdlib `sqlite3`
   无法直接从既有fd建立连接；持有原inode handle、SQLite `mode=rw`、连接后复检、inode
   lease及每次写双复检把窗口压缩并对持久替换fail closed，但不宣称消除该瞬时边界。
6. `recovery_evidence()` 与 `build_checkpoint()` 在单一 SQLite read transaction snapshot
   内读取，避免多表混合视图。该事务只包围本地恢复读取，绝不跨模型调用持有。

## schema 与恢复边界

统一因果链字段加入后，run storage 升为`paper1.run-storage.v5` / SQLite
`user_version=5`；checkpoint保持`paper1.checkpoint.v2`，新增完整统一因果前缀及root，
并从attempt/evidence前缀重放execution/current failure/current authorization。旧v4/v3/v2
store和checkpoint v1没有这些权威证据，open/load时
继续 fail closed；本工作包不猜测迁移语义。当前尚无正式实验 run，后续如需保留开发期
v2 mock 数据，应另建经过规格批准、带 hash 重算证据的显式迁移工具，而不是静默补表。

本轮R5没有改变任何表或持久payload字段，因此storage仍为v5、checkpoint仍为v2，
不做无语义依据的版本提升。

## 待独立Linux发布验证

Windows本轮只验证了Windows真实稳定handle/sidecar/lease行为。可在真实Linux仓库
`platform/`目录直接运行以下focused入口；在获得实际输出前保持“待验证”，不得把
Windows结构探针记为POSIX运行证据：

```bash
python -m pytest -q tests/test_storage.py \
  -k "posix_open_identity_smoke or posix_lease_branch or run_lease_is_exclusive_across_processes or hardlink"
```

## 未实现（刻意保留）

- `P1_TIMEOUT_RETRY`；
- `P1_MODEL_SEED_PAIRING`；
- 重试上限、timeout分类及自动恢复政策；
- engine、模型请求、并发 run 调度；
- checkpoint 频率和正式实验参数。

## N=50,000 性能证据边界

现有N=50,000测试只构造50,000-slot frozen schedule，并在`next_event_ordinal=0`的空执行
状态构建一次checkpoint；它验证大schedule/空state边界，不代表执行、重放或checkpoint了
50,000个event。真实50,000 events、累计sweep checkpoint频率与总成本留到Phase 4B-9
性能/集成验证，本文档不据此声称主实验吞吐已验证。
