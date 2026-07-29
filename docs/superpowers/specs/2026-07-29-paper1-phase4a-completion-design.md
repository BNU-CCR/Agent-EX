---
status: approved design; independently reviewed; pending user written-spec review
authority: Phase 4A completion design; subordinate to future frozen machine protocol and schema
approved-by: user
approved-date: 2026-07-29
supersedes: synchronous update and round-level exposure semantics in the 2026-07-14 focused spec
---

# Paper 1 Phase 4A 完成设计

## 1. 目的与完成边界

本规格完成 Paper 1 正式平台在进入 Phase 4B 前所需的最小研究设计。它冻结：

- topic、population、persona、network、activation、expression、exposure、memory
  和 event recovery 的机制语义；
- Phase 0 必须使用的候选、过程指标、失败规则和禁止读取的结果；
- 跨12 cells、跨matched seeds和跨RNG namespace的复用边界；
- Phase 4B必须提供的公开接口、制品、校验和mock能力。

本规格不伪造仍需数据、真实模型或运行基准才能确定的机器值。正式数据文件、模板原文、
分布参数、模型revision、运行预算、统计阈值及其hash仍须在相应gate冻结。formal配置
只要包含未决字段就必须失败。

## 2. 不变的研究边界

- 主矩阵固定为`identity 2 × continuity 2 × exposure 3 = 12 cells`。
- 正式规模固定为N=1000、T=50 sweeps、首批10个matched seeds，盲态规则最多扩到20。
- 每个sweep包含N次有放回事件；正式run共50,000个激活事件。
- 主模型路线为自部署Qwen3-8B、BF16、non-thinking、vLLM；revision和runtime制品后冻。
- Paper 1不微调权重，不加入动态重连、真人—AI混合网络、推荐算法、RLHF矩阵或
  weak/lifelong复合prompt。
- 私人意见是唯一primary状态；公开存量、公开流量和表达偏差为强制secondary。
- seed/run是独立重复单位，N不是重复数。

## 3. Topic package与议题选择

### 3.1 通用接口

平台必须以版本化topic package提供：

- `topic_id`、单一构念说明、目标总体与适用边界；
- 冻结事实卡、核心陈述、等义挑战题干及其hash；
- 七档文字标签、独立confidence字段及结构化输出合同；
- 来源约束论据家族、round-0理由库及其审计制品；
- 议题扩展人口字段，默认不得进入共同身份卡。

引擎、网络、feed和指标不得硬编码任何议题正文。

### 3.2 三议题probe与选择

Phase 0A同时probe延迟退休、转基因大豆油和AI净就业预测。硬门槛包括：

- 实质拒答率不高于1%；
- 至多一次格式重试后有效解析率不低于99%；
- 等义题干方向稳定，字段顺序挑战不改变构念；
- 七档响应不过度退化为单一点或单一端点；
- 理由与分值一致，事实卡不引入第二构念；
- 无不可接受的身份泄漏、安全模板化或议题无关答复。

若多个议题通过全部硬门槛，预先按`延迟退休 > 转基因 > AI就业`选择完整12-cell
主议题；下一顺位通过者进入缩减稳健性。不得根据网络极化、均质化、显著性或论文
叙事吸引力选择议题。

## 4. 合成人口、初始化与matched seed

### 4.1 人口来源和整数化

- 目标总体为中国大陆18岁以上、过去半年上网的家庭/社区居民。
- CFPS2022成年网民是联合微观供体；NBS2025、七普2020和CNNIC第57次报告分别提供
  兼容的最新总体、详细结构和网民边际；CGSS/CLDS仅作外部验证。
- 校准后连续权重使用TRS（truncate–replicate–sample）整数化：
  1. 截断每条供体权重；
  2. 按整数部分复制供体；
  3. 按小数余量概率补足；
  4. 输出必须恰好N条记录。
- 每个matched seed从同一冻结人口框独立执行TRS；同seed的12 cells复用完全相同的
  人口。因而seed间包含人口抽样变化，cell间保留common-random-number配对。
- 结构零、缺失、不可实现边际和超容差均须fail；不得独立随机拼接字段或运行中修配额。

### 4.2 字段和身份卡

共同记录保留年龄、调查记录性别、教育、当前城乡、主要活动/劳动状态和就业者宽
职业组。只在identity-present中显示最小共同身份卡；精确年龄、地区、户口、敏感
身份、主观好恶、议题知识和方向性经历不得自动显示。

正式数据版本、变量crosswalk、边际值、许可、容差和hash在population artifact构建时
冻结；在此之前formal population config保持未决。

### 4.3 初始立场和round 0

- 七档初始人数固定为`[50,100,200,300,200,100,50]`。
- 初始立场与人口字段受约束随机正交，并在同seed的12 cells逐Agent匹配。
- 每个Agent在round 0均具有私人初始立场、私人初始理由和一条公开初始帖子。
- 结构性潜水者只从round 0以后停止公开表达，仍可阅读和私人更新。
- round-0理由来自冻结的来源约束离线理由库，不在正式运行中自由生成。

## 5. Persona

四个模板由共同骨架确定性插入identity块与continuity块：

- absent条件真省略，不使用中性占位persona；
- identity只增删最小身份卡；
- continuity只增删历史解释连贯要求，并明确允许被有说服力的信息改变；
- 禁止抗从众、固定方向价值、最大步长和“永不改变”；
- 模板原文、块顺序、ID、hash和操纵阈值由Phase 0A冻结。

所有cells都具有相同的私人状态、可见自身记忆接口和输出合同；因素块以外不得出现
条件特异文字。

## 6. 网络与来源关系

### 6.1 E2：WS图

- 无向、简单、全连通；N=1000首选`k=10,p=.05`。
- `{6,10,20} × {.02,.05,.10}`只用于锁定NetworkX版本后的结构挑战。
- 每个matched seed生成一张图并随机映射Agent到节点；同seed所有E2 cells复用。
- 图选择只读取结构、连通和资源指标，禁止读取意见结果。

### 6.2 E1：shadow graph

- 每个matched seed生成一张整个run固定的无向简单shadow graph。
- 逐节点精确保留对应WS度数，禁止自环、重边和任何真实WS边，并要求全连通。
- 同seed所有E1 cells复用同一shadow graph。
- 构图、验证或hash失败即fail fast；不得运行中重抽或修边。

### 6.3 E0

E0没有社会来源，不使用无关文本补齐输入。它估计无社会信息相对于社会信息的总差异，
不解释为纯拓扑对照。

## 7. 激活、私人更新与公开表达

### 7.1 激活

- 每个Agent拥有严格正的长期注意/私人更新权重。
- 主权重族为截断对数正态，并归一化`sum(w_i)=N`。
- 截断Pareto是更重尾敏感性，全部`w_i=1`是无异质性机制基线。
- 每sweep按权重有放回抽取N次；同seed的12 cells复用权重和完整激活序列。
- 被激活Agent读取事件前已经提交的状态，成功后立即提交；后续事件可见该更新。
- run内每次抽取都分配连续全局`event_ordinal`；`event_id`由
  `run_id × event_ordinal`唯一派生。sweep与agent_id只是事件属性，不得替代ordinal。

### 7.2 私人和公开双状态

每个成功事件只调用一次主模型：

1. 构造自身记忆和当前社会feed；
2. 生成新的私人立场、私人理由和confidence；
3. 更新私人状态；
4. 读取预生成`publish_flag`；
5. 若为真，以本次私人立场/理由替换最近公开帖子；若为假，公开帖子保持不变。

社会feed只能读取公开帖子。私人状态、未公开理由和confidence不得泄漏给其他Agent。

### 7.3 公开表达

- 结构性潜水者在round 0后`publish_probability=0`。
- 非潜水者的个体表达倾向来自Beta分布。
- 主模型中注意权重与表达倾向独立于彼此、人口、初始立场、WS度数和实验cell。
- 正相关注意—表达仅作为预注册敏感性能力，不自动扩展主矩阵。
- 精确潜水比例、Beta参数、注意分布参数和截断在Phase 0只按过程指标校准。

## 8. 有限未读社会feed

### 8.1 候选与容量

- E1/E2候选为接收者上次激活游标之后，其曝光图邻居产生的全部新公开帖子。
- 主容量候选为`B=6`；Phase 0挑战`B∈{4,6,8}`。
- 候选超过B时取事件序列最新B条；更旧未读帖过期，游标仍推进到当前事件。
- 候选不足B时不回填已读旧帖；无新帖是合法空feed。
- 第一次激活将曝光图邻居的round-0帖子作为候选；相同round-0时间使用冻结seed
  均匀打破入选优先级。
- 同一发送者的多条新帖允许同时入选，使公开贡献不平等进入信息流；每发送者最多
  一条只作来源覆盖敏感性。

### 8.2 载荷与显示顺序

每条消息只显示稳定中性成员ID、七档文字立场标签和公开理由。不显示数字分数、人口
身份、私人状态、confidence、节点编号或条件。

新近性只决定入选。入选后的prompt槽位由
`matched_seed × receiver × event_ordinal`的冻结排列决定，并在E1/E2复用。
来源、候选、入选、过期、原始事件序、槽位、渲染文本和hash均须记录。

全邻居最近帖快照只作预注册高暴露稳健性；立场、相似性、热度或LLM排序不进入
Paper 1。

## 9. 自身记忆

- 模型可见自身记忆以最近K次成功私人更新为单位，而非最近K次公开发帖。
- 主候选`K=3`；Phase 0挑战`K∈{1,3,5}`。
- 每条记忆含私人文字立场、私人理由和该次是否公开；按旧到新排列。
- round 0只在尚未被滚动窗口挤出时可见，不永久置顶。
- 完整历史永久保存在证据链，但不全部放入prompt。
- 不使用LLM反思摘要或二次生成压缩。

K只按token、位置利用、continuity操纵、解析和吞吐gate冻结，禁止按极化或处理效应
选择。

## 10. 事件、失败和恢复

- 单run内严格串行提交事件；不同run/cell可并行。
- 激活序列与publish flag预生成；feed从已提交事件日志确定性构造。
- LLM或解析失败不得修改私人状态、公开帖、feed游标或publish状态。
- 每次重试创建同一event下的新attempt并保留原始响应、错误和请求hash。
- 重试耗尽后run停在该event并失败；主分析禁止跳过、插补或fallback。
- 恢复必须从同一event_id继续，并验证checkpoint、前序状态hash和事件链。
- sweep是观测、汇总和checkpoint边界，不是同步提交屏障。

主分析要求所有预期事件成功。`excluded`只可作为成功事件/完整run上的分析层标记，
不是状态链终态；imputed/fallback不得进入Paper 1主路径。任何例外必须由后续分析
冻结规则显式审批，不得在运行中临时放宽。

## 11. RNG、制品与证据合同

至少分离以下RNG namespaces：

- population TRS；
- initial stance assignment；
- initial reason assignment；
- WS graph与Agent—node mapping；
- shadow graph；
- attention weights；
- expression propensity；
- activation sequence；
- publish flags；
- round-0 tiebreak与message slots；
- model sampling（跨cell配对及同event重试复用语义保持
  `UNRESOLVED[P1_MODEL_SEED_PAIRING]`，adapter实现前必须显式冻结）。

所有事件级RNG键必须包含`event_ordinal`；有放回激活下不得使用
`sweep/round + agent_id`充当唯一键。

RNG作用域按component登记：population/initialization/network/attention/expression/
activation/publish/message-slot等跨12 cells复用的制品使用matched-seed common scope；
只有协议明确的cell特异过程才加入cell identity。model sampling的作用域继续由
`P1_MODEL_SEED_PAIRING`冻结。

Phase 4B至少实现以下版本化制品和验证报告：

- topic package；
- population与初始化；
- persona templates；
- WS、shadow graph与node mapping；
- attention/expression与frozen schedule；
- private state、public post、feed cursor与exposure record；
- event/attempt/checkpoint/run manifest。

所有制品必须有稳定ID、schema版本、生成算法版本、输入hash、输出hash和RNG provenance。

## 12. Phase 0非结果导向冻结

### 12.1 允许读取

- 拒答、解析、格式和理由—立场一致性；
- population边际/联合误差和TRS残差；
- 网络结构和shadow约束；
- 激活/发帖Gini、top份额、最大份额、零激活/零发帖；
- 空feed、过期、来源覆盖、同源重复、消息年龄、token和吞吐；
- continuity操纵、位置利用和模板退化；
- runtime失败、显存、吞吐和恢复完整性。

### 12.2 禁止读取

- 极化、均质化、漂移或双层结构的方向和大小；
- primary cell contrast、均值、CI、p值或显著性；
- 哪个议题、B、K或分布参数产生更“有趣”的论文结果。

### 12.3 仍未冻结

- 正式数据文件、crosswalk、边际值、模板/题干原文和hash；
- 注意、表达、B、K的最终机器值及容差；
- 模型revision、vLLM镜像、generation参数和runtime预算；
- primary终点、B/W公式、epsilon、形态阈值、推断和最小重要效应；
- API snapshot、稳健性规模、正式seed列表和归档URI。

这些字段在各自gate完成前继续使用`UNRESOLVED[...]`，但Phase 4B可实现其类型、
验证接口、draft config与mock fixtures。

## 13. Phase 4B实现边界

批准本规格后，Phase 4B按以下顺序准备实施计划：

1. 修订schema和domain records以支持事件级激活、私人/公开双状态、feed游标和新制品；
2. population TRS、初始化、topic/persona artifact；
3. WS/shadow graph生成与结构验证；
4. attention/expression制品、activation/publish schedule；
5. feed、memory、prompt view model；
6. mock adapter、严格串行event engine、checkpoint/recovery；
7. N=20/100/1000确定性与不变量测试。

旧pilot保持冻结；Notebook不得承载正式主循环、feed算法或指标定义。任何仍未决参数
不得用测试常量冒充正式值。
