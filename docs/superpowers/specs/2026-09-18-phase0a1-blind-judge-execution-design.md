---
status: approved design; independent specification review revision 1 pending
authority: Phase 0A-1 post-run blind-judge execution design; subordinate to the approved six-group packet, immutable v2 run evidence, and frozen semantic-review policy
approved-by: user
approved-date: 2026-09-18
supersedes: ad hoc or synthetic judge execution for the real Phase 0A-1 v2 run
---

# Phase 0A-1 盲态 Qwen Judge 执行设计

## 1. 目的与当前边界

Phase 0A-1 v2 云端校准已经完成 816 个逻辑 case，并导出：

- 797 个可进入语义复核的 judge items；
- 174 个确定性分层人工样本；
- 一个 `awaiting_codes` 的 `SemanticReviewBundle`；
- 与该 bundle 严格绑定的 human/judge coder packs。

当前平台已经能导出和导入盲审合同，但没有真实调用固定 Qwen judge、保存原始输出证据、
解析标签并生成 `IndependentCode` 的可恢复执行器。本设计只补齐这一缺口。它不重跑
816-case probe，不改变 probe response、parse evidence、case inventory、六组批准 hash、
environment lock 或 run manifest，也不授予正式 Paper 1 主实验权限。

人工样本必须由人类编码者独立完成。平台不得用 judge 输出填充人工记录，不得在 174 项
人工编码完成前把部分 judge 或人工结果导入最终 review bundle，也不得 seal 或选择议题。

## 2. 不可变输入与授权层级

### 2.1 既有不可变输入

受信控制面必须重新打开并严格验证以下输入：

1. approved six-group packet 及其 affirmative hash；
2. v2 cloud run manifest 及其 affirmative hash；
3. v2 durable run store 和完整 projection；
4. `blind-review-export.json` 及其 `BlindReviewExport.export_hash`；
5. 独立的 `SemanticReviewBundle.record_hash`；
6. judge coder pack、pack index 的 `record_hash`，以及 index 中绑定的
   `review_bundle_hash`；
7. `SemanticReviewPolicy`、judge `CoderContract`、797 个 item identity 和顺序；
8. supporting material 中的 judge prompt、ordering policy、classifier contract 及各自 hash；
9. 已批准环境锁的 hash；该锁只作为不可变引用，不得被本阶段改写。

任何 item、顺序、visible allowlist、模型 revision、prompt、标签集合或 hash 不一致都必须在
首个 judge 请求前失败。职责必须分离：受信的 `review-materialize-judge` 控制进程可以读取完整
bundle 和 hidden bindings，只用于验证来源、exact cover 和生成去盲后的 judge-only pack/index；
真正发送请求的 blinded runner 只能获得 judge-only pack/index、批准的授权和执行 manifest。
runner 的文件系统/input allowlist 必须拒绝完整 bundle、human pack、hidden bindings、候选 key、
条件标签、采样状态、human selection 标志、既有人工编码和汇总结果。

### 2.2 两阶段执行授权

六组 packet 已在 816 请求前批准，不能事后改写。为避免“manifest 绑定尚未生成的启动证据”
形成循环，judge 授权分两步，二者都不得修改旧 `SemanticReviewPolicy`：

1. `JudgeAuthorization` 在启动服务前物化并由 owner 批准。它绑定静态输入、旧环境锁引用、
   runtime 预期、完整 renderer/template、重试与恢复政策；
2. 服务只可在该 authorization hash 下启动。完成 fresh preflight 后生成
   `JudgeExecutionManifest`，绑定 authorization hash、fresh environment observation/lock 和
   service-start identity。owner 对最终 manifest 完整 hash 再次明确批准后，才允许首个请求。

`JudgeAuthorization` 必须绑定完整、可逐字重建的 `JudgeRequestRenderer` artifact/hash，而不只
绑定概括性的旧 judge prompt。renderer 至少冻结：

- system/user 消息角色、消息顺序及 chat-template 版本；
- 四个 visible fields 的名称、顺序、转义、空值和 canonical serialization；
- 八个字段的完整合法标签枚举、字段顺序和 exact JSON schema；
- 正常请求与 repair 请求的完整模板；
- renderer 版本、canonical JSON 算法以及每 item seed/request identity 派生算法；
- generation settings 和响应字节上限。

发布门必须包含至少一个完整 rendered-request golden fixture 及其 hash。旧 `JUDGE_PROMPT` 只作
上位语义约束，不能替代 renderer artifact。`JudgeExecutionManifest` 至少绑定：

- review bundle/export/judge pack hash；
- judge coder contract、旧 prompt、完整 renderer、ordering、classifier contract hash；
- 模型、tokenizer、chat template、vLLM runtime 和固定 revision；
- non-thinking 服务参数；
- 显式 generation settings、连接/读取/整次请求 timeout、retry budget 和 backoff；
- 每次请求只含一个 item、严格顺序、最大 item 数 797、每 item 显式最大 attempt 数；
- 旧环境锁 hash、fresh environment observation/lock hash、preflight hash 和 service-start
  identity hash；
- archive URI、source commit、calibration-only 和 no-formal-authority 标记。

不得在代码中为缺失字段提供研究默认值。任何 fresh observation 与 authorization 预期漂移都
必须在首个请求前失败；改变环境必须创建新的 authorization、manifest、archive 并重新批准。
旧六组批准只授权 probe，不自动授权新的 authorization 或 judge manifest。

## 3. 模块边界

### 3.1 Judge 合同与 projection

新增独立的 `judge_execution` 模块，负责下列严格类型：

- `JudgeExecutionManifest`：上述后置授权；
- `JudgeAuthorization` 与 `JudgeRequestRenderer`：上述两阶段授权和逐字请求合同；
- `JudgeRequestEvidence`：item、prompt、label schema、generation settings 和顺序身份；
- `JudgeResponseEvidence`：provider request ID、时间、termination、token、原始输出及 hash，
  或不含原始文本的 typed transport error；
- `JudgeParseEvidence`：严格 JSON 对象解析、八个维度 exact-cover、合法标签和失败代码；
- `JudgeAttemptEvidence`：request/response/parse 的单一不可变组合；
- `JudgeDispatchReconciliation`：unresolved dispatch 的 typed、签名式裁定证据；
- `JudgeRunProjection`：按 approved order 从 intents、attempts、resolutions 和 reconciliation
  重放得到 797 项状态；
- `JudgeEvidenceIndex`：每个 judge code record hash 到 manifest、request、intent、attempt、
  response、parse、raw artifact identity/hash 的 exact mapping；
- `HumanCodingRecord` 与 `HumanEvidenceIndex`：人类表单来源及转换证据；
- `IndependentCodeSetV2`：绑定 judge/human evidence index hash 的 971-record 完整集合。

这些类型只服务 Phase 0A-1 calibration review，不复用正式 event engine，也不把 judge
标签混入 probe attempt store。

### 3.2 Transport adapter

新增 loopback-only judge adapter。它可复用项目已有的底层 HTTP、deadline、request-ID、
model identity 和原始字节限制模式，但不得复用 `ProbeRequest` 的 stance/confidence parser。
每个请求只包含 renderer 已冻结的：

1. 完整、hash-bound judge system prompt；
2. 当前 item 的四个 visible fields；
3. 当前 policy 的八个维度、全部合法标签与字段顺序；
4. exact JSON schema 或同样冻结的 repair template。

一个请求只处理一个 item。不得携带先前 item、先前 judge code、人工 sample 标记、候选优先级
或任何 aggregate result。服务端必须是 `127.0.0.1`，模型身份必须等于 manifest；返回缺少
provider request identity 时按失败处理。

### 3.3 Append-only judge store

judge 证据写入 v2 archive 旁的新目录，不写入 Git，也不改动 probe store：

```text
/root/autodl-tmp/agent-ex-phase0a1-judge-v1/
  staging/manifest.json
  staging/attempts/<hash>.json
  staging/dispatch/<hash>.json
  staging/reconciliation/<hash>.json
  staging/projection.json
  staging/raw/<hash>.json
  staging/judge-evidence-index.json
```

每次发送前先原子写入 dispatch intent；收到并验证输出后写 raw artifact、attempt 和 dispatch
resolution，再推进 projection。raw artifact 只在外部 archive 中保存，日志和用户消息不得输出
响应正文。文件名、内容 hash 和 projection 列表必须 exact-cover。

## 4. 状态机、重试与恢复

每个 item 的状态和 attempt budget 只允许按下列完整转换累计：

```text
unstarted -> intent_durable -> dispatched -> response_durable -> coded
                         |              |             -> retryable_parse_failure -> intent_durable
                         |              -> retryable_runtime_failure -----------> intent_durable
                         -> reconciled_not_sent -------------------------------> intent_durable
                         -> reconciled_response -> response_durable
                         -> ambiguous_incomplete

retryable_* --budget exhausted--> terminal_failed
```

- 合法 JSON 且八维 exact-cover 才能成为 `coded`；
- “一个请求一个 item”不等于“一个 item 只能尝试一次”；所有正常/repair attempt 都累计进该
  item 的 manifest 预算，任何路径不得重置计数；
- format/label 错误只能按 manifest 中冻结的 repair policy 和预算重新请求同一 item；
- timeout、429、provider error 等只按 manifest 的 typed policy 与预算重试；
- OOM、模型身份漂移、缺少 request ID 或预算耗尽 fail closed；
- `coded` 是不可逆状态，恢复不得再次发送；
- intent 已 durable 但缺少 durable response/resolution 即为 unresolved dispatch，自动恢复必须
  拒绝。`judge-reconcile` 只接受两类可验证裁定：(a) 从 provider audit log 按冻结 request ID
  找回精确 response bytes/identity/hash，生成 `reconciled_response`；(b) 用 provider/transport
  证据证明请求未发送，生成 `reconciled_not_sent` 并授权在原 item identity 下创建新的 attempt
  identity。无法证明任一结论时写入 `ambiguous_incomplete`，禁止重发；
- `JudgeDispatchReconciliation` 必须绑定 manifest、item、intent、request identity、证据 locator/
  hash、裁定枚举、操作者、时间和自身 hash。provider request identity/idempotency key 在
  authorization 中冻结，恢复不得派生出会被误认为首次发送的身份；
- `ambiguous_incomplete` 或其他不可调和证据不能混入新运行。若必须重跑，须关闭当前 archive，
  新建 authorization、manifest、archive 并取得 owner 批准，从零执行完整 797 项。

`resume` 必须重新验证 manifest、当前服务身份、完整 append-only prefix 和 approved order，从
durable attempts 重建 projection。恢复输出使用新的 create-only 控制文件，不能覆盖先前输出。

## 5. CLI 与服务生命周期

在现有 `agent-ex-phase0a1` 命令面上新增窄命令：

- `judge-manifest`：从已批准输入物化后置执行 manifest；不访问模型；
- `review-materialize-judge`：受信控制面验证完整 bundle，并输出 runner-only judge pack/index；
- `judge-authorization`：物化静态授权和完整 renderer；不启动模型；
- `judge-run`：只允许空 judge store，执行 797 项；
- `judge-resume`：只恢复同一 manifest 的非终态 store；
- `judge-reconcile`：依据 provider/transport 证据生成 typed reconciliation；
- `judge-verify`：重放全部证据并核对 exactly 797 terminal coded items；
- `judge-export-codes`：只在 verify 通过后创建 797-record judge code-set 与
  `JudgeEvidenceIndex`；
- `human-export`：从已批准 human coder pack 生成便于填写的视图和空白记录模板，不填标签；
- `human-import`：验证完成的 174 项表单并生成 human IndependentCode records 与
  `HumanEvidenceIndex`；
- `human-verify`：验证 exact sample cover、合法标签、coder identity、source form hash、记录 hash；
- `review-compose-codes`：只把 exactly 797 judge + 174 human 合成为一个 971-record v2 set，
  绑定两个 evidence index hash 并证明 exact cover；不得手工拼 JSON。

vLLM 必须通过审计过的 service lifecycle 启停。启动前验证端口空闲、GPU、固定模型 artifacts、
runtime、已批准 authorization；启动后把 fresh observation 和 start identity 写入新的 judge
manifest，待其批准后才发送请求。运行完成或失败后记录 stop evidence，并确认端口 8000 关闭、GPU
计算进程为零。服务停止后 AutoDL 可关机，人工编码可离线继续。

## 6. 完整导入门

`review-import` 仍是唯一正式导入入口，但必须显式扩展为验证 v2 evidence，而不是假设现有 v1
足够。legacy `paper1.calibration.independent-code-set.v1` 只保留给历史/offline synthetic 路径；
真实 Phase 0A-1 judge 必须使用 `paper1.calibration.independent-code-set.v2`。v2 顶层绑定
`judge_evidence_index_hash`、`human_evidence_index_hash`、两个 affirmative index locator/hash、
review bundle/export hash、coder contracts 和 971-record hash。

`review-import` 必须读取并逐条 dereference 两个 index 指向的外部证据，验证 judge manifest、
request/intent/attempt/response/parse/raw artifact 和 human source form/record 的内容 hash；仅比较
code record 自身 hash 不足以通过。locator 只作定位，内容 hash 才是身份；缺失、不可读取、错配
或额外证据均 fail closed。

judge code-set 必须满足：

- exactly 797 records；
- 每个 approved judge item exactly once；
- coder ID/role/contract、export hash、item hash 全部匹配；
- judge request/order/provider-output identity 完整；
- raw evidence hash 与外部原始输出 artifact 匹配；
- 所有记录 `status=completed`，无缺失、失败或额外 item。

每个 `HumanCodingRecord` 必须 canonical 地绑定 item、coder contract/identity、八维标签、编码
时间、source form hash 和自身 record hash。`human-import` 是从完成表单到这些记录及
`HumanEvidenceIndex` 的唯一转换/签名边界。

human code-set 必须满足 exactly 174 records，且只覆盖分层样本。judge 与 human 必须分别完成
并验证后，由 `review-compose-codes` 合成一次 971-record v2 set，才可执行一次完整 import。任何
partial code-set 只能保留在外部 staging，不得调用 `review-import`。若两者在任一维度分歧，按
冻结 policy 进入 adjudication；缺失 adjudication 时 review 状态保持 incomplete。

## 7. 失败处理与测量边界

- judge 失败不改变 816-case probe 的完成状态，只使 semantic review incomplete；
- 不得因 judge 输出不利而改 prompt、标签、generation settings、retry 或 sample；
- 任何运行合同修订都要新 manifest、新 archive 和新批准，不得混合 attempts；
- 19 个 probe `parse_failed` case 不进入 eligible judge items；它们仍保留在 probe 完整性统计，
  不得伪造 judge code；
- 同一个 Qwen3-8B 被用作盲态 model judge，只能解释为冻结自动编码器，不声称是独立人类判断；
- 174 项人类复核与 agreement/adjudication 是自动编码质量控制的必要组成部分。

## 8. 测试与发布门

实现必须以 TDD 覆盖：

1. manifest 的 exact hash、旧 policy 从属关系和禁止默认值；
2. visible allowlist、标签 exact-cover、单 item 请求和 prompt/order hash；
   完整 rendered-request golden/hash、roles、serialization、schema 和 seed 派生；
3. success、invalid JSON、非法/缺字段标签、refusal、timeout、429、OOM、identity drift；
4. intent-before-send、attempt/resolution exact-cover 和 unresolved dispatch fail-closed；
   provider-log response recovery、proved-not-sent retry 与 ambiguous terminal 三个 crash window；
5. stop/resume 在多个断点与 uninterrupted projection/hash 等价；
6. 797 个 judge items 的 deterministic order、零重复、零遗漏；
7. code-set 完整导出、partial import 拒绝，以及 review-import 对 raw/judge evidence 的真实
   dereference（缺失或篡改 raw artifact 必须失败）；
8. 174 项 human template/sample exact-cover，human form -> IndependentCode -> evidence index ->
   797+174=971 compose/import 的端到端测试，且平台不会自动填人类标签；
9. runner 文件系统/input allowlist 测试，证明无法访问 full bundle/human pack/hidden bindings；
10. authorization -> fresh service observation -> manifest 的 hash 链与环境漂移拒绝；
11. service stop、port/GPU idle 和 raw evidence 不进入 Git；
12. 现有 Phase 0A-1、cloud run、legacy v1、review/import/seal 与全仓回归。

真实执行前还必须完成规格复核、代码质量复核、fresh focused/full tests、Ruff、format、pip、
diff 和 tracked-artifact hygiene。最终上传 bundle、`JudgeExecutionManifest.record_hash` 和任何新的
完整授权 hash 都须在首个 judge 请求前由 owner 明确批准。

## 9. 完成定义与后续顺序

本阶段完成必须同时满足：

1. 797 个 judge items 的完整、可验证 code-set；
2. 174 项 human template 已导出，人工记录尚未完成时明确保持 waiting；
3. judge service 停止且证据归档；
4. 不导入 partial codes、不 seal；
5. Git 只记录代码、manifest/hash、计数和外部 archive locator，不记录 raw outputs。

随后顺序固定为：人工编码 174 项 → 验证 judge/human 两套完整记录 → 一次性 import → 必要的
adjudication → gate report/topic selection → seal → Phase 0A-1 checkpoint。只有该 checkpoint 完成后，
才讨论 Phase 0B 和正式实验参数冻结。
