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

### 读侧因果输入已接通

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
这不是完整事件恢复：record_prepared_attempt、record_diagnostic_prepared_attempt、
append_attempt、commit_success在SIS subclass上仍明确拒绝调用。
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
