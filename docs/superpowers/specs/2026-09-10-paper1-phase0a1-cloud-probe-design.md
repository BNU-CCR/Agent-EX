---
status: approved design; pending independent written-spec review
authority: Paper 1 Phase 0A-1 cloud probe design; subordinate to frozen machine protocol, schema, and the approved Phase 0A probe design
approved-by: user
approved-date: 2026-09-10
supersedes: none
---

# Paper 1 Phase 0A-1 云端真实小样本 Probe 设计

## 1. 目的与完成边界

Phase 0A-1 把已经通过独立复核的 Phase 0A-0 离线合同部署到受控云端，使用固定候选
Qwen3-8B 系统完成真实模型 probe。它回答：

1. 三个候选议题在目标模型上的解析、拒答、量表使用、等义稳定和语义质量是否通过硬门；
2. identity 与 continuity 候选文本能否保持正交、可解释且不造成身份扩写、刻板化或立场锁死；
3. 候选模型、运行时、采样和恢复策略是否足以支持后续有限规模网络实验。

本阶段只运行相互独立的 calibration cases。它不构造社会网络，不调用正式 event engine，
不更新 Agent 私人或公开状态，不计算网络处理效应，也不运行 N=1000/T=50 主矩阵。
输出状态只能是 `proposal_only`、`no_candidate` 或 `incomplete`。程序不得自动修改
`docs/decisions.md`、正式协议、schema 或 formal config。

## 2. 前置条件与权限门

云端执行分为两个权限层：

1. **只读 preflight**：检查服务器、GPU、driver、CUDA、磁盘、Python 和现有软件状态；
   不下载模型、不安装依赖、不启动服务、不发送生成请求。
2. **受控执行**：只有六项启动制品全部获批并完成 hash 绑定后，才允许安装锁定环境、
   获取固定模型、启动本地 vLLM 和执行 probe。

六项启动制品是：

- 三个议题的题干、事实卡、量表锚点及 persona 文本候选；
- probe runtime policy；
- semantic-review policy；
- Qwen revision、tokenizer/chat template、vLLM/Linux/CUDA candidate stack 与 generation manifest；
- 凭据安全注入方式；
- 原始响应、review 和 bundle 的外部受控 archive location。

任何制品仍含未知 placeholder、未登记研究 ID、未绑定 hash 或与 manifest 不一致时，
受控执行必须 fail closed。

## 3. 云端与模型候选栈

### 3.1 模型身份

已批准的模型路线保持为 `Qwen/Qwen3-8B`、BF16、non-thinking、自部署 vLLM。候选模型与
tokenizer revision 均为：

`b968826d9c46dd6066d109eabc6255188de91218`

该 commit 已通过官方 Hugging Face repository metadata 只读核验，但在 artifact access、
文件身份、tokenizer/chat-template、non-thinking 和 response-contract smoke 通过前仍是
`UNRESOLVED[P1_MODEL_REVISION]`，不得描述为正式冻结值。

### 3.2 vLLM 与启动合同

候选运行时为 `vllm==0.23.0`。它在 image/runtime smoke 与镜像 digest 记录完成前仍是
`UNRESOLVED[P1_VLLM_VERSION]`。候选服务合同继承 `docs/allowed-apis-v1.md`：

- model 与 tokenizer 使用同一 immutable revision；
- `--dtype bfloat16`；
- `--max-model-len 32768`；
- 不启用 YaRN；
- `--generation-config vllm`，禁止模型仓库默认 generation config 静默覆盖请求；
- `--served-model-name qwen3-8b-paper1`；
- 服务端默认 chat-template kwargs 设置 `enable_thinking=false`；
- 启用 request-ID response headers；
- 服务只监听 loopback，客户端与服务在同一云端主机通信。

GPU 型号、driver、CUDA、Python、PyTorch、镜像 digest、vLLM wheel/hash、启动命令和环境锁
必须进入 runtime manifest。预检不得假设旧 AutoDL 实例、端口或历史镜像仍然存在。

### 3.3 Generation candidate

Qwen 官方 non-thinking 建议的 `temperature=0.7`、`top_p=0.8`、`top_k=20`、`min_p=0`
作为 Phase 0A-1 首选候选。实际请求还必须显式传递最大输出 token 数和
`enable_thinking=false`。这些值在 probe 证据和运行时会审完成前分别继续受
`UNRESOLVED[P1_TEMPERATURE]`、`UNRESOLVED[P1_TOP_P]` 及相应 runtime 决策约束；
官方建议本身不构成 formal authority。

requested seed 是否被 vLLM 接受、传播和回显必须通过 smoke 实测。实测不能证明模型
位级确定性；不支持或不可验证时必须显式记录，不得伪造 seed guarantee，也不得把 probe
seed 语义自动提升为正式 event/cell 的 `P1_MODEL_SEED_PAIRING`。

## 4. 软件边界

### 4.1 独立真实 adapter

真实 adapter 只实现现有 `ProbeAdapter` 窄接口，接受不可变 `ProbeRequest` 并返回
`ProbeResponse` 或版本化错误。它不得接受 `GenerationEvent`、feed、Agent state、
checkpoint 或正式 run manifest，也不得放宽现有 mock-only adapter guard。

每个 transport attempt 必须保存：

- 完整请求消息、请求字段和 canonical hash；
- HTTP status、可得 response headers、provider request ID；
- 原始 response/error body 的字节数与 SHA-256；
- choices/content/finish reason/usage；
- 开始、结束和耗时；
- timeout、连接、HTTP、OOM、schema 或未知错误分类。

客户端仅允许连接预登记 loopback endpoint。endpoint、served model name 或响应身份不匹配
时立即停止，不能跟随重定向或自动切换 provider。

### 4.2 Preflight 与 environment lock

preflight 生成不含凭据的候选环境报告。受控执行前再生成不可变 environment lock，绑定：

- Git commit 与 dirty 状态；
- OS/kernel、GPU、driver、CUDA；
- Python 与全部安装包 lock；
- model/tokenizer repository、revision 和本地 artifact hashes；
- chat template 原文/hash 与 rendered non-thinking smoke hash；
- vLLM 版本、镜像 digest、启动参数与健康检查结果。

模型文件、环境或模板任一变化都必须产生新 lock，并使旧 run 不可继续。

### 4.3 Artifact store

每个 probe run 使用独立、不可变的外部目录，保存 manifest、specification、case inventory、
requests、attempts、raw responses、parse evidence、machine metrics、blind-review export/import、
gate report、freeze proposal 和完整 hash index。目录根由云端环境安全注入，实际解析后的
绝对 URI 写入 run manifest；`UNRESOLVED[P1_DATA_ARCHIVE_URI]` 关闭前不得开始真实 run。

原始响应、数据库、checkpoint、coverage 和大型 bundle 不进入 Git。Git 只允许提交代码、
schema、测试、小型脱敏 fixture、manifest/hash 和外部归档定位。

### 4.4 Credential boundary

SSH 私钥、云平台 token 和任何 API secret 均不得写入仓库、YAML、日志、命令行参数或
artifact bundle。连接信息由用户环境或受控 secret store 注入。Qwen3-8B 当前公开且非 gated；
若实际下载无需 token，不为方便而引入 Hugging Face credential。vLLM 服务使用 loopback，
不公开到互联网。

## 5. Probe specification 与执行规模

真实 specification 继承 Phase 0A-0 已验证的三类 cases：

- topic quality：三个议题、三组等义题干、1--7 主量表、0--10 challenger 与字段顺序挑战；
- identity：在共同题干和状态下仅切换最小身份块；
- continuity：平衡合理保持、充分反向信息和信息不足三类场景，只切换 continuity 块。

首次受控 run 使用四个预登记 replicate，保持 816 个逻辑 cases：topic quality 144、
identity 96、continuity 576。case ID 由 specification hash 与全部 case 坐标派生，执行顺序
不得改变 identity。并发只影响墙钟和 provider IDs，不改变 case、seed scope 或 canonical
报告顺序。

三个议题及 persona 的最终机器文本、量表标签、历史情境和 hashes 在本规格获批后进入
独立 decision packet。任何尚未获批文本必须继续使用相应 `UNRESOLVED[...]`，不得把
`platform/tests/fixtures` 中的 mock 文本提升为真实候选。

## 6. Runtime policy

真实 run 前必须冻结独立 `ProbeRuntimePolicy`，至少指定：

- connect/read/overall timeout；
- retryable 与 nonretryable 错误分类；
- 每类 transport attempt 上限；
- Retry-After 接受范围和非法值处理；
- 确定性 backoff 序列；
- OOM、server crash、模型身份变化和磁盘不足停止规则；
- 总体 case/attempt/时间/token 预算。

transport retry 不改变 prompt、case ID 或 requested seed，也不消费唯一一次 format repair。
format repair 只能在首次语义响应格式无效时追加统一格式提醒。runtime policy 耗尽后，case
成为该 run 中不可逆的 `runtime_failed`，run 为 `incomplete`，不得计算候选 pass/fail。

精确 timeout、attempt 和 backoff 数值属于 `UNRESOLVED[P1_TIMEOUT_RETRY]`，必须由 preflight
和 adapter smoke 支持后经运行时会审批准；Phase 0A-0 scripted 值不是 coder 默认值。

## 7. Semantic-review policy

机器 scorer 只处理可机械复核指标；构念、理由一致性、identity 使用、刻板化、continuity
连贯、合理改变和无依据改变由冻结的 semantic-review policy 处理。

候选 policy 采用：

- 一个固定 revision、固定 prompt 的独立 model judge 审核全部 eligible items；
- 人工对按 topic、family、condition/scenario 分层的确定性样本独立编码；
- 审阅包只显示 `topic_text`、`history_text`、`identity_text` 和 `response_text`；
- 不显示 factor condition 名称、候选优先级、sampling settings、其他编码或聚合结果；
- 任一维度分歧触发追加 adjudication；原始编码不可覆盖；
- 缺失、无效或无法 hash 回绑的必审记录使报告 `review_incomplete`。

judge 身份、人工编码者数量、精确抽样规模/分层、一致性统计及门槛、标签、passing labels、
adjudicator 与聚合函数继续属于 `UNRESOLVED[P1_CONTINUITY_MC_SCORING]` 等稳定决策 ID。
这些值必须在首条真实 response 前写入 decision packet 和 specification，不能根据响应结果
调整。

## 8. 数据流

严格数据流为：

`cloud preflight -> approved decision artifacts -> environment lock -> adapter smoke -> immutable run manifest -> cases -> attempts -> parse evidence -> machine metrics -> blinded semantic review -> gate report -> freeze proposal`

preflight 和 smoke 分属不同权限层。smoke 是真实模型调用，只有候选栈、凭据边界和临时
smoke 归档位置批准后才能执行。正式 816-case run 只有在 smoke 通过且六项启动制品全部
绑定后才能开始。

## 9. Smoke 与停止门

adapter smoke 使用独立 `calibration_only` run，不与 816-case evidence 拼接。它最低验证：

- model 与 tokenizer revision 可读取且 hash 匹配；
- BF16、原生上下文和 no-YaRN 配置；
- non-thinking 响应不含 thinking 内容；
- 合法 JSON、格式失败、拒答和长度终止的原始证据；
- request ID、usage、finish reason、headers 和 raw body 保存；
- seed 接受/传播可观测性；
- timeout、不可达服务和至少一种受控 HTTP 错误的分类；
- 服务重启后未完成 case 的恢复边界；
- artifact 根目录容量、原子写入、hash index 和只读复验。

以下任一条件使受控 run 停止：模型/runtime/template 身份漂移，endpoint 非 loopback，
thinking 未禁用，响应证据不完整，archive 写入或 hash 失败，磁盘/显存低于预登记安全线，
policy 耗尽，或者代码/环境 lock 不一致。

## 10. 报告、选择与解释边界

完整 run 才能生成候选 gate。确定性硬门与 Phase 0A 总设计一致：至多一次 format repair 后
解析率至少 99%，实质拒答率不高于 1%，1--7 主量表至少使用四类，单个端点占比不超过
80%，等义配对 `abs(d_z) <= 0.20`，理由--立场直接矛盾率不高于 5%。完整分布差异必须
报告；未预登记阈值不得事后用于淘汰。

多个议题通过全部硬门时，按 `延迟退休 > 转基因大豆油 > AI净就业` 选择最高优先者；
下一顺位通过者才可进入缩减稳健性候选。三个议题均失败时停止并重开题干/量表设计。

报告不得计算或展示网络极化、均质化、方向漂移、cell contrast、CI、p 值或叙事吸引力。
freeze proposal 只是建议；只有后续人类/方法/运行时审批和 decision record 才产生 formal
authority。

## 11. 分级冲刺与下周交付

Phase 0A-1 完成后，后续运行仍按独立 gate 推进：

1. N=20/100：验证真实 event pipeline、恢复、证据和存储；
2. N=200/500：完整 12 cells 的有限规模机制趋势，形成明确标注为 preliminary 的图表；
3. N=1000 单 matched seed：容量与墙钟门；
4. 正式首批 10 matched seeds：仅在 formal protocol、统计规格、archive、环境锁和成本门
   全部关闭后启动。

下周优先交付是：真实 calibration report、主议题/persona freeze proposal、云端吞吐与成本
基准，以及通过完整性检查的 N=200/500 初步趋势。不能把有限规模趋势写成正式 Paper 1
验证结果，也不能承诺在真实吞吐未知时完成约 600 万次生成的正式主矩阵。

## 12. 验收标准

Phase 0A-1 只有同时满足以下条件才算完成：

- 六项启动制品获批且 hash 绑定；
- environment lock 与实际服务身份一致；
- adapter smoke 全部通过；
- 816 个逻辑 cases 均有唯一语义终态，或 run 明确 `incomplete` 且不产生选择；
- request/response/parse/review 证据数量和因果引用完整；
- semantic review 完成并通过一致性/裁决合同；
- gate report 和 freeze proposal 可从归档 evidence 重建；
- Git 中没有凭据、原始响应或大型运行制品；
- 三路独立复核无未关闭 P0--P2；
- 交接日志记录代码 SHA、环境/model/runtime identities、精确测试与运行计数、hash 和 archive URI。

通过以上验收仍只表示 Phase 0A-1 校准完成，不表示 Phase 0B、formal readiness 或正式实验
完成。
