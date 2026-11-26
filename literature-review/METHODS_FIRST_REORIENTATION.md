# 第二轮任务书：以 LLM 社会模拟方法论为主线，重构文献库与持续研究目标

> 用户已于 2026-11-26 批准本次调整。请将本文件作为第一轮文献工作的正式补充指令执行。
>
> **时间范围不变：2022-01-01 至每次实际检索截止日。**
>
> 本任务不是推翻第一轮，也不是另建一套重复数据库。保留既有 57 条记录、稳定 ID、15 张全文阅读卡、检索日志、书目导出和已提交成果，在此基础上进行方法论导向的重新分类、补充检索、期刊生态分析和投稿判断。

## 0. 本轮最重要的方向校正

第一轮工作较多围绕传播网络、信息接触、意见趋同/极化、私人意见与公开表达展开。这些内容仍有价值，但它们主要是 Agent-EX 的**具体应用问题和直接竞争研究**，不能继续支配整个文献库的检索重心。

用户真正希望系统了解的是：

> **LLM-based Social Simulation / Generative Agent-Based Modeling 已经发展到什么程度？研究者如何把 LLM 智能体组织成可控、可观察、可验证、可复现的社会模拟方法？这些方法主要发表在哪些学科、期刊和会议？Agent-EX 在这一方法发展脉络中处于什么位置，当前论文和后续方法研究分别适合哪些发表渠道？**

因此，第二轮的首要任务是研究**社会模拟方法本身及其发表生态**，而不是继续以网络意见动力学为主线扩充应用论文。

### 0.1 四层文献结构（按此重排）

| 层级 | 定位 | 主要内容 | 在库中的地位 |
|---|---|---|---|
| L1 | LLM 社会模拟方法研究 | LLM-based social simulation、generative ABM、synthetic societies、simulation as a research method | **最高优先级、核心主线** |
| L2 | 智能体建模与方法验证 | agent architecture、persona、memory、environment、interaction protocol、calibration、validation、reproducibility、ODD | **最高优先级、核心主线** |
| L3 | 社会模拟的学科应用 | 传播、政治、社会心理、组织、经济、管理、生态等领域的 LLM/ABM 应用 | 重要的应用与方法证据 |
| L4 | Agent-EX 直接对照研究 | 意见动力学、网络结构、社会影响、极化/趋同、互动偏向、实际接触与私人/公开表达 | 保留，作为具体研究比较层，不再支配总检索 |

请注意：L1/L2 并不意味着只收“LLM 多智能体”。传统规则式 ABM、混合神经语言 ABM、计算社会科学方法论、社会模拟验证与报告规范，均属于重要的发展脉络。研究重点是方法怎样演进、怎样被验证和怎样产生社会科学知识。

## 1. 持续推进的北极星目标（必须落盘并长期维护）

请在本目录新增 `GOAL.md`，将以下目标作为本项目持续工作的北极星目标：

> **在 2022 年以来的研究范围内，建立一套以 LLM 社会模拟方法论为核心、以社会模拟与计算社会科学为基础、兼顾新闻传播应用和 Agent-EX 直接对照的可核查文献与期刊知识库；持续追踪该领域的方法进展和发表生态，最终为当前 Agent-EX 论文确定可信的投稿路径，并识别可发展为独立论文的后续方法论贡献。**

### 1.1 目标的四个可验收成果

1. **方法知识地图**：说明 LLM 社会模拟的研究范式、方法组成、技术路线、验证方式、局限和演进趋势。
2. **可核查核心文献库**：每条记录有来源、日期、版本、研究类型、方法贡献、阅读状态和纳入理由；核心文献有全文阅读卡。
3. **学术发表地图**：找出哪些学科、期刊和会议持续发表社会模拟/生成式 ABM/LLM 社会模拟方法研究，区分“发表先例”与“投稿适配”。
4. **研究与投稿路线图**：分别判断当前 Agent-EX 应投哪里、需要什么论证；以及后续方法论文可发展什么贡献、适合什么渠道。

### 1.2 持续推进规则

这是一项持续研究任务，不是一次性生成报告。每次 Codex 会话或工作批次都必须：

1. 首先读取 `GOAL.md`、`progress.md`、本任务书和 `README.md`，确认当前 HEAD、分支、工作区与未完成事项。
2. 从 `progress.md` 的“下一项具体任务”恢复，不重新建立文献库，不重复已经完成的工作。
3. 每一批至少完成一项可核查的实质工作，例如：新增并核实一组核心文献、完成一张全文卡、核对一个方法期刊的发表先例、解决一项全文/日期缺口、完善一段方法综合。
4. 完成后立即更新 `progress.md`、相关数据表和 README 导航；提交本批已核实成果，并写明 commit SHA。
5. 在进度文件中保留“已完成、进行中、阻塞、下一项具体任务”四个栏目。下一项任务必须具体到文献、期刊、检索批次或报告章节，不能只写“继续检索”。
6. 不因某一数据库或全文受阻而停止其他可完成任务；记录访问缺口并切换到可用来源。
7. 不把预定篇数当作完成目标，不凑数、不虚构检索量、不把摘要阅读说成全文精读。
8. 当本轮工作达到工具、上下文或时间限制时，保存可恢复状态和明确交接，避免只输出聊天汇报而没有落盘。

**持续推进的含义**：在每个实际可运行的 Codex 工作会话中主动恢复并推进下一批任务，保持项目状态连续。不得声称会在会话结束后自行后台运行或在没有执行环境时持续工作。若用户以后再次打开任务，必须从 `GOAL.md` 和 `progress.md` 接续。

## 2. 第一轮成果的保留与重分类

### 2.1 不得破坏的内容

- 保留全部现有 record_id、work_id、venue_id 和 DOI。
- 保留 57 条文献记录及其 included/candidate/frontier/excluded 状态；若核查后需要变更，必须写变更原因和证据。
- 保留 15 张全文阅读卡，不批量覆盖或删减。
- 保留原始批次、231 行检索与来源核验日志、已有期刊档案、工作簿、BibTeX 和交叉核查报告。
- 不把 2022 年以前文献纳入本轮独立检索、核心文献统计或阅读卡；已有参考文献中的早期理论背景只在必要处保留。
- 不因本轮方法优先而删除传播网络、意见演化等应用文献。

### 2.2 对现有 57 条记录重新编码

在原 schema 上**新增字段**，不要改变既有字段语义。建议新增：

- `method_relevance_tier`: `core_method` / `method_validation` / `application` / `direct_comparator` / `peripheral`
- `method_contribution_type`: 可多标签，至少支持 `simulation_paradigm`、`agent_architecture`、`environment_design`、`interaction_protocol`、`memory_and_persona`、`model_calibration`、`validation_and_external_validity`、`measurement`、`reproducibility_and_reporting`、`theory_to_model_translation`、`emergence_analysis`、`application`、`other`
- `method_maturity`: `conceptual_framework` / `prototype` / `empirical_method_test` / `validated_workflow` / `review_or_critique` / `unclear`
- `disciplinary_home`: 论文实际归属学科/研究共同体，不简单等于期刊多学科标签
- `method_transferability`: 对其他研究者可复用程度及依据
- `method_evidence_level`: `conceptual_claim` / `worked_example` / `controlled_comparison` / `empirical_validation` / `multi_context_validation` / `unclear`
- `method_relevance_rationale`: 一句话说明为什么归入该层级

先形成字段字典和编码规则，再批量编码。多标签必须由全文或明确摘要内容支持；不能仅凭题名推断方法成熟度。未读全文时标记 pending。

请形成 `reports/method_reclassification.md`，总结原有 57 条中有多少条属于方法核心、方法验证、应用、直接对照和外围参考；统计时区分全文确认、摘要候选、日期待核。不要只给数量，还要列出每类代表记录和调整理由。

## 3. 第二轮重点检索：方法本身，而非单一应用

时间仍为 2022 年起。方法检索不限定新闻传播学期刊，优先跨学科搜索。每组检索词分别运行，不要求每篇论文同时命中所有词。

### 3.1 社会模拟范式与方法定位

关键词：

- `LLM-based social simulation`
- `large language model social simulation`
- `generative social simulation`
- `generative agent-based modeling` / `generative agent-based modelling`
- `LLM-driven agent-based modeling`
- `large language models as social simulators`
- `synthetic societies`
- `agent-based modeling with LLMs`
- `social simulation as a research method`
- `multi-agent social simulation framework`

重点回答：LLM 社会模拟被定义为什么方法？与传统 ABM、调查仿真、数字孪生、生成式智能体、任务协作型多智能体有什么区别？哪些研究将其用于理论检验、机制探索、经验再现、预测或方法演示？

### 3.2 智能体架构与建模

关键词：

- `LLM agent architecture`
- `generative agents memory planning reflection`
- `persona design`, `agent initialization`
- `agent memory`, `long-term memory`, `social memory`
- `agent environment`, `interaction protocol`
- `multi-agent coordination`, `agent communication`
- `agent heterogeneity`, `synthetic population`
- `agent-based social systems`

重点回答：研究者如何构造主体、设定异质性、组织记忆与环境、设计交互、管理更新时序和群体结构？哪些部分由 LLM 决定，哪些仍由研究者预设？

### 3.3 校准、验证与外部效度（最高优先级）

关键词：

- `validation of generative social simulation`
- `LLM agent calibration`
- `agent-based model validation`
- `external validity`, `ecological validity`
- `human validation`, `human behavior benchmark`
- `simulation fidelity`, `behavioral validity`
- `model alignment`, `simulation bias`
- `sensitivity analysis`, `ablation study`
- `benchmark for LLM agents`
- `replication study`, `reproducibility`

重点回答：什么证据足以说明模拟有用？模型输出像人类、复现宏观统计规律、复现微观行为、机制正确、可预测真实结果，分别是什么层次？模型偏差、提示敏感性、初始分布塌缩、角色一致性、随机性和跨模型稳定性如何检验？

不要把“输出看起来合理”“专家觉得可信”“模拟结果与预期一致”自动视为效度证据。

### 3.4 实验协议、报告规范与可复现性

关键词：

- `ODD protocol agent-based model`
- `ODD protocol generative agents`
- `reporting standards agent-based modeling`
- `reproducible agent-based simulation`
- `simulation experiment design`
- `random seed LLM agent simulation`
- `stochastic reproducibility`
- `model documentation`
- `computational experiment reporting`

重点回答：是否出现面向 LLM-ABM 的报告清单、协议、标准化工作流、开放代码和模型归档规范？传统 ODD、CoMSES、TRACE 等规范如何被采用、修改或批评？LLM 额外需要报告哪些信息（模型版本、system prompt、temperature、解码参数、记忆状态、工具、上下文、失败与重试、随机种子、运行成本等）？

不得把某一规范的推荐做法写成强制标准，须核对原始规范。

### 3.5 从理论到计算模型

关键词：

- `theory-driven agent-based modeling`
- `theory formalization agent-based model`
- `mechanism-based social simulation`
- `micro-macro link agent-based modeling`
- `emergence in generative agents`
- `computational social science methodology`

重点回答：社会科学理论如何转化为主体属性、行为规则、互动关系与宏观测量？LLM 是否让研究者更容易表达复杂行为，还是也增加了不可识别的自由度？如何区分研究者设计的规则与模型自主生成的行为？

### 3.6 应用领域作为方法检验场

按领域检索 LLM 社会模拟方法应用，不局限传播学：

- 政治行为、公共舆论、投票、政策偏好；
- 社会心理、规范形成、社会影响、群体决策；
- 经济行为、市场互动、组织行为；
- 健康传播与公共卫生行为；
- 城市、交通、生态和环境行为；
- 教育、文化与信息传播。

每篇应用文献同时标记它对方法本身的贡献：只是使用现成框架，还是提出/验证/改进了模拟方法。

## 4. 期刊与会议发表生态：重新建立方法导向期刊地图

第一轮的新闻传播期刊表继续保留，但第二轮新增独立的 `method_venue_map.csv`，将期刊/会议按发表方法贡献的类型分类。不要只按学科名称机械分组。

### 4.1 社会模拟与 ABM 核心期刊

优先核查：

- Journal of Artificial Societies and Social Simulation (JASSS)
- Journal of Simulation
- Simulation Modelling Practice and Theory
- Simulation
- Social Science Computer Review
- Computational and Mathematical Organization Theory
- Journal of Economic Interaction and Coordination（按实际相关发表判断）

重点检索 2022 年以来的 LLM、生成式 ABM、模型验证、方法规范、模型复现、理论到模型转化研究。若某刊没有 LLM 论文，也应检查其 ABM 方法论文是否构成相关发表传统，但明确区分“传统 ABM 发表先例”和“LLM-ABM 直接先例”。

### 4.2 计算社会科学、传播与跨学科社会科学

优先核查：

- Computational Communication Research (CCR)
- EPJ Data Science
- Humanities and Social Sciences Communications
- Information Processing & Management
- Social Networks
- Social Science Research
- Political Analysis
- Political Communication / Journal of Communication（只在出现方法或模拟相关发表时纳入）
- PLOS ONE / Scientific Reports / Nature Communications（作为跨学科实际发表渠道，不按名气预设适配）

### 4.3 AI、计算机与信息科学方法期刊

优先核查：

- Artificial Intelligence Review
- AI
- ACM Transactions on Social Computing
- ACM Transactions on Intelligent Systems and Technology
- ACM Transactions on Interactive Intelligent Systems
- Transactions of the Association for Computational Linguistics（只有语言机制、NLP 评价或计算语言学贡献时才适配）
- Information Sciences
- Information Processing & Management
- Expert Systems with Applications
- IEEE Transactions on Computational Social Systems

对每一本期刊必须检索实际相近发表、核查 aims & scope 和作者指南。期刊在候选清单中不等于推荐投稿。

### 4.4 会议与学术共同体

会议不能混入期刊表，但必须作为发表生态的一部分单列研究。按研究主题核查：

- AAMAS
- ICWSM
- ACL / EMNLP / NAACL
- NeurIPS / ICML / ICLR
- CHI / CSCW
- Web Conference (WWW)
- Social Simulation Conference / ESSA 相关会议
- Computational Social Science Society 相关会议

重点区分：会议论文、Findings、workshop、demo、position paper、poster、preprint。记录实际正式出版载体和同行评审类型，不将会议名称直接等同于论文质量。

### 4.5 期刊分类不要误用

至少分开三张表：

1. `method_venue_map.csv`：方法研究主要发表在哪里，含期刊与会议，但有独立 venue_type。
2. `journal_submission_candidates.csv`：当前/未来论文可能投稿的期刊。
3. 既有 `journals_master.csv`：第一轮新传 SSCI/CSSCI 检索期刊总表，保留其原始覆盖状态。

记录索引类型时，SSCI、SCIE、ESCI、CSSCI 来源版/扩展版分别核验；不能由 JIF、出版社页面泛称 Web of Science 或期刊声望反推具体索引。

## 5. 重点种子与待核查的方法文献

以下是第二轮优先核查线索，不是自动纳入的已确认事实。逐篇核实作者、题名、首次正式发表日期、期刊/会议、DOI、全文、方法内容和版本。

- Hu & Shen, *Multi-Agent Social Simulation: Protocolizing LLM-Driven Agent-Based Modeling as a Quantitative Research Method*（AI, 2026）。重点核查 MASS 框架、研究定位、实验案例、协议和验证证据。
- Larooij & Törnberg, *Validation is the central challenge for generative social simulation: a critical review of LLMs in agent-based modeling*（Artificial Intelligence Review, 2025 online-first / 2026 volume）。重点核查验证分类、效度主张和审查范围。
- Haase & Pokutta, *Beyond static responses: multi-agent LLM systems as a new paradigm for social science research*（Humanities and Social Sciences Communications, 2026）。重点核查其多层框架与社会科学研究方法主张。
- *Can large language models implement agent-based models? An ODD-based replication study*（Ecological Modelling, 2026）。重点核查 ODD 规范、复现任务、模型比较与评价指标。
- Ghaffarzadegan 等有关 LLM-based social simulation / computational social science 的方法教程与论文。核实正式发表版本与具体建议。
- 2022 年以来关于 LLM agent benchmark、agent simulation evaluation、social simulation validation 的代表性综述、方法论文和批评性研究。
- 第一轮的 Betz（JASSS, 2022）、Chuang 等、Cau 等、Brockers 等、Piao 等、Ashery 等保留为方法发展与应用对照，重新编码而非重复建档。

对于以上种子，优先获得出版社全文或合法机构全文；仅有摘要时只记录摘要支持的内容。任何未核实的作者、题名、日期、DOI 或方法结论均标记待核，不能沿用先前聊天中的二手描述作为最终证据。

## 6. 重新比较 Agent-EX：不要把“工程完整”直接等同于“方法创新”

请建立 `reports/agent_ex_method_positioning.md`，将 Agent-EX 与方法论文和直接应用研究放在同一比较框架中。

至少比较：

| 方法维度 | 需要核查的问题 |
|---|---|
| 研究对象 | 模拟人类社会、AI 群体自身，还是人机混合社会？ |
| 主体构造 | Persona、人口属性、初始状态如何生成与校准？ |
| 行为能力 | LLM 自由生成，还是规则与 LLM 混合？ |
| 记忆 | 私人记忆、公共记忆、长期记忆和有限上下文怎样区分？ |
| 环境 | 是否有显式社会环境、信息环境、平台规则和外部约束？ |
| 互动 | 配对、全体、固定网络、动态网络或环境中介？ |
| 时间过程 | 同步/异步、事件驱动、激活与更新规则如何定义？ |
| 信息流 | 信息如何生成、发布、暴露、选择、读取、过期和重复？ |
| 测量 | 个体状态、行为、公开表达、宏观涌现如何测量？ |
| 校准与验证 | 有无真实数据、人类行为、基准任务、经验规律或多模型对照？ |
| 稳健性 | seed、模型、议题、提示、参数、拓扑和敏感性如何检查？ |
| 可复现性 | prompt、模型 revision、解码参数、代码、运行环境、失败/重试、成本是否报告？ |
| 理论连接 | 社会科学理论怎样落实为模型构造与可检验机制？ |
| 贡献成熟度 | 概念框架、原型、受控比较、经验验证还是跨场景验证？ |

明确回答：

1. Agent-EX 哪些设计属于已有成熟方法的规范实施？
2. 哪些设计只是本项目的研究者选择，不构成一般方法创新？
3. 哪些过程记录、测量或对照设计具有可迁移性？
4. 当前证据支持的是方法应用、方法评估，还是方法创新？
5. 若未来写独立方法论文，必须增加哪些跨情境验证、基准、比较或规范化贡献？

不能将 N500、90 万事件、复杂平台、事件日志等工程规模单独当作方法创新。必须解释它们对研究可观察性、测量质量、机制识别或复现能力产生了什么可验证增量。

## 7. 投稿判断必须分成两种文章

### 7.1 当前 Agent-EX 实证/应用论文

定位暂定：**以社会模拟方法为基础，研究 LLM 智能体群体中的意见演化与社会互动过程。**

重新评估：

- JASSS：社会过程模拟、理论与模型解释是否充分？
- CCR：计算传播研究问题与可迁移方法贡献是否清晰？
- EPJ Data Science：是否有实质数据/系统科学洞见，而不只是模拟轨迹描述？
- SSCR：是否对社会科学计算方法提供可复用的研究贡献？
- 其他期刊：必须有真实发表先例和官网范围支持。

### 7.2 后续独立方法论文

定位暂定：**LLM-driven ABM 如何成为可控、可验证、可复现的社会科学研究方法。**

评估 JASSS、Journal of Simulation、Simulation Modelling Practice and Theory、SSCR、AI/计算机相关期刊等。尤其需要区分：

- 方法综述/批判性综述；
- 方法框架或协议；
- 受控基准和验证研究；
- 新模型/新平台；
- 具有跨场景证据的方法评估。

当前方法期刊有相关论文，不代表当前 Agent-EX 结果稿可以直接投稿。对每本候选期刊都要回答“它接收哪种贡献、Agent-EX 当前提供了什么、还缺什么”。

### 7.3 投稿证据表字段

`journal_submission_candidates.csv` 至少记录：

- venue_id、期刊名称、学科与索引类型；
- aims & scope 官方来源、作者指南官方来源、核验日期；
- 2022 年以来最相近正式发表（至少列题名、年份、DOI/URL、方法类型）；
- 期刊实际方法发表倾向（有几篇、跨几年、是否持续，证据不足时明说）；
- 当前稿适配判断及决定性理由；
- 方法论文适配判断及决定性理由；
- 所需写作调整、现有数据分析、新实验/验证；
- 文章类型、篇幅、代码/数据要求、OA 与费用；
- 建议等级和待核查项。

不要估造接受率、审稿周期、成功概率或历史索引状态。

## 8. 本轮新增交付物

在 `literature-review/` 内新增或更新：

| 文件 | 内容 |
|---|---|
| `GOAL.md` | 北极星目标、完成定义、持续推进规则、当前下一项任务 |
| `METHODS_FIRST_REORIENTATION.md` | 本任务书 |
| `data/method_venue_map.csv` | 方法研究发表生态（期刊/会议分列） |
| `data/journal_submission_candidates.csv` | 当前稿与后续方法论文的双轨投稿候选 |
| `reports/method_reclassification.md` | 对现有 57 条的第二轮方法导向重分类 |
| `reports/method_landscape.md` | 2022 年以来 LLM 社会模拟方法发展地图 |
| `reports/agent_ex_method_positioning.md` | Agent-EX 与现有方法的系统比较 |
| `reports/method_venue_landscape.md` | 方法论文主要发表学科、期刊、会议及其发表证据 |
| `reports/two_track_submission_strategy.md` | 当前稿与后续方法论文的双轨投稿策略 |
| `reading-cards/` | 为新纳入的核心方法论文新增阅读卡，沿用稳定 ID 规则 |
| `progress.md` | 目标执行状态、当前批次、下一项具体任务和 commit SHA |
| `README.md` | 更新入口，将方法主线置顶，原传播应用内容保留为第四层 |

如有必要，扩展 `data/literature_master.csv` schema，但必须同步更新 `data/README.md`、Excel 导出和 BibTeX 导出。新增的期刊表与第一轮 `journals_master.csv` 分开维护，不能混淆检索覆盖范围。

## 9. 执行顺序与首批任务

### 批次 A：研究定位与 schema 调整

- 阅读本文件、GOAL、README、progress 和第一轮所有核心成果。
- 确认项目当前分支和 HEAD；不得覆盖未提交工作。
- 先写入 GOAL.md。
- 制定新增字段字典与方法分类编码规则。
- 对 57 条记录先做方法导向重分类，不立即进行大规模新检索。
- 输出 method_reclassification.md。

### 批次 B：方法核心种子精读

优先核查第 5 节方法种子，补齐全文和正式发表信息；每篇完成方法阅读卡，重点提取研究框架、主体架构、交互协议、验证证据、限制和可复用性。将综述、方法框架、实证验证和批评性研究分开。

### 批次 C：跨学科方法检索

按第 3 节主题组执行多数据库/出版社/会议检索，记录真实查询、覆盖范围、命中数和访问缺口。优先方法核心和验证研究，再扩展应用场景。新期刊由命中文献驱动加入，不要只把预设期刊名单当封闭全集。

### 批次 D：发表生态与投稿双轨评估

完成 method_venue_map.csv 和双轨投稿表。每个重点期刊至少核实官方 scope 和 2022 年以来的真实发表证据；区分传统 ABM 先例、LLM-ABM 直接先例和方法验证先例。

### 批次 E：综合与持续接续

完成方法地图、Agent-EX 定位、期刊发表地图和双轨投稿建议；更新工作簿和 README。留下下一批明确任务。

**完成批次 A 后不要停下来等用户再次批准，直接继续批次 B；完成 B 后继续 C，按可访问证据持续推进。** 若遇到访问受阻，先完成其他可用工作，并在缺口报告中说明需要用户提供的数据库导出或全文。

## 10. 最终验收：真正回答用户的问题

最终报告必须清楚回答：

1. 2022 年以来 LLM-based Social Simulation / Generative ABM 形成了哪些研究范式与方法路线？
2. 方法的关键组成是什么：主体、记忆、环境、交互、时序、信息、测量、验证和复现？
3. 方法研究目前有哪些成熟度层次，哪些结论已有跨场景证据，哪些仍停留在概念框架或示范？
4. 研究主要发表在哪些学科、期刊和会议？哪些是持续发表的方法共同体，哪些只是偶发的跨学科先例？
5. 传统 ABM 与 LLM-ABM 的连续性和方法变化是什么？
6. Agent-EX 的设计在方法地图中属于什么位置，真正可辩护的贡献是什么？
7. 当前 Agent-EX 论文应优先考虑什么投稿渠道，需要怎样组织贡献？
8. 后续独立方法论文需要新增什么研究，适合什么期刊/会议？
9. 尚有哪些全文、日期、数据库、索引与验证证据缺口？

## 11. 学术表达与证据纪律

- 以社会模拟、计算社会科学和新闻传播学已有共同体术语为准，不生造概念。
- 先提出判断，再给具体论文、方法和证据。
- 严格区分作者原文主张、实证结果和本项目的推论。
- 不以摘要代替全文，不以预印本代替正式版，不以相关性代替适配性。
- 不以“用了 LLM”作为方法创新，不以系统复杂度、Agent 数量、事件量或平台工程量代替理论/方法贡献。
- 对验证研究尤其关注负面结果、方法批评、不可复现和外部效度限制。
- 2022 年以前文献不进入本轮独立纳入库；若为解释传统 ABM 背景必须提及，简短标为范围外背景，不展开检索或精读。
- 所有期刊索引、作者指南、费用与发表证据注明来源和核验日期。
- 检索受阻必须如实记录，不能把未访问说成零命中。

## 12. 立即开始

现在从批次 A 开始：创建 GOAL.md、调整 README、制定 schema 迁移规则、重分类现有 57 条，并完成第一批方法核心种子核查。每批都落盘、更新进度、提交并汇报。不要只给执行计划；请完成实际工作并在 `progress.md` 留下下一项明确任务。
