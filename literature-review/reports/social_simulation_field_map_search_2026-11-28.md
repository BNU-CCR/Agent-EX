# 社会模拟领域地图：本次范围与来源说明

日期：2026-11-28（Asia/Shanghai）｜批次：FIELD-MAP-01

## 本次任务变化

用户要求先推送已有成果，随后为组会梳理社会模拟大领域的发展、最新研究和期刊关注，项目位置只占较小篇幅。本批据此新增领域地图与汇报底稿；原方法论综述继续保留，不回滚第一／第二轮成果，不重新建立文献库。

开始工作时分支为codex/social-identity-network-2x3，HEAD为3246948，工作区干净，与已知origin比较0/0；实际推送返回Everything up-to-date。此次新文档另行提交推送。

## 证据策略与实际交付

- 复用现有241条主表及已读卡；不重新全文核查每项旧文献。
- 来源表列29项代表文献：17项直接以旧ID引用，12项以F01—F12作为地图锚点。其中F01=M081、F02=M060、F04=M013、F08=M052已经在主库；其余8项是本次为领域地图补充的来源（含1份官方技术报告）。F编号是地图别名，不是新论文或新实验计数。
- F01—F08均有正式出版社／期刊页面；F09为出版社索引与元数据，F10／F12为正式期刊HTML，F11为官方报告页。本次仅定向读摘要、部分导论及发表信息，不声称完成12篇全文精读，不改变任何主库纳入或成熟度编码。
- 新增10主题矩阵、领域总报告、12页／约20分钟讲述底稿及概念地图SVG。
- 本版有意展示非LLM研究。先识别健康／人口与系统动力学缺口，再补入F09—F12；这些分支的完整生态及组织犯罪、中文与区域共同体仍薄弱，正文逐项保留覆盖缺口。

## 实际检索表达式

以下为公开Web发现查询；搜索结果用于定位一手来源，没有导出或宣称检索了WoS、Scopus、CNKI授权数据库，也不把搜索结果数当召回率。

1. `site.jasss.org 2026 social simulation policy participatory simulation review`
2. `site.nature.com 2025 2026 agent based modelling social simulation empirical policy`
3. `site.jasss.org 2024 2025 empirical theory agent based social simulation inequality participatory`
4. `site.nature.com 2023 2024 agent based model climate macroeconomic transition policy`
5. `site.science.org 2022 agent based simulation COVID policy Covasim`
6. `site.jasss.org journal aims scope social simulation ESSA`
7. `site.springer.com journal 10588 aims scope Computational Mathematical Organization Theory`
8. `site.econ.iastate.edu tesfatsi agent based computational economics 2022 2026`
9. `site.onlinelibrary.wiley.com "System Dynamics Review" "2024" "health"`
10. `site.onlinelibrary.wiley.com "System Dynamics Review" "2025" "climate"`
11. `"COVSIM" "2024" "100752"`
12. `site.jasss.org "2025" "population" "microsimulation"`

代表文献的实际正文链接、阅读层次与边界见[data/social_simulation_field_sources.csv](../data/social_simulation_field_sources.csv)。未直接支持叙述的二手搜索结果不列作论据。

## 期刊与共同体资料

本次读到CMOT、JEIC、EPJ Data Science官方aims-and-scope及ESSA官网。JASSS官网首页无可读正文，尝试的admin/info.html不可达，因此JASSS表述主要依据实际正式论文和ESSA共同体资料，不伪称完整scope复核。System Dynamics Review、CCR等复用旧库来源与具体发表先例；本次没有重查全部投稿指南、费用和收录。

ESSA实际页面列出2022—2026会议与多个兴趣组，包括LLM4ABM、强经验建模、实验—ABM、人类决策、Qual2Rule、社会身份、转型和模拟游戏。正文只将其用作共同体结构证据，不采用网站关于自身重要性的宣传排名。

## 未采用或访问失败的线索

- ScienceDirect人口模型GEPOC与可持续食品政策论文的直接打开返回403。仅搜索索引可见，未作为本版代表研究或补全全文。
- npj Complexity DOI10.1038/s44260-026-00101-2正文及reference PDF被身份跳转阻断，未纳入；不猜测其结果。
- 2021 Covasim基础论文超出2022+近期窗口，本版不将其作为近期新研究；没有为填充健康板块把卷年2022但在线日期可能为2021的条目自动纳入。
- 没有执行第三方模型、下载大型代码仓库或重开前轮一般审计。

## 本批判断与下一项

领域地图宜沿社会问题与模型目的组织，再介绍方法路线与评价证据；LLM作为分支，项目落点最后一页。资料支持多条研究路线并行发展，但不足以给出全领域增长率、热点份额、期刊排名或统一成熟度。

补充阶段已在本会话继续完成：F09—F12覆盖健康行为模型、应急演练、人口微观模拟与系统原型综述。下一项具体工作是按组会时长压缩图表和案例，后续维护补组织／犯罪和中文共同体。无需重做已有LLM库，也无需为组会恢复逐文件技术审计。
