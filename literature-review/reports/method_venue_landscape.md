# 方法研究发表生态：定向证据版

检索与核验截至2026-11-27。已建立[37载体地图](../data/method_venue_map.csv)及[25刊双轨表](../data/journal_submission_candidates.csv)：26期刊、10会议入口、1预印本仓库。它们是论文驱动的样本地图；不是完成各刊2022起全量检索、索引认证或接受率比较。

## 已出现的共同体与贡献类型

1. **社会模拟与反馈建模。** JASSS已有R006自然语言主体、R003影响实验，并有2023定性建模方法、2026 THEMP理论—经验框架。它是本样本中最明确的持续社会模拟方法共同体。System Dynamics Review的R008教程说明GABM可进入反馈建模讨论；目前只一篇直接种子，不认定该刊持续LLM专门栏目。
2. **仿真方法与模型质量。** Journal of Simulation的2023代码分享综述、2025过程挖掘评估，SMPT的2023框架性能基准，显示贡献可围绕报告、评估与可复用比较。Ecological Modelling的ODD复现及Environmental Modelling & Software的理论/隐含假设论文，属于成熟ABM方法传统的延伸；其领域门槛不能由一篇LLM文献消除。
3. **跨学科AI方法与批评。** HSSComm有2024 Gao综述和2026 Haase框架；Frontiers有2025应用与2026效度批评。AIR的R015是验证综述；AI的M001是协议框架。跨年份样本提示方法讨论扩展，但AIR/AI各一篇直接种子不能证明持续专门共同体。Frontiers2025先例的Correction涉及引用遗漏，不称研究结论撤销。
4. **经验计算社会科学与传播。** EPJDS的M006是直接操作效度先例；CCR的2023–2026模型、方法批评与复现讨论支持传播方法路线。SSCR目前只以EN13传统ABM应用作对照，scope未取得，保持观察名单。
5. **会议与前沿。** NAACL/EACL提供网络意见与经验拟真比较，UIST提供认知架构/可信行为展示。正式会议不混入期刊统计；CogSci版本关系仍待核。arXiv的EASE、ODD+LLM等提供前沿方法提议，不能当已正式采纳的规范。

## 官网核查改变了哪些投稿判断

- [JASSS正文](https://www.jasss.org/v02/page_content_includes/_include_submit.html)建议5000–8000词、ODD和代码共享；足够复现信息与代码公开的措辞强度不同，不能一概写成强制开源。
- [HSSComm范围](https://www.nature.com/palcomms/journal-information/aims-and-scope)要求实质HSS贡献；[Frontiers范围](https://www.frontiersin.org/journals/artificial-intelligence/about)要求AI理解/开发/应用增量。两条门槛不可互换。
- [EPJDS范围](https://link.springer.com/journal/13688/aims-and-scope)要求社会系统新洞见，单纯描述模拟轨迹不足；官方指南要求数据可用性说明。
- [AI费用](https://www.mdpi.com/journal/ai/apc)当日为CHF1800另计适用税，发现摘要库旧费率不可直接沿用。JOS官网自列SCIE，AI自列ESCI，不把两者写成SSCI。
- [SSCR官方PDF](https://www.sagepub.com/docs/default-source/msg/submission-guidelines_-social-science-computer-review_-sage-journals.pdf)虽可读，摘要元信息与正文匿名审稿表述冲突；实时scope仍受阻。CCR可读作者PDF标2023版，当前门户细则仍需临投前复核。

详细范围、字数、资料要求、费用与未核项逐刊见CSV及b_odd/b_paradigm/b_validation的venue_notes。当前所有MJL索引独立核验均未完成；出版社自列与Clarivate目录确认分开。

## 尚未完成的生态工作

优先补全文：THEMP、CRISP-DM过程评估、Gao综述及EASE。优先补覆盖：逐刊2022+题名/摘要导出、不同年份先例的实际方法类型、LLM核心与传统ABM背景的比例。需要授权WoS/Scopus/CNKI导出才能进一步报告可重复覆盖与漏检；当前空缺不等于零发表。

本批新增ICML2026 Position Track正式先例M014（PMLR306），已读正式PDF；首次在线日期仍待核，不计入正式纳入数量。它证明验证议程进入机器学习正式观点论文渠道，不证明基准已建成、会议已采纳其建议或有持续年度专栏。

批次J补充：新增M017–M021、2张正式来源方法阅读卡和4个验证单元；完整覆盖状态见[载体覆盖审计](venue_coverage_audit.md)。78条/34卡/22单元/23载体均为当前累计量。M020首次在线日及M021正式全文仍待核；不能把新增载体当完整覆盖。

批次L：JEIC以M023传统经验ABM先例进入条件观察；TSC作者接收声明不计正式发表共同体证据，TIST/TiiS范围仍403。详见[共同体边界补查](community_boundary_updates.md)。

批次N补SIGDIAL正式组件验证先例，scope/指南尚待核，不作当前稿优先渠道，也不代替ACL/TIST覆盖。

批次O补PA与SOCNET地图；17刊条件投稿表只加入PA，SOCNET范围403暂不推荐；SSR仍待有界检索。详见[社会方法共同体](social_methods_community.md)。

批次Q补PLOS ONE、Scientific Reports、Nature Communications，均有正式先例和官方范围；持续性证据仅到表中标注的样本层级，详见[补查](general_journal_precedents.md)。

U补[JSC/AMPPS官方范围](evaluation_venue_updates.md)：JSC为交叉计算社会入口，AMPPS需跨心理学方法实践价值；单先例不推为持续专门共同体。

批次AB新增两刊官方核查见[社会心理与复杂性渠道](social_psychology_complexity_venues.md)。M029/M030各一先例，不能认定持续专门共同体；两者不与Frontiers in Artificial Intelligence混同。41入口未对账16项不因额外新刊自动减少。

AE补TCSS一正式平台论文与历史生成式社会智能CFP，见[tcss_method_ecology.md](tcss_method_ecology.md)。41入口15未对账；历史CFP不作开放机会，费用冲突未抹平。

AG新增ACL/EMNLP入口，三正式Main/Findings题录/摘要与2026CFP/ARR清单有界核查；不是全刊/全年完整清单。41入口13未对账，详见[专题](acl_emnlp_method_ecology.md)。
