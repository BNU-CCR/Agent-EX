"""Prepare a fingerprinted follow-up without upgrading publication/version gates."""
import csv,hashlib,json,pathlib
R=pathlib.Path(__file__).resolve().parents[3];F=pathlib.Path(__file__).parent
def save(p,s):p.write_text(s+'\n',encoding='utf8')
assert not (F/'results.json').exists(),'Archival batch already prepared'
url='https://arxiv.org/html/2509.18985v2'
save(R/'reading-cards/M021.md',f'''# M021 — 经验资料初始化与社会模拟评价

核查2026-11-26。实际读的是arXiv2509.18985v2（2026-04-03）作者稿的Experimental Design、结果/讨论及附录计算资源/数据/程序说明：{url}。机构题录及官方节目确认2026 ICWSM关系；正式PDF403、DOI/首次在线日仍pending，因此candidate。附录prompt标题可见但正文缺失，不能称完整提示已核。

作者用意大利2022选举资料初始化部分主体特征，并比较模拟与该资料的互动/毒性模式；100主体、21虚拟日、每条件10次运行。两种uncensored模型、两类初始网络及推荐条件的比较仍局限于此设定。

本库判断：这是经验模式比较，尚非独立留出预测验证。FJ对照读取模拟演化网络，轨迹相似也不是独立真人变化效标。四联盟的组内相关与十二组间单元须保留分母及run变异，较高相关不能代替精度、显著性或校准合格。

编码method_validation / empirical_method_test / empirical_validation；“有经验对照”不表示通过效度或成为validated_workflow。迁移建议是分开初始化与验证资料、结构/内容/轨迹效标及评价单位。动态重连和uncensored路线仅记录他文设定，不写回Agent-EX主矩阵。未复跑、未核全部图/提示或正式版差异。''')
patches=[dict(record_id='M021',preprint_date='2025-09-23',reading_status='fulltext_checked',fulltext_url=url,card_path='reading-cards/M021.md',supplement_status='partial_appendix_checked_prompts_missing_in_HTML',research_question='经验初始化能在多大程度再现互动、毒性及意见变化？',simulation_purpose='empirical_pattern_comparison;method_evaluation',method_type='empirically_initialized_LLM_social_simulation',method_maturity='empirical_method_test',method_evidence_level='empirical_validation',method_coding_status='fulltext_supported',method_evidence_location='Authorv2 ExperimentalDesign;Interactions;Toxicity;OpinionDynamics;Discussion;Appendix',method_coding_source='reading-cards/M021.md',method_pending_fields='formal_version_text;first_online_date;formal_DOI;heldout_validation;full_prompt_text;code_reexecution',method_last_checked='2026-11-26',disciplinary_home='计算社会科学/社交媒体模拟的经验拟真评估',findings='同一选举数据集初始化与模式比较；FJ沿模拟网络作条件模型对照；不等于留出预测效度。',evidence_location='Authorv2 ExperimentalDesign;Interactions;OpinionDynamics;Appendix',relation_to_agent_ex='把初始化资料、验证资料和模型对照分开；测量单位与run变异明确。动态重连/uncensored不回填主方案。',notes='Actual authorv2 read; formalPDF403 and exactformaldate/DOIpending. HTML prompt bodies missing despite headings. Empiricalcomparison is not claimed validationpass; no rerun.'),dict(record_id='M020',disciplinary_home='多智能体系统/可控生成式社会对话',method_pending_fields='first_formal_online_date;publication_artifact_match;judge_human_validation;exact_model_digest;code_reexecution',notes='FormalPDF read; static7file audit pinned93256122ecaa76943b0702cc6c6317765398b397 (Oct1 after Mayconference), not established paper runartifact. Judgeandoneagent both llama3:latest; runner default nonrepetition lexical; evidence first10charsmatch; noexecution.',method_last_checked='2026-11-26'),dict(record_id='M017',disciplinary_home='组织科学/传统ABM敏感性分析'),dict(record_id='M018',disciplinary_home='组织管理/ABM理论发展与方法综述'),dict(record_id='M019',disciplinary_home='建模与仿真/LLM辅助模型构建')]
save(F/'results.json',json.dumps(dict(batch_id='K-calibration-and-artifact-audit',date='2026-11-26',expected_master_sha256=hashlib.sha256((R/'data/literature_master.csv').read_bytes()).hexdigest(),updates=patches,new_records=[]),ensure_ascii=False,indent=2))
ops=[]
def op(key,url,status,note,platform='primary_source_operation',query=None):ops.append(dict(search_id='S-M2-K-'+key,platform=platform,search_date='2026-11-26',query_exact=query or url,source_url=url,status=status,notes=note))
op('PROGRAM-SEARCH','https://www.icwsm.org/2026/program.html','indexed_official_program_checked','OfficialindexedShortlabel andauthors verified; livebodydynamic','public_web_search','site.icwsm.org/2026 "Simulating Online Social Media"')
op('M021-VERSION','https://arxiv.org/abs/2509.18985','version_history_checked','v1 Sep23,2025;v2 Apr3,2026;notformalpubdate')
op('M021-FULL',url,'author_v2_focused_fulltext_checked','Design/results/discussion/appendixresourcesdataread; HTMLpromptbodymissing; lineopens/findsconsolidated')
op('M019-FULL','https://journals.sagepub.com/doi/full/10.1177/00375497241239360','not_accessible','Fulltextstillnotread; officialTOCnotreplacement')
op('QTMD-ROOT','https://api.github.com/repos/HongboBo/QTMD/contents','directory_inspected','Sourcefile discovery;notexecution','GitHub_connector')
op('QTMD-COMMIT','https://api.github.com/repos/HongboBo/QTMD/commits/main','commit_pinned','93256122ecaa76943b0702cc6c6317765398b397;Oct1,2026;not proved publicationartifact','GitHub_connector')
manifest=json.loads((F/'qtmd_source_manifest.json').read_text(encoding='utf8'))
for f in manifest['files']:op('QTMD-'+f['path'].replace('.','-'),f['url'],'static_file_read','Pinnedcommit;blobSHA='+f['blob_sha']+';no execution','GitHub_connector')
save(F/'source_operations.json',json.dumps(ops,ensure_ascii=False,indent=2));print('Prepared',len(patches),'updates;',len(ops),'operations')
