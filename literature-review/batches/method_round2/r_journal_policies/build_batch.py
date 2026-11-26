"""Policy evidence updates only; no paper or experiment status upgrade."""
import pathlib,json,csv,hashlib
R=pathlib.Path(__file__).resolve().parents[3];F=pathlib.Path(__file__).parent
def save(p,t):p.write_text(t.rstrip()+'\n',encoding='utf8')
def read(p):
 with p.open(encoding='utf-8-sig',newline='') as f:
  d=csv.DictReader(f);return d.fieldnames,list(d)
def write(p,h,rs):
 with p.open('w',encoding='utf8',newline='') as f:
  w=csv.DictWriter(f,h);w.writeheader();w.writerows(rs)
assert not (F/'results.json').exists()
base='https://journals.plos.org/plosone/s/'
sbase='https://www.nature.com/srep/'
sources=[('PLOS-CODE',base+'materials-and-software-sharing','Sharing Code;Recommendations'),('PLOS-DATA',base+'data-availability','Introduction;Minimal Data Set Definition'),('PLOS-GUIDE',base+'submission-guidelines','Length;Abstract'),('SREP-GUIDE',sbase+'author-instructions/submission-guidelines?error=cookies_not_supported','Format;Methods;Data availability'),('SREP-POLICY',sbase+'journal-policies/editorial-policies?error=cookies_not_supported','Availability of materials and data;Availability of computer code and algorithm')]
ops=[dict(search_id='S-M2-R-'+key,platform='official_policy',search_date='2026-11-26',query_exact=u,source_url=u,status='targeted_policy_sections_checked',notes=loc+';open/find/lineopens consolidated;not fees/index or whole-guide certification') for key,u,loc in sources]
save(F/'source_operations.json',json.dumps(ops,ensure_ascii=False,indent=2))
save(F/'results.json',json.dumps(dict(batch_id='R-journal-policy-evidence',date='2026-11-26',expected_master_sha256=hashlib.sha256((R/'data/literature_master.csv').read_bytes()).hexdigest(),updates=[],new_records=[]),ensure_ascii=False,indent=2))
evidence=[
 dict(venue_id='PLOSONE',kind='data',strength='required_with_legal_ethical_access_exceptions',finding='发表时公开复制研究发现所需最小数据与元数据/方法；投稿须DAS；限制需说明获取途径。',source_id='S-M2-R-PLOS-DATA'),
 dict(venue_id='PLOSONE',kind='code',strength='expectation_and_possible_publication_condition',finding='期望支撑发现的作者代码发表时不受限可得；核心代码可能成为发表条件；应可重用并有文档。法律/伦理例外须说明。',source_id='S-M2-R-PLOS-CODE'),
 dict(venue_id='PLOSONE',kind='code_archive',strength='encouraged',finding='DOI仓库、开源许可、依赖文档及DAS代码入口为鼓励实践；不可全部改写为无例外硬性要求。',source_id='S-M2-R-PLOS-CODE'),
 dict(venue_id='PLOSONE',kind='format',strength='guide',finding='正文/图数/SI无上限，鼓励简洁；摘要不超过300词。',source_id='S-M2-R-PLOS-GUIDE'),
 dict(venue_id='SREP',kind='data',strength='required_statement_and_review_access',finding='原创文章必须DAS；投稿时编辑/审稿人须能取得支撑数据；公开限制须说明，优先仓库。',source_id='S-M2-R-SREP-POLICY'),
 dict(venue_id='SREP',kind='code',strength='required_if_central',finding='对结论核心的未报告自编代码/算法须按编辑或审稿人请求提供；Methods须Code availability说明访问/限制；重要代码不可得可被拒。',source_id='S-M2-R-SREP-POLICY'),
 dict(venue_id='SREP',kind='format',strength='recommendation_except_specified_limits',finding='Article/Registered Report；建议11排版页、主文4500词（排除摘要/Methods/参考文献/图注），一般不严格限总字页；摘要≤200词；Methods不限字数；须披露LLM使用。',source_id='S-M2-R-SREP-GUIDE')]
save(R/'data/journal_policy_audit.json',json.dumps(dict(checked='2026-11-26',scope='Targeted policy sections only;not fees/index nor currentmanuscript compliance audit',sources=ops,evidence=evidence,project_inference='冻结配置/模型/prompt版本、事件制品定位、分析输入输出及复现文档应作为研究交付候选；具体逐项充分性未审。不把政策可访问性当科学有效性，不修改冻结协议。'),ensure_ascii=False,indent=2))
for file in ['method_venue_map.csv','journal_submission_candidates.csv']:
 h,rs=read(R/'data'/file)
 for r in rs:
  if r['venue_id']=='PLOSONE':r.update(article_types_and_length='Original research/methods;main length/figures/SI unrestricted;abstract≤300;officialguide checked2026-11-26',code_data_requirements='Minimal replication dataset+DAS required with stated legal/ethical exceptions;author-code expected unrestricted at publication;centralcode may be publicationcondition;DOIrepo/license encouraged;see journal_policy_audit.json',verification_status='scope_samples_and_targeted_policies_checked',pending_items='whole_journal_search;fees;independent_index;remaining_type_specific_guide',evidence_note=r['evidence_note']+';R official code/data/length sections checked;not manuscriptcompliance audit')
  elif r['venue_id']=='SREP':r.update(article_types_and_length='Article/Registered Report;recommended11typesetpages/main4500words(exclabstract/Methods/refs/legends),not blanketstrictlimit;abstract≤200;Methods unlimited',code_data_requirements='DAS mandatory;data to editors/referees at submission;centralcustomcode on editor/reviewer request;Code availability inMethods including restrictions;see journal_policy_audit.json',verification_status='scope_samples_and_targeted_policies_checked',pending_items='whole_journal_search;fees;independent_index;remaining_type_specific_guide',evidence_note=r['evidence_note']+';R official code/data/format sections checked;not blanketunrestrictedopensource policy')
 write(R/'data'/file,h,rs)
for name in ['reading-cards/R014.md','reading-cards/M026.md']:save(R/name,(R/name).read_text(encoding='utf8'))
p=R/'progress.md';t=p.read_text(encoding='utf8').replace('|提交后回填|','|513a9c6（已推送）|',1);save(p,t)
