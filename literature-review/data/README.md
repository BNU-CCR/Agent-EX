# 字段与状态（schema v1，2026-11-26）

主表一行是一个发表条目；record_id/work_id/venue_id是稳定标识，不因排序改变。R为跨学科、EN为英文新闻传播批次、CN为中文批次；前缀不是质量等级。CSV采用UTF-8、标准引号/逗号转义；空白表示尚未核实或不适用，不能按0解读。

## 文献字段

- 书目：title/authors/language/venue/document_type/doi/official_url。discovery_url与metadata_evidence_url单列，别篇参考文献或转载页不冒充论文原始入口。
- 版本：online_first_date保留可核实精度（YYYY、YYYY-MM、YYYY-MM-DD）；volume_year、preprint_date、date_basis、date_eligibility、related_versions。注册时间不替代发表时间。
- 筛选：screening_status为included（日期与全文门通过）、candidate（摘要/日期/全文待核）、frontier（合格预印本前沿）、excluded。date_eligibility为confirmed/date_pending/preprint_eligible/ineligible。仅正式年份且未核准online-first者保守降为date_pending，不计确认纳入。
- 核心程度：direct_comparison/theory_mechanism/method_validity/peripheral；候选上的层级为拟定，不能计为已确认核心。
- 阅读：metadata_only/abstract_read/fulltext_partial/fulltext_checked；fulltext_checked表示主文设计、测量、结果与限制已核查，不表示补充文件及代码逐项验证。supplement_status单列。未知字段写待核实；仅确认文章未报告时才写原文未报告。
- 独立编码：research_object与simulation_purpose分开；method_type另存。findings只写实际阅读支持信息；evidence_location保留章节/页码；relation_to_agent_ex是整理者推论。
- 来源：search_id可用分号连接多个真实查询；search_date为实际日期。批次无逐篇query映射时用实际引文/题名查询匹配，并在notes说明，不能编造搜索。
- card_path统一指向reading-cards/；source_batch指向原始整理批次，保存字段迁移与人工修订依据。

## 日志与覆盖

search_log包含发现、逐刊补查、文章核验、API元数据及访问/作者指南核验；row不是“数据库独立检索一次”的同义词。query_fields区分来源核查与公开索引。result_count未知留空，retrieved_count是实际保留条数，screened_count仅对应实际筛查；不从空白推断零命中。

期刊coverage_status：complete/ searched_zero 仅用于完整规定检索；public_supplement_only为公开补查；partial为部分；access_blocked为受阻；not_searched为仅列目录。source_verification_only用于跨学科来源期刊，仅核对文章而未遍历全刊。

index_type与index_verification分开：CSSCI_source、CSSCI_expanded不可混用。SSCI/SCIE只有官方目录或出版商具体明示才记录；Web of Science泛称或JIF不推断具体索引。index_historical未核实留空。目录高校镜像明确标NJU原件/镜像托管/直接NJU待核，不能把镜像当本次直接访问NJU。

## 派生表和迁移

core_source_journals仅统计included的期刊文献，另列候选数量；会议进conference_sources。reviews/editorials不是独立实验，work_id只做版本去重不代表因果重复单位。正式记录数与independent empirical study work数分开报告，不能把综述或预印本混为正式实证研究数。

exports/references.bib仅导出日期及全文门通过的included条目；候选与前沿仍保留于主表和工作簿。每个条目用稳定record_id作bibkey。Excel各表从同一CSV矩阵生成，不再手改。

原始英文eligible统一为confirmed；中文eligible_year_only统一date_pending；fulltext_partial不得升级为全文纳入。无DOI不补造。机制标签中尚未逐文确认的值保留待核实。本轮只是AI交叉检查，不称独立人工双人筛选。
