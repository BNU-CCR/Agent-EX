---
status: complete / independently reviewed
authority: Phase 4B-8C-3 implementation evidence; subordinate to the frozen protocol/specification chain
date: 2026-09-02
---

# Phase 4B-8C-3｜完整事件证据管线

## 边界

- 本阶段完成 mock event 从事件输入、策略、adapter 绑定、请求、调用响应、解析到终态提交的
  typed/hash-bound 持久证据链，并将其接入既有严格串行 lifecycle engine。
- SQLite schema 为 `paper1.run-storage.v6`。正常 v6 open/execution 路径在写入前拒绝 v5，
  不迁移、不补造缺失证据，并保持被拒文件字节不变。
- 新生成 checkpoint 为 `paper1.checkpoint.v4`；恢复验证显式兼容历史
  `paper1.checkpoint.v3`。v4 的策略证据投影绑定 `event_id`，v3 保留历史原始 row-hash
  语义；exact/current 与 stale-prefix 都按 checkpoint 自身版本重建。v2 与未知版本继续
  fail closed。
- 运行仍为 deterministic mock-only：没有网络访问、真实模型调用、vLLM、Qwen3-8B 或正式
  inference 配置。本阶段不能据此宣称已经具备正式实验运行条件。

## 提交边界

本阶段代码从设计/计划边界 `7e90fbb` / `a784f55` 后开始，已实现提交截至
`705b9a8fdd9bb45278e74af9278bb5878a45a08d`：

1. Task 1，immutable execution-evidence contracts：`94daf69`–`89f70da`。
2. Task 2，pre-invocation mock attestation 与 persisted-response capability：
   `0a6c777`–`4228040`。
3. Task 3，SQLite v6 schema 与 v5 byte-identical rejection：`48b6ba8`–`7f10fbd`。
4. Task 4，atomic evidence writes/readers 与 full finalization replay：
   `d6c7870`–`79a1869`。
5. Task 5，status-conditioned integrity、ordered evidence roots 与 checkpoint binding：
   `bdf188c`–`99033e7`。
6. Task 6，lifecycle evidence hooks 与 persisted invocation zero-resend recovery：
   `3b9a92c`。
7. Task 7，thin feed-memory-prompt-adapter-parser pipeline：`65d4f42`–`aa471a2`。
8. Task 8，failure/retry/reopen/tamper matrix、公开 reconciliation 与 checkpoint
   v4/v3 version split：`6db716c`–`705b9a8`。

Task 7 的完整门禁为 `942 passed, 2 skipped`；Task 8 最终新增修复后的完整平台门禁为
`979 passed, 2 skipped`。中间修复提交是审查问题的可追溯边界，不压缩或改写历史。

## 已验证的 durable crash prefixes

`tests/test_pipeline.py::test_reopen_resumes_exact_durable_prefix_without_blind_resend`
以真实 `close()` / `RunStorage.open()` 覆盖四个前缀：

- `after_pending`：尚未调用 adapter；恢复时仅调用一次，复用同一 event/request identity。
- `after_invocation`：invocation 已持久化、finalization 未落地；恢复时 adapter 调用为零。
- `after_terminal_success`：完整 SUCCEEDED attempt 已落地、event 尚未提交；恢复时 adapter
  调用为零。
- `after_sqlite_commit_before_context`：event/state/cursor 已原子提交、进程内 prompt context
  尚未推进；重新打开后从 SQLite 权威前缀重建，adapter 调用为零。

`tests/test_pipeline.py::test_reopen_in_progress_without_invocation_requires_explicit_reconciliation`
验证 `after_in_progress` 且没有 invocation evidence 时绝不盲重发，event prefix 与游标保持
不变。公开 `MockEventPipeline.execute` 要求调用方显式传入无默认值的 `reconciliation`；
`test_reopen_in_progress_accepts_exact_public_reconciliation_without_adapter_call` 验证真实重开后
exact reconciliation 可完成提交且 adapter 调用为零。

request、attempt、response 或 adapter binding 错配、非 IN_PROGRESS 状态提供 reconciliation、
以及已经存在 invocation evidence 时再次 reconciliation 均在写入新 evidence 前原子拒绝。
pipeline 只把 reconciliation 透传给 lifecycle engine，不复制第二套恢复判定。

## 失败、重试与原子性证据

- malformed response 保存 raw response 与完整 parse failure evidence；timeout 保存
  `ParseNotApplicableEvidence`。两者都不推进 private state、public post、feed cursor、
  event ordinal 或 event chain。
- `FinalizedAttemptEvidence` 在事务写入前做完整 typed replay。terminal request、attempt、
  response 与 parse request/attempt/response 六类错配均无部分写入。
- 显式授权重试保持相同 event identity 与 event-input evidence，使用 next attempt identity；
  request 参数变化只允许已冻结 policy 指定的叶路径。mapping/list/tuple 使用 canonical
  语义，非法 key alias 与数组歧义 fail closed。
- `model_seed` 只能通过明确授权的 retry drift 改变；未授权改变被拒。代码没有填入 retry
  limit、timeout、model seed、B、K 或 checkpoint cadence 默认值。

## 完整性、篡改与 checkpoint 证据

- v6 integrity/open gate 覆盖删除、orphan、extra row、错误 hash 与“重算局部 hash 后伪造”
  的篡改矩阵，并按 lifecycle status 验证 exact-cover。
- checkpoint 将 `event_input_evidence`、`attempt_policy_evidence`、
  `adapter_execution_bindings`、`adapter_requests`、`invocation_evidence`、
  `parse_evidence` 六组证据纳入有序 projection/root。
- 两个完整事件验证五张逐事件表的顺序绑定；调换行并重算内部 root 与外层 checkpoint hash
  仍与 SQLite 权威顺序冲突。run 级 adapter binding 保持单行绑定。
- legacy v3 fixture 在同一两事件 SQLite 上同时验证 current/exact 与较早 stale-prefix；新 v4
  对重复 policy row hash 仍通过 event identity 得到不同 commitment，避免跨事件重排歧义。
- prompt context 正常执行按事件增量维护；重开时仅从 SQLite 已提交前缀线性重建一次。该缓存
  是可丢弃派生状态，不是恢复真相来源。

## 2026-09-02 本地门禁

- 实现者最终 full suite：`979 passed, 2 skipped`。
- 实现者 focused evidence/pipeline/storage/checkpoint：`418 passed, 2 skipped`。
- 实现者 combined lifecycle matrix：`436 passed, 2 skipped`。
- 独立规格复核：focused `100 passed`；pipeline/storage/checkpoint
  `375 passed, 2 skipped`；P0–P3 均无，批准。
- 独立质量复核：新增 reconciliation/version gates `16 passed`；focused
  `418 passed, 2 skipped`；P0/P1/P2 均无，批准。仅记录非阻塞 P3：少量测试为白盒验证
  使用私有 helper/connection，部分 fixture 未统一 context-managed close。
- 主会话 fresh isolated full suite：`979 passed, 2 skipped in 162.83s`。
- Task 9独立release verification：`979 passed, 2 skipped in 152.89s`；P0/P1/P2无，批准。
- Task 9独立规格/反模式复核：`979 passed, 2 skipped in 172.39s`；P0/P1/P2无，批准。
- Task 9独立代码质量复核：`979 passed, 2 skipped in 166.74s`；P0/P1/P2无，批准。
- Ruff check、Ruff format check（47 files）、`pip check`、`git diff --check` 全部通过。
- 两个 skip 是既有 Windows 条件边界。本次 full suite 另出现一条既有 `.pytest-tmp`
  cache 权限 warning；测试使用独立系统 `basetemp`，结果不受影响。Windows 结果不能替代
  正式发布前要求的真实 Linux/云端环境复验。
- 最终复核保留的非阻塞P3：部分性能/legacy/reconciliation测试依赖私有helper或connection，
  少量fixture未统一显式close；checkpoint v6 projection在完整校验后按event/attempt逐点查询。
  前两项为测试维护性，后一项不是event热路径，但必须在4B-9真实50,000-event累计checkpoint
  门禁中测量，不能由当前较小测试外推。

## 明确保留到 Phase 4B-9

Phase 4B-8C-3 只证明单 run 严格串行 mock evidence pipeline 的正确性与可恢复性。以下门禁
尚未完成，因此当前状态仍是“本机平台代码继续搭建中”，不是“可正式跑主实验”：

1. 完整 `identity 2 × continuity 2 × exposure 3 = 12 cells` mock matrix。
2. N=20、N=100、N=1000 的 deterministic replay、跨 cell 不变量、隐私与因果一致性门禁。
3. N=1000、T=50，即 50,000 个真实 mock events 的累计执行、checkpoint、重开、内存与
   吞吐测量；现有 50,000-slot empty-state 测试不算这项证据。
4. checkpoint cadence、timeout/retry policy、model seed pairing、B/K 精确值等所有仍在
   `UNRESOLVED[...]` 的研究/运行参数，须经 Phase 0 冻结后才能进入 formal config。
5. Linux/云端目标环境复验，以及后续真实 Qwen3-8B BF16、non-thinking、vLLM 接入与
   revision 冻结；API 仍只允许作为固定 snapshot 外部稳健性子集。

原始大规模结果、数据库、模型响应与运行缓存不得进入 Git；后续只提交 manifest、hash 与
归档定位。任何实际执行与冻结机器协议不一致的 run 必须标记为偏离并停止进入主分析。
