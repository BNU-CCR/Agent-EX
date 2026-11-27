"""Bounded taskbook audit: evidence gates and current presentation, not research certification."""
import collections,csv,hashlib,json,pathlib,re,subprocess
R=pathlib.Path(__file__).resolve().parents[1]
def read(p):
 with p.open(encoding='utf-8-sig',newline='') as f:q=csv.DictReader(f);return q.fieldnames,list(q)
def write(p,h,rows):
 with p.open('w',encoding='utf8',newline='') as f:w=csv.DictWriter(f,h);w.writeheader();w.writerows(rows)
_,rs=read(R/'data/literature_master.csv');by={x['record_id']:x for x in rs}
_,vs=read(R/'data/method_venue_map.csv');_,cs=read(R/'data/journal_submission_candidates.csv')
_,logs=read(R/'data/search_log.csv');_,coverage=read(R/'data/venue_coverage_audit.csv')
cards=[]
for x in rs:
 if x['card_path']:
  p=R/x['card_path'];t=p.read_text(encoding='utf8');cards.append(dict(record_id=x['record_id'],path=x['card_path'],numbered_sections=len(re.findall(r'^## \d+\.',t,re.M)),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
h,requirements=read(R/'data/delivery_requirements.csv');assert len(requirements)==66
evidence={};missing=[];directories={};git_evidence={}
for row in requirements:
 rid=row['requirement_id'];row['checked']='2026-11-27'
 for path in row['evidence_path'].split(';'):
  p=R/path
  if p.is_file():evidence[path]=hashlib.sha256(p.read_bytes()).hexdigest()
  elif p.is_dir():directories[path]=dict(files=sum(y.is_file() for y in p.rglob('*')),boundary='Directoryexists_inventoryonly_notcontentcertification')
  elif path=='Git branch':git_evidence=dict(branch=subprocess.check_output(['git','branch','--show-current'],cwd=R.parent,text=True).strip(),head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R.parent,text=True).strip(),boundary='BeforeBPcommit;pushreceiptseparate')
  elif path:missing.append(dict(requirement_id=rid,path=path))
 if rid=='R2-1':row.update(assessment='implemented_current_protocol',remaining_gap='完整目标未验收；持续接续不等于会话外后台运行')
 elif rid=='R2-2.1':row.update(assessment='verified_by_bounded_preservation_checks',remaining_gap='57ID/18文件hash/231日志前缀与43原字段变更账通过；非全部研究内容认证')
 elif rid=='R2-2.2':row.update(assessment='implemented_roundA_vocab_verified_semantics_partial',remaining_gap='非空词表0漂移；5空字段，原57分类语义与所有卡内容尚未全量二次复核')
 elif rid.startswith('R2-3.'):row.update(assessment='partial_public_evidence',remaining_gap='1134分组操作非独立数据库查询数；授权全量导出/筛选语料与各主题召回未认证')
 elif rid.startswith('R2-4.') and rid!='R2-4.5':row.update(assessment='partial_bounded_venue_evidence',remaining_gap='41入口0未对账/12部分不等于全目录；部分范围/指南/正式文献与持续性待核')
 elif rid=='R2-4.5':row.update(assessment='three_table_structure_verified_index_partial',remaining_gap='52载体与30条件期刊分开；独立MJL及CSSCI版本核验未齐')
 elif rid.startswith('R2-5-') and rid.removeprefix('R2-5-') in by:
  x=by[rid.removeprefix('R2-5-')];row.update(assessment='source_gates_pass_content_limits_retained' if x['screening_status']=='included' else 'author_fullread_formal_gate_pending',remaining_gap=f"{x['record_id']}: {x['reading_status']}; {x['date_eligibility']}; {x['screening_status']};卡内容/版本边界仍按源卡；独立重跑或未来框架效果试验不是本轮必执行项")
 elif rid=='R2-5-benchmarks':row.update(assessment='partial_curated_evidence',remaining_gap='143证据单元有负面结果/版本限制，非领域覆盖率或独立实验数')
 elif rid.startswith('R2-6.Q'):row.update(assessment='literature_based_answer_with_project_evidence_limits',remaining_gap='八项参照权威综合补充BO；不是项目运行/因果验证；未来实验只提需求不执行')
 elif rid in ['R2-7.1','R2-7.2']:row.update(assessment='conditional_strategy_delivered_not_manuscript_readiness',remaining_gap='当前JASSS/CCR优先比较；后续三路线有失败判据；论文实际达标/投稿不属于已完成声明')
 elif rid=='R2-7.3':row.update(assessment='linked_precedent_metadata_expanded_policy_partial',remaining_gap='49有主表关联载体补完整题名/日期/DOI/URL/类型及状态；3无主表关联保留边界；指南/索引/费用/持续性仍未齐')
 elif rid=='R2-8-cards' or rid=='1.9.2':row.update(assessment='content_audit_pending_numbered_structure37of62',remaining_gap='37卡有11编号；25无同格式编号只作复核队列，不能据此断言25卡均缺内容；首轮保护卡需附录/伴随卡而非覆盖')
 elif rid=='R2-8-export':row.update(assessment='current_schema_counts_exports_verified',remaining_gap='9表/42Bib与非空词表核验，5空分类、卡内容、全库覆盖不由导出通过证明')
 elif rid.startswith('R2-8-'):row.update(assessment='exists_bounded_content_review_not_full_acceptance',remaining_gap='文件存在及入口可核；正文更新/具体缺口见BP审计，非仅凭存在完成验收')
 elif rid.startswith('R2-9-'):row.update(assessment='executed_foundation_not_whole_goal_complete',remaining_gap='不重建第一轮、不重跑A；按当前验收缺口推进')
 elif rid.startswith('R2-10.Q'):row.update(assessment='substantive_answer_available_current_consolidation_pending',remaining_gap='九问题分散在方法/定位/生态/双轨及专题；需统一现行版本和对应证据，不以新论文数量代替')
 elif rid=='R2-11':row.update(assessment='identity_date_vocab_preservation_gates_verified_semantics_partial',remaining_gap='作者/正式版分列、未来实验不充成果；全文/日期/卡内容与范围仍有明确未决')
 elif rid=='R2-12':row.update(assessment='executed_through_BO_BP_audit_in_progress',remaining_gap='BO4e01f56已推送；BP核验/提交后回填，不称目标完成')
 elif rid=='1.8':row.update(assessment='partial_version_date_reading_evidence',remaining_gap='42纳入门通过；29日期未决、作者/正式版本及独立双筛未齐，不强升')
 elif rid.startswith('1.'):row.update(assessment='historical_and_public_evidence_partial',remaining_gap='首轮原成果保留；授权检索/完整索引目录/双筛与覆盖缺口仍未认证，公开补查不冒充全量')
write(R/'data/delivery_requirements.csv',h,requirements)
result=dict(checked_date='2026-11-27',head_before_BP='4e01f56',requirements=len(requirements),requirement_assessments=requirements,counts=dict(records=len(rs),cards=len(cards),included=sum(x['screening_status']=='included' for x in rs),candidate=sum(x['screening_status']=='candidate' for x in rs),date_pending=sum(x['date_eligibility']=='date_pending' for x in rs),venues=len(vs),journal_candidates=len(cs),source_operations=len(logs)),card_structure=cards,numbered11=sum(x['numbered_sections']==11 for x in cards),unreconciled=[x['requested_venue'] for x in coverage if x['audit_status'].startswith('not_yet_reconciled')],partial_venues=[x['requested_venue'] for x in coverage if x['audit_status'].startswith('partial')],venues_without_master_link=[x['venue_id'] for x in vs if not x['record_ids']],evidence_paths_missing=missing,evidence_hashes=evidence,boundary='Filehash/presence/vocabulary/countauditnotsemanticfullreview;noexternaldatabasequeryornewexperiment;newexperimentsinrecommendationsnotrequiredliteratureexecution')
result.update(directory_evidence=directories,git_evidence=git_evidence)
(R/'data/delivery_requirement_audit_BP.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(dict(requirements=66,counts=result['counts'],cards11=result['numbered11'],missing_evidence_paths=missing),ensure_ascii=False))
