---
status: approved design; pending written-spec review
authority: Paper 1 Phase 0A-1 ten-request smoke authorization design only
approved-by: user
approved-date: 2026-09-15
supersedes: none
---

# Paper 1 Phase 0A-1 十请求 Smoke 授权设计

## 1. 授权目的与范围

本规格定义 `2026-09-10-paper1-phase0a1-cloud-probe-design.md` 所述第二权限层的一次性精确
授权边界。只有书面复核、实现验收、新 source-bound preflight 和新 SmokeManifest 最终
批准全部关闭后，它才允许在受控云端主机上安装候选环境、获取固定候选模型与 tokenizer、
启动 loopback vLLM，并执行 hash 绑定的十条 smoke 请求。服务器当前关闭；批准和书面
记录本规格本身不启动服务器，也不产生模型请求。

本授权不允许读取或执行 816-case inventory，不允许运行 formal、Phase 0B、任何主实验，
也不允许冻结任何研究参数。smoke 结果只能作为后续 816-case 审批包的候选运行时证据，
不能产生议题或 persona 选择，不能修改正式协议、schema、`docs/decisions.md` 或 formal
config。

## 2. 已批准的精确绑定

### 2.1 来源与 preflight

| 项目 | 精确值 |
|---|---|
| source commit | `6711a6d767cc1993db1d823d183bb125070c107e` |
| preflight schema | `paper1.calibration.cloud-preflight.v1` |
| preflight canonical `record_hash` | `5e51819d3e6a8b9e1232b1142c77f06d16fa29620eccb84d6bc296d80e9f685e` |
| preflight 文件 SHA-256 | `d6c599570b91d8f29905e454618be6b61a2f1850e62d936b5792975867d5da31` |
| preflight authority | `calibration_only: true`; `formal_parameter_authority: false` |

该 preflight 仍是 source commit `6711a6d767cc1993db1d823d183bb125070c107e` 的有效历史
证据，不得覆盖或改写。但本规格批准的恢复与 deterministic transport diagnostics 需要先
形成新的实现代码提交，因此该历史 preflight 不能授权修复后代码执行 smoke。代码完成后
必须部署新的 exact clean commit，再次执行只读 preflight，并由新 preflight
`record_hash` 派生新的完整 SmokeManifest；不得用旧记录冒充新 source binding。

### 2.2 模型、tokenizer、服务与模板

| 项目 | 精确值 |
|---|---|
| model/tokenizer repository | `Qwen/Qwen3-8B` |
| model revision | `b968826d9c46dd6066d109eabc6255188de91218` |
| tokenizer revision | `b968826d9c46dd6066d109eabc6255188de91218` |
| vLLM | `0.23.0` |
| dtype | BF16（`bfloat16`） |
| max model length | `32768` |
| generation config | `vllm` |
| served model name | `qwen3-8b-paper1` |
| thinking | `enable_thinking=false` |
| request identity | 启用 request-ID response headers |
| endpoint | `http://127.0.0.1:8000/v1/chat/completions` |

服务必须由 `platform/scripts/phase0a1-serve.sh` 所表达的候选合同启动：model 与 tokenizer
使用同一 pinned revision，服务仅监听 `127.0.0.1:8000`，使用 BF16、原生
`32768` 上下文、`--generation-config vllm`、served name
`qwen3-8b-paper1`、默认 chat-template kwargs `enable_thinking=false`，并启用 request-ID
response headers。不得使用 moving revision、不同 endpoint、重定向或备用 provider。

chat template 只取自上述 pinned revision 的 `tokenizer_config.json`，并同时绑定：

| 模板证据 | 精确值 |
|---|---|
| `tokenizer_config.json` 文件 SHA-256 | `d5d09f07b48c3086c508b30d1c9114bd1189145b74e982a265350c923acd8101` |
| HTTP `X-Repo-Commit` | `b968826d9c46dd6066d109eabc6255188de91218` |
| HTTP `ETag` | `417d038a63fa3de29cfde265caedae14d1a58d92` |
| chat template UTF-8 长度 | `4168` bytes |
| chat template canonical hash | `41d5929bf73796beb66809ac700b2cf3ff81694f933e5c14d52b7fd6963c947d` |

SmokeManifest 的 `chat_template_hash` 字段绑定最后一项 canonical hash，而不是整个
`tokenizer_config.json` 的文件 SHA-256。

### 2.3 十条 prompts 与待 supersede 的 SmokeManifest candidate

本次只能执行固定十条 smoke prompts，其 prompt-set hash 为
`da354eaeda9d83a018d6022a6e094cf03f4a461cc5576ea0c339fc8555608ea5`。不得增加、删除、
替换或重排后以本授权名义执行；不得加载 816-case specification 或 inventory。

已按原 source/preflight 计算的 SmokeManifest candidate 使用 schema
`paper1.calibration.smoke-manifest.v1`，其字段精确绑定为：

| 字段 | 精确值 |
|---|---|
| `calibration_only` | `true` |
| `formal_parameter_authority` | `false` |
| `preflight_hash` | `5e51819d3e6a8b9e1232b1142c77f06d16fa29620eccb84d6bc296d80e9f685e` |
| `model_repository` | `Qwen/Qwen3-8B` |
| `model_revision_candidate` | `b968826d9c46dd6066d109eabc6255188de91218` |
| `tokenizer_revision_candidate` | `b968826d9c46dd6066d109eabc6255188de91218` |
| `vllm_version_candidate` | `0.23.0` |
| `endpoint` | `http://127.0.0.1:8000/v1/chat/completions` |
| `served_model_name` | `qwen3-8b-paper1` |
| `chat_template_hash` | `41d5929bf73796beb66809ac700b2cf3ff81694f933e5c14d52b7fd6963c947d` |
| `runtime_policy_hash` | `e0c72256eb39927f0e76565bb95b7b570c5930c22c40a28267ec872d97af0f13` |
| `smoke_prompt_set_hash` | `da354eaeda9d83a018d6022a6e094cf03f4a461cc5576ea0c339fc8555608ea5` |
| `credential_boundary_hash` | `4522015a0a1aaf3d1fc14ad295d88bd4e1bd519bb9abf2f23ff29ade0cd8fffa` |
| `archive_uri` | `/root/autodl-tmp/agent-ex-phase0a1-evidence/smoke-6711a6d-001` |
| `record_hash` | `9e6e738346508c005486cc8b3a01cb2ab55849b48eac0415774b355c82497304` |

`9e6e738346508c005486cc8b3a01cb2ab55849b48eac0415774b355c82497304` 经原字段重算正确，
但它绑定旧 source 的 preflight。在恢复与 diagnostics 代码提交后，该 candidate 不可执行并
将被 supersede。新代码必须先 exact clean 部署并产生新的只读 preflight，之后材料化包含新
`preflight_hash` 的完整 SmokeManifest；其新 `record_hash` 必须由 owner 再次精确批准，批准
前不得安装、启服或发出 smoke 请求。

新 manifest 中下列四项批准绑定保持不变：

- `chat_template_hash`：`41d5929bf73796beb66809ac700b2cf3ff81694f933e5c14d52b7fd6963c947d`；
- `runtime_policy_hash`：`e0c72256eb39927f0e76565bb95b7b570c5930c22c40a28267ec872d97af0f13`；
- `smoke_prompt_set_hash`：`da354eaeda9d83a018d6022a6e094cf03f4a461cc5576ea0c339fc8555608ea5`；
- `credential_boundary_hash`：`4522015a0a1aaf3d1fc14ad295d88bd4e1bd519bb9abf2f23ff29ade0cd8fffa`。

新 manifest 获批后，执行器必须通过 `SmokeManifest.from_payload` 或等价的严格 schema/hash
校验重新打开它。任一字段或 canonical `record_hash` 不匹配时不得启动 smoke。

## 3. Smoke-only runtime policy

本次临时诊断策略的 canonical payload 精确内容为：

| 字段 | 精确值 |
|---|---|
| `schema_version` | `paper1.calibration.probe-runtime-policy.v1` |
| `policy_id` | `phase0a1-smoke-runtime-v1` |
| `retryable_error_codes`（canonical sorted） | `provider_busy`, `provider_unreachable`, `timeout` |
| `nonretryable_error_codes`（canonical sorted） | `oom`, `provider_fatal`, `provider_invalid_json`, `provider_redirect`, `provider_response_too_large`, `provider_schema_error` |
| `max_transport_attempts_by_code`（canonical sorted mapping） | `oom: 1`, `provider_busy: 1`, `provider_fatal: 1`, `provider_invalid_json: 1`, `provider_redirect: 1`, `provider_response_too_large: 1`, `provider_schema_error: 1`, `provider_unreachable: 1`, `timeout: 1` |
| `timeout_seconds` | `120.0` |
| `obey_retry_after` | `false` |
| `backoff_seconds` | 空序列 |
| `metadata.calibration_only` | `true` |
| `metadata.formal_parameter_authority` | `false` |
| `metadata.research_parameter_status` | `not_frozen` |
| `record_hash` | `e0c72256eb39927f0e76565bb95b7b570c5930c22c40a28267ec872d97af0f13` |

用于 hash 的完整 canonical content payload 为：

```json
{
  "schema_version": "paper1.calibration.probe-runtime-policy.v1",
  "policy_id": "phase0a1-smoke-runtime-v1",
  "retryable_error_codes": ["provider_busy", "provider_unreachable", "timeout"],
  "nonretryable_error_codes": ["oom", "provider_fatal", "provider_invalid_json", "provider_redirect", "provider_response_too_large", "provider_schema_error"],
  "max_transport_attempts_by_code": {
    "oom": 1,
    "provider_busy": 1,
    "provider_fatal": 1,
    "provider_invalid_json": 1,
    "provider_redirect": 1,
    "provider_response_too_large": 1,
    "provider_schema_error": 1,
    "provider_unreachable": 1,
    "timeout": 1
  },
  "timeout_seconds": 120.0,
  "obey_retry_after": false,
  "backoff_seconds": [],
  "metadata": {
    "calibration_only": true,
    "formal_parameter_authority": false,
    "research_parameter_status": "not_frozen"
  }
}
```

因为每个错误码的 transport attempt 上限均为一次，所以任一 transport failure 都不会在
本次 smoke 内自动重试；空 backoff 序列与该预算一致。请求不得因失败而改变 prompt、
request identity 或绑定内容。

上述 schema、字段顺序无关的 canonical mapping 和完整 metadata 已按
`ProbeRuntimePolicy.content_payload()` 重新计算；结果仍为
`e0c72256eb39927f0e76565bb95b7b570c5930c22c40a28267ec872d97af0f13`。

该策略只关闭本次十请求 smoke 的临时诊断行为，不关闭
`UNRESOLVED[P1_TIMEOUT_RETRY]`，也不构成 816-case、Phase 0B、formal 或主实验的 timeout、
错误分类、attempt budget、Retry-After 或 backoff 冻结。后续权限层仍须按
`docs/research-qa.md` 完成独立运行时会审。

## 4. 凭据与网络边界

凭据边界声明必须精确为：

| 字段 | 精确值 |
|---|---|
| schema | `paper1.calibration.credential-boundary.v1` |
| metadata | `calibration_only: true`; `formal_parameter_authority: false` |
| `injection_channel` | `controller-local-ssh-key; no model credential` |
| `credential_values_archived` | `false` |
| canonical hash | `4522015a0a1aaf3d1fc14ad295d88bd4e1bd519bb9abf2f23ff29ade0cd8fffa` |

仓库、日志、manifest、命令和 smoke evidence 均不得写入私钥路径、私钥值、任何凭据值或
凭据变量名。Qwen 仓库公开，本次不得引入 Hugging Face token；loopback vLLM 不对公网
开放。凭据声明只描述边界，不携带秘密，也不授权新的凭据渠道。

AutoDL network turbo 的 `source /etc/network_turbo` 只可出现在 Git/Hugging Face 下载专用
的 subshell 或等价进程作用域。该作用域必须以 `trap`/`finally` 保证成功、失败和中断路径
都执行清理；退出下载作用域后，
必须清理并检查 `http_proxy`、`https_proxy`、`HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY`、
`all_proxy`，以及实际脚本可能设置的其他代理变量。执行时必须使用显式白名单/无代理断言，
证明启动环境未残留未批准代理；任何清理或断言失败都禁止启动服务。vLLM 进程不得继承
代理设置。代理配置不是凭据，不进入 credential-boundary declaration；它也不得改变 model、
revision、template 或 artifact 的 hash 验证。

## 5. 归档边界

原 SmokeManifest candidate 的独立临时 archive URI 是
`/root/autodl-tmp/agent-ex-phase0a1-evidence/smoke-6711a6d-001`；若不存在，可在执行前创建。
所有 manifest、请求、attempt、原始响应、错误、headers、解析、服务身份、环境与 hash
证据均写入该 smoke 专属位置，并保持可复验。失败 evidence 同样保留，不得覆盖为成功
记录。

该 URI 随旧 manifest candidate 一同处于不可执行状态。新 SmokeManifest 必须绑定本次
执行专属且不会混入旧 attempt 的临时 archive URI；如果继续使用上述 URI，必须先证明其
不存在或为空，并把该精确值纳入 owner 对新完整 manifest hash 的批准。临时 URI 不关闭
`UNRESOLVED[P1_DATA_ARCHIVE_URI]`，不得成为 816-case 或 formal archive 的默认值。原始
evidence、模型文件、数据库和大型 bundle 不得进入 Git；Git 只可保存本规格及后续脱敏的
hash/定位记录。

## 6. 模型请求与 transport diagnostics 的计数边界

完整 smoke 必须包含恰好十次成功的 Qwen3-8B 模型生成请求；固定十条 prompts 各且仅各
请求一次，不得因恢复、解析、诊断或失败重复任何模型 prompt。前九条成功并持久化后必须
形成明确的重启边界；固定 prompt set 中名为 `service-identity-recovery` 的第十条只能在
恢复完成后执行。

模型请求之外，还必须在云端本机运行 deterministic transport diagnostics。它们使用独立的
loopback test endpoints/ports，覆盖：

- 连接预先确认未监听的 closed port，预期分类为 `provider_unreachable`；
- 由受控本机 endpoint 延迟超过 `timeout_seconds: 120.0`，预期分类为 `timeout`；
- 由受控本机 endpoint 返回 HTTP 429，预期分类为 `provider_busy`，并捕获其
  `Retry-After`；由于 `obey_retry_after: false` 且 attempt budget 为 `1`，不得据此重试。

这些 diagnostics 不访问 Qwen、不调用真实 vLLM、不算模型生成请求，也不读取 816-case
inventory。不得故意令正式 vLLM 产生 timeout、429、不可达或其他错误来验证分类。每项
diagnostic 的 endpoint identity、输入、时间、原始响应或错误、headers、预期/实际分类及
canonical hash 都必须追加到 smoke 专属 append-only store；已有诊断记录不得覆盖。

## 7. 获批执行顺序

1. 在本规格通过用户书面复核后，先按另行批准的实施计划，以 TDD 实现第 6 节的恢复与
   diagnostics 能力并完成验收；不得在该门之前写实现代码。
2. 将实现代码提交部署为 exact clean commit，再次执行只读 preflight。由新的 preflight
   `record_hash` 材料化新完整 SmokeManifest，取得 owner 对新 manifest 全长
   `record_hash` 的明确批准；旧 `9e6e738346508c005486cc8b3a01cb2ab55849b48eac0415774b355c82497304`
   不可执行。
3. 保持服务器关闭，严格重新验证 credential-boundary declaration、runtime policy、固定
   十条 prompt set、新 preflight 和新 SmokeManifest 的 canonical hashes。
4. 确认 smoke archive URI；不存在时创建独立目录，并在任何模型请求前验证 append-only
   写入、持久化、hash evidence 和恢复路径。
5. 建立 fresh Python 3.12 环境，使用 vLLM `0.23.0` 的 official CUDA 12.9 wheel path；不得
   复用预装 PyTorch。记录全部 package versions、wheel identities 和 environment hash，
   并形成不可变 environment lock。安装来源、包版本、wheel identity、PyTorch 来源或 lock
   任一漂移均 fail closed。
6. 仅在下载专用 subshell/进程中获取依赖与 pinned model/tokenizer；由 `trap`/`finally`
   清理后完成代理白名单/无代理断言。核对 `tokenizer_config.json` 文件 hash、响应来源
   headers、chat template 字节长度和 canonical hash。任何不一致或代理残留均不得启服。
7. 在真实 vLLM 仍关闭时，使用独立 loopback test endpoints/ports 执行并持久化第 6 节三项
   deterministic transport diagnostics；确认实际分类和必需 evidence 与预期完全一致。
8. 按 `platform/scripts/phase0a1-serve.sh` 的完全相同锁定合同启动真实 loopback vLLM；验证
   endpoint、served name、BF16、max model length、generation config、non-thinking、
   request-ID headers、model/tokenizer/template identity、environment lock 和健康状态。
9. 第一阶段仅依次执行固定 prompts 的前九条。每条必须首次成功并立即追加完整请求、响应、
   解析、身份和 hash evidence；任一失败立即结束整体 smoke，不得重复 prompt。
10. 前九条全部成功后，持久化 projection/checkpoint，明确记录九条 terminal-success 与
    `service-identity-recovery` 仍为 `pending`。干净关闭客户端，关闭 store 的进程与文件句柄，
    并停止真实 vLLM；磁盘上的 append-only evidence 不得删除或改写。
11. 使用与第一次完全相同的锁定 serve contract 重启真实 vLLM，并重新验证服务身份、模型、
    tokenizer、chat template、runtime、environment lock、endpoint 和健康状态。
12. 从 append-only store 新开客户端恢复，重新验证前九条 evidence 与 projection 不可变，
    确认没有重复/跳过且只有第十条 `service-identity-recovery` 为 `pending`；然后仅执行该
    第十条一次。它必须首次成功并追加完整 evidence。
13. 验证恰好十条唯一 prompts、恰好十次成功 Qwen 生成、三项独立 diagnostics、全部
    identity/hash bindings 和 archive 完整性，然后停止 vLLM。无论成功或失败，服务都不得
    因本授权继续驻留。
14. 保留并标记 smoke evidence。成功时只准备六组 816-case 审批包；失败时记录失败边界与
    新候选需求。两种结果都不得自动进入 816-case。

## 8. 失败与停止规则

出现以下任一情况必须立即停止后续请求、停止服务、保留截至失败点的 evidence，并禁止
进入 816-case：

- preflight 文件 hash、preflight canonical hash、source commit 或 clean binding 漂移；
- SmokeManifest、runtime policy、credential declaration 或 prompt-set hash 不匹配；
- model repository/revision、tokenizer revision、vLLM version、dtype、上下文长度、served
  name 或 endpoint 漂移；
- `tokenizer_config.json`、来源 headers、chat template 长度或 hash 漂移；
- endpoint 非批准的 loopback URL、发生重定向、provider 替换或 thinking 未被禁用；
- 任一请求产生 timeout、不可达、provider/JSON/schema/OOM/长度类错误，或没有形成完整且
  可 hash 复验的证据；
- 任一 deterministic diagnostic 的实际分类不符、`Retry-After` 未按要求捕获，或诊断
  evidence 不完整、不可追加或无法 hash 回绑；
- 服务重启后的 model/tokenizer/template/runtime/endpoint/environment identity 或健康状态
  漂移；
- 恢复后前九条记录发生变化、第十条不再是唯一 pending 项，或任何 prompt 被重复、跳过、
  重排或执行超过一次；
- 最终不是恰好十次成功的 Qwen 模型生成请求，或 diagnostics 被计入模型请求；
- fresh Python 3.12、official CUDA 12.9 wheel path、不得复用预装 PyTorch、package/wheel
  identities 或 environment lock 任一安装门不满足；
- 下载作用域未隔离，代理清理/无代理断言失败，或 vLLM 继承任何未批准代理；
- archive 无法创建、追加、校验或保留，或任何原始 evidence 被要求写入 Git；
- 任一未授权 artifact、816-case inventory、formal config 或主实验路径被加载或调用。

失败后不得就地改变 hash 绑定的 policy、prompt、模型、模板或 endpoint 并继续；修订候选
必须形成新的书面授权和新 manifest。成功也不产生自动升级权限。

## 9. 仍未授权事项

本规格明确不授权：

- 816 个 calibration cases、其 specification、inventory、gate algorithm 或 semantic review；
- `UNRESOLVED[P1_TIMEOUT_RETRY]` 与 `UNRESOLVED[P1_DATA_ARCHIVE_URI]` 的关闭或冻结；
- model revision、vLLM、generation settings 或其他研究参数的 formal freeze；
- Phase 0B 的 N=20/50/100、N=200/500 scale gate、N=1000 容量 gate；
- N=1000、T=50、12-cell 主矩阵，API 稳健性子集或任何正式分析；
- 对 event engine、Agent state、网络状态、协议、schema、decision records 或 formal config
  的修改；
- 依据 smoke 结果作议题/persona 选择或提出 Paper 1 实证结论。

## 10. 实现验收边界

本修订只批准设计，不授权立即写代码。必须先完成本规格的用户书面复核，再创建并另行批准
实施计划；之后才可开始实现。实现必须采用 TDD，至少以针对性测试证明：

- 十 prompt 唯一性、前九/停服/恢复/第十条状态机和重复/跳过 fail-closed；
- append-only store 跨客户端、store handle 和真实服务关闭后的恢复与不可变性；
- 三种独立 loopback diagnostics 的确定性分类、429 `Retry-After` capture 与模型请求计数
  隔离；
- exact serve/environment identity 重启复验与漂移停止；
- 下载专用作用域的成功、失败、中断清理，以及 vLLM 无代理启动断言；
- fresh Python 3.12、official CUDA 12.9 wheel、package/wheel identities 和 environment lock
  的 fail-closed gates；
- 旧 preflight/旧 SmokeManifest 被拒绝，新 source-bound preflight 与 manifest 审批门生效。

实现阶段运行与变更直接相关的针对性测试并记录精确命令与结果；不会自动运行当前约
80 分钟的完整测试套件。完整套件只有在 owner 另行明确要求时才运行，未运行时必须如实
记录，不能用针对性测试声称全套通过。

## 11. 下一步

书面规格通过复核后，下一步只是创建独立实施计划并取得批准；随后按第 10 节完成代码与
针对性测试，提交并部署 exact clean commit，再生成新的只读 preflight 与完整
SmokeManifest。只有 owner 明确批准新 manifest 全长 `record_hash` 后，才可按第 7 节执行
十请求 smoke。

若 smoke 任一检查、diagnostic、恢复门或模型请求失败，停止服务、保留失败 evidence，后续
需针对新候选重新授权。若恰好十次 Qwen 请求全部成功且 diagnostics 与 evidence 完整，只
形成包含完整 probe specification、独立 runtime policy、semantic-review policy、
环境/model/runtime generation manifest、凭据边界和正式 archive location 的六组 816-case
审批包，提交用户与相应会审者审批；在新的明确批准到达前不得执行 816 cases。
