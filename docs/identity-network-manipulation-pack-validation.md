# 身份操纵检验包：保存后冷核验边界

`identity_network.manipulation.validate_manipulation_pack(pack, topic_package=topic)`
要求已冷读取的 `ArtifactEnvelope` 和独立提供的 `TopicPackage`。返回重建的
`CheckCase` 元组；不发送请求，不读取响应，不修改 SQLite。

校验内容：

- fixture 字段精确覆盖、prompt/evidence hash 与 renderer 内容符合该 topic；
- 四个 Blue/Green × same/other trial 的内容、唯一身份、sampling seed；
- 从固定 RNG provenance 重建的排列，以及全部派生字段和 envelope；
- predefined stage 和 stage-two receipt 结构，不接受附加字段或授权标签漂移。

即使篡改者重新计算全部 hash，添加“赞同群体”系统指令、替换 fact card 或单独
修改 trial、seed、顺序也不能通过该派生核验。一个完整重建且合法的新来源包则是
另一份候选，仍须单独批准；hash 自身不是人类授权或来源真实性证明。

## 与候选来源绑定

`manipulation_sources.build_source_bound_manipulation_pack` 接收完整六格 candidate，
以及显式非空 selections：每项严格为 `case_id/receiver_id/source_id/sampling_seed`。
禁止 receiver 与 source 相同、未知人口、重复 case identity 或隐式采样默认值。

它从共同来源读取 receiver 的真实候选 persona、round-0 private update，以及同一
`build_memory_view` 规则的初始记忆；来源帖子由指定 source 的已绑定 round-0
公开 update 派生，保持匿名 alias。四个配对变体共用全部这些内容。
`validate_source_bound_manipulation_pack(artifact, candidate=independent_candidate)`
再从独立 candidate 完整重建，拒绝 renderer 合法但不属于来源包的替代 persona。

这是 **round-0 controlled single-message check**，不是 randomized/WS 邻居曝光，
也不模拟已发生的多轮互动。初始记忆只有 round-0 条目，不人工填满 K；如果后续
研究者选择更长历史的检验样本，须另行绑定真实历史来源，不能把该接口当作已支持。
纯素材物化不评估 signal、不核验 stage-one 结果，不授予第二阶段发送权限。

未覆盖：候选来源的人类真实性审查、实际 selections/采样规则冻结、结果真实性和
stage-one no-signal 判定、独立 dispatch authorization、真实运行器与报告。
StageTwoReceipt 仅记录归属，不能凭一份自造 receipt 启动第二阶段。

候选仍是 preliminary / not_frozen / formal_parameter_authority=false。
不以本地合成测试 fixture 代替研究候选，不通过修改 prompt 反复寻找效应。
服务器目前不需要开启。
