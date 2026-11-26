"""One-time companion tables and coverage audit for batch J."""
import csv,pathlib
R=pathlib.Path(__file__).resolve().parents[3]
def read(p):return list(csv.DictReader(p.open(encoding='utf-8-sig',newline='')))
def write(p,rows):
 with p.open('w',encoding='utf8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
def save(p,s):p.write_text(s+'\n',encoding='utf8')
vs=read(R/'data/method_venue_map.csv');assert 'CMOT' not in {x['venue_id'] for x in vs},'Already applied'
def venue(vid,name,scope,guide,ids,precedent,judgment,notes,typ='journal'):
 v={k:'' for k in vs[0]};v.update(venue_id=vid,venue=name,disciplinary_home='modeling and simulation' if typ=='journal' else 'agents/computational social science',scope_url=scope,author_guidelines_url=guide,record_ids=ids,precedents_2022_onward=precedent,method_publication_type='traditional_ABM_and_LLM_modeling_process' if typ=='journal' else 'LLM_social_simulation',continuity_evidence='multiple_years_ABM_sample' if vid=='CMOT' else 'single_year_sample_not_continuity_proof',current_paper_judgment='conditional_watchlist',future_method_paper_judgment=judgment,current_paper_gap='需对该共同体提出明确社会过程/模拟方法问题；当前不提升为优先刊',future_method_paper_gap='可迁移方法增量、评价独立性、替代方案与复现证据',oa_fees='pending',index_status='current_MJL_not_independently_checked',venue_type=typ,verified_date='2026-11-26',verification_status='scope_and_sample_checked' if vid in ['SIMULATION','CMOT','AAMAS'] else 'formal_relation_checked_scope_and_fulltext_pending',evidence_note=notes,required_writing_changes='分清建模辅助、主体行为控制和社会效度',required_existing_analyses='运行单位/不确定性、测量层级与协议忠实性',required_new_experiments='依目标主张设计跨情境/独立评价；本库未实施',recommendation_grade='conditional_watchlist',pending_items='whole_venue_search;precise_submission_requirements;fees;indexing',requirements_authority='Recommendations are review inferences; only cited official fields are editorial requirements',master_venue_ids='V-'+vid,venue_id_namespace='methods_map; master aliases explicit; round1 journal IDs preserved');return v
v=venue('SIMULATION','SIMULATION: Transactions of the Society for Modeling and Simulation International','https://scs.org/publications/','https://journals.sagepub.com/author-instructions/sim','M019','M019,2024-04-14,10.1177/00375497241239360; narrative-to-simulation-code;abstractonly','methods_conditional','SCSscope inspected: generalM&S relevance/effectiveness;sample is modeling assistance, not demonstrated LLMsociety community')
v.update(article_types_and_length='Research papers; methodology/application/reviews/tutorials; exact length pending',code_data_requirements='Specific code/data submission policy not yet checked');vs.append(v)
v=venue('CMOT','Computational and Mathematical Organization Theory','https://link.springer.com/journal/10588/aims-and-scope','https://link.springer.com/journal/10588/submission-guidelines','M017;M018','M017,2022-01-11,sensitivity protocol; M018,2023-07-24,organization ABM review (issue2024)','methods_conditional','TraditionalABM methods evidence across2022/2023; no directLLM socialsimulation precedent verified in this batch')
v.update(article_types_and_length='Abstract100–150words;4–6keywords;SNAPPdoubleanonymous;guidelines being revised',code_data_requirements='Scope encourages code sharing but explicitly does not require it; describe access/runtime/language and processes; broader data-policy section pending');vs.append(v)
v=venue('AAMAS','International Conference on Autonomous Agents and Multiagent Systems','https://cyprusconferences.org/aamas2026/call-for-papers-main-track/','https://cyprusconferences.org/aamas2026/submission-instructions/','M020','M020,2026 Research Paper Track1518–1526,10.65109/VAVC8140; FODD995–1003 queued not coded','methods_conditional','Officialcall listsSIM/GAAI; officialTOC+formalPDF distinguishResearchPaperTrack fromextendedabstract/workshop;precisefirstonlinedatepending','conference');v.update(index_status='not_applicable_journal_MJL',article_types_and_length='M020 actual9p published paper; submission limits not inferred',code_data_requirements='M020 links code; conferencewide mandate pending');vs.append(v)
v=venue('ICWSM','International AAAI Conference on Web and Social Media','https://www.icwsm.org/2026/program.html','','M021','M021 formal2026proceedings relation via institutionalrecord; exactdate/DOI/fulltextpending','methods_conditional','Officialindexedprogram identifies Short; live dynamicbody incomplete; institutionalPDF403;scope/CFP not independentlyread;mainpaper notworkshop','conference');v.update(index_status='not_applicable_journal_MJL',article_types_and_length='ProgramShort label indexed; exact paper type/length pending PDF',code_data_requirements='pending');vs.append(v)
write(R/'data/method_venue_map.csv',vs)
cs=read(R/'data/journal_submission_candidates.csv');cs.extend(v for v in vs if v['venue_id'] in ['SIMULATION','CMOT']);write(R/'data/journal_submission_candidates.csv',cs)
ms=read(R/'data/method_validation_matrix.csv')
units=[('VC19','M017','数值与程序因素共同进入敏感性设计','GarbageCan参数/类别程序全因子','只变单参数漏掉结构交互','模拟内因素重要性/交互','11,664情景；传统ABM示例','single_model_numerical_method_comparison','LLM有效性、现实组织外部效度','预先说明可变构件及遗漏的交互；不改写冻结主矩阵','§§3–6'),('VC20','M017','按目标选择输出分布与分析方法','重要性/方向/交互/稳健性分开','一个均值稳健被泛化为全部输出有效','敏感性目标与方法对应','随机输出与S-ICE方法；本文未独立复算','method_protocol_and_worked_comparison','通用最优设计或因果机制唯一','意见/表达/接触各自的测量目标与不确定性分开','§§4–5;7.1'),('VC21','M020','规则/权重/组件控制','两场景三主体十轮五问题各五run','可控对话被误当人类行为预测','对话控制与代理指标','正式ResearchPaperTrack受控比较','small_dialogue_controlled_comparison','真人网络轨迹或跨社会总体效度','用独立效标审查操纵与意见测量；不采用论文动态权重作默认','§§3.3–4.4;Tables1–6'),('VC22','M020','测量及judge身份核查','persona嵌入相似与独立立场效标','persona相似被当私人意见；judge独立性表述冲突','测量构念与评价独立性','§4.1用Llama3judge且Table2有Llama3主体；§4.3称judge不参与框架','source_internal_reporting_ambiguity_not_resolved','judge实际实现已独立；stance等于私人意见','先查精确模型/配置和代码，做人工或独立指标验证','§3.3;§4.1;Table2;§4.3')]
for row in units:
 x=dict(zip(list(ms[0])[:11],row));x.update(evidence_status='source_read_not_reexecuted',checked_date='2026-11-26');ms.append(x)
write(R/'data/method_validation_matrix.csv',ms)
# Taskbook inventory, not claims of a complete search. Related venues do not stand in for named ones.
groups=[('4.1','JASSS|Journal of Simulation|Simulation Modelling Practice and Theory|SIMULATION|Social Science Computer Review|Computational and Mathematical Organization Theory|Journal of Economic Interaction and Coordination'),('4.2','Computational Communication Research|EPJ Data Science|Humanities and Social Sciences Communications|Information Processing & Management|Social Networks|Social Science Research|Political Analysis|Political Communication|Journal of Communication|PLOS ONE|Scientific Reports|Nature Communications'),('4.3','Artificial Intelligence Review|AI|ACM Transactions on Social Computing|ACM Transactions on Intelligent Systems and Technology|ACM Transactions on Interactive Intelligent Systems|Transactions of the Association for Computational Linguistics|Information Sciences|Expert Systems with Applications|IEEE Transactions on Computational Social Systems'),('4.4','AAMAS|ICWSM|ACL|EMNLP|NAACL|NeurIPS|ICML|ICLR|CHI|CSCW|Web Conference (WWW)|Social Simulation Conference / ESSA|Computational Social Science Society meetings')]
aliases={'JASSS':'JASSS','Journal of Simulation':'JOS','Simulation Modelling Practice and Theory':'SMPT','SIMULATION':'SIMULATION','Social Science Computer Review':'SSCR','Computational and Mathematical Organization Theory':'CMOT','Computational Communication Research':'CCR','EPJ Data Science':'EPJ','Humanities and Social Sciences Communications':'HSSCOMM','Information Processing & Management':'IPM','Artificial Intelligence Review':'AIR','AI':'AI','AAMAS':'AAMAS','ICWSM':'ICWSM','ICML':'ICML-POS','NAACL':'NAACL-F'}
by={x['venue_id']:x for x in vs};coverage=[]
for group,names in groups:
 for name in names.split('|'):
  v=by.get(aliases.get(name,''));coverage.append(dict(taskbook_section=group,requested_venue=name,map_venue_id=v['venue_id'] if v else '',audit_status='curated_map_entry_partial' if v else 'not_yet_reconciled_no_negative_claim',sample_record_ids=v['record_ids'] if v else '',scope_check=v['verification_status'] if v else 'pending',coverage_boundary='Map entry/sample does not certify whole-venue2022+ search' if v else 'No completed audit in this inventory; may have legacy discovery hits; do not infer zero papers',next_action='complete whole-venue source search / date / guide gaps' if v else 'search actual2022+ precedents, then verify scope and guide',checked_date='2026-11-26'))
write(R/'data/venue_coverage_audit.csv',coverage)
save(R/'reports/venue_coverage_audit.md',f'''# 任务书载体覆盖审计（批次J）

2026-11-26；按任务书§4逐项列出{len(coverage)}个入口，IPM跨章节重复只列一次。见[覆盖表](../data/venue_coverage_audit.csv)。其中“已有地图条目”也只表示定向样本；未对账不等于未发现或零发表。原先19载体地图不是任务书完整覆盖。EACL、UIST不能代替ACL、CHI/CSCW；Findings NAACL不能代替主会；ICML position不能代替主研究轨。

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

官方依据：[CMOT范围](https://link.springer.com/journal/10588/aims-and-scope)、[作者指南](https://link.springer.com/journal/10588/submission-guidelines)、[SIMULATION学会范围](https://scs.org/publications/)、[正式TOC](https://journals.sagepub.com/toc/sim/100/7)、[AAMAS正式目录](https://ifaamas.org/Proceedings/aamas2026/forms/contents.htm)、[ICWSM机构题录](https://re.public.polimi.it/handle/11311/1317866)。''')
print('venues',len(vs),'journals',len(cs),'matrix',len(ms),'coverage entries',len(coverage))
