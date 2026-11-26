# JASSS / Journal of Simulation 方法定位与投稿核验

核验日期：2026-11-26。仅为定向公开补查，不是期刊完整检索或录用概率判断；未更新主表。B包两篇精读之外，下列新增文献只是方法先例核查，未冒充完整精读卡。

## JASSS：社会过程解释与建模方法

**官方范围。** [About](https://www.jasss.org/admin/info.html)的实际[动态内容源](https://www.jasss.org/v02/page_content_includes/_include_about.html)明示以计算机模拟理解社会过程，接收社会模拟与agent societies相关原创研究和批评性综述；官网About自列SSCI。它可支持社会模拟方法定位，但不是新闻传播Communication期刊目录的替代。

**官方投稿页。** [How to submit](https://www.jasss.org/admin/submit.html)正文由站点脚本加载，本次直接取得[同站正文源](https://www.jasss.org/v02/page_content_includes/_include_submit.html)，HTTP200，并保存原文文本以便复核。正常篇幅5,000–8,000词，摘要≤300词、关键词≤6个。建议公开模型代码与文档，推荐CoMSES库和ODD；ODD并非强制格式。文章须可独立理解，不能让读者靠读代码补全正文。About用“requires”描述足够复现信息，投稿页用“strongly encouraged”；两页措辞强度应保留，不能缩成“代码必须公开”。预印本不自动构成重复发表。未核当前费用、匿名材料具体清单；不借旧镜像补成现行规定。

**2022后方法先例。**

| 文献/正式首发 | 本次实际核查 | 对方法定位的含义与界限 |
|---|---|---|
| Wijermans, Vriens & Andrighetto, *Harmonising Theory and Empirics: The THEMP Approach for Developing, Testing and Exploring Social Simulation Models*, DOI[10.18564/jasss.6211](https://www.jasss.org/29/4/6.html)，2026-10-31，29(4)6 | 官方题录及HTML方法部分：Introduction、Background、THEMP design/testing/exploration与ODD映射、示例开头；未独立检查其Norms@Risk外部模型 | 正式的方法框架先例；把理论/经验在设计、验证、探索中的作用显性化，示例展示不等于框架提升理论质量的独立效果检验。与R015、R021互补，不能合成一套已验证标准。 |
| Nespeca, Comes & Brazier, *A Methodology to Develop Agent-Based Models for Policy Support Via Qualitative Inquiry*, DOI[10.18564/jasss.5014](https://www.jasss.org/26/1/10.html)，2023-01-31，26(1)10 | 官方题录、摘要与方法概述/模型开发部分；未全读案例及附录 | 以定性资料与理论构造概念框架，再用通用模型开发ABM的两阶段方法；Jakarta灾害信息管理是示范，不能据此称跨情境验证已完成。 |

**对Agent-EX的判断（本次推论）。** 当前应用稿若回答“身份与曝光如何改变这个AI群体”，应论证社会过程问题、作用机制、对照与边界。后续方法稿则须提出可复用的建模/评估问题、给出明确流程和超越单个结果图的证据。THEMP显示解释性理论建模本身有发表空间，不能推导“现有流水线完整即可方法创新”。最有用的补充是逐机制假设来源、可替代机制与何种观测会使解释失效；不在本任务开展实验。

## Journal of Simulation：可复用评估流程与仿真技术

**官方范围。** [T&F官方期刊首页](https://www.tandfonline.com/journals/tjsm20)的搜索可读索引说明接收仿真技术/工具/方法、理论与应用，涵盖DES、ABM、system dynamics及混合模型，允许方法、教程、综述及较短technical notes。官方[期刊信息](https://www.tandfonline.com/action/journalInformation?journalCode=tjsm20&show=instructions)索引自列SCIE/WoS与Scopus，不能写成SSCI。目标是OR Society/T&F、ISSN1747-7778/1747-7786；同名journalofsimulation.com刊不是本对象。

**指南缺口。** 官方[Instructions for authors](https://www.tandfonline.com/action/authorSubmission?show=instructions&journalCode=tjsm20)经公开抓取与普通HTTP均403；替代author-guidelines路径也不可达。本次核实了官方范围和稿型，未核字数、结构化摘要、匿名方式、必交报告清单与数据政策。不把JORS的要求或2013年第三方存档挪作本刊现行要求。

**2022后方法先例。**

| 文献/正式首发 | 本次实际核查 | 方法贡献及边界 |
|---|---|---|
| Bemthuis, Govers & Asadi, *A CRISP-DM-based methodology for assessing agent-based simulation models using process mining*, DOI[10.1080/17477778.2025.2508245](https://www.tandfonline.com/doi/full/10.1080/17477778.2025.2508245)，2025-06-06（卷期20(5)，2026） | 官方可读搜索全文片段：摘要、引言、§3及§5限制；直接全文URL403，未据片段称全文精读 | 将CRISP-DM转成仿真事件日志评估流程，以Schelling示范，单人评估有局限。直接涉及Agent-EX现有事件日志，但“日志齐备”与“具有独立外部行为效度”之间仍有差距。 |
| Monks & Harper, *Computer model and code sharing practices in healthcare discrete-event simulation: a systematic scoping review*, DOI[10.1080/17477778.2023.2260772](https://www.tandfonline.com/doi/abs/10.1080/17477778.2023.2260772)，2023-09-30（卷期19(1)，2025） | 官方题录与检索返回的§6.3等全文片段；未重新执行综述 | 表明代码/模型分享、运行说明与依赖等可成为方法审计对象；领域为医疗DES，不能把其分享率外推给LLM社会仿真。 |

**对Agent-EX的判断（本次推论）。** 若形成可由他人复用的事件级校验、行为调用重构或跨模型评估方法，并通过有意义的比较证明用途，Journal of Simulation有明确范围和发表先例。当前身份/网络应用结果本身不足以证明上述方法贡献。与JASSS相比，本刊需要更突出仿真过程/分析方法的普遍用途；这是基于scope和先例的条件判断，不是编辑部承诺。

## 证据与边界

两个期刊均有2022后正式方法先例；不需靠2018 STRESS补入时间窗来证明。STRESS早于2022，只能背景引用。未把本次新线索自动升级主表纳入；需要root去重、编码或进一步精读。JASSS页面脚本正文已取得；JOS指南仍pending。检索日志见venue_search_log.json；JASSS官方正文文本见同目录jasss_include_submit.txt、jasss_include_about.txt。
