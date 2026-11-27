"""Formal EFECT reading; distinguish marginal reproducibility, path structure, and validity."""
import csv,hashlib,json,pathlib,fitz
R=pathlib.Path(__file__).resolve().parents[3];F=pathlib.Path(__file__).parent;T=pathlib.Path('C:/Users/Bai Yuexi/AppData/Local/Temp/agentex-literature-export')
def save(p,t):p.write_text(t.rstrip()+'\n',encoding='utf8')
assert not (F/'results.json').exists()
url='https://www.nature.com/articles/s44260-026-00094-y?error=cookies_not_supported';pdf='https://www.nature.com/articles/s44260-026-00094-y.pdf?error=cookies_not_supported'
save(R/'reading-cards/M030.md',f'''# M030 — EFECT：随机模拟的统计复现

## 1. 书目、版本与阅读范围
T. J. Sego等，EFECT enables reliable and reproducible stochastic simulations across disciplines. npj Complexity3:33；DOI10.1038/s44260-026-00094-y。[正式页]({url})：首次在线2026-08-05，VoR2026-11-23。2026-11-27定向读[11页VoR PDF]({pdf})Results/Discussion/Methods，尤其pp3,5,7–9；与Y取得23页先行版关键方法段对照，未全量逐字校勘。旧缓存仍可返回先行页，不覆盖新版本证据。

## 2. 问题与对象
独立随机模拟结果是否在指定观测量上分布一致；不是LLM人类行为校准。

## 3. 方法原理
逐变量/测量时点比较经验特征函数，汇总EFECT误差（Methods式1–3）；分开Modeler自样本复现与Curator比较。

## 4. 设计与制品
主文含不同随机来源与多种建模形式；数据压缩报告用于比较。补充表/软件未逐项审计。

## 5. 比较与重复
Grass-Sheep-Wolf三实现各自可稳定却彼此不等分布（p3/Fig2）；执行次数是样本单位，不是主体数。

## 6. 测量与阈值
收敛点与显著性水平分开；0.075及ECF采样设置是本文情境选择，非通用准则（pp5,8–9）。

## 7. 发现与证据层
控制模型/参数差异的技术比较，编码empirical_method_test / controlled_comparison；不据此判定通用社会模拟工作流已验证。

## 8. 限制
作者明确不解决不可识别性（p7），成本/固定测量时间有约束（p8）。逐时点边缘分布不自动证明联合轨迹一致，这是本项目由公式导出的范围判断，非作者已测试结论。

## 9. Agent-EX比较（本项目推论）
独立run、观测量、测量时间、复现误差和目标效度须分开；原冻结seed规则不由本文阈值改变。

## 10. 写作与投稿用途
为“可运行”之外的分布复现提供方法对照。本文正式先例不证明当前稿适合npj Complexity；期刊范围尚未在本批核。

## 11. 待核与制品
未复跑、未核全部40余用例、代码或SI；先行稿/VoR差异仅核关键段。hash见source_acquisition_manifest_Z.json；路径反例详见stochastic_reproducibility_scope.md。
''')
n=dict(record_id='M030',work_id='WM030',venue_id='V-NPJCOMPLEX',title='EFECT enables reliable and reproducible stochastic simulations across disciplines',authors='T. J. Sego; Matthias König; Luis L. Fonseca; Dilan Pathirana; Frank T. Bergmann; Hernán E. Grecco; Mauro Silberberg; Subhasis Ray; Baylor Fain; Adam C. Knapp; Krishna Tiwari; Henning Hermjakob; Herbert M. Sauro; James A. Glazier; Reinhard C. Laubenbacher; Rahuman S. Malik-Sheriff',language='en',venue='npj Complexity',document_type='journal_article',doi='10.1038/s44260-026-00094-y',official_url='https://www.nature.com/articles/s44260-026-00094-y',metadata_evidence_url=url,discovery_url='https://arxiv.org/abs/2406.16820',online_first_date='2026-08-05',volume_year='2026',preprint_date='2024-06-24',date_basis='PublisherPublished05August2026;VoR23November2026;PDFp9publishedonline05August2026',date_eligibility='confirmed',related_versions='Y:23pformalearlyreference;Z:11pVoR;arXiv2406.16820v2(2025-08-15)relatedpredecessor,not fullycollated;do notdoublecount',search_id='S-M2-Z-META;S-M2-Z-VOR',search_date='2026-11-27',screening_status='included',core_level='method_validity',reason='正式日期/VoR方法与结果定向精读；随机模拟统计复现先例，不是人类社会有效性验证。',research_question='如何量化独立随机模拟样本的分布复现？',research_object='other',simulation_purpose='method_evaluation',primary_purpose='method_evaluation',method_type='stochastic_simulation_reproducibility_test',mechanisms='empirical_characteristic_functions;modeler_curator_workflow;sample_size_convergence',reading_status='fulltext_checked',fulltext_url=pdf,supplement_status='not_checked;no_code_execution_or_full_SI_audit',findings='主文三GSW实现各自可稳定却彼此不等分布；阈值与检出差异依样本/情境；作者明确EFECT不解决不可识别性。',evidence_location='VoRpp3,5,7–9;Fig2;MethodsEqs1–7',relation_to_agent_ex='观测量分布复现、联合轨迹与经验有效性分层，独立run非agent数；不得照搬阈值或改冻结seed规则。',card_path='reading-cards/M030.md',source_batch='batches/method_round2/z_efect_reproducibility/results.json',notes='OfficialfreshHTML/11pPDFsupportsVoR;webPDFclickcanreturnearlycachedHTML;preserveboth versions. Reviewerpointwise/pathcounterexample is analytic,not paperexperiment.',method_relevance_tier='method_validation',method_contribution_type='reproducibility_and_reporting;measurement;validation_and_external_validity',method_maturity='empirical_method_test',disciplinary_home='stochastic simulation;complexity;computational reproducibility',method_transferability='可借鉴Modeler/Curator和分布误差/报告；只到选定观测量，联合依赖/经验效度需另证，LLM成本下阈值需独立设计。',method_evidence_level='controlled_comparison',method_relevance_rationale='直接补随机模拟复现测试及其可迁移边界。',method_coding_status='fulltext_supported',method_pending_fields='full_SI_and_code_audit;all40plus_cases;LLM_social_simulation_application;predecessor_version_comparison',method_evidence_location='VoRResults;Discussion;Methods;analyticreviewscope separate',method_coding_source='reading-cards/M030.md',method_last_checked='2026-11-27')
save(F/'results.json',json.dumps(dict(batch_id='Z-EFECT-statistical-reproducibility',date='2026-11-27',expected_master_sha256=hashlib.sha256((R/'data/literature_master.csv').read_bytes()).hexdigest(),updates=[],new_records=[n]),ensure_ascii=False,indent=2))
ops=[dict(search_id='S-M2-Z-META',platform='official_publisher',search_date='2026-11-27',query_exact=url,source_url=url,status='current_version_date_checked',notes='FreshHTMLshowsVoR23Nov2026/3:33;firstAug5;oldcachealsoobserved'),dict(search_id='S-M2-Z-VOR',platform='official_PDF_download_and_reading',search_date='2026-11-27',query_exact=pdf,source_url=pdf,status='HTTP200_verified_VoR_focused_read',notes='1856573bytes/11pages;Results/Discussion/Methods;Eqpage9rendered;noSI/code'),dict(search_id='S-M2-Z-WEBPDF',platform='web_tool_PDF_click',search_date='2026-11-27',query_exact='NaturePDFlink10',source_url='https://www.nature.com/articles/s44260-026-00094-y.pdf',status='redirect_returned_early_cached_HTML_notPDF',notes='NotPDFsuccess;do notreplaceactual11pdownload evidence withtoolrewrite'),dict(search_id='S-M2-Z-EARLY-READ',platform='local_acquired_PDF_reading',search_date='2026-11-27',query_exact='Y_efect.pdf;source_acquisition_manifest_Y.json',source_url='https://www.nature.com/articles/s44260-026-00094-y_reference.pdf?error=cookies_not_supported',status='critical_sections_compared',notes='23pearlyreference:pp5–6,16–18;notnewnetworkdownload orfulltextdiff')]
save(F/'source_operations.json',json.dumps(ops,ensure_ascii=False,indent=2))
manifest=[]
for name,version in [('Y_efect','early_accepted_23p'),('Z_efect_vor','VoR_2026-11-23_11p')]:
 p=T/(name+'.pdf');b=p.read_bytes();manifest.append(dict(version=version,sha256=hashlib.sha256(b).hexdigest(),bytes=len(b),pages=len(fitz.open(p)),checked='2026-11-27',storage='scratchPDF;repo manifestonly',scope='keymethod/resultsections,notfullbyte-equivalence'))
save(R/'data/source_acquisition_manifest_Z.json',json.dumps(manifest,ensure_ascii=False,indent=2))
p=R/'data/method_validation_matrix.csv'
with p.open(encoding='utf-8-sig',newline='') as f:d=csv.DictReader(f);h=d.fieldnames;rs=list(d)
units=[('VC51','M030','独立实现分布比较','GSW三实现','视觉相似掩盖差异','统计复现','各自可收敛、彼此不等分布','技术控制比较','哪个实现真实或人类效度','记录规范/实现与独立run分母','VoRResults/Fig2pp3,5','source_read_not_reexecuted'),('VC52','M030','逐时点与联合路径分开','边缘相同/相关性相反的解析例','遗漏时间依赖','测量范围','由Eq1–3逐变量形式推导','本项目解析判断','作者已测得路径错误或框架不可扩展','若关心过程需另报路径观测量','VoRpp8–9;reviewreportanalyticcounterexample','reviewer_analytic_scope_inference'),('VC53','M030','收敛点/显著性/重复数分开','不同样本量与参数扰动','低检出力或成本','复现检验能力','情境阈值与成本讨论','所测技术案例','通用0.075阈值或LLM标准','不据本文调冻结seed规模','VoRpp3,5,7–9','source_read_not_reexecuted'),('VC54','M030','自样本稳定与外部重构分开','Modeler/Curator','自重跑当独立复制','复现角色','两个流程分开设计','技术工作流','Agent-EX已独立复建','复建证据与同实现稳定分别报告','VoRResults/Workflowpp3,5','source_read_not_reexecuted')]
for unit in units:rs.append(dict(zip(h,[*unit[:11],unit[11],'2026-11-27'])))
with p.open('w',encoding='utf8',newline='') as f:w=csv.DictWriter(f,h);w.writeheader();w.writerows(rs)
