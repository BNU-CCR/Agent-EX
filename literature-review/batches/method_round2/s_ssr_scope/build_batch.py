"""Bounded failed directory access plus successful publisher scope evidence."""
import pathlib,csv,json,hashlib
R=pathlib.Path(__file__).resolve().parents[3];F=pathlib.Path(__file__).parent
def save(p,t):p.write_text(t.rstrip()+'\n',encoding='utf8')
assert not (F/'results.json').exists()
qs=['"Social Science Research" journal "large language models" simulation','"Social Science Research" "agent-based" 2022 2023 2024 2025','site.sciencedirect.com/journal/social-science-research "agent" "simulation"','"Social Science Research" "10.1016/j.ssresearch" "simulation"','"Social Science Research" "large language models" "10.1016/j.ssresearch"','"Social Science Research" "ISSN" "0049-089X" aims scope','site.sciencedirect.com/science/article/ "Social Science Research" "agent-based model" 2023']
ops=[dict(search_id=f'S-M2-S-Q{i:02}',platform='public_web_search',search_date='2026-11-26',query_exact=q,status='bounded_query_not_journal_census',notes='Off-targetvenues/SSRN/topickeywordcollisions;noqualifiedSSR2022+methodprecedentverified;notzeropapers or independentlycountedhits') for i,q in enumerate(qs,1)]
urls=[('SCOPE-FAIL','https://www.sciencedirect.com/journal/social-science-research/about/aims-and-scope','403'),('ISSUES-FAIL','https://www.sciencedirect.com/journal/social-science-research/issues','403'),('VOL-FAIL','https://www.sciencedirect.com/journal/social-science-research/vol/124/suppl/C','403'),('GUIDE-FAIL','https://www.sciencedirect.com/journal/social-science-research/about/guide-for-authors','403'),('SCOPE','https://shop.elsevier.com/journals/social-science-research/0049-089X','publisher_scope_checked'),('MJL','https://mjl.clarivate.com/cgi-bin/jrnlst/jlresults.cgi?ISSN=0049-089X&PC=D','search_excerpt_only_render_empty')]
ops += [dict(search_id='S-M2-S-'+key,platform='official_source_access',search_date='2026-11-26',query_exact=u,source_url=u,status=status,notes='MJLsearch showsSSCI butopenonlyiframe;do notclaim fullyverifiedcurrentindex' if key=='MJL' else 'Scope andavailability evidence,not paperinclusion or directorycoverage') for key,u,status in urls]
save(F/'source_operations.json',json.dumps(ops,ensure_ascii=False,indent=2))
save(F/'results.json',json.dumps(dict(batch_id='S-SSR-bounded-scope-audit',date='2026-11-26',expected_master_sha256=hashlib.sha256((R/'data/literature_master.csv').read_bytes()).hexdigest(),updates=[],new_records=[]),ensure_ascii=False,indent=2))
p=R/'data/venue_coverage_audit.csv'
with p.open(encoding='utf-8-sig',newline='') as f:d=csv.DictReader(f);h=d.fieldnames;rs=list(d)
for r in rs:
 if r['requested_venue']=='Social Science Research':r.update(audit_status='publisher_scope_checked_precedent_unresolved',scope_check='ElsevierShop publisherdescription checked;ScienceDirect403',coverage_boundary='7boundedpublicqueries;issues/volume/guide403;noqualifiedprecedentverified;notzeropapers',next_action='authorizedjournalexport or accessibleTOC;first verifyactualvenue/DOI beforeaddingpaper',evidence_urls=r['evidence_urls']+';'+urls[4][1],source_operation_ids=r['source_operation_ids']+';'+';'.join(o['search_id'] for o in ops))
with p.open('w',encoding='utf8',newline='') as f:w=csv.DictWriter(f,h);w.writeheader();w.writerows(rs)
for name in ['progress.md','GOAL.md','README.md','reports/venue_coverage_audit.md']:
 p=R/name;t=p.read_text(encoding='utf8')
 if name=='progress.md':
  t=t.replace('|提交后回填|','|c491b5e（已推送）|',1).replace('509条累计检索/来源获取操作','522条累计检索/来源获取操作',1).replace('|R|两刊代码/数据/格式政策与7条强度证据|c491b5e（已推送）|','|R|两刊代码/数据/格式政策与7条强度证据|c491b5e（已推送）|\n|S|Social Science Research官方范围与有界目录审计|提交后回填|',1).replace('1. 批次S核Social Science Research官方目录/范围与2022+方法先例，有界记录查询与访问失败；R已补两刊目标政策段落。M025首次在线日与SOCNET范围仍缺。','1. 批次T先查重并核Evaluating the Use of Large Language Models as Synthetic Social Agents in Social Science Research（10.23919/JSC.2025.0022）与A Primer for Evaluating Large Language Models in Social-Science Research（10.1177/25152459251325174）的正式日期/全文；作为方法验证和报告规范线索。SSR先例/目录、M025首次在线日与SOCNET范围仍缺。',1)
  t+='\n### 批次R/S接续\nR c491b5e已推送；9表行数/缓存核验，汇总数字未变，未另作本批视觉检查。S核Elsevier官方SSR范围，7查询/4目录指南失败/2官方来源操作，522日志；无新增论文、卡或纳入。MJL仅搜索摘要显示SSCI，实际打开为空iframe，仍不强称独立索引核验完成。全文/全库缺口继续保留，下一批T补方法评价与报告规范种子。\n'
 else:t+='\n批次S：[Social Science Research范围与覆盖边界](reports/ssr_scope_and_search_boundary.md)。' if name in ['GOAL.md','README.md'] else '\n批次S见[SSR范围与检索边界](ssr_scope_and_search_boundary.md)：官方范围已补，目录/指南403，未确认先例，不是零发表。'
 save(p,t)
