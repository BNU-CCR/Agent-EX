"""MOZAIC focused formal reading; acquire, but do not yet read/code, EFECT formal PDF."""
import csv,hashlib,json,pathlib,fitz
R=pathlib.Path(__file__).resolve().parents[3];F=pathlib.Path(__file__).parent;T=pathlib.Path('C:/Users/Bai Yuexi/AppData/Local/Temp/agentex-literature-export')
def save(p,t):p.write_text(t.rstrip()+'\n',encoding='utf8')
assert not (F/'results.json').exists()
u='https://www.frontiersin.org/journals/social-psychology/articles/10.3389/frsps.2026.1772740/pdf'
save(R/'reading-cards/M029.md',f'''# M029 — MOZAIC：理论形式化与验证分开

## 1. 书目、日期与阅读范围
Stefanie Schutera; Geeske Scholz; Sarah Wolf. MOZAIC: A mathematical approach to formalizing behavioral theories – applied to an agent-based model of mobility. Frontiers in Social Psychology4:1772740，2026-08-12；DOI10.3389/frsps.2026.1772740。[正式PDF]({u})。2026-11-26定向读§2方法、§3模型/五理论示例、§4限制；未审仓库或复跑。

## 2. 问题与对象
自然语言行为理论如何变成可比较的数学构件；本文是传统ABM方法，非LLM主体验证。

## 3. 理论到模型
作者将情境/理论选择、实体/环境/互动、决策元素和数学形式化分步表达（§2）。模型者仍需补充假设。

## 4. 设计
简化汽车所有权场景，形成五种理论的数学示例；构件须进一步实现为代码（§3、§4）。

## 5. 比较与重复
比较的是理论表达与假设；不是五次独立验证实验。本文没有据此建立MBB的效果比较或经验通过率。

## 6. 测量与操作
效用、选项与决策规则须分开；同一理论可有多种形式化（§3.3–3.4）。不从示例推出统一参数或阈值。

## 7. 主要判断与位置
数学表达能使附加选择显式，但不唯一确定理论实现；§4明确未处理MBB评价/验证，复杂动态/互动仍有缺口。

## 8. 证据层与限制
conceptual_framework / worked_example；不称validated_workflow。§3.4.4只作特定偏差示例，不充当完整前景理论定义；未额外核其风险偏好文字。

## 9. Agent-EX比较（本项目推论）
身份标签、曝光与状态规则需列出理论之外的附加假设。形式化和可执行性不能单独识别社会机制。

## 10. 写作与投稿用途
支持区分理论约束与研究者选择，沿既有规范链解释设计；不授权改主矩阵或按结果选参数。新期刊范围另待核。

## 11. 待核与制品
代码仓库/补充材料和独立构件效果未审；下载hash见source_acquisition_manifest_Y.json。无新模拟或项目运行审计。
''')
p=dict(record_id='M029',screening_status='included',reason='正式日期及方法/示例/限制定向全文核实；理论形式化工作示例，不是经验验证工作流。',reading_status='fulltext_checked',fulltext_url=u,card_path='reading-cards/M029.md',supplement_status='not_checked;code_repository_not_audited',findings='MBB明确附加假设；同一理论存在多种形式化。作者§4说明尚未评价/验证MBB，复杂动态/互动需后续工作。',evidence_location='§§2–4;pp4–6,9,11–16;§4footnote8',method_maturity='conceptual_framework',method_evidence_level='worked_example',method_coding_status='fulltext_supported',method_transferability='理论表达/附加假设的分层记录可借鉴；未证明构件跨模型有效或形式化提高经验预测。',method_pending_fields='code_and_supplement;MBB_effectiveness_and_complex_dynamic_validation',method_evidence_location='§2steps;§3.4multipleformalizations;§4limitations',method_coding_source='reading-cards/M029.md',method_last_checked='2026-11-26')
save(F/'results.json',json.dumps(dict(batch_id='Y-theory-formalization-focused-reading',date='2026-11-26',expected_master_sha256=hashlib.sha256((R/'data/literature_master.csv').read_bytes()).hexdigest(),updates=[p],new_records=[]),ensure_ascii=False,indent=2))
ops=[dict(search_id='S-M2-Y-Q01',platform='public_web_search',search_date='2026-11-26',query_exact='"EFECT" "Reproducibility" Sego 2024',status='bounded_version_discovery',notes='Found2026formalnpjComplexity;do notcountold/newtitlesasindependentstudies'),dict(search_id='S-M2-Y-Q02',platform='public_web_search',search_date='2026-11-26',query_exact='"10.1016/j.trc.2026.105818"',status='official_search_text_metadata',notes='Authors/October2026issue/abstract discovered;preciseonlinefirststillpending')]
sources=[('MOZAIC-PDF',u,'PDF200_focused_read','1492499bytes/18pages;§2–4focused;notcodererun'),('EFECT-META','https://www.nature.com/articles/s44260-026-00094-y?error=cookies_not_supported','official_early_access_metadata_abstract','PublishedAug5,2026;earlyaccepted article notfinalVoR;mainnotyetfocusedread'),('TRC-OPEN','https://www.sciencedirect.com/science/article/pii/S0968090X26003062','HTTP403','Searchtextreadnotmainfulltext'),('EFECT-ARXIV','https://arxiv.org/abs/2406.16820','version_metadata_checked','v1Jun24,2024;v2Aug15,2025;formalrelationshipneedscomparison'),('EFECT-WEBPDF','https://www.nature.com/articles/s44260-026-00094-y_reference.pdf','redirect_inaccessible','toolPDFopenfailedcookieidentity;notallmethodsfailed'),('EFECT-DOWNLOAD','https://www.nature.com/articles/s44260-026-00094-y_reference.pdf?error=cookies_not_supported','PDF200_acquired_not_focused_read','1209012bytes/23pages;retainearlyacceptedversion;readnextZ'),('TRC-CROSSREF','https://api.crossref.org/works/10.1016/j.trc.2026.105818','HTTP200_metadata','publishedonline null;printOct2026;notusecreatedasfirstdate')]
ops += [dict(search_id='S-M2-Y-'+key,platform='primary_source_access',search_date='2026-11-26',query_exact=url,source_url=url,status=status,notes=notes) for key,url,status,notes in sources]
save(F/'source_operations.json',json.dumps(ops,ensure_ascii=False,indent=2))
manifest=[]
for name,url,status in [('Y_mozaic',u,'focused_read'),('Y_efect',sources[5][1],'acquired_not_yet_focused_read')]:
 q=T/(name+'.pdf');b=q.read_bytes();assert b.startswith(b'%PDF');manifest.append(dict(url=url,sha256=hashlib.sha256(b).hexdigest(),bytes=len(b),pages=len(fitz.open(q)),checked='2026-11-26',status=status,storage='scratch_PDF;repository_manifest_only',version='formal_publisher_PDF' if name=='Y_mozaic' else 'formal_early_accepted_reference_PDF_notfinalVoR'))
save(R/'data/source_acquisition_manifest_Y.json',json.dumps(manifest,ensure_ascii=False,indent=2))
q=R/'data/method_validation_matrix.csv'
with q.open(encoding='utf-8-sig',newline='') as f:d=csv.DictReader(f);h=d.fieldnames;rs=list(d)
for unit in [('VC48','M029','理论与额外假设分开','同理论的多种数学表达','把标签当唯一机制','理论转译','有界理性两种形式化示例','工作示例','形式化唯一/经验有效','列明附加假设再判断操纵','§3.4.2;§4'),('VC49','M029','评价与选择分开','效用与平局处理','隐藏研究者自由度','机制识别','选项/函数/选择的显式定义','数学示例','最优模型/真实人机制','区分理论约束和未决参数','§3.3–3.4.1'),('VC50','M029','框架示例与效果验证分开','作者限制','把形式化当验证','方法有效性','§4称未评价验证MBB','边界说明','跨场景动态有效','透明/可执行与外部效度分别证明','§4p16;footnote8')]:rs.append(dict(zip(h,[*unit,'worked_example_not_reexecuted','2026-11-26'])))
with q.open('w',encoding='utf8',newline='') as f:w=csv.DictWriter(f,h);w.writeheader();w.writerows(rs)
