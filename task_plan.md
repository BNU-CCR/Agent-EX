# 任务计划：Agent-EX 长期研究平台与 Paper 1

## 目标
在保留 pilot-1.0/2.0/3.0 历史证据的前提下，建立清晰的项目知识体系，并重新实现一个以 Paper 1 为首个研究协议、可供后续论文复用的可测试、可恢复、可扩展实验平台。

## 当前阶段
Phase 0A-0 离线 probe 骨架已完成并通过规格、代码质量和最终验证三路独立审查。
修复后 full/coverage 均为1463 passed、2 skipped、1 release-scale deselected，coverage
为86%；下一阶段是 Phase 0A-1 云端真实小样本校准，不是直接启动正式主实验。

## 各阶段

### 阶段 1：设计固化与规格审阅
- [x] 盘点本地项目、Notion、GitHub 和 pilot-3.0
- [x] 审计实验设计、统计分析和代码风险
- [x] 与用户确认总体架构
- [x] 写入正式设计规格
- [x] 完成独立规格审阅并修正问题
- [x] 用户确认总体平台规格
- [x] 结合历史研究脉络收束 Paper 1 概念设计
- [x] 完成 Paper 1 聚焦研究规格独立审阅
- [x] 用户确认 Paper 1 聚焦书面规格与 N=1000 分级方案
- [x] 完成文档、代码与方法三路实施发现
- [x] 完成逐文件实施计划审阅
- **状态：** complete

### 阶段 2：知识归档与研究协议
- [x] 建立项目总览、长期研究计划、归档索引和 AI 接手规则
- [x] 将 pilot-1.0/2.0/3.0 标记为冻结原型，不物理移动
- [ ] 冻结 Paper 1 的构念、实验条件、指标和统计方案
- [x] 明确 Notion、本地文档、机器配置和实验输出的权威边界
- **状态：** in_progress（formal-required 研究决策仍待冻结）

### 阶段 3：正式平台基础
- [x] 建立单一 Python package 和依赖锁定
- [x] 完成 Phase 3A：协议/schema gate、领域记录、运行身份、冻结 schedule、manifest 与证据图契约
- [ ] 实现 population、persona、network/exposure、prompt、model adapter
- [ ] 实现严格串行事件引擎、逐事件/分段 checkpoint 持久化和同事件恢复执行
- [ ] 建立 mock LLM 与自动化测试
- **状态：** in_progress

### 阶段 3A：Phase 4A 文献驱动决策
- [ ] 模块 1：候选议题与精确构念比较（候选已定；最终主/稳健性议题待probe）
  - [x] 完成第一轮跨议题文献短名单：核能、AI就业替代、指定场景人脸识别
  - [x] 扩展传播学社会议题候选：转基因、延迟退休、生育支持、算法推荐治理等
  - [x] 按统一权重审查六个议题并形成排序、逐项建议和采纳数量建议
  - [x] 形成“文献短名单 + 目标模型无网络 topic probe”的建议程序
  - [x] 用户确认 Phase 0 probe 候选：延迟退休、转基因食品、AI就业替代
  - [ ] 用户决定最终主议题和缩减稳健性议题
  - [ ] 冻结 probe 题干、量表和预先筛选规则
- [x] 模块 2：精确题干与量表（研究设计已确认；机器值待Phase 0 probe冻结）
  - [x] 为延迟退休、转基因大豆油、AI净就业分别限定单一构念
  - [x] 起草三份中性事实卡、核心陈述及同方向等义改写
  - [x] 比较5点、7点、1–10/0–10、中点、DK与独立置信度方案
  - [x] 形成1–7 stance、1–5审计型confidence和固定JSON输出建议
  - [x] 起草目标模型topic probe与题干冻结判据
  - [x] 用户会审并采纳`DR-P1-044`至`DR-P1-048`
  - [x] 写入`D-2026-07-29-02`；最终议题、机器原文、量表值和hash继续保持`UNRESOLVED`
- [x] 模块 3：目标人口与数据来源（研究设计已确认；机器参数待冻结）
  - [x] 比较全国成年人、成年网民和18–64岁劳动力三种目标总体
  - [x] 核对NBS 2025、七普2020、CNNIC第57次、CFPS2022、CGSS2021和CLDS的覆盖边界
  - [x] 形成“总体边际+网民校准+微观供体+外部验证”的来源分工
  - [x] 起草数据版本、许可、crosswalk、hash、缺失与校准验证规则
  - [x] 用户会审并采纳`DR-P1-049`至`DR-P1-051`
  - [x] 写入`D-2026-07-29-03`；精确字段、约束和整数化容差继续保持`UNRESOLVED`
- [x] 模块 4：人口字段及配额/prompt/分析三层用途（研究设计已确认；机器值待冻结）
  - [x] 核对CFPS2022官方问卷可支持的基础、劳动、互联网和敏感字段
  - [x] 比较人口态度相关证据与persona prompt有效性/刻板印象证据
  - [x] 形成共同字段、最小身份卡、分析/扩展/禁用字段和缺失审计建议
  - [x] 起草`DR-P1-052`至`DR-P1-055`并更新`DR-P1-003`
  - [x] 用户会审并采纳`DR-P1-003`、`DR-P1-052`至`DR-P1-055`
  - [x] 写入`D-2026-07-29-04`；精确数据crosswalk、边际值与容差继续待机器冻结
- [x] 模块 5：初始立场与初始理由（研究设计已确认；机器制品待冻结）
  - [x] 审计三个pilot的初始化分布、身份—立场混杂、理由缺失和硬编码问题
  - [x] 比较受控单峰、均匀、经验调查和目标模型自由生成四种初始立场来源
  - [x] 形成七档受控分布、人口正交、跨cell匹配和固定初始组建议
  - [x] 比较固定模板、真实语料、自由生成和来源约束混合理由库
  - [x] 起草理由生成、机器/人工审计、round-0语义和跨seed复用规则
  - [x] 起草`DR-P1-056`至`DR-P1-060`并更新`DR-P1-011`、`DR-P1-020`至`DR-P1-025`
  - [x] 用户会审并采纳模块5建议包
  - [x] 写入`D-2026-07-29-05`；精确容差、judge阈值和理由库hash保持待冻结
- [x] 模块 6：Persona 四模板（研究设计已确认；模板制品待Phase 0冻结）
  - [x] 核对聚焦规格中identity、continuity和四cell正交边界
  - [x] 审计旧pilot的weak/lifelong复合prompt、立场锁定和隐藏confound
  - [x] 检索人口Persona有效性、默认Persona、刻板化和prompt改写敏感性证据
  - [x] 检索既往意见可见、公开承诺、一致性与说服抵抗证据
  - [x] 形成“共同骨架+两个可插拔因素块+absent真省略”的四模板建议
  - [x] 起草identity与continuity候选原文、操纵检查、锁死gate和版本治理
  - [x] 起草`DR-P1-061`至`DR-P1-065`并更新`DR-P1-026`至`DR-P1-030`
  - [x] 用户会审并采纳模块6建议包
  - [x] 写入`D-2026-07-29-06`；模板原文、阈值、ID和hash保持待Phase 0冻结
- [x] 模块 7：WS 网络（研究设计已确认；图制品待结构gate冻结）
  - [x] 核对聚焦规格、schema、测试fixture与三个pilot中的WS参数和重连边界
  - [x] 检索WS原始理论、小世界量化和意见动力学中的网络敏感性证据
  - [x] 比较无向/有向、connected/giant component和运行时修复/失败方案
  - [x] 对N=1000、`k={6,10,20}`、`p={.02,.05,.10}`做纯结构候选预计算
  - [x] 形成`k=10,p=.05`首选锚点、结构gate和不得按意见结果选参的建议
  - [x] 起草图seed、Agent—node随机映射、跨cell复用和非法图治理
  - [x] 起草`DR-P1-066`至`DR-P1-070`并更新`DR-P1-031`至`DR-P1-035`
  - [x] 用户会审并采纳模块7建议包
  - [x] 写入`D-2026-07-29-07`；NetworkX版本、正式seed、阈值和图hash待冻结
- [x] 模块 8：激活、暴露与记忆（研究设计已整包批准；机器参数待Phase 0冻结）
  - [x] 对齐聚焦规格、协议、schema及`DR-P1-036`至`DR-P1-042`
  - [x] 检索同步/异步调度、LLM记忆和长上下文位置偏差证据
  - [x] 比较全员同步、全员同步+截断和子集同步三种路径
  - [x] 核算正式10/20 matched seeds对应600万/1200万次生成
  - [x] 起草全邻居degree matching、消息位置随机化和严格shuffled映射
  - [x] 起草模型可见K=3滚动历史、K=1/5 Phase 0挑战和全历史证据保存
  - [x] 起草`DR-P1-071`至`DR-P1-077`并更新研究问答
  - [x] 用户否决全员同步主方案，并明确Paper 1优先追求舆论过程仿真
  - [x] 补充在线参与不平等、爆发活动和异质节点活跃度证据
  - [x] 比较异质子集同步、加权随机顺序激活和连续时间爆发模型
  - [x] 用户批准固定WS上的异质加权随机顺序激活
  - [x] 写入`D-2026-07-29-08`并确认`DR-P1-071`、`DR-P1-072`
  - [x] 识别潜水者“阅读但不发帖”不能等同于意见冻结
  - [x] 用户批准私人更新与公开表达两阶段分离
  - [x] 写入`D-2026-07-29-09`和`DR-P1-078`
  - [x] 决定活跃权重分布族、校准维度和Phase 0非结果导向冻结原则
  - [x] 写入`D-2026-07-29-12`和`DR-P1-081`
  - [ ] 冻结活跃权重精确参数、目标区间、容差和校准算法
  - [x] 决定公开表达倾向的hurdle–Beta结构和主模型注意—表达独立性
  - [x] 写入`D-2026-07-29-11`和`DR-P1-080`
  - [ ] 决定结构性潜水比例、Beta参数和贡献不平等校准目标
  - [x] 决定私人意见与公开可见舆论的分析优先级
  - [x] 写入`D-2026-07-29-10`和`DR-P1-079`
  - [x] 决定E1采用整个run固定、逐节点度数保持的shuffled shadow graph
  - [x] 写入`D-2026-07-29-13`和`DR-P1-082`
  - [x] 确认有限、未读优先、最新B条且不回填的事件级feed结构
  - [x] 写入`D-2026-07-29-14`和`DR-P1-083`
  - [x] 整包批准B=6主候选与`{4,6,8}`挑战、首激活round-0、同源多帖、随机槽位和feed过程gate
  - [x] 将自身记忆改为最近K次成功私人更新，主候选K=3、挑战`{1,3,5}`
  - [x] 完成模块8整体会审并修订聚焦规格与纸面协议；schema/代码进入后续实施阶段
- [x] 汇总为 Phase 4A 一次性建议决策包，由用户整体复核
  - [x] 盘点所有剩余Phase 4A决策并区分“现在冻结/Phase 0校准/后续阶段”
  - [x] 补齐人口整数化、matched-seed、表达/活跃参数、feed、记忆与制品gate依据
  - [x] 准备一个主推荐包及替代方案/重开条件
  - [x] 用户一次性批准整包
  - [x] 批准后形成完整书面规格
  - [x] 完成独立整份规格审查并修复事件ID、RNG作用域、恢复和主分析准入冲突
  - [x] 完成传播学/ABM方法匿名审稿式复核并形成major-revision问题清单
  - [x] 用户批准Phase 4A.1方法论重构方向并形成书面规格、决定卡与文献依据卡
  - [x] 完成Phase 4A.1三轮独立规格审查；最终稳定ID迁移问题已本地修复
  - [x] 用户完成整份书面规格复核
  - [x] 完成Phase 4B文档发现与分阶段实施计划
  - [x] 用户整包批准Phase 4B实施计划与连续执行边界
- [x] 形成议题包可替换的平台设计规格；书面规格复核前不改代码
- **状态：** Phase 4A/4A.1 approved and user-reviewed; Phase 4B executing
- **产出：**
  - 检索过程与发现进入 `findings.md`
  - 每个选择的支持、反对和边界证据进入 `docs/paper1-design-rationale.md`
  - 用户批准后的模块化设计进入新的书面规格

### 阶段 4：Paper 1 实验实现
- [x] Phase 4B-0：建立可移植Python 3.12环境并确认迁移基线
- [x] Phase 4B-1：迁移协议/schema/YAML/人类摘要并恢复测试全绿
- [x] Phase 4B-2：迁移event ordinal、schedule v2、domain records与artifact/RNG基础
  （complete / independently reviewed；fresh全套194 passed，无skip/xfail；独立全量覆盖率85%）
- [x] Phase 4B-3：实现topic/population/initialization/persona mock制品
  （complete / independently reviewed；规格/反模式与代码质量审查均`APPROVED`；最终
  fresh全套274 passed且无skip/xfail，覆盖率1817 statements / 257 missed / 86%；
  fixture继续为mock-only/not-frozen）
- [x] Phase 4B-4：实现WS/shadow图与node mapping
  （`complete / independently reviewed`；规格、反模式与代码质量审查均`APPROVED`；最终
  连续fresh全套318 passed，覆盖率2237 statements / 323 missed / 86%；所有精确`P1_*`
  机器值仍为`UNRESOLVED[...]`，制品与hash仅为mock-only/not-frozen）
- [x] Phase 4B-5：实现attention/expression与冻结schedule
  （`complete / independently reviewed`；规格/反模式与代码质量审查均`APPROVED`，release
  verification为`PASS`；最终连续fresh全套402 passed in 69.92s，coverage 402 passed in
  204.17s、2876 statements / 419 missed / 85%，schedule.py为638/96/85%；draft仍含
  88个UNRESOLVED，mock制品保持mock_only/not_frozen）
- [x] Phase 4B-6：实现private/public/feed/memory
  （`complete / independently reviewed`；规格/反模式与代码质量复审均`APPROVED`，release
  verification为`PASS`；最终连续fresh全套459 passed in 68.59s，coverage 459 passed in
  218.13s、3922 statements / 566 missed / 86%；B/K仍为显式mock挑战输入，formal值未冻结，
  draft仍含88个`UNRESOLVED[...]`；Phase 4B-7未开始）
- [x] Phase 4B-7：实现prompt/parser/mock adapter
  （`in_progress / review repairs implemented / pending independent re-review`；前两轮审查的
  prompt/event/exposure、memory、persona、serialization/budget、adapter capability/response
  replay及parser/evidence P1/P2，以及view/response capability、static system和preflight预算均按
  RED→GREEN修复；恢复后又将typed RunManifest、canonical cell、冻结schedule slot、同run
  successful source prefix/final attempt接入prompt可信重放；最终review repairs进一步统一四cell
  system合同、令I0/C0真省略且C0保留同memory，将final attempt parsed content绑定更新，并引入
  一次验证的`ValidatedPromptRunContext`消除逐prompt manifest扫描；定向118 passed，连续fresh
  全套514 passed in 80.54s，production coverage 514 passed in 248.34s、4981 statements /
  729 missed / 85%；N=1000 prompt+render为8.827秒，N=50000 context验证0.317秒且后续索引
  O(1)；mock_only/not_frozen，未进入4B-8）
  （2026-08-27追加P1修复：run context改为内容绑定HMAC完整性哨兵并覆盖全部索引；撤销
  未获批准的retry model-seed相等约束；全部候选含expired round-0均先做typed source replay。
  最终fresh full 522 passed，production coverage 522 passed / 85%；仍待独立复审。）
  （2026-08-28最终收尾：逐consumer全图HMAC改为独立typed snapshot的exact-owner弱注册表；
  `model_sampling`从公共RNG namespace移除并在未决期fail closed；parser字符/字节gate前移到
  seal/hash之前。四项预期RED后focused 151 passed；待独立复审，再只跑一次final full/
  coverage；未提交、未推送、未进入4B-8。）
  （2026-08-28并发P2收尾：每context writer lock + 不可变cursor/prefix版本最后发布；prompt与
  metadata只捕获一次版本，无全局长锁或prefix复制。确定性RED后新增2 passed、context 17 passed、
  扩展focused 161 passed；待独立复审，未跑full/coverage、未提交、未推送、未进入4B-8。）
- [x] Phase 4B-8：实现SQLite事务存储、严格串行engine与checkpoint/recovery
  （4B-8A、8B、8C-1、8C-2、8C-3均完成；最终verification/spec/quality三路复核
  P0-P2均无，三路fresh full分别为`979 passed, 2 skipped`，证据日志完整保留4B-9门禁。）
- [x] Phase 4B-9：完成N=20/100/1000 mock集成与交接
  （Tasks 1--7完成至`7749609`并推送；50,000-event release gate为1 passed，最终full为
  1124 passed/2 skipped/1 deselected，coverage为85%；Task 8三路终审P0-P3均无。）
- [ ] 实现 Paper 1 机器可读协议和配置
- [ ] 完成构念与 prompt Phase 0
- [x] 完成 Phase 0A-0 离线 probe 骨架、确定性 dry run、盲审/gate/report/bundle 与交接
- [ ] 完成 mock N=20/100/1000 验证
- [ ] 完成真实 API 小规模校准与成本评估
- [ ] 冻结正式主实验矩阵
- **状态：** Phase 0A-0 complete / independently reviewed（formal仍由Phase 0A-1/0B
  未冻结研究/模型参数fail closed；尚未运行真实模型或正式实验）

### 阶段 5：正式实验与分析
- [ ] 完成 N=200/500/1000 的有限规模检验
- [ ] 运行 N=1000、T=50、12 cells、首阶段10个 matched seeds 的主实验
- [ ] 根据预注册盲态功效重估决定是否扩展至20个 matched seeds
- [ ] 完成 run 完整性验证和数据归档
- [ ] 完成 seed-blocked 统计、文本指标和敏感性分析
- [ ] 根据功效、成本和机制需要决定 N=1000 稳健性实验
- **状态：** pending

### 阶段 6：Paper 1 交付与平台复用
- [ ] 形成可复现研究包
- [ ] 完成 Paper 1 结果与写作同步
- [ ] 为 Paper 2 和 GLM-agent benchmark 建立扩展入口
- **状态：** pending

## 关键问题
1. `[已解决]` 使用 Codex 用户目录下的隔离 worktree；当前路径见 `logs/2026-07-29-phase3a-handoff.md`。
2. 双层结构的初始立场组切点如何在 Phase 0 中冻结？
3. 主议题如何保证只测量单一态度构念？
4. `δ_min` 应依据何种理论与 Phase 0 信息在正式实验前冻结？
5. 正式模型/provider/runtime 采用何种组合？
6. Paper 1 哪个议题最适合识别多轮 Agent 网络中的均质化、漂移与极化？
7. 如何把议题内容封装为可替换的 topic package，而不改变通用模拟引擎？

## 已做决策
| 决策 | 理由 |
|------|------|
| Paper 1 是未来 6–8 周首要交付 | 用户明确确认 |
| 同时建设长期复用实验平台 | 避免每篇 Paper 重复造轮子 |
| pilot-1.0/2.0/3.0 原地冻结 | 保留路径、Git 历史和结果上下文，避免破坏性搬迁 |
| 新建 `platform/` 作为唯一活跃代码 | 消除 Notebook 与 src 双实现 |
| Notebook 只负责编排和展示 | 核心逻辑必须可测试、可复用 |
| `docs/paper1-protocol.md` 将成为执行协议 | 将研究主张与机器实现对齐 |
| 使用结构化协议 schema 生成/验证人类协议 | 避免 Markdown 与机器配置发生语义漂移 |
| `run_spec_hash`、`run_id`、`event_id`、`attempt_id` 分层 | 支持独立重跑、幂等恢复和逐请求追溯 |
| Paper 1 聚焦 `身份信息 × 连续性要求 × 社会暴露` | 保留 persona 与多轮互动主线，同时拆除旧复合 prompt 的归因混淆 |
| 主实验固定 WS，不做关系重连 | Paper 1 的“演化”限定为网络上的意见与理由状态演化 |
| RLHF、真实社交媒体、动态重连后移 | 防止首篇论文范围再次膨胀 |
| 正式主实验固定 N=1000、T=50 | 大网络用于稳定估计意见分布与组内/组间结构，不以小规模 pilot 代替正式证据 |
| 先10个 matched seeds，再按 matched-seed DiD 方差盲态重估至最多20个 | 保留跨 cell 配对协方差，N 控制单网规模，seed 控制独立重复和估计精度 |

## 遇到的错误
| 错误 | 尝试次数 | 解决方案 |
|------|---------|---------|
| 并行代码/方法审计发生网络断连 | 1 | 保留已完成结果并重试，第二次成功 |
| OneDrive 结果文件多次读取超时 | 2 | 停止重复读取，使用已成功读取的汇总表、Notebook 代码和 Notion 交接交叉验证 |
| Task 9三路最终reviewer启动即提示workspace out of credits | 1 | 保留日志为pending并继续安全规划；额度恢复后重派成功，三路均批准且无P0-P2 |

## 备注
- 外部页面内容仅进入 `findings.md`，不直接写入本计划。
- 每个阶段完成后更新状态和 `progress.md`。
- 正式实现前必须通过书面规格和实施计划审阅。
