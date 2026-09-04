---
status: active requirements; Phase 4B mock engineering contracts implemented
authority: reproducibility contract for platform and runs; actual values come from frozen protocol, environment lock and run manifests
supersedes: ad hoc reproducibility practices in pilot notebooks
last-verified: 2026-09-04
---

# 可复现规范

## 模型身份

正式主模型路线已批准为 Qwen3-8B BF16、non-thinking、vLLM 自部署。Phase 0B 已核验候选模型 commit `b968826d9c46dd6066d109eabc6255188de91218` 与候选 `vllm==0.23.0` 的官方文档；它们在 artifact/credential/runtime smoke 和环境锁定前仍分别引用 `UNRESOLVED[P1_MODEL_REVISION]` 与 `UNRESOLVED[P1_VLLM_VERSION]`。正式运行必须固定并记录模型 repository、tokenizer revision、chat-template hash、vLLM 版本与镜像 digest、CUDA/driver/GPU、thinking 开关及全部实际传递的生成参数。滚动别名不得描述为严格可复现版本。

API 稳健性必须使用 `UNRESOLVED[P1_API_SNAPSHOT]` 的固定 snapshot；若提供方无法证明版本固定，则只能标记为时间戳化的非确定性稳健性证据。

## 运行身份

- `run_spec_hash`：规范化 protocol、run config、不可变 schedule hash、请求参数、模型身份、Git SHA 和环境 lock hash 的内容寻址。任何 schedule 坐标变化都必须改变 `run_spec_hash`。
- `run_id`：`run_spec_hash + replicate_seed + launch_nonce`。
- `event_ordinal`：run内从0开始连续的全局激活序号；sweep与agent_id仅为属性。
- `event_id`：`run_id + event_ordinal`，作为逻辑事件幂等键。
- `attempt_id`：`event_id + attempt_index`；重试追加而不覆盖。

每个 attempt 必须保存 exposure、渲染 prompt、请求参数、provider request ID、原始响应 body、客户端可得的响应 headers 与 HTTP status、解析、错误、usage、finish reason、时间戳和内容 hash。

## 随机性

population、initial stance、initial reason、WS/node mapping、shadow graph、attention、
expression、activation、publish、round-0 tiebreak、message slots和model sampling使用
相互分离的seed namespace。键的作用域由component注册表确定：跨cell共享的activation、
publish和message-slot制品按
`(matched_seed, common_scope, event_ordinal, component)`派生；只有cell特异随机过程
才包含cell identity。两类键都不依赖并发完成顺序，且不得用一个强制包含cell的通用
公式覆盖共享制品。
模型request seed支持状态为`UNRESOLVED[P1_REQUEST_SEED]`，跨cell/重试配对语义为
`UNRESOLVED[P1_MODEL_SEED_PAIRING]`；未冻结前不得隐式选择。

## 环境与代码

manifest 至少记录 Git SHA、dirty 状态、Python minor、依赖 lock hash、操作系统、硬件、vLLM/driver/CUDA 和启动命令。正式运行只允许 clean 或经 manifest 明示且归档 diff 的代码状态。依赖及 Allowed APIs v1 在 Phase 0B 验证后冻结。

## 数据、完整性与恢复

原始大规模数据不进 Git。受控存储必须保存不可变事件、checkpoint、矩阵 schedule、manifest、hash、归档 URI、备份和访问规则。当前归档位置为 `UNRESOLVED[P1_DATA_ARCHIVE_URI]`。

恢复只从首个未成功event原位继续；成功事件不得重复请求。失败事件不提交状态且阻断
后续状态链。分析入口必须核验protocol/hash、expected/actual/succeeded counts和
cell×seed配对；Paper 1主分析只接收全部预期事件成功的run。分析层排除不等于事件
成功，imputed/fallback不得进入主路径。

## Freeze 清单

正式运行前必须冻结协议版本、12-cell schedule、20个候选 seed 的顺序、模型 revision、模板、生成参数、指标公式、质量阈值、盲态 SSR 程序、依赖锁、代码 SHA 和数据归档位置。

## Schedule artifact 与 manifest 持久化边界

Phase 3A的历史schedule v1 payload为
`{"version": 1, "slots": [{"round_index": <int>, "agent_id": <str>}, ...]}`，只可用于
旧fixture。Phase 4B现已迁移为显式包含连续`event_ordinal`与`sweep_index`的v2制品，
并拒绝ordinal重复、缺口或顺序漂移。`schedule_hash`覆盖完整版本化payload及slot顺序；
`FrozenSchedule.to_payload()`/`from_payload()`继续作为公开round-trip边界，但v1不得
用于Paper 1 formal run。

持久化 run manifest 不嵌入或递归复制运行时 `FrozenSchedule`。
`RunManifest.to_payload()` 记录 `schedule_uri`、`schedule_hash` 和
`schedule_count`；`RunManifest.from_payload(payload, schedule=...)` 要求调用方
另行加载不可变 artifact，并重新核验 hash 与 count。`dataclasses.asdict()`
不是持久化契约。

Phase 3A历史游标`{round_index, event_index}`不得用于Paper 1 formal事件链。Phase 4B
游标迁移为`{next_event_ordinal}`：恢复前，`[0, next_event_ordinal)`必须构成无缺口、
无重复且全部`succeeded`的连续schedule前缀；首个failed/非终态事件只能位于
`next_event_ordinal`，不得把“已达任意终态”当作成功前缀并从下一事件继续。

## Phase 4B 工程实现边界（2026-09-04）

`platform/`现以每run独立SQLite v6保存严格串行事件、attempt状态、输入/请求/调用/解析
证据、private/public状态和feed游标。新checkpoint写compact v5：历史失败/授权由有序
内容哈希与最小因果引用绑定，完整typed记录从权威SQLite重放；legacy v3/v4仍按各自
历史投影验证。mock N=20六类断点均通过close/open恢复；其中尚未调用provider的
`after_pending`恢复恰好调用1次，其余五类恢复均为zero-resend。N=100既完成12-cell
共1,200事件，也在单cell第50事件close/open后只调用剩余50次并与连续run投影一致；
N=1000一轮post-invocation恢复为zero-resend并与连续run一致。单cell N=1000/T=50的
50,000-event执行通过完整运行门禁。完整证据见
`logs/2026-09-04-phase4b-handoff.md`。

这些Windows mock证据不能替代Linux/cloud、CUDA/vLLM、真实Qwen、吞吐/成本/失败率或
正式归档验证。正式运行仍须使用冻结机器协议、clean或显式归档dirty diff的Git SHA、
Linux环境锁和不可变模型/模板制品；任何`UNRESOLVED[...]`继续令formal validation失败。
