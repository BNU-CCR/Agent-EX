"""Append method coding to the existing master without rebuilding round-one rows."""
import collections,csv,hashlib,json,pathlib,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
BASE='d88ba3c'
FIELDS=['method_relevance_tier','method_contribution_type','method_maturity','disciplinary_home','method_transferability','method_evidence_level','method_relevance_rationale','method_coding_status','method_pending_fields','method_evidence_location','method_coding_source','method_last_checked']
TIERS={'core_method','method_validation','application','direct_comparator','peripheral'}
MATURITY={'conceptual_framework','prototype','empirical_method_test','validated_workflow','review_or_critique','unclear'}
EVIDENCE={'conceptual_claim','worked_example','controlled_comparison','empirical_validation','multi_context_validation','unclear'}
TAGS={'simulation_paradigm','agent_architecture','environment_design','interaction_protocol','memory_and_persona','model_calibration','validation_and_external_validity','measurement','reproducibility_and_reporting','theory_to_model_translation','emergence_analysis','application','other'}
def read_csv(path):
 with path.open(encoding='utf-8-sig',newline='') as f:
  reader=csv.DictReader(f);return reader.fieldnames,list(reader)
def write_csv(path,fields,rows):
 with path.open('w',encoding='utf8',newline='') as f:
  w=csv.DictWriter(f,fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
def baseline():
 raw=subprocess.check_output(['git','show',BASE+':literature-review/data/literature_master.csv'],cwd=ROOT.parent)
 import io
 reader=csv.DictReader(io.StringIO(raw.decode('utf8')));rows=list(reader)
 files=['exports/literature_and_journals.xlsx','exports/references.bib','data/journals_master.csv']+[f'reading-cards/{r["record_id"]}.md' for r in rows if r['card_path']]
 manifest=dict(base_commit=BASE,master_git_blob_sha256=hashlib.sha256(raw).hexdigest(),original_fields=reader.fieldnames,record_ids=[r['record_id'] for r in rows],screening_counts=dict(collections.Counter(r['screening_status'] for r in rows)),preserved_files={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files},first_round_log_rows=231)
 dest=ROOT/'data/round1_preservation_manifest.json'
 if not dest.exists():dest.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
 return rows,manifest
def apply():
 base,manifest=baseline();fields,master=read_csv(ROOT/'data/literature_master.csv')
 coding=[]
 for name in ['classification_cross.json','classification_en.json','classification_cn.json']:
  coding+=json.loads((ROOT/'batches/method_round2'/name).read_text(encoding='utf-8-sig'))
 ids=[r['record_id'] for r in coding]
 assert len(ids)==57 and len(set(ids))==57 and set(ids)==set(manifest['record_ids']),'Coding must cover original57 exactly'
 code={r['record_id']:r for r in coding}
 for r in master:
  if r['record_id'] not in code:continue
  c=code[r['record_id']]
  assert c['method_relevance_tier'] in TIERS and c['method_maturity'] in MATURITY and c['method_evidence_level'] in EVIDENCE
  assert set(c['method_contribution_type'].split(';'))<=TAGS
  if c['method_coding_status']!='fulltext_supported':assert c['method_maturity']=='unclear' and c['method_evidence_level']=='unclear'
  for k in FIELDS:r[k]=c[k]
 for old,new in zip(base,master):
  assert old['record_id']==new['record_id']
  assert all(old[k]==new[k] for k in manifest['original_fields']),old['record_id']+' legacy value changed in batchA'
 for p,h in manifest['preserved_files'].items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p+' altered'
 fields=fields+[k for k in FIELDS if k not in fields];write_csv(ROOT/'data/literature_master.csv',fields,master)
 counts={t:dict(total=sum(r['method_relevance_tier']==t for r in master),fulltext_confirmed=sum(r['method_relevance_tier']==t and r['screening_status']=='included' and r['method_coding_status']=='fulltext_supported' for r in master),abstract_provisional=sum(r['method_relevance_tier']==t and r['method_coding_status']=='abstract_provisional' for r in master),date_pending=sum(r['method_relevance_tier']==t and r['date_eligibility']=='date_pending' for r in master),frontier=sum(r['method_relevance_tier']==t and r['screening_status']=='frontier' for r in master),excluded=sum(r['method_relevance_tier']==t and r['screening_status']=='excluded' for r in master)) for t in sorted(TIERS)}
 (ROOT/'data/method_reclassification_counts.json').write_text(json.dumps(counts,ensure_ascii=False,indent=2),encoding='utf8')
 report=['# 批次A：既有57条方法导向重分类','', '编码日期2026-11-26；基线d88ba3c。原57个ID、全部旧字段值和筛选状态、15卡、原工作簿/BibTeX及期刊覆盖状态逐项验证未改变。新规则见[字段字典](../protocol/method_coding_rules.md)。','', '| 首要方法层级 | 总记录 | 全文确认 | 摘要暂定 | 日期待核 | 前沿 | 原排除 |','|---|---:|---:|---:|---:|---:|---:|']
 for t,c in counts.items():report.append('|'+t+'|'+'|'.join(str(c[k]) for k in ['total','fulltext_confirmed','abstract_provisional','date_pending','frontier','excluded'])+'|')
 report+=['','日期待核、前沿、摘要暂定是交叉维度，不能把各列相加。全文确认必须同时通过原included/日期和本轮fulltext_supported门。层级不是质量排序。','', '## 逐条编码与理由','', '| 编号 | 首要层级 | 内容证据状态 | 成熟度 | 方法证据 | 分类理由 |','|---|---|---|---|---|---|']
 for r in master:report.append('|'+ '|'.join(r[k].replace('|','/') for k in ['record_id','method_relevance_tier','method_coding_status','method_maturity','method_evidence_level','method_relevance_rationale'])+'|')
 report+=['','## 分类带来的判断','', 'R006和R008进入方法核心，重点是神经语言ABMA及GABM耦合/教程；R004从直接比较主线转为方法验证，因为核心增量是响应函数与偏向分解。R010为邻近问卷效度评估，不冒充互动网络。R015/R016/R021等方法重点仍仅摘要或前沿，成熟度、证据和迁移性pending，优先批次B精读。','', '意见/网络研究保留direct_comparator；传统ABM应用保留理论到模型的作用，但不因使用仿真就归通用方法创新。CN006是概念方法、CN007是综述，不把其建议记成已验证工作流。','', '## 已完成与直接下一步','', '批次A完成后直接进入B：核查MASS、R015、Haase/Pokutta、ODD-based replication四组正式来源与全文；同时推进GABM教程/架构/报告规范核心，保留负面效度证据。首轮目录/全文缺口不是停止方法主线的条件。']
 (ROOT/'reports/method_reclassification.md').write_text('\n'.join(report)+'\n',encoding='utf8');print(json.dumps(counts,ensure_ascii=False,indent=2))
if __name__=='__main__':apply()
