# 新 2×3 单事件接口交接（2026-10-01）

## 本阶段完成

工作分支为 codex/social-identity-network-2x3；旧实验归档与 main 不变。
新增 identity_network/execution.py 的 prepare_study_event 与
finalize_study_response，不引入第二套解析器或云端调度器。

renderer v2 使用 typed TopicPackage、文字 stance labels、整数 1–5 confidence。
准备接口绑定原状态、TopicPackage、实际模型可见内容、事件/尝试身份、外生
publish_flag 和显式模型 seed/settings。完成接口复核响应与 transport 实际发送内容，
严格解析后构造候选 PrivateUpdate/PrivateState/PublicPost。
失败不改变原状态；重试保留事件身份。trace 是 prospective，committed=false。

独立审查发现的重新哈希 prompt 投影篡改及 wire body 篡改已修复并闭环复核。
最终专项：六个 identity_network 测试文件及旧 adapter/parser/state/topic，
106 passed in 1.42s；Ruff check 通过。所有 HTTP 响应为测试替身，
并非真实模型结果；未启动 AutoDL、未运行全仓 pytest。

## 下一阶段：持久化与完整六条件运行

### 当前最新阶段：SIS 响应与成功/失败终态前缀

`start_diagnostic_attempt`只接受当前已落盘的精确PENDING，保存IN_PROGRESS；
不发送HTTP，也不构成真实运行授权。IN_PROGRESS重开仍要求provider reconciliation，
不能自动重发。普通append与commit仍关闭。

`record_diagnostic_invocation_evidence`从durable input/request重建PreparedStudyEvent，
核对实际source/common contract与exact wire消息、settings、seed、served model。
invocation授权必须与durable request相同；成功响应必须声明相同provider model。
调用共享bounded finalizer，保留畸形/越限响应为失败解析而非丢弃响应证据。

`record_diagnostic_finalized_attempt`要求parse与独立bounded重放完全相等，复用
共享v6事务原子保存parse及成功/失败terminal。插入中断parse/terminal均回滚。
六格成功和失败终态关闭重开核验通过，private state/cursor/ordinal仍不变。
冷重放也核对wire/model/authorization及bounded parse，重哈希不能绕过这些合同。

本阶段支持当前未提交事件的response/terminal；historical input replay、状态
atomic commit、失败收口/重试授权、发送意向/恢复编排、六格runner仍待接入。
不要用旧MockEventPipeline读取SIS输入。所有新测试为合成provider响应，
没有新真实模型数据、没有云端调用；服务器仍不需开启。
验证：391 passed、2环境skip；Ruff/format/diff通过，独立响应阶段审查收口。

### 上一阶段：SIS 请求前 PENDING 原子落盘

`StoredStudyInput`（stored-event-input.v2）保存 typed SIS input 与完整 causal
snapshot；不是旧 ExposureRecord，也不通过旧十二格输入 reader 冒充兼容。
manifest 同时保存完整 `identity_network_execution_inputs` 与候选
`sis_diagnostic_authorization_hash` 引用；缺任一项不得写入请求前记录。
后者只是候选哈希绑定，尚非真实运行审批凭证或正式参数授权。

`record_diagnostic_prepared_attempt` 在单个 SQLite 事务中写 input、policy、
adapter binding、request 与 PENDING transition。核对实际 round-0、当前状态、
排程、source posts/private history、有限feed/memory及exact group/alias/persona
prompt；模型seed/settings和policy来自共同制品。重复相同PENDING不会增行；
插入中断全部回滚。六格关闭重开可重放，重新哈希的错误来源绑定仍拒绝。

最初PENDING阶段门已按上述response阶段扩展；advanced ordinal仍拒绝，
普通append/commit入口仍关闭。共享diagnostic topic引用已改为受保护投影，
下一步扩展历史输入重放和atomic commit，随后接发送意向与运行编排。
不能仅删除这些阶段门就认为运行器可用。
没有真实HTTP、云端使用或新实验数据；云服务器仍不需要开启。

### 共同执行制品已绑定（上一阶段）

execution_inputs.build_execution_inputs显式传入StudyRunBinding、完整persona_by_agent、
initial_updates tuple、feed_capacity、memory_window、typed parser_limits、generation
settings、完整model_seeds tuple、DiagnosticAdapterBinding和DiagnosticAttemptPolicy。
输出payload是六格共同身份与实际配置；common_inputs_hash引用artifact.output_hash。
可先用候选binding构造制品，再用相同不可变基础制品重新创建binding写入该hash；
不含cell或binding.record_hash以避免循环，不改变已创建数据库manifest。

validate_execution_inputs重建全包并核对输出hash/envelope/嵌套权限/完整覆盖。
StudyRunStorage.prepare_bound_snapshot_event(snapshot, common_inputs, attempt_index=...)
核对actual round-0完整updates，并从artifact得到接收者persona、feed/memory、parser、
当前event seed、generation及adapter binding，不接受调用者覆盖这些设置。

同对象的深度不可变制品/binding在同一store内仅校验一次；数据库每次仍先复核
connection signature。完整性重放已调用SIS sealed round0 validator，避免额外反复
全人口扫描；unsealed partial仍检查，重开无缓存，两种数据库篡改路径有负例。
该接口仍不派发/写入/授权retry。候选population注意与表达的抽样provenance须由
materializer另行关联；正式N/T/seeds/outcome仍未冻结。下一步接durable lifecycle。

### 读侧因果输入已接通

新增 prepare_snapshot_event(snapshot, persona_text=..., feed_capacity=..., memory_window=...,
attempt_index=..., parser_limits=..., model_seed=..., generation_settings=...,
adapter_binding_hash=...)。方法要求lease并重新生成当前完整快照，任何snapshot字段或
envelope身份不一致就拒绝；之后只从current快照构造原PreparedStudyEvent。
专项101 passed（包括六格SQLite输入→假HTTP adapter→解析，库状态不变）。
此接口不派发请求、不持久化input/policy/intent，也不授权retry。必须保留snapshot
作为未来durable-prefix配套来源证据；单独的PreparedStudyEvent尚无完整候选feed。

StudyRunStorage.snapshot_next_input(persona_text=..., feed_capacity=..., memory_window=...)
要求本实例持有writer lease、round-0已封存且还有schedule slot；只读事务内复核库，
根据bound node mapping/实际B1或B2图读取neighbors的公开未读帖子，读取接收者私人
历史，复用共享选择规则并调用renderer v2。返回包含完整source rows、selection、
memory、pre-state、chain head、publish flag和prompt evidence的ArtifactEnvelope。
返回后read transaction rollback；没有写入状态、游标、attempt或发送请求。

最终专项114 passed，独立审查无阻断问题；含邻居帖子超容量的过期覆盖。
候选capacity/window仍限共享Phase0 challenge值（4/6/8与1/3/5），
不是正式参数；persona/feed/memory共同制品完整绑定仍需完成。通用envelope roundtrip
并不是授权输入reader，后续prefix必须复核数据源并拒绝rehashed语义篡改。

### 六条件运行绑定与 round-0 存储已接通

identity_network/storage.py 新增 StudyRunBinding 与 StudyRunStorage。
绑定包括完整 group/topic/schedule/WS/randomized 制品、节点agent映射、中性别名和
显式common_inputs_hash，完整payload存入manifest.run_spec.identity_network_binding。
先以binding.storage_arguments()提供共享create/open所需参数；实例复用原SQLite v6。
默认RunStorage仍拒绝SIS，SIS subclass也拒绝legacy manifest。

已测试六格创建、20个测试agent初始化、seal、关闭和重开，及初始化/seal中断回滚。
未封存的partial状态也核验bound stance/topic；独立审查收口。
旧存储相关回归265 passed/2环境skip；最终新接口专项64 passed。
这不是完整事件恢复：当前仅record_diagnostic_prepared_attempt已开放为上述
PENDING原子前缀；record_prepared_attempt、append_attempt、commit_success仍关闭。
下一批实现SIS自己的causal prefix/finalization/commit入口，保留共用底层事务。
common_inputs_hash并非正式参数授权，也未替代materializer对共同persona/reason/
memory/feed/model/publication制品的核验。云服务器仍无需开启。

### 已接续完成 Step 5b-1

新增 identity_network/evidence.py 的 StudyEventInputEvidence，含 to_payload /
from_payload / from_prepared，schema 为 paper1.identity-network.event-input.v1。
其完整 topic、parser、原状态和 prompt 可重建，不含 request/attempt，重试不改输入。
storage.decode_event_input_payload 明确分流 SIS / legacy；当前旧 RunStorage
依然拒绝 SIS 记录。独立审查收口了嵌套证据字段/权限、历史类型、重复帖与别名漏洞。
存储相关回归 290 passed / 2 Windows 环境 skip；最终修复后接口专项 52 passed。
这是读取前置，不是已经能写入运行。下一步优先是第 1 项的 SIS 运行 binding
与第 2 项原子提交，仍需将 feed 的候选/过期/选中链和源帖上下文绑定进去。

1. 为 SIS cell 和输入证据新增明确的存储 discriminator / reader union；
   不绕过旧 RunStorage 对 legacy P1 cell 的验证。
2. 串行原子提交 state/public output/feed cursor，失败不推进；重开、重试、
   resume/checkpoint 必须复用事件身份并验证 exact cover。
3. 六条件 materializer 绑定同一人口、初始状态、组别、记忆和 matched seed 网络；
   验证跨事件中性别名、帖子来源及只读真实公共表达。
4. 绑定实际获准模型 revision / 服务身份，再准备 manipulation check 的明确
   样本、判据、运行配置。保持 SIS 未决参数，不使用程序默认值填补。
5. 本地闭环后再请求开云服务器，先做真实 identity manipulation check，
   再进入小规模六条件 pilot。正式 N/T/seeds/primary outcome 尚未冻结。

不能把候选公开输出当作实际发表；当前接口不写 SQLite、不修改游标，
不证明真实服务模型身份或源帖因果来源。旧 797 盲判证据不应重跑或合并到新研究。
