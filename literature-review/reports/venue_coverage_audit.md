# 任务书载体覆盖审计（批次J）

2026-11-26；按任务书§4逐项列出41个入口，IPM跨章节重复只列一次。见[覆盖表](../data/venue_coverage_audit.csv)。其中“已有地图条目”也只表示定向样本；未对账不等于未发现或零发表。原先19载体地图不是任务书完整覆盖。EACL、UIST不能代替ACL、CHI/CSCW；Findings NAACL不能代替主会；ICML position不能代替主研究轨。

本批新增SIMULATION、CMOT、AAMAS、ICWSM四入口，地图23项（15刊、7会议入口、1预印本仓库），15刊投稿表仅列条件候选，不是15项推荐。新M017–M021中只有M017本批正式纳入；M018/M019未读全文，M020正式全文已读但首次在线日未核，M021正式出版关系已核但全文403、DOI与精确日期待核。

## 发表先例改变的判断

- CMOT在2022敏感性协议及2023首次在线的2024卷期综述中显示传统ABM方法脉络；本批没有确认其直接LLM社会模拟共同体。M017 DOI含2021却在2022首次发表，日期以出版社为准。
- SIMULATION官方学会范围要求一般模拟问题相关性，区分方法与应用。M019是叙事到模拟代码的LLM建模辅助先例，不能据此声称该刊持续发表LLM社会主体方法。其TOC日期2024-04-14已核；相邻论文2023-12-21不能误配。
- AAMAS官方2026call有SIM与GAAI入口，正式Research Paper Track有M020；FODD正式先例已定位995–1003但未读，不新增记录。该证据支持其是方法共同体入口，尚不足判断当前稿可投或计算接受概率。
- ICWSM官方索引节目列M021为Short，机构库确认会议出版关系；节目演讲时长不能独立证明论文类型。正式PDF403，不能把预印本当正式全文。

## 对双轨定位的影响

当前应用稿仍优先论证社会过程、测量与替代解释；本批不改变既有JASSS/CCR优先比较。独立方法稿可向一般模拟/多主体共同体组织贡献，但须展示可迁移评价或控制增量。流程透明、输出可控、对话多样与真实社会效度须逐层论证。

## 仍缺什么

任务书表中未对账载体须逐个实际检索；WoS/Scopus/CNKI仍无授权完整导出，不能用公开样本填补。新增刊索引/MJL、费用和部分指南未核。M020代码、judge具体身份/指标实现未审；M021正式全文/DOI/日期及M019全文为下一批优先。检索操作数是合并的查询/来源获取事件，不是命中论文数；行开/重试合并说明在source_operations中。

官方依据：[CMOT范围](https://link.springer.com/journal/10588/aims-and-scope)、[作者指南](https://link.springer.com/journal/10588/submission-guidelines)、[SIMULATION学会范围](https://scs.org/publications/)、[正式TOC](https://journals.sagepub.com/toc/sim/100/7)、[AAMAS正式目录](https://ifaamas.org/Proceedings/aamas2026/forms/contents.htm)、[ICWSM机构题录](https://re.public.polimi.it/handle/11311/1317866)。

批次K：补M021作者v2方法/经验评价精读及M020固定代码快照的七文件静态核查；累计78条/35卡/25验证单元。正式纳入仍27项，作者稿不升级为正式版全文。详见[校准与制品核查](calibration_and_artifact_audit.md)。

批次S见[SSR范围与检索边界](ssr_scope_and_search_boundary.md)：官方范围已补，目录/指南403，未确认先例，不是零发表。

V批确认41命名入口仍16项未对账；其余为局部证据。额外JSC/AMPPS不替代它们。见[交付审计](delivery_requirement_audit.md)。

AE将TCSS从not_yet_reconciled更新为部分对账：官方范围/格式、费用冲突、历史CFP与M032正式全文。未对账入口余15，部分对账不是2022+全刊覆盖完成。

AG补ACL/EMNLP部分对账，三正式Main/Findings题录及官方CFP/ARR指导；13入口未对账。正式全文/精确日期与完整语料仍待核，不把摘要候选当全文纳入。

AL将TACL改部分对账，复用R010与官方政策文档；12命名入口未对账，不是完整语料认证。 见[TACL政策专题](tacl_policy_and_fit.md)。

AM将ICLR改部分对账：M036正式会议全文、2027官方指南/CFP；41入口余11未对账。不是全目录或当前开放机会。

AN将NeurIPS改部分对账，余10命名入口未对账；M037仅正式摘要，ED完整CFP两次超时。

AR只补既有ICML入口与3观点案例/官方要求/正式卷日期，10未对账数不变；不把已有地图入口重复计数。

AV将CHI改部分对账；41指定入口余9未对账。正式M041摘要/日期与2027指南已核，实时DOI403、全文/完整目录/独立索引仍待核。

BJ当前对账：Information Sciences/ESWA官方shop范围与邻接先例、IPM题录线索更新为部分核查。41入口2未对账（Political Communication、Journal of Communication）、10部分，见[状态账](../data/coverage_status_summary_BJ.json)。地图49载体不等同任务书全部目录检索；[本批报告](information_systems_method_venues.md)保留403、摘要和首发日期边界。

BL完成最后两个未对账入口的有界核查；41项现0未对账/12部分，见[状态账](../data/coverage_status_summary_BL.json)。这是入口账闭合，不是2022+全目录或授权数据库完成；两新增文献只读摘要，PDF失败留账。[两刊方法边界](communication_method_venue_boundaries.md)。
