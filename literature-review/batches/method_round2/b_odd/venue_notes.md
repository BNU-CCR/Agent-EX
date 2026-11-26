# C/D补充：建模方法期刊适配与2022+先例

核查时间：2026-11-26。本文是来源核实与适配判断，非投稿建议定案、非期刊层级认证。全部scope来自出版商官方介绍，未采用第三方期刊排名。新先例仅供集中去重，未改主表、未创建稳定ID。搜索范围是公开网页，不是完整数据库检索。

## 三刊scope与本项目关系

| 期刊 | 已核官方范围 | 对Agent-EX的适配判断（推断） |
|---|---|---|
| Ecological Modelling，ISSN0304-3800 | 生态过程模型与系统分析，重视有理论和因果主体的过程模型，涵盖人类生态/社会生态系统；支持模型可复现性与效用。 | M003、ODD+NetLogo显示可发表跨模型实现与复现方法，但题材仍扎根生态建模；纯传播网络应用须证明生态/社会生态贡献，不能因一篇LLM文章就视为一般LLM社会模拟出口。 |
| Environmental Modelling & Software，ISSN1364-8152 | 环境建模与软件，鼓励可跨系统迁移的方法、模型评价、敏感性/不确定性与质量保证；明确要求开发理由、充分测试、量化可靠性证据及许可说明。方法发展通常应以环境领域应用展示。 | 理论转译、方法规范与复现审计有直接先例；一般社会传播题目仍需论证环境或社会生态联系。规范综述的可迁移方法价值高于一般应用相似性。 |
| Simulation Modelling Practice and Theory，ISSN1569-190X | 各类系统建模仿真；明确列出形式建模、实验设计、敏感性分析、元模型、验证与校验、比较程序和智能代理；要求呈现模型开发、实现、可扩展性与真实数据核对步骤。 | 三刊中范围对一般仿真方法最直接；适合把贡献表述为可检验的仿真方法/实现评价问题。仅展示社会现象或生成文本通常不足，需要清楚的技术新增及评价。 |

官方来源（已读Description）：

- [Ecological Modelling官方介绍](https://shop.elsevier.com/journals/ecological-modelling/0304-3800)，Description第92–96行。
- [Environmental Modelling & Software官方介绍](https://shop.elsevier.com/journals/environmental-modelling-and-software/1364-8152)，Description第92–116行。
- [Simulation Modelling Practice and Theory官方介绍](https://shop.elsevier.com/journals/simulation-modelling-practice-and-theory/1569-190X)，Description第91–105行。

## 已完成阅读的直接先例

M003与TMP-ODD02见本目录results.json及两张阅读卡。前者让LLM依据ODD编写规则生态ABM；后者是人类依据ODD重写/复现18个规则模型。两者均不能作为模拟内部LLM社会主体经过人类数据验证的证据。

TMP-ODD03展示Environmental Modelling & Software有标准发展专题文章，但当前只读摘要。KNAW机构记录首次在线2026-10-16、卷期2027-01；不要混用Crossref建档2026-10-10作发表日期。

## 补充正式方法先例（尚未全文精读，不编码成熟度/证据等级）

1. Antosz et al. **What do you want theory for? - A pragmatic analysis of the roles of “theory” in agent-based modelling.** Environmental Modelling & Software168,105802，DOI10.1016/j.envsoft.2023.105802。首次在线2023-08-21，由机构库记录与出版PDF首面一致确认。已读官方摘要/亮点及机构库元数据，只浏览部分正文；不作全文读毕声明。讨论理论与ABM的多种关系及谨慎推广，直接支持方法导向理论定位。[官方文章](https://www.sciencedirect.com/science/article/pii/S1364815223001883)；[机构库和在线日期](https://eprints.whiterose.ac.uk/id/eprint/203297/)；[出版PDF](https://eprints.whiterose.ac.uk/id/eprint/203297/1/1-s2.0-S1364815223001883-main.pdf)。

2. Banitz et al. **Model-derived causal explanations are inherently constrained by hidden assumptions and context: The example of Baltic cod dynamics.** Environmental Modelling & Software156,105489，DOI10.1016/j.envsoft.2022.105489。首次在线2022-08-18，出版PDF首面；卷期2022年10月。Position Paper。已读官方摘要/亮点及PDF首面，未全文读毕。模型间因果结论与隐含假设/情景的关系，是论证边界的直接方法先例；不能从题名或摘要给其成熟验证标签。[官方文章](https://www.sciencedirect.com/science/article/pii/S136481522200192X)；[合法机构PDF](https://uu.diva-portal.org/smash/get/diva2%3A1705902/FULLTEXT01.pdf)。

3. Moreno, Jorba, Peralta, César, Sikora & Hanzich. **A methodology for selecting a performance-convenient ABMS development framework on HPC platforms.** Simulation Modelling Practice and Theory128,102812，DOI10.1016/j.simpat.2023.102812。首次在线2023-07-29，出版PDF首面；2023年卷期。已读首面摘要/日期，20页未全文精读。提出基于问题类别和基准实验选择FLAME/RepastHPC/DMASON框架，表明该刊认可可迁移框架比较方法；比较对象是传统并行ABM，不是LLM模型质量。官方文章直接访问403，由机构库出版版本核题录。[官方文章](https://www.sciencedirect.com/science/article/pii/S1569190X23000898)；[UAB出版PDF](https://ddd.uab.cat/pub/artpub/2023/967161b1ed5d/1-s2.0-S1569190X23000898-main.pdf)。

4. **Using linear regression metamodels for evaluating interventions in an individual-based influenza epidemic model.** Simulation Modelling Practice and Theory，2023年7月，102772，DOI10.1016/j.simpat.2023.102772。仅官方摘要读到，首次正式在线具体日与完整作者未核，不作为完成题录纳入。是仿真实验/元模型评价的备用先例。[官方摘要](https://www.sciencedirect.com/science/article/pii/S1569190X23000497)。

## 精确检索与障碍

本轮真正执行的搜索串（web.search_query）：

- site.sciencedirect.com/journal/ecological-modelling/about/aims-and-scope
- site.sciencedirect.com/journal/environmental-modelling-and-software/about/aims-and-scope
- site.sciencedirect.com/journal/simulation-modelling-practice-and-theory/about/aims-and-scope
- site.sciencedirect.com "Simulation Modelling Practice and Theory" "2024" "reproducibility"
- site.sciencedirect.com "Simulation Modelling Practice and Theory" "2023" "agent-based" validation
- "What do you want theory for" "2023"
- "Model-derived causal explanations" "2022"
- "What do you want theory for" "105802" site.sciencedirect.com
- "Model-derived causal explanations" "105489" site.sciencedirect.com

各刊about页面检索未得到足够官方内容，转而读取Elsevier Shop官方Description成功。SMPT基准论文ScienceDirect直接访问403，UAB出版PDF成功。未登录、未绕过付费墙；尚未阅读全文的先例保留未完成状态。当前适配判断建立于官方范围和少量真实先例，不能代表编辑接收概率。
