# 方法导向扩展：字段字典与编码规则 v2

2026-11-26；依据已批准GOAL与METHODS_FIRST_REORIENTATION。扩展首轮主表，原字段及其语义不变。四层是检索/分析视角；method_relevance_tier是每条记录的首要功能，不是质量评分，也不替代screening_status。

## 新增字段

| 字段 | 值/解释 |
|---|---|
| method_relevance_tier | core_method：主要贡献是模拟范式、框架或通用建模方法；method_validation：主要贡献是校准、效度、测量或复现评估；application：用仿真解释某领域过程；direct_comparator：主要是Agent-EX意见/互动直接比较；peripheral：不属于模拟方法核心或当前证据不支持直接关联 |
| method_contribution_type | 分号多标签：simulation_paradigm/agent_architecture/environment_design/interaction_protocol/memory_and_persona/model_calibration/validation_and_external_validity/measurement/reproducibility_and_reporting/theory_to_model_translation/emergence_analysis/application/other |
| method_maturity | conceptual_framework/prototype/empirical_method_test/validated_workflow/review_or_critique/unclear。不是质量等级；validated_workflow需有明确完整工作流和经验验证，不能由工程复杂度判断 |
| disciplinary_home | 依据论文研究问题、用途、比较对象及作者自我定位，写实际共同体；不直接复制期刊跨学科标签 |
| method_transferability | 可复用的对象、依据与边界；代码存在不等于通用有效，未核则pending |
| method_evidence_level | conceptual_claim/worked_example/controlled_comparison/empirical_validation/multi_context_validation/unclear。只评价该论文所提方法的证据，不给综述汇集的别人证据算自己的验证 |
| method_relevance_rationale | 为什么这一层级；指出真实范围、边界与定位 |
| method_coding_status | fulltext_supported/abstract_provisional/metadata_pending/partial_provisional/excluded_context |
| method_pending_fields | 明列尚待核查的扩展字段，尤其成熟度、验证及可迁移性 |
| method_evidence_location | 本次实际阅读可定位章节/页码或Abstract；元数据行不虚构内容 |
| method_coding_source | 已有卡/主表、或本轮新来源的路径；与原始检索日志分别记录 |
| method_last_checked | 本轮编码日期，ISO日期 |

## 分层决策

1. 先判断文章的主要问题与贡献；方法作为工具且无通用方法命题的应用研究，不因含LLM就进core_method。
2. 跨应用可复用的架构、范式或协议，可进core_method；主要检验/批评方法效度、测量或复现的，进method_validation。
3. 意见/网络/社会影响应用与Agent-EX紧密者归direct_comparator；可另以method_contribution_type保留其方法增量，不让直接比较层继续支配总检索。
4. 第一轮included/candidate/frontier/excluded保持；excluded仍可保存分类语境，但不进入方法核心确认数。2021条目不重新展开研究。
5. 先分类功能，再评成熟度/证据。综述和概念稿不因综述覆盖数或模型架构图而升级为经验验证。

## pending与验证门

未全文者即使摘要明确研究方向，也只作暂定功能/标签编码：method_coding_status标provisional；method_maturity和method_evidence_level统一unclear，pending_fields明确待全文。不从题名补方法标签；metadata_only行留other或少量已有引文明确支持的应用标签，成熟度/验证不推断。日期待核与内容分类是独立门。

empirical_validation须有对外部人类行为/经验数据的实际比较，且说明比较层级；仅“符合理论预期”“看起来像人”“重复生成稳定”不够。multi_context_validation须核准跨任务/人群/环境及其外部标准，多个模型或议题的内部稳定不自动满足。controlled_comparison可以是合成环境内消融，不等于人类效度。worked_example为教程/原型实例。

## 迁移与审计

批次A针对既有57条逐条编码，保存method_coding_round2.json；主表仅追加字段。使用原Git基线d88ba3c的表头、行顺序、所有旧字段值、ID、DOI、筛选状态与15卡哈希逐项比较。第一轮231条日志、原期刊总表、原工作簿/BibTeX保留，第二轮导出使用methods后缀。

摘要候选后续全文核查会改变方法字段；若改变原screening_status/日期，须在change_log中记录原值、新值、原始来源与理由，不能静默升级。方法确认统计须同时满足included、fulltext_checked、合格日期、fulltext_supported；候选/日期待核/前沿分列。
