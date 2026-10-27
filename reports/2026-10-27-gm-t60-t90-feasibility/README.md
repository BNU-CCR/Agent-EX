# GM T60→T90续跑可行性与实施准备

状态：只读初审完成；版本化执行器/合同尚未实现或验收，未授权真实请求。本轮交付计划而非可执行冻结包。

## 1. 已实际检查的12个父run

云根 `/root/autodl-tmp/agent-ex-cross-topic-run-20261025-v1`。路径模式 `research/gm-market-support/seed-{seed}/SIS-A{a}-B{b}/run.sqlite3`，seed20261201/2、a0/1、b0/1/2，恰好12个。分别以SQLite URI mode=ro及PRAGMA query_only=ON读取；无写连接、无模型请求。

| seed | cells | 每run commits | ordinal范围 | 每run snapshots | 未提交attempts | WAL/SHM |
|---|---|---:|---|---:|---:|---|
| 20261201 | A0B0/A0B1/A0B2/A1B0/A1B1/A1B2 | 各30000 | 各0..29999 | 各61 | 各0 | 均无 |
| 20261202 | 同上六格 | 各30000 | 各0..29999 | 各61 | 各0 | 均无 |

全部终态快照有next_event_ordinal/private/private_update_count/public/public_last_ordinal；binding包含原run_id、contract_hash、slots_hash、event_chain_head、Round0/common/binding/authorization等。字段存在并不证明新的恢复器已正确消费完整状态。

本轮未再次全链冷重放或重新hash全部DB；既有根审计/四归档验收见 [阶段证据索引](../../docs/research/2026-10-27-stage-status-and-evidence.md)。新续跑准入时必须重新验证当前DB/原dispatch与冻结hash、最终事件链及完整消息历史，不把本轮计数检查代替新门。

## 2. A/B方案及候选成本

| 项目 | A：仅网络 | B：完整六格 |
|---|---:|---:|
| seeds | 20261201/2 | 同左 |
| cells/seed | A0/A1×B1/B2 | A0/A1×B0/B1/B2 |
| runs | 8 | 12 |
| 新ordinal | 30000..44999 | 同左 |
| 新事件/run | 15000 | 15000 |
| 新研究请求 | 120000 | 180000 |
| 候选技术额外上限 | 4 | 4 |
| 候选总上限 | 120004 | 180004 |
| token粗估（仅研究） | 约7556万 | 约11334万 |
| 采集墙钟粗估 | 约4小时 | 约6小时 |
| 新DB基础投影含25%余量 | 6299668480字节 | 9449502720字节 |
| 规划可用磁盘目标 | 约20GB | 约30GB |

预算基础：上一跨题批720000请求/453370535 tokens/84118.227721秒、8并发；不同条件/晚期输入改变实际吞吐和token，不能当承诺。DB以当前最大1259933696字节/30000事件线性折半再乘run数及1.25。20/30GB还需在冻结包中明确日志、schedule、分析与双端归档峰值，不是准入既成事实。技术4是提议独立预算，不继承已耗尽旧4次；含失败尝试，禁止盲重发。

建议B用于同期B0对照，A作为资源受限选项。选择/上限为 `UNRESOLVED[SIS_NEXT_GM_T90_SCOPE]`；未批准前二者都不能开跑。

## 3. 原状态→新合同映射

| 原证据 | 新扩展必须记录/保持 |
|---|---|
| run_id/event head | 显式parent_run_id与parent_event_head；续接因果链，扩展operation_id独立，不冒充fresh R0 |
| commits/attempts/dispatch/journal | 前30000个事件逐identity、模型seed及排程hash不变；原合同不扩写 |
| R60 private/update counts | 完整500Agent原值；恢复前逐项匹配 |
| public/public_last_ordinal | 含原公开帖及时间，不能把私人状态抄作最新公开帖 |
| 历史与读取游标 | 保留恢复feed和K3所需已提交历史/未读边界；只读父历史+新tail联合读取，不能仅复制终态向量 |
| common/round0/binding | 原人口、注意权重、群体、网络、材料、理由、外生发布、B4/K3及renderer不变 |
| 原模型/服务 | 同revision/BF16/non-thinking/8192/native采样，部署前核验实际服务，不重启/换模型 |
| budget | 独立原子账本，新研究与额外均有持久reservation，旧720004只读不清零 |

新尾段独立SQLite，禁止父路径别名/symlink/hardlink误写；原DB/journal/hash/manifest保持字节不变。schema中暂无新扩展类型，不以写个T=90字段当实现完成。

尾激活/发布随机流必须定义新namespace和global ordinal、同seed跨cell匹配、不得含结果或totalT。模型generation seed沿用原事件身份规则并验证范围30000..44999碰撞；现有两题schedule与退休extension看似相近也不能未经审计混用。确切namespace、公式与绑定见 `UNRESOLVED[SIS_NEXT_GM_T90_RNG]`，未决即fail closed。

## 4. 工程实施计划（零真实请求阶段）

新增能力只在platform版本化模块，例如identity_network/gm_temporal_contract.py、gm_temporal_store.py、gm_temporal_run.py，及对应tests；这些是计划路径，当前不承诺文件已存在。livePACKAGE、旧cross_topic及退休temporal合同不改科学含义。

- [ ] 新扩展合同单元测试先拒绝旧预算、非GM、外部seed、错误parent head/前缀和未决字段；然后实现最小不可变合同及canonical hash。
- [ ] 父只读+tail单写存储测试：同事件commit严格串行，错误不改状态/游标；注入父路径和符号链接必须在任何DDL前拒绝。
- [ ] 新schedule测试：prefix30000逐字节与父schedule一致，tail15000同seed跨A/B匹配，模型seed与事件身份可追溯，不重新生成原R0–60。
- [ ] Linux假运输完整tail15000/91边界验收；分别在intent未发、已发无response、已存response未commit、commit后中断。保存响应仅重放提交、无response歧义停止，不自动重发。
- [ ] 联合只读冷重放R0–90；原T0–60数值精确一致，T61–90事件流量/公开库存/私态/91边界守恒，原父SHA前后不变。
- [ ] 源码、输入、model/service/context压力、实际容量、授权、V盘目的地、源/整包/成员校验全部内部绑定；独立规格/质量复核及Linux同候选验收后才考虑真实门。

## 5. 真实门与停止规则（待新授权）

选择A/B及技术上限→冻结父证明/新合同/截止→仅一次技术预检→审查原parser/保存响应/账本一致→固定最多8并发且run内串行。任何共同服务/源码失配全局停止新派发，局部歧义隔离；不重跑已完成事件。ordinal45000终止新请求，排空writer再离线冷验。

所有snapshot/CSV/图表支持R0..90共91点，固定T30/T60/T90及三个30轮窗口；同时报3/5份额、迁移、方差/斜率、初始组、公开stock/flow/gap、实际曝光与网络局部指标。T90是事先确定终点，不因峰是否消失延长或早停。只描述平台内趋势，不把两seed或晚期低变化率称数学吸引态。

完成标准：真实新增精确事件数、无未决、旧prefix/source/DB不变、全程冷验、实质数值包、Linux/V迁移严格复算、云/V整包及每成员hash/CRC闭合。新档必须包含恢复所需父依赖定位，不把tail-alone称完整恢复包。

## 6. 容量与删除边界

当前云余6504673280字节，A仅DB投影就约6.3GB，不通过真实准入。本轮不扩容、不清理。可先在V完成离线准备；真实前另审扩盘或按逐文件manifest覆盖/恢复演练核对后回收旧副本。旧research/run.sqlite3与云tar原来明确保留，未经新授权不得删除；尤其GM父12DB暂保留。第二模型显存问题不能靠扩盘解决。
