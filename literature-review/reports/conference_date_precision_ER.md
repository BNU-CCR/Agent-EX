# ER：恢复正式论文集出版年月的日期资格

2026-11-28，逐条重新取得七个ACL官方论文页，DOI、题名、正式载体、页码和citation_publication_date匹配，均已有正式PDF定向全文卡。依据批准任务书3.2“没有在线首发日期时，采用可核实的正式出版日期”“正式会议论文按论文集的正式发表日期判定”以及既有检索协议“官方论文集月份可以保留年月精度”，纠正此前额外施加的精确日门槛。没有扩大2022时间范围、没有猜日，也不以会期/注册created当发表日期。

|ID|正式出版月|正式载体|本次状态|
|---|---|---|---|
|M034 GA-S3|2025-07|Findings ACL|confirmed/included|
|M035 EcoLANG|2025-11|Findings EMNLP|confirmed/included|
|M175 LiveCultureBench|2026-07|ACL Main Long|confirmed/included|
|M176 ReliMap|2026-10|EMNLP Main|confirmed/included|
|M178文化方差|2026-11|IJCNLP-AACL Main Long|confirmed/included|
|M179开放式立场|2026-03|EACL Main Long；自称position|confirmed/included|
|M180德国意见|2025-07|ACL Main Long|confirmed/included|

这里确认的是按正式出版年月回退规则的时间资格，而非精确在线“日”。M178同月论文当前官方正式可获取，未将月末未来日期编入记录。既有online_first_date保留原年月字符串，date_basis明确formalpublicationfallback；未知日继续留空，不伪装精度。所有七项均已按此前全文范围判断与方法主题相关；统计/实现争议、代码访问与外部效度限制不被资格修订抹去，也不要求“没有局限”才纳入。M179仍conceptual_claim，不能因纳入升级为经验验证。

七项从candidate移入included，记录总数237不变；正式纳入60→67、候选167→160；date_pending32→25。87卡/252证据单元、54载体/30条件刊及方法等级均不变；正式纳入核心17→21、验证35→38、直接7/应用1。八前沿/两排除保持，正式Bib67与前沿Bib8分列。这不是新增七篇研究、七次验证或模型运行。

七篇卡前态按EQ提交Git原字节保存；主表字段变更经指纹补丁和历史账，会议表/发表先例/现行报告与导出同步。EQ是当时32pending/60纳入的历史审计，本批提供明确后续修正，不倒改其快照。首次在线日的可选精度缺口与真正时间资格不明分开；其余25项不自动改动，期刊/作者版本/正式身份未明须逐项核。

当前source操作1771（新增七官方页、规则核查、整合九项分组操作），不是检索式或新增论文数。下一项ES优先M012指定ODD二十年种子的正式全文/方法分类，结合已有机构在线信息核版本；受阻则转M003正式对应或优先刊政策实际缺口，不重新扩库凑数。原始运行复演不属于本轮新增验收门，授权覆盖/WoS等仍开放，目标未完成验收。
