---
status: approved design; pending independent specification review
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

执行器必须重新打开并严格验证以下输入：

1. approved six-group packet 及其 affirmative hash；
2. v2 cloud run manifest 及其 affirmative hash；
3. v2 durable run store 和完整 projection；
4. `blind-review-export.json` 和其 `SemanticReviewBundle.record_hash`；
5. judge coder pack、pack index 和各自 `record_hash`；
6. `SemanticReviewPolicy`、judge `CoderContract`、797 个 item identity 和顺序；
7. supporting material 中的 judge prompt、ordering policy、classifier contract 及各自 hash。

任何 item、顺序、visible allowlist、模型 revision、prompt、标签集合或 hash 不一致都必须在
首个 judge 请求前失败。执行器不得读取 hidden binding 中的候选 key、条件标签、采样状态、
human selection 标志、既有人工编码或汇总结果。

### 2.2 新的后置执行授权

六组 packet 已在 816 请求前批准，不能事后改写。judge 执行所需而旧 policy 未显式携带的
运行值必须进入单独、不可变、owner-approved 的 `JudgeExecutionManifest`，而不是修改旧
`SemanticReviewPolicy`。manifest 至少绑定：

- review bundle/export/judge pack hash；
- judge coder contract、prompt、ordering、classifier contract hash；
- 模型、tokenizer、chat template、vLLM runtime 和固定 revision；
- non-thinking 服务参数；
- 显式 generation settings、连接/读取/整次请求 timeout、retry budget 和 backoff；
- 每 item 一个请求、严格顺序、最大 item 数 797；
- archive URI、source commit、calibration-only 和 no-formal-authority 标记。

不得在代码中为缺失字段提供研究默认值。执行前必须物化完整 manifest、计算
`record_hash`，并取得 owner 对完整 hash 的明确批准。旧六组批准只授权 probe，不自动授权
这个新的 judge manifest。

## 3. 模块边界

### 3.1 Judge 合同与 projection

新增独立的 `judge_execution` 模块，负责下列严格类型：

- `JudgeExecutionManifest`：上述后置授权；
- `JudgeRequestEvidence`：item、prompt、label schema、generation settings 和顺序身份；
- `JudgeResponseEvidence`：provider request ID、时间、termination、token、原始输出及 hash，
  或不含原始文本的 typed transport error；
- `JudgeParseEvidence`：严格 JSON 对象解析、八个维度 exact-cover、合法标签和失败代码；
- `JudgeAttemptEvidence`：request/response/parse 的单一不可变组合；
- `JudgeRunProjection`：按 approved order 从 attempts 重放得到 797 项状态；
- `JudgeCodeSet`：只有全部 797 项都得到合法终态后才可创建的完整
  `paper1.calibration.independent-code-set.v1`。

这些类型只服务 Phase 0A-1 calibration review，不复用正式 event engine，也不把 judge
标签混入 probe attempt store。

### 3.2 Transport adapter

新增 loopback-only judge adapter。它可复用项目已有的底层 HTTP、deadline、request-ID、
model identity 和原始字节限制模式，但不得复用 `ProbeRequest` 的 stance/confidence parser。
每个请求只包含：

1. 完整、hash-bound judge system prompt；
2. 当前 item 的四个 visible fields；
3. 当前 policy 的八个维度及其全部合法标签；
4. “只返回一个 JSON 对象”的精确字段合同。

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
  staging/projection.json
  staging/raw/<hash>.json
```

每次发送前先原子写入 dispatch intent；收到并验证输出后写 raw artifact、attempt 和 dispatch
resolution，再推进 projection。raw artifact 只在外部 archive 中保存，日志和用户消息不得输出
响应正文。文件名、内容 hash 和 projection 列表必须 exact-cover。

## 4. 状态机、重试与恢复

每个 item 的状态只允许：

```text
unstarted -> pending -> coded
                    -> parse_failed
                    -> runtime_failed
```

- 合法 JSON 且八维 exact-cover 才能成为 `coded`；
- format/label 错误可按 manifest 中显式预算重新请求同一 item；
- timeout、429、provider error 等只按 manifest 的 typed policy 重试；
- OOM、模型身份漂移、缺少 request ID 或预算耗尽 fail closed；
- `coded` 是不可逆状态，恢复不得再次发送；
- 只有存在 intent、没有 durable response 的 item 才是 unresolved dispatch，自动恢复必须拒绝，
  等待人工 reconciliation；不得盲重发。

`resume` 必须重新验证 manifest、当前服务身份、完整 append-only prefix 和 approved order，从
durable attempts 重建 projection。恢复输出使用新的 create-only 控制文件，不能覆盖先前输出。

## 5. CLI 与服务生命周期

在现有 `agent-ex-phase0a1` 命令面上新增窄命令：

- `judge-manifest`：从已批准输入物化后置执行 manifest；不访问模型；
- `judge-run`：只允许空 judge store，执行 797 项；
- `judge-resume`：只恢复同一 manifest 的非终态 store；
- `judge-verify`：重放全部证据并核对 exactly 797 terminal coded items；
- `judge-export-codes`：只在 verify 通过后创建完整 code-set；
- `human-export`：从已批准 human coder pack 生成便于填写的视图和空白记录模板，不填标签；
- `human-verify`：只验证人类编码记录的 exact sample cover、合法标签、coder identity 和 hash。

vLLM 必须通过审计过的 service lifecycle 启停。启动前验证端口空闲、GPU、固定模型 artifacts、
runtime 和新的 judge manifest；运行完成或失败后记录 stop evidence，并确认端口 8000 关闭、GPU
计算进程为零。服务停止后 AutoDL 可关机，人工编码可离线继续。

## 6. 完整导入门

现有 `review-import` 仍是唯一正式导入入口。judge 执行器不得绕过它。

judge code-set 必须满足：

- exactly 797 records；
- 每个 approved judge item exactly once；
- coder ID/role/contract、export hash、item hash 全部匹配；
- judge request/order/provider-output identity 完整；
- raw evidence hash 与外部原始输出 artifact 匹配；
- 所有记录 `status=completed`，无缺失、失败或额外 item。

human code-set 必须满足 exactly 174 records，且只覆盖分层样本。judge 与 human 必须分别完成
并验证后，才可组合为一次完整 import。任何 partial code-set 只能保留在外部 staging，不得调用
`review-import`。若两者在任一维度分歧，按冻结 policy 进入 adjudication；缺失 adjudication 时
review 状态保持 incomplete。

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
3. success、invalid JSON、非法/缺字段标签、refusal、timeout、429、OOM、identity drift；
4. intent-before-send、attempt/resolution exact-cover 和 unresolved dispatch fail-closed；
5. stop/resume 在多个断点与 uninterrupted projection/hash 等价；
6. 797 个 judge items 的 deterministic order、零重复、零遗漏；
7. code-set 完整导出和 partial import 拒绝；
8. 174 项 human template/sample exact-cover，且平台不会自动填人类标签；
9. service stop、port/GPU idle 和 raw evidence 不进入 Git；
10. 现有 Phase 0A-1、cloud run、review/import/seal 与全仓回归。

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
