"""Assemble reviewed BH evidence; does not execute third-party models."""
import csv,hashlib,json,pathlib
R=pathlib.Path(__file__).resolve().parents[3]
B=pathlib.Path(__file__).resolve().parent
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def read(p):
 with p.open(encoding='utf-8-sig',newline='') as f:
  q=csv.DictReader(f);return q.fieldnames,list(q)
def write(p,h,rs):
 with p.open('w',encoding='utf8',newline='') as f:
  w=csv.DictWriter(f,h);w.writeheader();w.writerows(rs)
date='2026-11-27'; sha='1e9be1490bcbd5fa23632aeff9cbf872bd18957f'
blog='https://www.gisagents.org/2026/10/llm-assisted-workflows-for-replicating.html?m=0'
repo='https://github.com/wang-boyu/csssa2026-abm-replication'
pdf='https://www.dropbox.com/scl/fi/1x0ghs8b6s8sj9gnugwyf/CSSSA2026_Replication.pdf?rlkey=yk1aetuq8f65r5es0kt0xxhm6&st=gtozsa20&dl=1'
fixed=f'https://raw.githubusercontent.com/wang-boyu/csssa2026-abm-replication/{sha}/README.md'
ops=[
 ('author_blog_discovery',blog,'author_blog_read','2026-10-26post;directauthorPDFandrepositorylinks'),
 ('dropbox_preview',pdf.replace('dl=1','dl=0'),'HTML_preview_not_fulltext','webpreview0lines;notPDF'),
 ('repository_live_readme',repo,'public_README_read','under_review;two_workflows;noexecution'),
 ('blog_raw_link_extraction',blog,'public_HTML_links_extracted','authorprovidedDropboxqueryretained'),
 ('author_PDF_download',pdf,'PDF_acquired_HTTP_headers_not_retained','17pages;1685932bytes;hashmanifest;notformalversion'),
 ('PDF_maintext_and_tables','reading-cards/M045.md','local_fulltext_read','pp1-15;refs15-17identityonly;Table1rendered'),
 ('blog_recheck',blog,'web_fetch_failed','500redirectGoogle_sorry;earlierreadandPDFpreserved'),
 ('repository_recheck',repo,'public_README_read','webcurrentREADMEunderreview;notfixedreleaseproof'),
 ('pin_commit', 'https://api.github.com/repos/wang-boyu/csssa2026-abm-replication/commits/main','HTTP200_commit_identity',sha+';committer2026-10-04T21:13:04Z'),
 ('fixed_README',fixed,'HTTP200_static_README','4085bytes;SHA25628c2aff81f6e06a517a7eadee9b2ac89d696230c8c03511451cb09f8e0033fbf'),
 ('Table1_visual','reading-cards/M045.md','local_render_visual_check','PDFp11captionSD/100vs30;12rows;nooriginalpaperverification')]
dump(B/'source_operations.json',[dict(search_id=f'BH-{i:02}',platform='local_audit' if u.startswith('reading-') else 'public_primary_source',search_date=date,query_exact=q,source_url=u,status=s,notes=n) for i,(q,u,s,n) in enumerate(ops,1)])
h,_=read(R/'data/literature_master.csv');n={k:'' for k in h}
n.update(record_id='M045',work_id='WM045',venue_id='V-CSSSA',title='Large Language Model-Assisted Workflows for Replicating Agent-Based Models',authors='Boyu Wang;Andrew Crooks',language='English',venue='CSSSA 2026 author manuscript; formal proceedings publication pending',document_type='preprint',official_url='https://computationalsocialscience.org/css2026program/',discovery_url=blog,metadata_evidence_url=blog+';'+repo,volume_year='2026',date_basis='Authorblog2026-10-26andCSSSA2026programnotformalpublicationdate',date_eligibility='date_pending',related_versions='17pageauthorPDF;fixedrepositoryREADMEunderreview;formalchapterunverified',search_id='BH-01;BH-05;BH-06;BH-09;BH-10',search_date=date,screening_status='candidate',core_level='method_validity',reason='Authorfulltextsupportsboundedworkflowcaseevidence;formalpublicationdateandversionpending',research_question='Canrole-separatedLLMassistancehelpcross-platformABMreplicationunderunequalsourcematerials?',research_object='other',simulation_purpose='method_evaluation',primary_purpose='method_evaluation',method_type='ThreecaseLLMassistedcross-platformABMreimplementation',mechanisms='Role_separation;human_adjudication;skillcoordination;sourceconditionalverification',reading_status='fulltext_checked',fulltext_url=pdf,supplement_status='fixedREADMEonly;code/resultsnotread_or_executed;papercommitunverified',findings='ThreeMesareplications;workflowandtaskconfounded;sourceconditionalpattern/outputcorrespondence;nolabor/time/costmeasurement;SlumulationSDexplanationrequiresaudit',evidence_location='authorPDFpp1-15;Tables1-3;fixedREADME',relation_to_agent_ex='Separatemodeller_assistantvalidationfromruntimeLLMsocialagentvalidity;measureimplementationdeviationundercomparabletasks',card_path='reading-cards/M045.md',source_batch='BH',notes='17pages1685932bytesSHA25689a521b3aa24f274b3bea0f02ae7d9281e43450f4e8d0a9fcb08b85b52ca1914;noformalpublicationclaim;noauthorcodeexecution',method_relevance_tier='method_validation',method_contribution_type='reproducibility_and_reporting;validation_and_external_validity;theory_to_model_translation',method_maturity='empirical_method_test',disciplinary_home='social_simulation;ABM;computational_social_science',method_transferability='Twoassistedworkflowpatternswiththreeworkedcases;efficiencyandcross-taskgeneralisationnotestablished',method_evidence_level='worked_example',method_relevance_rationale='作者稿报告跨平台复现及不同验证对象；无同任务助手效果对照，不升级成熟验证工作流。',method_coding_status='fulltext_supported',method_pending_fields='formalpublication/date;papercommit;LLMconfigs;SDaggregationdefinition;independentworkfloweffect',method_evidence_location='authorPDF§2/§3/§4;pp3-15',method_coding_source='reading-cards/M045.md;reports/llm_assisted_replication_workflows.md',method_last_checked=date)
dump(B/'results.json',dict(batch_id='BH-LLM-assisted-replication-workflow-reading',date=date,expected_master_sha256=hashlib.sha256((R/'data/literature_master.csv').read_bytes()).hexdigest(),updates=[],new_records=[n]))
dump(R/'data/source_acquisition_manifest_BH.json',dict(checked_date=date,title=n['title'],author_url=blog,actual_version='undated_author_manuscript_linked_by2026-10-26blog;notverifiedformalchapter',pdf=dict(url=pdf,bytes=1685932,pages=17,sha256='89a521b3aa24f274b3bea0f02ae7d9281e43450f4e8d0a9fcb08b85b52ca1914',http_status='not_retained',read_scope='mainpp1-15;references15-17identityonly;Table1p11visual'),repository=dict(url=repo,commit=sha,committer_date='2026-10-04T21:13:04Z',readme_url=fixed,readme_http_status=200,readme_bytes=4085,readme_sha256='28c2aff81f6e06a517a7eadee9b2ac89d696230c8c03511451cb09f8e0033fbf',scope='READMEonly;code/resultsnotread;notexecuted;notprovenpapercommit')))
mh,ms=read(R/'data/method_validation_matrix.csv')
ms=[x for x in ms if x['record_id']!='M045']
units=[
 ('工作流比较','人工中介一模型/skills两模型','案例与来源混淆','助手流程效果','三案例报告成功重实现','工作流程可行性案例','两流程优劣或LLM净效应','同任务来源资源条件比较','§2pp3-5/§4pp13-15'),
 ('结构和调度','Ya-TASERPS源实现/ODD','实现时序偏离','跨平台机制与分布','729组合每组合10次；方向与分布对应','被测组合与来源','精确数值/轨迹同一或外部社会效度','冻结规则与事件顺序核对','§3.1pp6-8'),
 ('视觉与统计范围','Sakoda八情境各五次','代表图冒充统计验证','空间模式对应','40次视觉检查；明确无统计比较','粗粒度模式','统计通过率/完整轨迹','按主张选择验证粒度','§3.2p7/图3p9'),
 ('Slumulation汇总','原文100次/两实现各30次','SD/SE及聚合单位混淆','均值/离散程度/情境对应','表1SD差异；作者归因重复次数未证明','表1-3描述比较；定义待核','数值等价/真实政策效果/错误定论','分列SD与SE并核原始run','§3.3pp9-14/表1p11'),
 ('成本效果与可复现','未测助手资源/固定README','有代码等于已复现或效率增益','工作流成本和制品身份','作者承认未记人工时间调用成本','缺失测量及README静态核','加速/降本/第三方复现成功','记录成本/版本/运行对应','§4p15;fixedREADME')]
for i,(control,ref,error,target,reported,scope,notest,transfer,loc) in enumerate(units,126):
 ms.append(dict(zip(mh,[f'VC{i}','M045',control,ref,error,target,reported,scope,notest,transfer,loc,'author_manuscript_case_evidence_not_independent_replication',date])))
write(R/'data/method_validation_matrix.csv',mh,ms)
vh,vs=read(R/'data/method_venue_map.csv')
for v in vs:
 if v['venue_id']=='CSSSA':
  v['record_ids']='M045'
  v['evidence_note']+=';BH_M045author17ppfullread_notformalchapter;fixedREADMEunderreview'
  v['master_venue_ids']='V-CSSSA'
write(R/'data/method_venue_map.csv',vh,vs)
print('BH prepared: one record, five evidence units, eleven grouped source operations')
