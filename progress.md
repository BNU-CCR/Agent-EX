# 进度日志

## 会话：2026-07-14

### 阶段 1：项目盘点与审计
- **状态：** complete
- 执行的操作：
  - 读取本地仓库结构、README、设计文档、日志、pilot 代码和正式结果汇总。
  - 读取 Notion 2026-06-12 研究页和 2026-06-25 基金页。
  - 核对个人仓库、BNU-CCR 组织仓库与本地 Git 哈希。
  - 完成代码、实验方法、统计和文档一致性三路只读审计。
- 创建/修改的文件：
  - 无项目代码修改。

### 阶段 2：总体架构确认
- **状态：** complete
- 执行的操作：
  - 提出“旧 pilots 原地冻结 + 新建 platform + Paper 1 协议作为执行真相”的总体设计。
  - 用户确认首先实现 Paper 1，同时建设长期复用实验平台。
- 创建/修改的文件：
  - `task_plan.md`
  - `findings.md`
  - `progress.md`
  - `docs/superpowers/specs/2026-07-14-agent-ex-paper1-platform-design.md`

### 阶段 3：书面规格审阅
- **状态：** in_progress
- 执行的操作：
  - 写入正式设计规格。
  - 第一轮独立审阅识别出协议 schema、运行身份追溯和失败终态三个实现阻塞项。
  - 已补充结构化协议契约、run/event/attempt 身份模型和运行状态机。
  - 第二轮复审发现旧幂等键表述与新 `event_id` 契约冲突，已统一为 `event_id` 唯一幂等键。
  - 最终独立规格复审结果为 `Approved`。
  - 用户确认总体平台规格，并要求按既有研究脉络进一步收束 Paper 1。
  - 回读 Notion v2.0、Paper 1 收口页、2026-06-12 最新页和本地历次方案，确认主线为 persona 条件化与多轮网络互动下的意见形态。
  - 新建 Paper 1 聚焦研究规格，明确不把真人网络、动态重连、RLHF 和 N=1000 纳入主实验。
  - 第一轮独立审阅发现连续性操作重叠、shuffled exposure 不可执行和 primary estimand 未排序三个阻塞项。
  - 已将 continuity 限定为先前立场/理由/发言的连贯性；明确 cell 内 degree-matched 置换算法；将 primary outcome 收束为 `Δ log(B/W)`，primary estimand 收束为 continuity 对 `WS - shuffled` 的 matched-seed 调节效应。
  - 第二轮独立复审结果为 `Approved`。
  - 用户确认聚焦设计，并最终确定分级实现与 N=1000 正式主实验。
  - 将正式规模更新为 N=1000、T=50、12 cells；先10个 matched seeds，再按盲态功效重估扩展至最多20个。
  - 规模方案复审发现 pooled within-cell variance 不适用于 matched-seed DiD；已改为直接估计每 seed 主对比 `z_s` 的中心化方差，并固定 α、power、MDE、取整、上限和首批数据纳入规则。
  - 复核三轮 pilot 代码，写入可迁移机制、禁止直接复用部分和测试先行的迁移边界。
  - 最终规模与迁移方案独立复审结果为 `Approved`。
  - 用户已确认该方案；下一步进入 Paper 1 protocol 与逐文件实施计划。
- 创建/修改的文件：
  - 待审阅后更新设计规格。

## 测试结果
| 测试 | 输入 | 预期结果 | 实际结果 | 状态 |
|------|------|---------|---------|------|
| Git 远端一致性 | 个人与 BNU-CCR 仓库 | 与本地已提交版本一致 | 均为 `5c31951` | 通过 |
| pilot-3.0 N 扩展静态审计 | `n_agents=1000` | 创建1000个Agent | 角色池只有20条，无法运行 | 发现阻塞 |
| 配置传递审计 | `top_p=0.9` | 进入模型请求 | 未进入 `LLMClient.generate` | 发现阻塞 |

### 阶段 4：实施计划
- **状态：** in_progress
- 执行的操作：
  - 按 make-plan 规则完成文档、代码和方法/统计三路 Phase 0 发现。
  - 2026-07-14 当时确认 `platform/` 尚不存在、运行依赖未锁定，pilot-3.0 Notebook 是实际实现。
  - 写入分阶段、逐模块、测试先行的实施计划。
  - 第一轮计划审阅发现官方API发现滞后、执行参数库存不全和大规模矩阵编排缺失。
  - 已增加 Phase 0B 官方API/依赖 gate、完整 unresolved inventory 与 formal-required 校验、registry/worker/矩阵审计/盲态扩样 orchestration 阶段。
  - 第二轮独立计划审阅结果为 `Approved`。
  - 2026-07-14 当时代码实施仅被 worktree 位置选择阻塞；该阻塞已于 Phase 3A 解决。
- 创建/修改的文件：
  - `docs/superpowers/plans/2026-07-14-paper1-platform-implementation-plan.md`
  - `task_plan.md`
  - `progress.md`

## 错误日志
| 时间戳 | 错误 | 尝试次数 | 解决方案 |
|--------|------|---------|---------|
| 2026-07-14 | 并行审计网络断连 | 1 | 重试后完成 |
| 2026-07-14 | OneDrive CSV 读取超时 | 2 | 停止重复读取，改用已获取证据交叉验证 |

## 五问重启检查
| 问题 | 答案 |
|------|------|
| 我在哪里？ | 正式平台阶段 3；Phase 3A 已完成，Phase 4 尚未开始 |
| 我要去哪里？ | Phase 4 模块实现 → mock/真实模型校准 → 有限规模 gate → 正式实验 |
| 目标是什么？ | 建成以 Paper 1 为首个协议的长期复用实验平台 |
| 我学到了什么？ | 见 `findings.md` |
| 我做了什么？ | 见上方记录 |

## 会话：2026-07-29

### Phase 3A：协议、领域与运行证据基础
- **状态：** complete
- 执行的操作：
  - 从 `c050655` WIP checkpoint 恢复，确认原 78 个失败同时来自旧 wheel 污染和待实现 release-hardening 测试。
  - 修复 editable install 与 pytest 临时目录，建立普通 import、root/platform 双入口和隔离 wheel smoke。
  - 完成协议/schema gate、decision value hash、human summary 同步和 Unicode placeholder 防绕过。
  - 完成领域记录、分层运行身份、FrozenSchedule、RunManifest、恢复游标、证据图与严格 JSON round-trip。
  - 经过多轮独立发布验证、边界审计和代码质量审查，逐项修复测试外绕过。
- 验证结果：
  - `353 passed`
  - Ruff check/format、`pip check`、`git diff --check` 通过
  - schema 镜像与17项依赖锁一致
  - 最终三路独立审查均为 PASS，无 blocker/major
- 边界：
  - 未修改旧 pilots。
  - 未运行 formal，未伪造审批记录。
  - 未实现真实 model adapter、engine 或正式实验。
- 下一步：
  - Phase 4：population、persona、network/exposure 与 mock fixtures。
  - formal-required 研究决策与 provider/runtime gate 继续保持 blocked。
  - 代码位置和恢复命令见 `logs/2026-07-29-phase3a-handoff.md`。

### Phase 4A：文献驱动的决策准备
- **状态：** in_progress
- 执行的操作：
  - 建立逐项“决策—支持/反对/边界文献”台账。
  - 将 Phase 4A 拆为议题、量表、目标人口、人口字段、初始状态、Persona、WS 网络、
    激活/暴露/记忆八个检索模块。
  - 用户要求重新开放议题选择，并要求平台支持可替换 topic package。
- 当前工作：
  - 首先检索并比较适合多轮 LLM-agent 舆论演化实验的候选议题。
  - 已重新打开原“AI 就业替代”主议题决定，完成核能、AI就业替代、指定场景人脸识别、
    气候政策的第一轮比较。
  - 当前建议先完成核心比较池的精确构念审查，再选择不超过三个候选做目标模型无网络
    topic probe，不在看到网络演化结果后再选题。
  - 已记录声明式 `TopicSpec`/`TopicResources`/`PopulationSpec` 分层建议，尚未冻结。
  - 用户要求保留 AI 就业替代并扩展社会议题候选；新增评估转基因食品、延迟退休、
    生育支持、算法推荐治理、疫苗和内容审核。当前建议核心比较池为 AI就业替代、
    转基因食品、延迟退休、生育支持政策；核能和人脸识别暂存，待统一判断。
  - 已按同一七维加权框架统一审查 AI就业、延迟退休、转基因、生育支持、核能和
    人脸识别六项。建议三项进入 topic probe（延迟退休、转基因、AI就业），Paper 1
    最终采纳两个议题资产，但只让一个运行完整12-cell主矩阵，另一个用于缩减稳健性。
  - 用户已确认延迟退休、转基因食品和AI就业替代进入Phase 0 topic probe。决定已
    记录为 `D-2026-07-29-01` 和 `DR-P1-043`；最终主议题及稳健性议题仍未冻结。
  - 已完成模块2的会审建议包并记录为`DR-P1-044`至`DR-P1-048`：三题均采用
    “中性事实卡+单一核心陈述”；建议共用1–7全标签有序立场量表、独立1–5
    confidence审计字段和`stance → confidence → public_reason`固定输出。
  - 延迟退休限定为对现行渐进式年龄调整方案的支持；转基因限定为依法标识的
    转基因大豆油市场销售支持；AI限定为未来10年生成式AI对中国就业岗位总量造成
    净减少的预测。三者均明确排除了容易混入的相邻构念。
  - 已起草每题两个同方向等义改写、7点与0–10挑战者比较、字段顺序检查及统一冻结
    判据。阈值被明确标为项目操作建议而非既有文献结论，须在比较候选结果前冻结。
  - 用户已于2026-07-29批准模块2方案；已记录为`D-2026-07-29-02`，并将
    `DR-P1-044`至`DR-P1-048`更新为“已确认方向”。模块2的研究设计完成。
  - 已进入模块3并完成目标人口与数据来源建议包`DR-P1-049`至`DR-P1-051`。
    当前推荐三议题共用“中国大陆18岁以上、过去半年使用互联网的家庭/社区居民”
    总体，不设64岁上限；在线资格不等于发帖或每轮激活。
  - 数据建议采用四层分工：NBS 2025提供最新总体边际、七普2020提供详细交叉结构、
    CNNIC第57次提供网民定义/边际、CFPS2022提供加权联合微观供体；CGSS2021和
    CLDS仅作一般成年人及劳动子群外部验证。
  - 已明确人口配额只控制模拟输入组成，不能据此宣称Agent代表真实中国民意；正式
    数据必须保存版本、许可、下载日期、变量crosswalk、权重、hash和校准误差。
  - 用户已于2026-07-29批准模块3方案；已记录为`D-2026-07-29-03`，并将
    `DR-P1-049`至`DR-P1-051`更新为“已确认方向”。模块3的研究设计完成。
  - 已进入模块4，开始审查人口字段在配额、prompt可见和分析专用三层中的不同用途。
  - 模块4建议包已形成：新增`DR-P1-052`至`DR-P1-055`，并把原三层结构扩展为
    校准、身份可见、分析审计和议题扩展四类用途。共同身份卡建议只显示年龄段、
    调查记录性别、教育、当前城乡、主要活动和就业者宽职业组。
  - 身份卡被界定为捆绑的实验处理，而非真实群体意见复刻；姓名、精细地点、收入、
    户口、婚姻、民族以及态度/价值近邻变量默认不显示。硬校准只使用能与成年网民
    总体兼容的高质量边际，不做全字段笛卡尔积配额。
  - 用户已于2026-07-29批准模块4方案；已记录为`D-2026-07-29-04`，并将
    `DR-P1-003`、`DR-P1-052`至`DR-P1-055`更新为“已确认方向”。模块4完成。
  - 已进入模块5，开始审查初始立场分布、人口—立场关联、跨cell匹配和初始理由来源。
  - 模块5建议包已形成：新增`DR-P1-056`至`DR-P1-060`。建议N=1000在1—7量表上采用
    `[50,100,200,300,200,100,50]`受控对称单峰分布；初始立场与人口约束正交，
    同matched seed跨12 cells逐Agent匹配。
  - 初始理由建议采用“来源支持的论据家族+冻结模型受控改写+机器/人工审计”的离线
    理由库；每个Agent都有一条round-0理由，不再概率性缺失。该建议包正等待用户会审，
    尚未写入正式决策，也未冻结任何机器参数。
  - 用户已于2026-07-29批准模块5方案；已记录为`D-2026-07-29-05`，并将
    `DR-P1-056`至`DR-P1-060`及关联队列项更新为“已确认方向”。模块5完成。
  - 已进入模块6，开始审查identity有/无、continuity有/无四个Persona模板的基线
    等值性、唯一允许差异、措辞强度和模板制品治理。
  - 模块6建议包已形成：新增`DR-P1-061`至`DR-P1-065`。建议四条件由单一共同骨架
    确定性插入identity和continuity两个因素块；absent条件真省略，不用“普通人”
    “中立公众”或等长语义placebo。
  - identity建议使用结构化最小人口字段卡并禁止补写身份故事；continuity建议对
    保持/改变提供对称许可，只要求解释连贯，不设置反向证据门槛。建议包包括旧pilot
    禁用词、三路操纵检查、锁死gate、顺序/改写挑战、模板ID/hash与变更治理，正等待
    用户会审，尚未冻结模板原文。
  - 用户已于2026-07-29批准模块6方案；已记录为`D-2026-07-29-06`，并将
    `DR-P1-061`至`DR-P1-065`及关联队列项更新为“已确认方向”。模块6完成。
  - 已进入模块7，开始审查WS网络的`k`、`p`、图方向、连通要求、非法图处理和
    N=1000下每轮曝光/推理成本。
  - 模块7建议包已形成：新增`DR-P1-066`至`DR-P1-070`。建议主图采用无向、简单、
    全连通且T=50固定的标准WS骨架；同matched seed的图和Agent—node随机映射跨12
    cells完全复用。
  - N=1000纯结构预计算建议以`k=10,p=.05`为主锚点，并用
    `k={6,10,20} × p={.02,.05,.10}`做不调用LLM的结构挑战。参数只能按聚类、路径、
    small-world指标、连通与资源gate冻结，不得按极化结果选择；当前等待用户会审。
  - 用户已于2026-07-29批准模块7方案；已记录为`D-2026-07-29-07`，并将
    `DR-P1-066`至`DR-P1-070`及关联队列项更新为“已确认方向”。模块7完成。
  - 已进入模块8，开始审查全体/子集激活、同步提交、三种曝光的数量匹配、邻居消息
    排序和记忆窗口，并核算N=1000×T=50×12 cells×seeds的真实推理规模。
  - 模块8建议包已形成：新增`DR-P1-071`至`DR-P1-077`。建议主实验使用全体同步，
    每轮激活当前N的全部Agent；正式10个matched seeds预计600万次生成，扩至20个为
    1200万次，资源不足不得静默改成子集激活。
  - 建议E2读取全部一阶邻居，E1逐Agent按WS度数精确匹配，并同时保持发送者出度；
    消息使用稳定中性成员编号、文字立场标签和上一轮理由，槽位按独立seed随机化。
    shuffled映射应以严格受约束b-matching预生成，不可行则在运行前失败。
  - 建议证据链保存全部历史，但模型只见最近3轮自身立场/理由，并在Phase 0以
    K=1/3/5做不读取意见结果方向的构念与资源挑战；不使用LLM自动摘要。该建议包正
    等待用户会审，尚未写入正式决策或机器协议。
  - 用户指出Paper 1核心更偏向真实舆论过程仿真，因此否决全员同步作为主过程。
    补充文献审计显示，在线讨论存在沉默多数、活跃少数和爆发性发帖，异质节点活动
    还可能改变共识速度与碎片化；原模块8建议因此正式重开。
  - 用户已于2026-07-29批准新的过程架构，并记录为`D-2026-07-29-08`及
    `DR-P1-071`至`DR-P1-072`：固定WS关系不变，每个Agent具有冻结的长期活跃权重，
    每次事件按权重有放回抽取一个Agent并即时提交；同matched seed的12 cells共享
    权重和完整激活序列。
  - T=50现解释为50个sweeps，每sweep包含N次事件；正式run仍为50,000次生成，10个
    matched seeds仍约600万次。全员同步降为稳健性上界，不以减少调用量为选择理由。
  - 活跃权重分布/校准目标仍未决；E1/E2事件级最近帖子语义、来源映射和自身记忆单位
    也已重开。上位规格、纸面协议、schema和代码尚未修改，formal配置继续fail closed。
  - 用户已进一步批准“私人意见更新—公开表达”两阶段设计，并记录为
    `D-2026-07-29-09`、`DR-P1-078`：每次激活用一次LLM调用更新私人状态，预生成的
    `publish_flag`决定是否替换最近公开帖子；E1/E2只能读取公开帖子。
  - 注意/更新活跃权重与公开表达倾向必须使用独立制品并跨12 cells复用。精确表达
    分布、结构性潜水比例、贡献Gini、top-user份额，以及私人/公开结果的分析排序仍
    保持未决；当前没有修改schema或事件引擎。
  - 用户已批准私人/公开分析排序并记录为`D-2026-07-29-10`、`DR-P1-079`：全部
    Agent的私人意见分布为唯一primary；公开存量、公开流量和私人—公开表达偏差为
    强制预注册secondary。不得在结果出来后用更显著的公开结果替换私人primary。
  - 用户已批准hurdle–Beta公开表达结构并记录为`D-2026-07-29-11`、`DR-P1-080`：
    所有Agent均有正注意权重；结构性潜水者round 0后不发帖，其他Agent的表达倾向
    来自Beta分布。主模型注意权重与表达倾向独立，正相关只作预注册敏感性。
  - 用户已批准注意权重分布族及校准框架并记录为`D-2026-07-29-12`、`DR-P1-081`：
    主模型为正截断对数正态并归一化`sum(w_i)=N`，截断Pareto为重尾敏感性，等权
    为无异质性机制基线；校准只看激活过程统计，不读取意见演化结果。
  - 用户已批准E1固定shadow graph并记录为`D-2026-07-29-13`、`DR-P1-082`：
    每个matched seed生成一张全程固定、逐节点保持WS度数、排除自环/重边/真实WS边
    且全连通的对照图；E1/E2都保留稳定关系，动态换人不进入主矩阵。
  - 用户已批准有限未读feed并记录为`D-2026-07-29-14`、`DR-P1-083`：每次激活只
    考虑游标后的邻居新公开帖，取最新至多B条，超量过期、不用已读帖回填；入选按
    新近性，prompt槽位另行冻结随机化。B及精确过程gate进入Phase 4A批量审阅。
  - 用户要求停止逐小点审批；后续将所有剩余Phase 4A事项整合为一次性决策包，整体
    批准后转入书面规格与实现计划。
  - 已完成Phase 4A剩余项清仓盘点：将机制/接口、Phase 0校准制品以及统计/运行时
    后续gate分层；补证TRS人口整数化、seed间重新抽样/common random numbers、私人
    更新记忆窗口和参与不平等边界。下一步仅等待用户对整包一次性审阅。
  - 精确潜水比例、Beta参数、注意权重参数、相关敏感性强度和校准容差仍保持未决；
    参数必须匹配零新帖比例、Gini、top-user份额和每sweep发帖量等过程统计，不能按
    意见结果选择。
  - 用户已于2026-07-29整包批准Phase 4A剩余建议。新增`D-2026-07-29-15`至`19`与
    `DR-P1-084`至`088`，并形成
    `docs/superpowers/specs/2026-07-29-paper1-phase4a-completion-design.md`。
  - 整包确认三议题probe及预先优先级、TRS恰好N与seed间重新抽样、最近K次成功私人
    更新记忆、失败不变式/同事件恢复，以及B=6/K=3主候选与Phase 0挑战集合。
  - 已同步修订研究问答、纸面协议、07-14聚焦规格和平台规格，清除正式路径中的旧
    全员同步提交语义。下一步是整份书面规格复核；复核前不实施schema或事件引擎。
  - 独立规格审查共完成三轮。已修复有放回激活下`round+agent_id`事件键碰撞，统一为
    连续全局`event_ordinal`；按component区分matched-seed common RNG scope与
    cell-specific scope；恢复只接受连续、无缺口、全部succeeded前缀。
  - 同步清除旧平台规格中的同步测试/迁移要求，明确failed即原位停止、excluded只属
    分析层、Paper 1主路径禁止imputed/fallback；B稳定旧ID被明确解释为消息容量并把
    B/K最终冻结gate移至Phase 0B。独立审查提出的blocker/major均已逐项关闭。
  - 随后按用户要求从传播学审稿人与ABM方法专家角度复核Phase 4A。结论为
    `major revision`而非设计作废：工程可追溯性很强，但研究问题与primary estimand、
    identity/continuity构念、LLM行为效度、拓扑—消息剂量识别和真实舆论表述仍需修订。
  - 识别出若干实施前必须解决的问题：public post事件/stock语义、shadow graph结构
    目标、WS-shadow实际曝光剂量差异、稳定来源记忆缺失，以及baseline分组导致
    `log(B/W)`初始值机械偏高。完整证据和建议记录于`findings.md`。
  - 用户批准不改机制、不增加真人的Phase 4A.1方法论重构。新增方法规格
    `docs/superpowers/specs/2026-07-29-paper1-phase4a1-methodological-reframing-design.md`、
    决定`D-2026-07-29-20`和依据卡`DR-P1-089`。
  - 修订将Paper 1定位为理论驱动的生成式舆论动力学计算实验；收窄identity、
    continuity、private/public和network术语；将`WS-shadow`解释为两个网络约束
    暴露系统的总效应，并建立四级验证与三层主张边界。实验机制和12-cell矩阵不变。
  - 独立规格首轮审查发现旧协议与新规格形成双重primary，并指出“同步上界”会暗改
    引擎。已将旧continuity DiD降为关键secondary、将四persona等权`WS-shadow`设为
    primary estimand，重开单一primary outcome，并以严格串行`w_i=1`基线取代同步
    稳健性；generated summary/schema迁移明确留给Phase 4B且当前继续fail closed。
  - 第二轮审查发现07-14旧规格仍残留“主检验/相同消息数量”措辞，且`epsilon`和
    有限规模gate仍占用旧primary路径。已把continuity DiD统一为关键secondary总效应，
    将`epsilon`迁移为候选组际结构路径，并要求scale gate在新primary outcome盲态
    冻结后检查其四persona等权`WS-shadow`对比。
  - 第三轮审查发现稳定旧ID`P1_GATE_DELTA_STABILITY`仍会把scale gate绑定旧ΔS。
    已新增`P1_GATE_PRIMARY_OUTCOME_STABILITY`，旧ID明确降为候选组际结构secondary
    诊断；schema/YAML字段迁移仍留给Phase 4B。三轮审查上限已到，最终修订待用户书面
    复核，不声称获得第四轮独立批准。
  - 用户已完成Phase 4A.1书面规格复核；提交`0600e2a`及此前Phase 4A提交已直接推送
    至GitHub `origin/main`。
  - 按make-plan要求完成Phase 4B三路只读文档发现。确认当前platform只有协议验证和
    不可变证据地基，不存在population/network/feed/memory/adapter/engine/checkpoint
    实现，且旧event/schedule/state/exposure语义与Phase 4A存在结构冲突。
  - 使用旧Phase 3A Python 3.12.13环境运行基线：`342 passed, 11 failed`；Ruff check
    和format check通过。11项失败来自已批准研究文档与尚未迁移schema/QA路径的预期
    不一致，Phase 4B-1必须先恢复全绿。默认Python 3.14无pytest/ruff，不可作为项目
    环境。
  - 新增
    `docs/superpowers/plans/2026-07-29-paper1-phase4b-implementation-plan.md`，
    将Phase 4B拆为环境、协议迁移、domain v2、研究制品、网络、schedule、feed/memory、
    mock adapter、事务engine/recovery及三档mock集成十个连续工作包。
  - 用户整包批准Phase 4B：4B保持mock-only、不保留旧同步API兼容层、每run使用独立
    SQLite事务库并生成不可变证据导出，按4B-0至4B-9连续执行，仅在新增研究参数或
    重大范围变化时暂停。决定与工程依据记录为`D-2026-07-29-21`和`DR-P1-090`。
  - Phase 4B-0完成：在当前隔离worktree建立项目本地`platform/.venv`，Python为
    `3.12.13`；按`requirements-dev.lock`安装并通过`pip check`。基线精确复现
    `342 passed, 11 failed`，11项均为Phase 4A/4A.1已批准文档与旧schema/YAML的
    预期迁移RED，不存在导入或依赖失败。
  - Phase 4B-1进入TDD：先新增新primary层级、严格串行有放回激活、private/public、
    finite unread feed及event/checkpoint协议测试，定向运行得到`3 failed`，失败原因
    分别为旧estimand、缺`feed_message_capacity`和缺activity-weight结构，确认RED有效。
  - 已迁移canonical/mirror schema、draft YAML、research-QA路径和generated summary
    投影；旧`Δlog(B/W)`移至`outcomes.group_structure`，新primary outcome保持
    `UNRESOLVED[P1_PRIMARY_OUTCOME]`，新primary estimand为
    `P1_PRIMARY_WS_SHADOW_AVERAGE_EFFECT`。中间全套测试达到`353 passed, 2 failed`，
    仅剩generated summary漂移；随后调用`update_human_protocol_summary(...)`重生成，
    相关定向测试`2 passed`。
  - Phase 4B-1首次实现验收：格式化后fresh全套为`357 passed in 13.13s`；Ruff check、
    Ruff format check、`pip check`和`git diff --check`均通过；canonical与packaged
    schema字节一致，SHA-256均为
    `A057D5D52AFFD146631BE8C7AC7ECA04EB62A0423EC69A55D5B3223E30E1CB6E`。
  - 独立规格审查要求修正三处candidate约束：`memory.window`不得保留旧
    `all_history`；`activation_count`必须固定为每sweep N=1000次；尚未决的
    `generation.seed_pairing`不得被schema预先锁成唯一resolved答案。三个最小回归
    测试先得到`3 failed`，分别确认旧值被错误接受及其他可审计resolved值被错误拒绝；
    随后只修改schema，定向GREEN为`3 passed`。
  - 修订后使用显式`--basetemp .pytest-tmp\phase4b1-fix`完成fresh验收：
    `360 passed in 12.18s`；Ruff check、Ruff format check、`pip check`、
    `git diff --check`和旧语义扫描均通过。canonical与packaged schema字节一致，
    SHA-256均为
    `150A34E0D6F79A666E4FFA1104D7F1FC3FB60D757DC945EA19B5E3A855B15D3A`。当前等待
    规格复审，复审关闭前不进入4B-2。
  - Phase 4B-1规格复审已`APPROVED`。随后代码质量审查发现JSON Schema只能约束
    数值类型和区间端点，不能保证activity-weight最小值严格小于最大值，也不能保证
    calibration `[lower, upper]`顺序；同时人类协议手写区仍保留机器迁移未完成的
    过期说明。本轮按质量审查意见进入语义验证与文档状态修订，完成前继续停留4B-1。
  - 质量修订先以真实`validate_protocol`路径建立9项RED：activity-weight
    `minimum == maximum`、`minimum > maximum`，六个calibration区间倒置及人类协议
    stale blocker均被旧实现错误接受。新增集中语义排序验证后定向GREEN为`9 passed`；
    `minimum < maximum`使用严格关系，range使用`lower <= upper`，只在相关值已解析为
    数值时比较，不填任何研究默认值。
  - 质量修订fresh验收使用
    `--basetemp .pytest-tmp\phase4b1-quality-fix`：`369 passed in 12.07s`；Ruff
    check、Ruff format check、`pip check`、`git diff --check`、schema镜像/hash、
    旧同步语义扫描和stale blocker扫描均通过。schema未改，SHA-256仍为
    `150A34E0D6F79A666E4FFA1104D7F1FC3FB60D757DC945EA19B5E3A855B15D3A`。当前停止
    修改并等待代码质量复审。
  - Phase 4B-1规格复审与代码质量复审均已`APPROVED`。提交前fresh验证再次得到
    `369 passed in 12.27s`；覆盖率套件同为`369 passed`，总覆盖率`91%`；
    Ruff check、Ruff format check、`pip check`、`git diff --check`、draft验证、
    formal fail-closed smoke及schema字节镜像均通过，两个schema的SHA-256均为
    `150A34E0D6F79A666E4FFA1104D7F1FC3FB60D757DC945EA19B5E3A855B15D3A`。4B-1
    已进入精确文件提交状态；4B-2尚未开始实现。
  - Phase 4B-2进入严格TDD实现时先建立未审查安全checkpoint。首组RED确认旧
    `derive_event_id(run_id, round, agent)`与schedule v1
    无法表达有放回事件；迁移后`event_ordinal`从0连续，schedule v2显式记录
    sweep/draw/agent/publish与算法版本，支持同Agent同sweep重复，并通过N=1000、
    T=50的50,000-slot轻量构造。
  - 新增版本化`ArtifactEnvelope`与`RNGProvenance`：制品ID绑定内容、算法、输入hash
    与RNG证据；seed由matched seed、注册namespace和稳定coordinates确定性派生，
    事件级namespace必须含`event_ordinal`，禁止`attempt_index`推进重试seed。
  - domain主路径已破坏性迁移为ordinal事件：运行态仅保留
    `pending/in_progress/succeeded/failed`，`excluded`不再是事件终态，
    `imputed/fallback`不再存在于Paper 1运行链；recovery cursor仅含
    `next_event_ordinal`和当前`event_id`。Exposure基础允许空社会feed和同发送者多帖，
    evidence graph只要求来源事件在ordinal上更早，不再硬编码“恰好上一轮”。
  - 旧`test_domain.py`的同步/round+agent契约被整体迁移，首次fresh全套为
    `174 passed`。测试总数从4B-1的369下降，不是功能性失败，而是删除了约200项已经
    失效的schedule v1、round cursor、同步AgentState及disposition兼容契约测试；
    protocol/installation测试保持全绿。随后补上attempt/event严格JSON round-trip、
    hash漂移和重试model-seed回归，当前全套为`177 passed`，覆盖率套件同为
    `177 passed`、总覆盖率`84%`。
  - 已在台式机以Codex bundled Python 3.12.13重建`platform/.venv`，按
    `requirements-dev.lock`安装17项精确版本依赖；`pip check`通过，lock SHA-256为
    `13878C75C775657BBFB0896AE858645C0FE37CC4C3717EDD5FBAD4833B6FD292`。台式机fresh
    基线精确复现`177 passed in 11.35s`与总覆盖率`84%`。
  - 本轮继续以五组可复现RED→GREEN补强domain失败关闭：拒绝不由event identity派生的
    attempt IDs；恢复manifest模型/环境复现身份必需字段及非空字符串；拒绝JSON boolean
    冒充单槽`schedule_count`；拒绝object键冒充`event_ids`数组；拒绝纯空白
    `launch_nonce`。定向domain回归为`41 passed`。
  - 同步修正Phase 4B计划中的低层笔误：`event_ordinal`应从0连续到`N×T-1`，与
    Phase 4A权威规格、代码和测试保持一致；attempt index仍从1开始，二者不得混淆。
  - 本轮fresh验收得到`183 passed in 11.62s`；覆盖率套件同为`183 passed`，总覆盖率
    从`84%`提高至`85%`。Ruff check、Ruff format check、`pip check`与
    `git diff --check`均通过。
  - 独立代码质量审查发现P1：`rng.py`只拒绝顶层`attempt_index`，嵌套object/array
    可改变同一event的model seed。两个参数化回归先得到预期RED：`2 failed`且均为
    `DID NOT RAISE ValueError`；最小GREEN在严格JSON transport校验后递归拒绝任意
    层级该键。定向RNG回归为`7 passed`，domain回归为`43 passed`。当时4B-2尚未
    关闭并等待该审查项复核，未进入4B-3。修复后的fresh完整套件与
    覆盖率套件均为`185 passed`，总覆盖率`85%`；Ruff check、Ruff format check、
    `pip check`与`git diff --check`均通过。
  - 当时checkpoint尚未通过独立规格审查与代码质量复核，因此未标记4B-2 complete。
    fail-closed补强后进入独立规格/反模式审查与代码质量复审；最终关闭情况见下方
    Phase 4B-2收口记录。
  - Phase 4B-2代码质量审查的四项修订已按严格TDD实现；当时继续等待复审。
    定向RED为`7 failed`，覆盖provider响应证据字段缺失、FAILED真实响应被拒、冻结typed值
    无法复用，以及非法`rng_provenance`错误类型不明确；最小GREEN为`7 passed`。
    `GenerationAttempt`现恢复4B-1的provider metadata/headers、HTTP status、usage、
    finish reason及对应hash，并拒绝空`model_identity`；FAILED允许保留真实raw response
    及元数据但禁止parsed success。RNG/Artifact typed构造现支持自身冻结值及
    `dataclasses.replace`，而`from_payload`严格JSON边界不变；artifact工厂在派生ID前明确
    校验provenance类型。实现代理的fresh全套为`194 passed in 12.92s`；其coverage
    coverage运行报告使用了与最终独立全量验证不同的统计口径，不作为4B-2最终
    覆盖率。待复审关闭前未进入4B-3。
  - Phase 4B-2独立规格审查与反模式审查均为`APPROVED`，独立代码质量复审为
    `APPROVED`。RNG嵌套`attempt_index` P1以及provider证据、FAILED响应保存、冻结typed
    值复用、provenance错误合同四项质量修订均已关闭。
  - Phase 4B-2最终fresh验证为`194 passed`，无skip、无xfail；独立全量coverage为
    `1245 statements / 187 missed / 85%`。Ruff check、Ruff format check、`pip check`、
    `git diff --check`、schema镜像、draft gate和formal fail-closed gate均通过。
  - 文档收口前验证快照的Git diff SHA-256为
    `481BFA0FB75EEFC9E438732B9CF3A93FC889BB19DFA061E9ACAD545DC215B081`；这是
    pre-documentation verification hash，文档修改后会变化，不是最终提交hash。
  - Phase 4B-2状态已更新为`complete / independently reviewed`。下一工作包是4B-3，
    但4B-3尚未开始；本次收口未新增研究参数，也未填补任何`UNRESOLVED[...]`。
- 边界：
  - 模块2虽已批准，但population、persona及其他Phase 4A模块尚未完成；当前不实现
    topic package，也不修改正式实验代码。
  - 本次批准不等于机器协议字段冻结；最终主议题、稳健性议题、目标模型probe结果、
    最终题干原文、量表实际值和hash仍保持未决，formal配置继续失败关闭。
  - 模块3的批准不等于人口制品冻结；CFPS筛选变量、精确人口字段、交叉约束、
    N=1000整数化和容差属于模块4/实现规格，当前没有填入coder默认值。
  - 模块4批准不等于字段或Persona制品冻结；正式身份模板原文、source-variable
    crosswalk、人口百分比、校准容差和审计阈值尚未写入机器协议。
  - 模块5批准不等于初始化制品冻结；正交容差、初始化RNG、论据家族、理由文本、
    judge阈值、人工编码规则和hash仍保持未决，formal配置继续失败关闭。
  - 模块6批准不等于Persona模板冻结；最终逐字原文、顺序挑战、操纵检查阈值、
    template ID/token计数/hash仍保持未决，formal配置继续失败关闭。
  - 模块7批准不等于网络制品冻结；NetworkX版本、精确k/p、正式图seed、结构阈值、
    edge list、Agent—node映射和hash仍保持未决，formal配置继续失败关闭。
  - 模块8机制设计已经批准，但B、K、活跃/表达分布参数与过程阈值仍只是Phase 0
    候选；它们在真实gate冻结前继续保持`UNRESOLVED[...]`。当前未修改schema、
    formal YAML或实验运行代码。
