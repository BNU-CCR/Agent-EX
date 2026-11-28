# FN：Social Science Research真实先例与版本获取

2026-11-28。通过ISSN限定的出版者登记记录找到正式传统ABM先例，解决原“未确认相近正式发表”的一项实质缺口；不把它升级为LLM直接先例或投稿推荐。

## 正式身份与时间

M183，Dan Goldhaber、Matt Kasman、Vanessa Quince、Roddy Theobald、Malcolm Wolff，*How did it get this way? Disentangling the sources of teacher quality gaps through agent-based modeling*，Social Science Research，DOI **10.1016/j.ssresearch.2023.102941**。

Crossref按ISSN0049-089X限定的返回记录给出完整五作者、题名、刊名及published-print2023-11；[出版者API](https://api.elsevier.com/content/article/PII:S0049089X23000960?httpAccept=text/xml)再次匹配DOI、题名、刊名和ISSN，coverDisplayDate为November2023。按原规则以**2023-11精度**确认时间资格，首次在线日未知；不把coverDate11-30或许可证起始11-01推断成首次在线日期。

出版者API本次200仅1863字节元数据，没有摘要或正文；[linkinghub](https://linkinghub.elsevier.com/retrieve/pii/S0049089X23000960)200仅重定向壳，同样不算取得正式全文。

## 可核检索及实际失败

Crossref journal works端点，ISSN0049-089X，时间filter2022-01-01至2026-11-28，rows20：`agent based`返回10项相关性排序记录，逐项核实际刊名；目标M183为其中一项。`simulation`返回0项；`large language model`返回429限流。以上分别是限定查询结果和访问失败，不能合并为“该刊没有LLM论文”或全刊筛选完成。两次公开网页查询工具连接失败，也不作为零命中。

## 合法作者版本已经取得，尚未精读正文

OpenAlex仅用于发现开放位置，随后直取[EdWorkingPapers正式记录页](https://edworkingpapers.com/ai22-552)，其仓储DOI **10.26300/pgkj-sa84** 与期刊DOI分开。仓储标March2022版本；其[下载PDF](https://edworkingpapers.com/sites/default/files/CALDER%20WP%20259-0122.pdf)封面为CALDER WP259-0122、January2022，五作者/题名一致。二者日期标签均保留，不推断首次上网日。

已取得33页/1224090字节PDF并核SHA256，本批只读封面身份及仓储摘要，正文留下一批。摘要描述使用华盛顿州纵向资料构建教师流失、流动和招聘的ABM情景；摘要所述情景结果属于2022作者工作论文，不回写为2023正式版已核结果，更不作为真实政策干预因果效应。PubMed203仅cookie挑战页，未取得摘要。

M183列**application候选/abstract_read/unclear**，无阅读卡、无新增方法验证单元。已取得作者PDF不等已经阅读；正式版本差异、参数/资料角色及反事实解释尚待正文核查。

## 发表生态与接续

Social Science Research新增为正式传统ABM发表单例，范围的既有出版者说明可追溯，作者指南等仍未核准，不加入31条件投稿表。41指定入口现均有地图对应；这只解决映射与显式状态，不能称41入口检索/政策核验全部完成。当前仍有5入口的主表关联记录缺日期已确认的正式样本；TiiS相邻先例等需按原范围解释。

当前240记录/76纳入/155候选/7前沿/2排除，89卡/260单元；61载体=40期刊/20会议入口/1仓库，31条件项/14日期保持；正式来源53期刊记录/33来源刊+23会议不变。八项分组操作后1915，不是新增1915条检索式。

下一项FO：精读已取得的M183作者工作论文，重点核经验初始化/参数、模型内反事实、现实参照及版本差异，决定其方法贡献与纳入状态；不重复索取已取得PDF，不额外执行模型。整体目标保持进行中。
