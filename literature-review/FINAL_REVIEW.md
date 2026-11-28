# LLM社会模拟与Generative ABM：方法论综述与Agent-EX发表建议

限时交付版｜文献窗口：2022-01-01至2026-11-28｜第二轮方法导向调整

## 可以直接采用的结论

LLM社会模拟已经形成多种可操作路线：语言主体进入规则环境，平台/行为过程的经验模拟，合成受访者，以及LLM辅助模型设计和实现。但“生成得出、运行得通、输出相似、机制成立、可代表真人”是不同主张。现有证据支持在明确任务、模型和参照下的局部方法比较；不能据单个案例、规模或通顺叙事宣布一种通用社会科学方法已经获得全面验证。

对Agent-EX，当前最稳妥的定位是**受控LLM群体中的意见演化与社会互动研究**。当前稿优先按JASSS的社会模拟论证组织，CCR作为传播问题和测量贡献更突出的另一主路线。后续独立方法稿优先发展信息流/测量与结论敏感性的可比较证据，而非单凭平台、日志或更大规模另写一篇方法论文。

本轮主体成果已有可用交付。完整授权数据库检索、部分关键正式版本和若干投稿字段仍未取得；这些限制明确列出，不以“全领域系统穷尽”包装本综述。

## 1. 方法版图：先分清LLM在做什么

|路线|真正的研究对象|评价重心|本库证据入口|
|---|---|---|---|
|运行时LLM主体与规则环境|主体行为及其闭环群体过程|状态、记忆、信息、调度与互动效果|R006、R008、R016、M001、M008|
|平台/行为过程模拟|特定活动、行为或宏观轨迹|资料角色、时间划分、基线与外推目标|M006、M007、M034|
|合成人格/受访者|特定任务中的回答或行为替代|构件保真、任务效标、群体差异|M026、M040–M042、M049|
|LLM建模助手|规格、概念或代码到模型的转译|语法、可执行、实现忠实、动态与使用成本|M003、M056、M057、M184|
|校准、识别、测量与技术复现|参数、观测或实现与参照的关系|恢复目标、可识别性、误差与泛化|M029、M030、M053、M054|
|报告规范、批评与议程|研究实践和方法责任|适用范围、实现充分性与证据强度|M004、M012、M028、M060、M065|

同一研究可以跨路线。传统ABM、非LLM生成模型和反应网络作为方法对照保留；不把它们全部算成LLM社会主体研究。传播网络意见演化保留为直接对照与应用层，不再支配整库检索。

## 2. 怎样构成一个可解释的LLM社会模拟

可报告的基本结构包括：研究目的与目标系统；主体/状态/尺度；环境与资源；身份/目标/记忆；信息可见性；互动和时间顺序；输出测量；校准、验证与制品。每个构件都应说明为何需要、怎样操作、能否与替代解释区分。

“网络里有边”不等于主体实际接触了信息；提供信息不等于注意、理解或受其影响。私人状态、最近公开内容、表达流与观测读出也可能给出不同结论。记忆长度、更新顺序和输入整理不是无关的工程细节，它们可以改变研究对象。

ODD帮助明确目的、状态、过程、设计概念和子模型，并可建立说明—代码映射；它自身不替代参数校准、验证、运行证据或现实效度。AI生成的规范草稿仍可能误解逻辑或遗漏边界行为。依据：M012正式综述与M011重构研究，见相应阅读卡。

### 传统ABM的连续性与LLM新增的责任

两类方法都需要明确目标系统、主体/环境、过程、时间、观测与评价。主要变化是部分行为规则由条件化语言生成承担：提示、模型版本、上下文组织和解析过程成为行为生成的一部分，规则透明性与可重复性需要另外说明。LLM帮助写模型、LLM在模型里行动，以及以LLM回答替代人类资料，是三种不同变化，不能因都使用自然语言而混合判断。

## 3. 校准和验证必须对准具体主张

|层次|足够具体的问题|证据的边界|
|---|---|---|
|语法/运行|能解析、执行并形成规定输出吗？|通过不证明模型做对了事|
|规格—实现忠实|状态、信息、调度、规则是否实现预定含义？|代码、日志、hash存在不等忠实性已验证|
|模型内受控比较|改变一个构件或条件后结果怎样变化？|机制解释依赖操纵与对照，不能自动外推人类|
|已知真值恢复|恢复的是结构、参数还是参照轨迹？|三者不可用一个“恢复率”合并|
|经验拟合与外推|资料用于初始化、参数估计还是独立评价？|同资料回拟不等未见时间/人群/闭环泛化|
|现实干预解释|某项现实政策或传播干预会产生什么效果？|模型规则切换不等现实政策因果识别|

M184的84.5%是200个合成样本上的特定反应匹配；M003比较生成实现与已知参照轨迹；M053考察合成参数后验恢复与SBC。M183的教师市场反事实来自经验参数化模型，并非某项实际政策的效果识别。这些证据能指导评价设计，不能互相替代。详见[恢复目标对照](data/recovery_targets_FW.csv)。

M184也说明测试设计的重要性：提示数量、训练配置及最佳训练种子按测试表现选择，最终指标不再来自完全未触碰的持出。语法约束有时引入新的语义错误，五人诊断研究中的复杂任务与交互修正也有失败。因此成熟度判断应包含失败和选择过程，而不只摘取最高分。

### 成熟度与跨场景证据的判断

本库区分概念/批评、框架或原型、实际受控方法评价，以及具有经验参照的验证研究。概念分类能界定问题，但不是效用效果量；合成基准能检验规定任务，但不是人类替代证据；多个领域或数据源也不自动形成通用工作流。M003/M184提供受限定任务中的实现/生成比较，M053提供给定生成模型下的推断诊断，M006提供特定平台情境的经验评价。

跨场景支持最应按对象表述：例如M030的跨模型随机模拟技术检验支持技术一致性，不能由此认证LLM在不同社会群体中的行为效度。当前材料不足以给整个LLM社会模拟领域一个统一的“已验证”等级；成熟度判断必须随任务、版本、参照和外推目标给出。

## 4. 可复现性：材料链与结果重现分开

至少区分模型/提示版本、规格和配置、输入构造、原始响应与解析、失败/重试/缺失、随机单位、测量实现及归档定位。生成实现、训练种子、解码种子、模拟run、主体和用户是不同单位。

对群体模拟，主要独立重复通常是seed/run，不能把N名主体当N次独立实验。区间也要标明涵盖的是哪些变动：解码种子SD不是训练不确定性，后验抽样数不是经验样本量，未拒绝差异也不是严格等价。

公开代码提高可检查性，不能单独证明结果已被重现。本库区分获取、静态核查和实际重跑；本轮没有执行第三方模型或训练。M184已发现的评价器规范化/匹配边界只支持限定其指标，尚不能量化对原结果的影响，不继续为此扩张逐文件审计。

## 5. 发表生态与当前稿选择

|渠道|本轮建议|文章应围绕什么组织|
|---|---|---|
|JASSS|当前稿首选组织路线；后续方法稿也优先考虑|社会模拟问题、理论转译、条件对照、独立重复及过程认识|
|Computational Communication Research|当前稿另一优先路线|曝光—回应—公开表达等传播问题，以及计算设计带来的知识增量|
|EPJ Data Science|条件备选|超越轨迹描述的社会系统洞见；现实平台外推需经验锚定|
|IEEE TCSS|有社会系统/可迁移方法增量时考虑|不能只以网络规模、工具集成或工程清单定位|
|Journal of Simulation / TOMACS等|更适合特定建模、实现或形式化方法研究的条件比较|与其方法共同体和评价对象明确对接；单篇先例不等适配|
|Environmental Modelling & Software|当前纯意见演化稿不优先|其方法发展需环境应用；ODD先例不能消除领域边界|

保留31项条件候选供定向选择，**不把31项都当成熟推荐**。JASSS/CCR的选定报告、费用及索引快照已有来源，但部分现行字段和WoS具体子库仍有缺口；不估造接受率、周期或录用概率。Envsoft可读范围已核，完整指南仍受限。具体已核/未核字段见[候选表](data/journal_submission_candidates.csv)。

## 6. Agent-EX当前稿的可辩护贡献

按冻结研究边界，主矩阵为identity 2 × continuity 2 × exposure 3，N=1000、T=50、首批10个matched seeds及盲态扩展规则；主路线为Qwen3-8B BF16/non-thinking。它们是批准规范，不是本综述证明已经执行完成的事实。本轮不修改该设计或未决参数。

论文应把身份构件、持续性和曝光条件对应的理论问题说清，以seed层对照解释群体过程；说明私人意见、公开存量、表达流和实际feed的差异如何影响结论。更大的N、完整日志或严格协议不是独立的方法创新；身份操作未成功也不能直接写成身份理论普遍失效，单向端点集中不能自动称经典双峰极化。

直接对照补充：EN04正式2026摘要已涉及网络结构、规则模型和Higgs社区的定性外部合理性，因此不能只以“网络比较/经验网络”作为新意。其arXiv目前只有2024年v1，正式正文仍未得；不把定性合理性等同独立预测，也不因未读正文断言其没有检验。见[关键版本说明](reports/EN04_critical_version_FY.md)。

建议先以JASSS的社会模拟问题组织一版论证；若主要新增认识落在传播曝光和测量，则改以CCR为主。两条路线都明确“研究AI群体本身”与“代表现实人类”的界限，不能借其他论文替本项目取得效度。

## 7. 后续独立方法论文：收敛到一个可检验贡献

优先方向是**信息流/测量选择怎样改变模拟结论，以及能否检出已知偏离**。固定同一输出比较预声明读出规则；若读出又反馈到行为，应作为不同介入处理。比较替代流程时报告失败、独立单位、人工时间与成本。没有可靠参照时只能报告分歧，不能把一致性当正确性。

第二方向是校准泛化边界：在相同可见信息下，区分校准窗口、未见时间/人群和闭环评价。第三方向是建模助手的规格—实现偏离：可运行、结构匹配和轨迹符合分别判断。三条路线是后续研究建议，相关新实验本轮没有执行，也不是本轮文献交付的附加完成门。

## 8. 已完成与仍需明确保留的限制

已完成原57条的方法重分类/schema扩展、A–E主体交付，后续核心精读、跨学科补查、方法综合、发表地图及双轨策略。当前241条记录：79正式纳入、153候选、7前沿、2排除；92张卡包含作者版和未决工作，273个证据单元不等独立实验。62载体包含41期刊、20会议入口、1仓库；正式纳入来源为56期刊记录/36来源刊及23会议。

按用户限时要求，本轮交付收敛于综述结论与实际投稿选择。以下不隐藏，也不把它们扩张成新的全面审计任务：

1. 授权WoS/Scopus/CNKI完整检索与原新闻传播目录覆盖尚未取得，公开补查不能冒充完整数据库语料。
2. EN03/EN04、EN07、M015、CN012等重要正文/版本仍有缺口；M019仅摘要及索引片段，不能展开完整实验设计。13条日期资格仍待核。
3. 部分期刊指南、篇幅、资料义务、费用/索引字段未核。实际投稿时只刷新目标刊必要字段，无需为写作先填齐所有候选。
4. 个别论文原始运行身份、补充材料和指标边界未完全核准；这些限制约束相应结论，不推为整库无用，也不声称独立复现成功。

因此本文件是**本轮任务书范围内的完成交付版，附已披露的来源限制**。原任务书允许按实际权限检索、未知字段待核并交付缺口清单；本轮以此收尾，不声称完整检索覆盖或未知科学主张已获验证。后续有新合法正文、授权导出或实际投稿需求时，可在同一知识库维护。见[交付完成对照](DELIVERY_COMPLETION.md)。

## 核心证据快速入口

下表是阅读顺序建议，不代表全部论文同一版本、范围或证据强度。具体读本和限制以阅读卡为准。

|条目|题名与正式出处|用途|
|---|---|---|
|[R008](reading-cards/R008.md)|[Generative agent-based modeling: an introduction and tutorial](https://doi.org/10.1002/sdr.1761)；System Dynamics Review，卷期年2024|生成式ABM入门与研究职责|
|[M001](reading-cards/M001.md)|[Multi-Agent Social Simulation: Protocolizing LLM-Driven Agent-Based Modeling as a Quantitative Research Method](https://doi.org/10.3390/ai7080279)；AI，卷期年2026|协议化方法与报告边界|
|[M004](reading-cards/M004.md)|[From the fluency fallacy to the micro-to-macro validity gap: opportunities and pitfalls of LLMs in social simulation](https://doi.org/10.3389/frai.2026.1988865)；Frontiers in Artificial Intelligence，卷期年2026|流畅性与微观—宏观效度风险|
|[M006](reading-cards/M006.md)|[Towards operational validation of LLM-agent social simulations: a replicated study of a Reddit-like technology forum](https://doi.org/10.1140/epjds/s13688-026-00674-x)；EPJ Data Science，卷期年2026|经验/平台过程评价|
|[M029](reading-cards/M029.md)|[MOZAIC: A mathematical approach to formalizing behavioral theories – applied to an agent-based model of mobility](https://doi.org/10.3389/frsps.2026.1772740)；Frontiers in Social Psychology，卷期年2026|理论到模型的形式转译|
|[M053](reading-cards/M053.md)|[Assessing Parameter Identifiability in Agent-Based Models with Bayesian Amortized Inference](https://doi.org/10.18564/jasss.6393)；Journal of Artificial Societies and Social Simulation，卷期年2026|参数恢复、识别与SBC|
|[M003](reading-cards/M003.md)|[Can large language models implement agent-based models? An ODD-based replication study](https://doi.org/10.1016/j.ecolmodel.2026.111624)；Ecological Modelling，卷期年2026|规格实现/参照行为，读本为作者v2|
|[M011](reading-cards/M011.md)|[Using the ODD protocol and NetLogo to replicate agent-based models](https://doi.org/10.1016/j.ecolmodel.2024.110967)；Ecological Modelling，卷期年2025|独立重构与成功/失败范围|
|[M012](reading-cards/M012.md)|[Twenty years of the ODD protocol: development, usage, extensions, and lessons learned about modelling standards development](https://doi.org/10.1016/j.envsoft.2026.107203)；Environmental Modelling & Software，卷期年2027|报告标准的适用范围与AI草稿风险|
|[M030](reading-cards/M030.md)|[EFECT enables reliable and reproducible stochastic simulations across disciplines](https://doi.org/10.1038/s44260-026-00094-y)；npj Complexity，卷期年2026|随机模拟技术复现|
|[M183](reading-cards/M183.md)|[How did it get this way? Disentangling the sources of teacher quality gaps through agent-based modeling](https://doi.org/10.1016/j.ssresearch.2023.102941)；Social Science Research，卷期年2023|经验参数与模型反事实，读本为作者WP|
|[M184](reading-cards/M184.md)|[Using (Not-so) Large Language Models to Generate Simulation Models in a Formal DSL: A Study on Reaction Networks](https://doi.org/10.1145/3733719)；ACM Transactions on Modeling and Computer Simulation，卷期年2025|形式匹配/选择偏差/用户失败，正式PDF定向读|

完整数据：[主表](data/literature_master.csv)｜[Excel](exports/literature_and_journals_methods.xlsx)｜[正式书目](exports/references_methods.bib)｜[九问题详版](reports/methods_review_current_synthesis.md)｜[必要缺口](FINAL_GAPS.md)。
