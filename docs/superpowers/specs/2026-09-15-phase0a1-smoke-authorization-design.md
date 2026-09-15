---
status: approved design; pending written-spec review
authority: Paper 1 Phase 0A-1 ten-request smoke authorization design only
approved-by: user
approved-date: 2026-09-15
supersedes: none
---

# Paper 1 Phase 0A-1 十请求 Smoke 授权设计

## 1. 授权目的与范围

本规格是 `2026-09-10-paper1-phase0a1-cloud-probe-design.md` 所定义第二权限层的
一次性精确授权。它只允许在已通过只读 preflight 的受控云端主机上，安装候选环境、
获取固定候选模型与 tokenizer、启动 loopback vLLM，并执行 hash 绑定的十条 smoke
请求。服务器当前关闭；批准和书面记录本规格本身不启动服务器，也不产生模型请求。

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

执行前必须重新打开既有 preflight 记录，并同时核对文件 SHA-256、canonical
`record_hash`、source commit 和 clean source binding。任何不一致均使本授权失效，且不得
用重新观察、另一 commit 或手工改写的记录替代。

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

### 2.3 十条 prompts 与 SmokeManifest

本次只能执行固定十条 smoke prompts，其 prompt-set hash 为
`da354eaeda9d83a018d6022a6e094cf03f4a461cc5576ea0c339fc8555608ea5`。不得增加、删除、
替换或重排后以本授权名义执行；不得加载 816-case specification 或 inventory。

获批 SmokeManifest 使用 schema `paper1.calibration.smoke-manifest.v1`，其字段精确绑定为：

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

执行器必须通过 `SmokeManifest.from_payload` 或等价的严格 schema/hash 校验重新打开该
manifest。上述任一字段或 canonical `record_hash` 不匹配时不得启动 smoke。

## 3. Smoke-only runtime policy

本次临时诊断策略采用 `paper1.calibration.probe-runtime-policy.v1`，精确内容为：

| 字段 | 精确值 |
|---|---|
| `policy_id` | `phase0a1-smoke-runtime-v1` |
| `retryable_error_codes`（canonical sorted） | `provider_busy`, `provider_unreachable`, `timeout` |
| `nonretryable_error_codes`（canonical sorted） | `oom`, `provider_fatal`, `provider_invalid_json`, `provider_redirect`, `provider_response_too_large`, `provider_schema_error` |
| `max_transport_attempts_by_code` | 上述每个 error code 均为 `1` |
| `timeout_seconds` | `120.0` |
| `obey_retry_after` | `false` |
| `backoff_seconds` | 空序列 |
| `record_hash` | `e0c72256eb39927f0e76565bb95b7b570c5930c22c40a28267ec872d97af0f13` |

因为每个错误码的 transport attempt 上限均为一次，所以任一 transport failure 都不会在
本次 smoke 内自动重试；空 backoff 序列与该预算一致。请求不得因失败而改变 prompt、
request identity 或绑定内容。

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

AutoDL network turbo 只可临时用于 Git/Hugging Face 下载进程：需要下载时在该进程前
执行 `source /etc/network_turbo`，下载完成后必须 `unset http_proxy https_proxy`。它不进入
凭据声明，不得用于或改变 loopback 服务，也不得改变 model、revision、template 或
artifact 的 hash 验证。

## 5. 归档边界

本次独立临时 archive URI 是
`/root/autodl-tmp/agent-ex-phase0a1-evidence/smoke-6711a6d-001`；若不存在，可在执行前创建。
所有 manifest、请求、attempt、原始响应、错误、headers、解析、服务身份、环境与 hash
证据均写入该 smoke 专属位置，并保持可复验。失败 evidence 同样保留，不得覆盖为成功
记录。

该临时 URI 只服务于本次 smoke，不关闭 `UNRESOLVED[P1_DATA_ARCHIVE_URI]`，不得成为
816-case 或 formal archive 的默认值。原始 evidence、模型文件、数据库和大型 bundle
不得进入 Git；Git 只可保存本规格及后续脱敏的 hash/定位记录。

## 6. 获批执行顺序

1. 保持服务器关闭，先材料化并严格重新验证 credential-boundary declaration、runtime
   policy、固定十条 prompt set 和 SmokeManifest 的 canonical hashes。
2. 重新打开 authoritative preflight，核对其文件 SHA-256、canonical `record_hash`、source
   commit、clean binding 与 calibration-only authority；确认当前执行 checkout 精确绑定
   source commit `6711a6d767cc1993db1d823d183bb125070c107e`。
3. 确认 smoke archive URI；不存在时创建独立目录，并在任何模型请求前验证可写与 hash
   evidence 路径。
4. 建立 fresh locked Python/vLLM `0.23.0` 候选环境。只有 Git/Hugging Face 下载进程可
   临时使用 network turbo；下载完成后清除代理设置。
5. 获取并验证 `Qwen/Qwen3-8B` 的 pinned model/tokenizer revision，核对
   `tokenizer_config.json` 文件 hash、响应来源 headers、chat template 字节长度和 canonical
   hash。任何绑定不一致均不得启动服务。
6. 按 `platform/scripts/phase0a1-serve.sh` 的精确合同启动 loopback vLLM；验证 endpoint、
   served name、BF16、max model length、generation config、non-thinking 设置和 request-ID
   headers。
7. 仅加载 hash 绑定的十条 prompts，按 smoke-only runtime policy 各执行一次，并逐请求
   追加完整请求、响应或错误及其身份/hash 证据。不得加载 816-case inventory。
8. 验证十请求 evidence、manifest/runtime/model/template/endpoint/source bindings 和 archive
   完整性，然后停止 vLLM 服务。无论成功或失败，服务都不得因本授权继续驻留。
9. 保留并标记 smoke evidence。成功时只准备六组 816-case 审批包；失败时记录失败边界与
   新候选需求。两种结果都不得自动进入 816-case。

## 7. 失败与停止规则

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
- archive 无法创建、追加、校验或保留，或任何原始 evidence 被要求写入 Git；
- 任一未授权 artifact、816-case inventory、formal config 或主实验路径被加载或调用。

失败后不得就地改变 hash 绑定的 policy、prompt、模型、模板或 endpoint 并继续；修订候选
必须形成新的书面授权和新 manifest。成功也不产生自动升级权限。

## 8. 仍未授权事项

本规格明确不授权：

- 816 个 calibration cases、其 specification、inventory、gate algorithm 或 semantic review；
- `UNRESOLVED[P1_TIMEOUT_RETRY]` 与 `UNRESOLVED[P1_DATA_ARCHIVE_URI]` 的关闭或冻结；
- model revision、vLLM、generation settings 或其他研究参数的 formal freeze；
- Phase 0B 的 N=20/50/100、N=200/500 scale gate、N=1000 容量 gate；
- N=1000、T=50、12-cell 主矩阵，API 稳健性子集或任何正式分析；
- 对 event engine、Agent state、网络状态、协议、schema、decision records 或 formal config
  的修改；
- 依据 smoke 结果作议题/persona 选择或提出 Paper 1 实证结论。

## 9. 下一步

书面规格通过复核后，owner 才可按第 6 节执行本次十请求 smoke。若 smoke 任一检查或请求
失败，保留失败 evidence 并停止，后续需针对新候选重新授权。若十请求全部成功且 evidence
完整，只形成包含完整 probe specification、独立 runtime policy、semantic-review policy、
环境/model/runtime generation manifest、凭据边界和正式 archive location 的六组 816-case
审批包，提交用户与相应会审者审批；在新的明确批准到达前不得执行 816 cases。
