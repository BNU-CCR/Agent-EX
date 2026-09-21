# Phase 0A-1 当前前缀观察值（609/797）

> **证据等级：** `preliminary / incomplete / not_frozen`；
> `formal_parameter_authority=false`。这是一份运行元数据快照，不是语义分析结果。

## 当前前缀观察值

固定投影生成时，连续前 **609** 项状态为 `coded`，第610项为
`dispatch_unresolved`。因此快照的运行完成比例为609/797（76.41%），但没有输出任何
语义标签频数、通过率、题目比较或参数结论。

元数据方法是在609项投影固定后、剩余188项完成前冻结的。最终797项只能用同一脚本复算
运行元数据；不能在看到剩余项后修改字段或解释规则。`cutoff == expected_total` 时，脚本还会
要求投影恰有797项且全部为 `coded`，并把 `incomplete` 改为 `false`；否则始终为 `true`。

机器可读快照见 [metadata-snapshot-609.json](metadata-snapshot-609.json)。

## 为什么暂不提供609项语义统计

当前正式 projection 只含状态、顺序和证据哈希。语义标签位于包含原始模型输出的
reconciliation/attempt 记录中；当前证据链没有独立、已批准且不含原始文本的标签导出。
为遵守“不读取或解析raw response”的边界，本次没有打开这些文件，并撤回任何由它们产生的
609项标签统计。

只有在平台生成一个经正式契约验证、哈希绑定、字段白名单化且明确不含raw/prompt/reason的
导出后，才能另行开展阶段性语义汇总。在此之前可以安全报告的只有当前完成数和运行状态。

## 绑定与安全边界

- 投影记录哈希：`358adaa062c9f69a2679dd239c5d93c1557fde4b39c8361272aaa0121ec8c2d1`
- 投影文件 SHA-256：`63dae15c80ec8517e625febed3927c37d0024efacc643f33f0315ed25864dcd9`
- manifest记录哈希：`2cf46ae940d904383881ac74e4cc64d1f9bd3cdd623c67e56c52f04a06a567f1`
- policy记录哈希：`12012960c93b9c55c3ddeff0d7075d0bb5faec5e29b7a35bed7dbb13e2b4e6f9`
- renderer记录哈希：`747550632924afbc1adbdb6a07c8fffd469fccc2cefd088878af7c37a6d418fb`
- 前缀绑定哈希：`fad024b7e6c214f60560f763554424fccba6bb25999c9a2f58bec809513e15d7`
- 快照记录哈希：`ad9538081b6c5a750af560cd0c5fcc22faeed2b1b7365cf8df766caa36fefb1e`
- 脚本 SHA-256：`b9a291f94dfec83379c59381bec51b081849b83d0392a659875d9b1b31dcb509`

脚本使用项目正式的 `JudgeProjection`、`JudgeExecutionManifest`、
`SemanticReviewPolicy` 和 `JudgeRequestRenderer` 解析器重算并验证记录哈希，同时验证
projection→manifest、manifest→renderer、renderer→policy 的绑定。脚本自行读取自身字节并
计算方法哈希，不接受外部 `method_sha256`。

不可变源定位：

```text
ssh://root@connect.bjb2.seetacloud.com:35947/root/autodl-tmp/agent-ex-phase0a1-judge-v2/run-store/staging/projections/000000002441-358adaa062c9f69a2679dd239c5d93c1557fde4b39c8361272aaa0121ec8c2d1.json
```

## 精确复算命令（PowerShell）

以下命令只下载projection、manifest、policy和renderer四个不含运行时原始回答的正式制品，
不会访问 reconciliation、attempts 或 raw 目录：

```powershell
$cache = Join-Path $env:TEMP 'agent-ex-phase0a1-prefix-609-safe'
New-Item -ItemType Directory -Force -Path $cache | Out-Null
$key = 'C:\Users\Bai Yuexi\.ssh\agent_ex_autodl_20260910'
$hosts = 'C:\Users\BAIYUE~1\AppData\Local\Temp\agent-ex-autodl-35947-f0228843-known_hosts'
$remote = 'root@connect.bjb2.seetacloud.com:/root/autodl-tmp/agent-ex-phase0a1-judge-v2'

scp -P 35947 -i $key -o UserKnownHostsFile=$hosts -o StrictHostKeyChecking=yes `
  "$remote/run-store/staging/projections/000000002441-358adaa062c9f69a2679dd239c5d93c1557fde4b39c8361272aaa0121ec8c2d1.json" "$cache/projection.json"
scp -P 35947 -i $key -o UserKnownHostsFile=$hosts -o StrictHostKeyChecking=yes "$remote/manifest.json" "$cache/manifest.json"
scp -P 35947 -i $key -o UserKnownHostsFile=$hosts -o StrictHostKeyChecking=yes "$remote/policy-runtime.json" "$cache/policy.json"
scp -P 35947 -i $key -o UserKnownHostsFile=$hosts -o StrictHostKeyChecking=yes "$remote/renderer-runtime.json" "$cache/renderer.json"

$env:PYTHONPATH = 'platform/src'
platform/.venv/Scripts/python.exe platform/scripts/phase0a1-judge-prefix-snapshot.py `
  --projection "$cache/projection.json" --manifest "$cache/manifest.json" `
  --policy "$cache/policy.json" --renderer "$cache/renderer.json" `
  --approved-manifest-hash 2cf46ae940d904383881ac74e4cc64d1f9bd3cdd623c67e56c52f04a06a567f1 `
  --approved-policy-hash 12012960c93b9c55c3ddeff0d7075d0bb5faec5e29b7a35bed7dbb13e2b4e6f9 `
  --approved-renderer-hash 747550632924afbc1adbdb6a07c8fffd469fccc2cefd088878af7c37a6d418fb `
  --cutoff 609 --captured-at '2026-09-21T16:25:38+08:00' `
  --source-locator 'ssh://root@connect.bjb2.seetacloud.com:35947/root/autodl-tmp/agent-ex-phase0a1-judge-v2/run-store/staging/projections/000000002441-358adaa062c9f69a2679dd239c5d93c1557fde4b39c8361272aaa0121ec8c2d1.json'
```
