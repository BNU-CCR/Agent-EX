# 跨学科LLM模拟评价：有界正式来源补查

2026-11-28，EA。面向方法验证与复现缺口，以2025–2026增量查询补充既有2022+库，不重建首轮，不把本批时窗改成整个综述时窗。四条实际查询、首条`site.aclanthology.org`误写而非`site:...`、筛选标准和边界见[协议](../batches/method_round2/ea_crossdisciplinary_validation/search_protocol.json)。错误未静默修正或称为严格域检索；选中论文均另取一手来源。

去重后的17条具体论文线索保存为[发现清单](../batches/method_round2/ea_crossdisciplinary_validation/discovery_inventory.csv)：6项新增候选，2项为既有M007/M039，9项暂缓（6项正式来源线索、3项预印本线索）。搜索返回的重复PDF/镜像和非研究新闻不计论文；清单不是全部搜索结果或领域召回率。暂缓不是全文排除，未核预印本不写正式发表。

| 新ID | 正式来源/工作 | 摘要阶段的评价对象与待核问题 |
|---|---|---|
| M174 | ICLR2026 SimBench | 人类行为模拟的统一基准；需核20数据集、评分与人口对应，不自动证明长期群体过程 |
| M175 | ACL2026 Main LiveCultureBench | 仿真城镇中的AI任务/文化规范及判别器；需核人类参照与judge独立性 |
| M176 | EMNLP2026 Main ReliMap | 人类个体/人口可靠性分层；需核指标、条件及抽样/留出 |
| M177 | KDD2026 ReplicatorBench | 研究复现助手评价；需核新资料检索、不可复制判据与过程/结果区分 |
| M178 | AACL/IJCNLP2026 Long Limits of Simulated Societies | 跨文化问卷准确与方差保留；需核训练/留出、摘要/正文一致性及替代解释 |
| M179 | EACL2026 Long Too Open for Opinion? | 开放式输出的方法观点；需区分立场、演示和实测效度收益 |

六项只读完整摘要和身份资料，成熟度/证据均unclear，不新增阅读卡或验证单元。ReplicatorBench由出版社登记Crossref与作者机构托管PDF首页互证，12页文件取得但仅读p1身份/摘要，不能称正式正文已核或版本等同。其DOI网页工具不可达，未把该失败变成未发表判断。其余五项使用官方会议页面。来源响应、hash、元数据与日期字段见[清单](../batches/method_round2/ea_crossdisciplinary_validation/acquisition_manifest.json)。

ICLR页面citation_publication_date给出2026-04-20；KDD出版社登记published-online为2026-08-08，印刷8月9日，两者分列。四项ACL页面只给月份；三项Crossref无online、仅出版年，第四项TooOpen请求429，均不以created/会期补正式在线日。因此新增4项date_pending，当前31，不把正式出版身份已知误写为精确日期已知。ACL的两种DOI格式按页面实际字段保存，没有强加`/v1/`。

新MASS线索为Memory-Augmented Social Simulation，与M001的Multi-Agent Social Simulation是不同作品；不能按缩写去重。这项仍待查，不冒充本批已读或新增候选。

发表地图新增KDD与AACL/IJCNLP两个元数据线索入口，54载体=33期刊+20会议+1仓库，30条件期刊不变；不是新推荐渠道。已有ICLR/ACL/EMNLP/EACL仅补具体正式先例，会议指南、费用、索引和持续发表程度未在本批刷新。KDD助手复现任务与ICLR人类行为基准也提示，方法评价共同体不限于社会模拟期刊，但单篇先例不能证明Agent-EX适配。

当前236条（58正式纳入、168候选、8前沿、2排除）、80卡、217验证单元；13项分组操作至1681，并非13检索式或独立实验。新增库量是补查结果，不作成熟度分数。下一项EB精读M174正式SimBench，优先核参照任务、聚合分数、人口条件与可复现边界，避免停留在题录增长。
