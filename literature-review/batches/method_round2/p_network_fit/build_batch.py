"""Focused fulltext upgrade; retain unresolved first-online date."""
import pathlib,csv,hashlib,json
R=pathlib.Path(__file__).resolve().parents[3];F=pathlib.Path(__file__).parent
def save(p,s):p.write_text(s+'\n',encoding='utf8')
assert not (F/'results.json').exists()
u='https://federico-bianchi.github.io/publications/23_sn_abm.pdf'
p=dict(record_id='M025',reading_status='fulltext_checked',card_path='reading-cards/M025.md',supplement_status='mainAppendixA_checked;externalSupplementB_and_code_notchecked',findings='同一Lazega横截面网络用于逐步建模与参数搜索；中央95%模拟区间定义适配，非独立留出验证。',evidence_location='§§3.3–3.7;§4;AppendixA Algorithm3',relation_to_agent_ex='多个宏观指标吻合不唯一识别微观机制；区分校准/选择与独立验证，并报告拟合停止规则。',notes='P:focusedauthorhostedpublisherlayoutPDFmethods/results/discussion/AppendixA read;formalfirstdaystillpending;nocodererun or externalSupplementB. Olddataset is not separatelyincludedpre2022work.',method_maturity='empirical_method_test',method_evidence_level='empirical_validation',method_coding_status='fulltext_supported',method_transferability='经验宏观分布/替代规则比较可借鉴；同网络目标指导搜索，未证明留出动态预测或机制唯一；不把动态重连引入Agent-EX主矩阵。',method_pending_fields='precise_first_online_date;externalSupplementB;code_reexecution;independent_longitudinal_validation;scope_and_guide',method_evidence_location='§3.3metrics;§3.6search/stopping;§3.7fit;§4limitations;AppendixA',method_coding_source='reading-cards/M025.md',method_last_checked='2026-11-26')
save(R/'reading-cards/M025.md',f'''# M025 — 网络宏观拟合与替代生成路径

2026-11-26核查。实际定向读作者托管正式版式PDF的§3方法/结果、§4讨论、AppendixA搜索策略；未审外部SupplementB与代码。来源：{u}。Social Networks76(2024)150–159，DOI10.1016/j.socnet.2023.09.001；精确首次在线日仍pending，保留candidate。

模型从局部信息、地位偏好与过载规则生成咨询网络；逐步增加假设、细化参数区间，使同一经验网络的宏观指标进入模拟分布中央95%区间。经验资料既指导选择又用于评估，未核出独立留出验证；停止于目标密度也应算拟合条件。

作者明确只检验横截面网络，纵向资料仍缺。因此编码application / empirical_method_test / empirical_validation，仅指实际经验比较；不称动态预测、机制唯一或validated_workflow。多项结构吻合不单独识别行为机制。

对Agent-EX的推论：区分理论约束、参数选择、停止规则、目标指标与独立检验。不同指标若定义/实现有歧义应单列；不能按意见结果调参数。他文动态重连与过载阈值不进入本项目冻结主矩阵。未复跑。''')
save(F/'results.json',json.dumps(dict(batch_id='P-network-fit-validation',date='2026-11-26',expected_master_sha256=hashlib.sha256((R/'data/literature_master.csv').read_bytes()).hexdigest(),updates=[p],new_records=[]),ensure_ascii=False,indent=2))
save(F/'source_operations.json',json.dumps([dict(search_id='S-M2-P-FULL',platform='author_hosted_publisher_layout_PDF',search_date='2026-11-26',query_exact=u,source_url=u,status='focused_fulltext_methods_checked',notes='§3methods/results;§4;AppendixA;find/lineopensconsolidated;notexternalSupplementB/codererun;datepending')],ensure_ascii=False,indent=2))
