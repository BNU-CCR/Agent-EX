"""Current-state requirement audit. Presence and bounded evidence never prove full coverage."""
import csv,collections,hashlib,json,pathlib,re
R=pathlib.Path(__file__).resolve().parents[3];F=pathlib.Path(__file__).parent
def read(p):
 with p.open(encoding='utf-8-sig',newline='') as f:d=csv.DictReader(f);return d.fieldnames,list(d)
def save(p,t):p.write_text(t.rstrip()+'\n',encoding='utf8')
def write(p,h,rs):
 with p.open('w',encoding='utf8',newline='') as f:w=csv.DictWriter(f,h);w.writeheader();w.writerows(rs)
h,master=read(R/'data/literature_master.csv');by={x['record_id']:x for x in master}
# Repair incomplete presentation of already acquired precedents; no new claims/sources.
for file in ['method_venue_map.csv','journal_submission_candidates.csv']:
 h,rs=read(R/'data'/file)
 for r in rs:
  linked=[by[x] for x in r['record_ids'].split(';') if x]
  missing=[x for x in linked if not all(s in r['precedents_2022_onward'] for s in [x['title'],x['doi'] or x['official_url'],x['method_type']])]
  if missing:r['precedents_2022_onward'] += ' | V existing-master evidence: '+' || '.join(f"{x['record_id']}: {x['title']} ({x['online_first_date'] or 'firstdatepending'};issue{x['volume_year']}); DOI:{x['doi'] or 'noneverified'};URL:{x['official_url']};method:{x['method_type']};status:{x['screening_status']};version:{x['related_versions'] or 'see reading status'}" for x in missing)
  if r['venue_id']=='AMPPS':r['evidence_note']='Single formal M028 reporting-primer precedent;not2022+fulljournaloutput;targeted officialscope/guide checked;independentindex pending'
 write(R/'data'/file,h,rs)
allowed={'core_level':{'direct_comparison','theory_mechanism','method_validity','peripheral'},'research_object':{'human_social_process_simulation','ai_collective_behavior','human_ai_mixed','other'},'primary_purpose':{'theory_exploration','mechanism_test','empirical_replication','empirical_prediction','method_evaluation','system_development','other'},'simulation_purpose':{'theory_exploration','mechanism_test','empirical_replication','empirical_prediction','method_evaluation','system_development','other'}}
drift=[]
for r in master:
 for k,values in allowed.items():
  bad=[v for v in r[k].split(';') if v and v not in values]
  if bad:drift.append(dict(record_id=r['record_id'],field=k,value=r[k],outside_dictionary=bad))
cards=[]
for r in master:
 if r['card_path']:
  p=R/r['card_path'];t=p.read_text(encoding='utf8');cards.append(dict(record_id=r['record_id'],path=r['card_path'],chars=len(t),numbered_section_count=len(re.findall(r'^##\s+\d+[.、．]',t,re.M)),boundary='Structure indicator only;not proof of semantic completeness/fulltext coverage'))
spec=(R/'METHODS_FIRST_REORIENTATION.md').read_text(encoding='utf8');_,logs=read(R/'data/search_log.csv')
terms=[]
for sec in range(1,6):
 chunk=spec.split(f'### 3.{sec} ',1)[1].split('### ',1)[0]
 for term in re.findall(r'`([^`]+)`',chunk):
  found=[x['search_id'] for x in logs if term.lower() in x['query_exact'].lower()]
  terms.append(dict(section=f'3.{sec}',term=term,literal_query_log_ids=found,status='literal_query_text_present' if found else 'no_literal_query_text_match',boundary='Not recall estimate,not database execution certification;variants may exist'))
_,coverage=read(R/'data/venue_coverage_audit.csv');_,venues=read(R/'data/method_venue_map.csv');_,journals=read(R/'data/journal_submission_candidates.csv')
seedids=['M001','R015','M002','M003','R008','R006','R001','R002','R004','R013','R020']
evidence=dict(checked='2026-11-26',head_before_audit='3419ee7',master_sha256=hashlib.sha256((R/'data/literature_master.csv').read_bytes()).hexdigest(),records=len(master),schema_nonempty_outside_dictionary=drift,blank_categorical_fields=[dict(record_id=x['record_id'],fields=[k for k in allowed if not x[k]]) for x in master if any(not x[k] for k in allowed)],cards=cards,keyword_literal_audit=terms,coverage_status_counts=dict(collections.Counter(x['audit_status'] for x in coverage)),venues_without_master_link=[x['venue_id'] for x in venues if not x['record_ids']],venue_count=len(venues),journal_candidates=len(journals),seeds=[{k:by[r][k] for k in ['record_id','title','date_eligibility','screening_status','reading_status','card_path','method_pending_fields']} for r in seedids if r in by],completion='not_proven;known incomplete requirements remain',limits='No fresh paper retrieval,experiment rerun,claim of exhaustive search or independent human screening')
save(R/'data/delivery_requirement_audit.json',json.dumps(evidence,ensure_ascii=False,indent=2))
rows=[]
def add(i,req,artifact,status,gap):rows.append(dict(requirement_id=i,requirement=req,evidence_path=artifact,assessment=status,remaining_gap=gap,checked='2026-11-26'))
add('R2-1','北极星/持续接续','GOAL.md;progress.md','implemented_current_protocol','目标未完成，保持active')
add('R2-2.1','保留首轮57ID/15卡/原导出/日志','data/round1_preservation_manifest.json;reports/methods_validation.json','verified_by_bounded_preservation_checks','不证明全部研究编码或检索完整')
add('R2-2.2','扩展字段/规则/57条重分类','protocol/method_coding_rules.md;reports/method_reclassification.md','implemented_roundA;maintenance_gap','后续新记录旧分类字段存在字典漂移；见JSON逐项')
for sec,name in [(1,'方法范式'),(2,'主体架构'),(3,'校准验证'),(4,'报告复现'),(5,'理论转译'),(6,'跨学科应用')]:
 add(f'R2-3.{sec}',name+'主题组检索','data/search_log.csv;data/delivery_requirement_audit.json;reports/method_landscape.md','partial_public_evidence','未取得授权数据库完整导出；字面词匹配不是覆盖率，应用领域不均衡')
for sec,name in [(1,'模拟/ABM刊'),(2,'跨学科社会刊'),(3,'AI信息刊'),(4,'会议轨道')]:
 add(f'R2-4.{sec}',name+'实际先例/范围/指南','data/venue_coverage_audit.csv;data/method_venue_map.csv','partial','41入口仍有未核项；地图非逐刊全集；部分正式版本/指南待核')
add('R2-4.5','三表分开/索引不反推','data/method_venue_map.csv;data/journal_submission_candidates.csv;data/journals_master.csv','structure_verified_index_partial','current/historicalMJL及CSSCI仍未全量独立核实')
for r in ['M001','R015','M002','M003','R008']:
 x=by[r];add('R2-5-'+r,'指定方法种子身份/全文/日期',x['card_path'] or 'data/literature_master.csv','partial' if x['screening_status']!='included' or x['method_pending_fields'] else 'supported_in_current_sample',x['method_pending_fields'] or '补充制品与再运行未审；具体边界见卡')
add('R2-5-benchmarks','2022+评价/批评/综述','reports/method_validation_matrix.md;reading-cards/','partial_curated_evidence','47证据单元不证明领域覆盖')
add('R2-5-legacy','Betz/Chuang/Cau/Brockers/Piao/Ashery保留','data/literature_master.csv;reports/method_reclassification.md','stable_IDs_preserved','逐项版本、日期及负面结果边界仍按主表')
for i,name in enumerate(['规范实施','研究者选择','可迁移设计','应用/评估/创新','独立方法新增证据'],1):add(f'R2-6.Q{i}',name,'reports/agent_ex_method_positioning.md;reports/claim_evidence_readiness.md','answered_as_literature_based_inference','不是项目运行复核；不能借他文证明项目有效')
for i,name in [(1,'当前应用稿'),(2,'后续方法稿')]:add(f'R2-7.{i}',name+'双轨定位','reports/two_track_submission_strategy.md;data/journal_submission_candidates.csv','supported_conditional_strategy','未实际投稿、未证明已具全部研究证据；指南缺口仍列pending')
add('R2-7.3','逐刊完整投稿证据字段','data/journal_submission_candidates.csv','presentation_repaired_policy_partial','V已从既有主表补题名/日期/DOI/URL/方法；SMPT未关联主记录，索引/费用/指南仍不齐')
for name in ['GOAL.md','METHODS_FIRST_REORIENTATION.md','data/method_venue_map.csv','data/journal_submission_candidates.csv','reports/method_reclassification.md','reports/method_landscape.md','reports/agent_ex_method_positioning.md','reports/method_venue_landscape.md','reports/two_track_submission_strategy.md','progress.md','README.md']:
 add('R2-8-'+name,'命名交付文件内容/存在',name,'exists_with_bounded_content_review' if (R/name).is_file() else 'missing','存在不等于全项内容验收，关联主题/版本缺口见本表')
add('R2-8-cards','核心新卡沿用ID与11项结构','reading-cards/;data/delivery_requirement_audit.json','partial','部分新卡为定向简卡，未按原任务书11项结构展开；不能以卡数代替完整卡验收')
add('R2-8-export','schema字典/Excel/Bib同步','data/README.md;exports/literature_and_journals_methods.xlsx;exports/references_methods.bib','counts_verified_schema_gap','9表32Bib；旧分类枚举漂移待修；原导出冻结')
for stage in 'ABCDE':add('R2-9-'+stage,'已批准批次'+stage,'progress.md','executed_not_goal_completion','后续缺口仍须按范围补齐，不重跑A')
for i,path in enumerate(['reports/method_landscape.md','reports/method_landscape.md','reports/method_validation_matrix.md','reports/method_venue_landscape.md','reports/method_landscape.md','reports/agent_ex_method_positioning.md','reports/two_track_submission_strategy.md','reports/two_track_submission_strategy.md','reports/coverage_and_gaps.md'],1):add(f'R2-10.Q{i}','最终问题'+str(i),path,'draft_answer_available_not_final_coverage','需结合当前缺口/本审计；未最终验收')
add('R2-11','证据/版本/2022下限/不冒充标准','protocol/search_strategy.md;data/literature_master.csv;reading-cards/','gates_verified_semantics_partial','方法枚举检查不覆盖全部旧字段；卡结构/部分版本未决')
add('R2-12','实际工作/落盘/推送/接续','progress.md;Git branch','executed_through_U','本批V提交后回填，保持目标未完成')
for i,name,path,gap in [('1.5.1','英文SSCI Communication完整目录','data/journals_master.csv','目录与WoS授权导出未齐'),('1.5.1-CN','中文CSSCI来源版/扩展区分','data/journals_master.csv;reports/coverage_and_gaps.md','镜像来源版与CNKI全量检索分开，扩展不外推'),('1.6','真实查询/日志/三路径','data/search_log.csv;protocol/search_strategy.md','公开来源操作不等于数据库独立检索'),('1.7','试检索与校准后继续','reports/pilot_report.md;progress.md','第一轮历史已保留，不以种子找回声称召回率'),('1.8','两轮筛选/版本/阅读状态','data/literature_master.csv','21日期未决，作者稿与正式版差异仍待核'),('1.9.2','11项完整阅读卡','reading-cards/','新简卡须补结构与证据位置；无证据写未审/不适用'),('1.10','三类第一轮期刊表/档案/会议','data/journals_master.csv;data/core_source_journals.csv;data/submission_candidates.csv;journal-profiles/','第一轮冻结快照与方法表分开；不是最新全量成果'),('1.11','组织与最终交付','README.md;reports/coverage_and_gaps.md','核心成果存在；完整验收未通过')]:add(i,name,path,'partial_or_historical_verified',gap)
write(R/'data/delivery_requirements.csv',list(rows[0]),rows)
save(F/'results.json',json.dumps(dict(batch_id='V-requirement-coverage-audit',date='2026-11-26',expected_master_sha256=hashlib.sha256((R/'data/literature_master.csv').read_bytes()).hexdigest(),updates=[],new_records=[]),ensure_ascii=False,indent=2))
save(F/'source_operations.json','[]')
print(json.dumps(dict(requirements=len(rows),schema_drift_fields=len(drift),schema_drift_records=len(set(x['record_id'] for x in drift)),cards=len(cards),numbered11_indicator=sum(x['numbered_section_count']==11 for x in cards),keyword_terms=len(terms),literal_matches=sum(bool(x['literal_query_log_ids']) for x in terms),coverage=dict(collections.Counter(x['audit_status'] for x in coverage))),ensure_ascii=False))
