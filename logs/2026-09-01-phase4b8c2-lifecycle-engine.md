---
status: implementation and local release gates complete; pending independent review and commit
authority: Phase 4B-8C-2 implementation evidence; subordinate to frozen protocol/specification chain
date: 2026-09-01
---

# Phase 4B-8C-2｜单事件生命周期内核

## 边界

本工作包实现 `StrictSerialLifecycleEngine`，仅负责单run、单event、单attempt的严格串行
生命周期。它不是完整feed/prompt engine，不连接网络或真实模型，不选择重试上限、timeout、
model seed、B/K或checkpoint频率。C3仍须补齐上下文构建及其完整provenance持久化；本工作包
不得据此宣称Phase 4B-8全部完成。

## 已实现

- engine作为context manager持有storage v5全run OS lease；获取lease时主动完整回放SQLite
  integrity一次，`execute()`不再主动逐event调用`verify_integrity()`，异常退出和`close()`可靠
  释放。显式checkpoint仍通过storage snapshot执行完整校验。storage仍会累计序列化`event_ids`
  等运行级证据，因此这里不宣称整体O(E)或已经通过50,000 events性能门禁；该门禁留给4B-9。
- typed边界包含`AttemptAuthorization`、`PreparedAttempt`、`AttemptExecutionEvidence`、
  `AttemptInvocationResult`、`AttemptLifecycleFailure`、`SuccessfulEventCommit`和
  `AttemptOutcome`。所有时间、HTTP状态、provider metadata、usage、finish reason、模型身份、
  参数hash、model seed及resume authorization均由调用方显式提供；没有200/0/stop/now默认值。
- 新attempt只按当前journal写`PENDING → IN_PROGRESS → terminal`；PENDING恢复要求完全相同的
  sealed request，IN_PROGRESS恢复必须提供显式provider reconciliation且绝不盲重发。
- FAILED只落attempt/execution证据，不推进private/public/cursor/progress/event chain；kernel
  不自动halt或retry。retry只接受当前event、next attempt index和exact resume authorization hash。
- 已落地SUCCEEDED恢复不调用adapter，直接以typed commit bundle重试原子`commit_success`；
  commit builder或SQLite提交故障后仍保持landed状态，可再次恢复。
- checkpoint只通过显式`write_checkpoint(path)`构建于SQLite truth；写失败不回滚已提交SQLite，
  原文件保持完整并被正确判为stale，可重新构建current。
- 普通Python异常不会被kernel改写成虚假失败证据；可预期的adapter/parse/finalize失败必须通过
  `AttemptLifecycleFailure`携带完整、typed、hash-bound FAILED attempt。若进程在provider调用后
  未留下终态证据，SQLite保持IN_PROGRESS并要求C3 reconciliation。
- adapter返回后，`AttemptInvocationResult`要求execution metadata精确包含sealed
  `AdapterResponse`的response hash、outcome、error、runtime identity/hash及script hash；终态
  attempt再逐字段重放实际raw/hash、HTTP、provider metadata、usage、finish reason和完成时间。
  因而raw伪造、timeout/error伪装success及parse/finalize失败丢失实际raw均fail closed。
- 所有公开typed输入中的mapping/list均复制并递归冻结；调用方随后修改原始嵌套容器不会改变
  authorization、execution evidence或context provenance。reconciliation参数在非IN_PROGRESS状态
  会在prepare/invoke和journal写入前拒绝。

## TDD证据

首个测试先在collection阶段RED：`ModuleNotFoundError: agent_ex.engine`。最小公开类型GREEN后，
首个生命周期行为测试再次RED于缺少`execute`。随后每组恢复与失败行为均先加入测试再实现；
retry测试曾准确发现fixture只脚本化attempt 1却调用attempt 2，确认根因后仅修fixture。

最终focused覆盖21项：成功、typed invocation/finalize失败、PENDING exact/drift、IN_PROGRESS
reconciliation/no-reconciliation、landed success、commit fault、unauthorized/authorized retry、
complete、第二engine lease、foreign identity、lease loss、explicit checkpoint与atomic write fault。
复审新增6项回归分别覆盖实际response raw绑定、typed finalize失败保留response证据、timeout不得
伪装success、递归深冻结、错位reconciliation拒绝，以及每次engine open只完整回放一次且显式
checkpoint仍触发完整校验。最后一个测试最初RED为`verify_integrity`调用5次，移除逐event全回放
后GREEN；response/evidence伪造测试也均先RED后修复。
最终关闭复审另以RED证明未使用的`AttemptOutcome(state="landed")`会被接受，随后删除该状态并
GREEN；`prepare`回调的类型也由宽泛`object`收紧为实际`EventJournalState`。

截至日志更新前的fresh证据：

- `tests/test_engine.py`: `21 passed in 2.80s`；
- `tests/test_engine.py tests/test_storage.py tests/test_checkpoint.py`:
  `235 passed, 2 skipped in 41.59s`；
- 关闭修复前的完整平台fresh证据：`770 passed, 2 skipped in 117.55s`；最终关闭修复后的
  全量门禁由独立发布复审重跑；
- 关闭修复前的engine定向coverage：`308 statements / 59 missed / 81%`，20项全部通过；
- Ruff check、Ruff format check、`pip check`、`git diff --check`全部通过。

完整平台早期曾有且仅有一个public API精确集合RED；它来自新增engine导出尚未进入既有集合，
最小更新`test_domain.py`后关闭。复审后唯一残余focused失败是错误消息regex只接受
`response|raw`，而实现先以更强的完整execution evidence不一致拒绝；测试仅扩展为接受
`evidence`，没有弱化任何验证。

两个skip沿用storage既有Windows环境边界，不是engine新增skip。独立复审与提交仍由后续
发布步骤完成。

## 明确保留到C3/后续

- feed、memory、prompt及其源证据的构建与storage持久化；
- parser evidence到terminal attempt的正式factory；
- provider reconciliation实现与真实adapter；
- `P1_TIMEOUT_RETRY`、`P1_MODEL_SEED_PAIRING`、重试上限与timeout分类；
- checkpoint频率、跨run调度、真实50,000 events性能。
