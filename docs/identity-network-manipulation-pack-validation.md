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

未覆盖：fixture 与实际人口/persona/初态来源的绑定、采样规则、结果真实性和
stage-one no-signal 判定、独立 dispatch authorization、真实运行器与报告。
StageTwoReceipt 仅记录归属，不能凭一份自造 receipt 启动第二阶段。

候选仍是 preliminary / not_frozen / formal_parameter_authority=false。
不以本地合成测试 fixture 代替研究候选，不通过修改 prompt 反复寻找效应。
服务器目前不需要开启。
