---
status: active requirements; Phase 3A identity and persistence contracts implemented
authority: reproducibility contract for platform and runs; actual values come from frozen protocol, environment lock and run manifests
supersedes: ad hoc reproducibility practices in pilot notebooks
last-verified: 2026-07-29
---

# 可复现规范

## 模型身份

正式主模型路线已批准为 Qwen3-8B BF16、non-thinking、vLLM 自部署。Phase 0B 已核验候选模型 commit `b968826d9c46dd6066d109eabc6255188de91218` 与候选 `vllm==0.23.0` 的官方文档；它们在 artifact/credential/runtime smoke 和环境锁定前仍分别引用 `UNRESOLVED[P1_MODEL_REVISION]` 与 `UNRESOLVED[P1_VLLM_VERSION]`。正式运行必须固定并记录模型 repository、tokenizer revision、chat-template hash、vLLM 版本与镜像 digest、CUDA/driver/GPU、thinking 开关及全部实际传递的生成参数。滚动别名不得描述为严格可复现版本。

API 稳健性必须使用 `UNRESOLVED[P1_API_SNAPSHOT]` 的固定 snapshot；若提供方无法证明版本固定，则只能标记为时间戳化的非确定性稳健性证据。

## 运行身份

- `run_spec_hash`：规范化 protocol、run config、不可变 schedule hash、请求参数、模型身份、Git SHA 和环境 lock hash 的内容寻址。任何 schedule 坐标变化都必须改变 `run_spec_hash`。
- `run_id`：`run_spec_hash + replicate_seed + launch_nonce`。
- `event_id`：`run_id + round + agent_id`，作为逻辑事件幂等键。
- `attempt_id`：`event_id + attempt_index`；重试追加而不覆盖。

每个 attempt 必须保存 exposure、渲染 prompt、请求参数、provider request ID、原始响应 body、客户端可得的响应 headers 与 HTTP status、解析、错误、usage、finish reason、时间戳和内容 hash。

## 随机性

人口、初始状态、网络、exposure、激活和模型采样使用分离 seed namespace。每个 `(base_seed, round, agent_id, component)` 派生独立 RNG，不依赖并发完成顺序。模型 request seed 的支持状态为 `UNRESOLVED[P1_REQUEST_SEED]`；不支持时明确记录生成非完全确定。

## 环境与代码

manifest 至少记录 Git SHA、dirty 状态、Python minor、依赖 lock hash、操作系统、硬件、vLLM/driver/CUDA 和启动命令。正式运行只允许 clean 或经 manifest 明示且归档 diff 的代码状态。依赖及 Allowed APIs v1 在 Phase 0B 验证后冻结。

## 数据、完整性与恢复

原始大规模数据不进 Git。受控存储必须保存不可变事件、checkpoint、矩阵 schedule、manifest、hash、归档 URI、备份和访问规则。当前归档位置为 `UNRESOLVED[P1_DATA_ARCHIVE_URI]`。

恢复只认领非终态 event；终态事件不得重复请求。分析入口必须核验 protocol/hash、expected/actual counts、cell×seed 配对和 allowed terminal states。未完成或不合规 run 不得因“已有多数结果”进入主分析。

## Freeze 清单

正式运行前必须冻结协议版本、12-cell schedule、20个候选 seed 的顺序、模型 revision、模板、生成参数、指标公式、质量阈值、盲态 SSR 程序、依赖锁、代码 SHA 和数据归档位置。

## Schedule artifact 与 manifest 持久化边界

不可变 schedule artifact 的 canonical JSON payload 为
`{"version": 1, "slots": [{"round_index": <int>, "agent_id": <str>}, ...]}`。
`schedule_hash` 是完整版本化 payload（包括 slot 顺序）的 canonical SHA-256。
`FrozenSchedule.to_payload()` 与 `FrozenSchedule.from_payload()` 是公开的
round-trip 边界。

持久化 run manifest 不嵌入或递归复制运行时 `FrozenSchedule`。
`RunManifest.to_payload()` 记录 `schedule_uri`、`schedule_hash` 和
`schedule_count`；`RunManifest.from_payload(payload, schedule=...)` 要求调用方
另行加载不可变 artifact，并重新核验 hash 与 count。`dataclasses.asdict()`
不是持久化契约。

恢复游标为 `{round_index, event_index}`，其中 `event_index` 是该轮下一个
slot 的零基索引。已完成轮必须精确存在且全部为终态；游标存在时，下一轮
已观测事件必须恰好等于 `event_index` 之前的有序 schedule 前缀。
