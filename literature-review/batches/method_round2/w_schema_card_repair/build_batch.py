"""Normalize only documented categorical aliases; preserve original evidence and scope."""
import csv,hashlib,json,pathlib
R=pathlib.Path(__file__).resolve().parents[3];F=pathlib.Path(__file__).parent
def save(p,t):p.write_text(t.rstrip()+'\n',encoding='utf8')
assert not (F/'results.json').exists()
rs=list(csv.DictReader((R/'data/literature_master.csv').open(encoding='utf-8-sig')))
allowed=json.loads((R/'data/categorical_schema.json').read_text(encoding='utf8'))['fields']
purpose={'framework_development':'method_evaluation','empirical_reproduction':'empirical_replication','hypothesis_generation':'theory_exploration','critical_review':'method_evaluation','research_agenda':'method_evaluation','review':'method_evaluation','mechanism_exploration':'theory_exploration','controlled_dialogue':'method_evaluation','empirical_pattern_comparison':'empirical_replication','retrospective_pattern_reconstruction':'empirical_replication','controlled_intervention':'mechanism_test','process_exploration':'theory_exploration','empirical_strategy_identification':'empirical_replication','calibrated_simulation':'method_evaluation','policy_scenario':'theory_exploration','component_evaluation':'method_evaluation','human_judgment':'method_evaluation','simulated_decision_comparison':'method_evaluation','mechanism_explanation':'theory_exploration','empirical_network_fitting':'empirical_replication'}
changes=[];updates=[]
for r in rs:
 patch={'record_id':r['record_id']}
 for field,legal in allowed.items():
  old=r[field]
  if not old:continue
  vals=old.split(';') if field=='simulation_purpose' else [old]
  if set(vals)<=set(legal):continue
  assert r['record_id'].startswith('M'),'Do not normalize original57 silently'
  if field=='core_level':
   assert old in ['method_core','method_validation','application'];new='method_validity';reason='Original core_level describes relevance to current study;method tier remains separate and unchanged;M025 supplies method-fit caution while application tier preserved'
  elif field=='research_object':
   assert old in ['research_methodology','dialogue_and_group_simulation_method','organizational_advice_network','synthetic_personality_responses','social_science_methodology'];new='human_social_process_simulation' if old=='organizational_advice_network' else 'other';reason='Four-category object field;method/component subtypes retained in original-value ledger and method_type,not introduced as new object enum'
  else:
   mapped=[v if v in legal else purpose[v] for v in vals];new=';'.join(dict.fromkeys(mapped));reason='Conservative canonical purpose aliases;empirical_replication denotes intended comparison/reconstruction,not validated fidelity;no maturity/evidence/status upgrade'
  patch[field]=new;changes.append(dict(record_id=r['record_id'],field=field,old=old,new=new,reason=reason))
 if len(patch)>1:
  patch['notes']=r['notes']+' | W:documented category aliases normalized;oldvalues/reasons in data/categorical_alias_migration_W.json;method tier/evidence/status unchanged.';updates.append(patch)
save(R/'data/categorical_alias_migration_W.json',json.dumps(dict(date='2026-11-26',source_audit='data/delivery_requirement_audit.json',original57_untouched=True,fields_changed=len(changes),records_changed=len(updates),empty_values_not_defaulted=True,changes=changes),ensure_ascii=False,indent=2))
save(F/'results.json',json.dumps(dict(batch_id='W-categorical-alias-card-structure',date='2026-11-26',expected_master_sha256=hashlib.sha256((R/'data/literature_master.csv').read_bytes()).hexdigest(),updates=updates,new_records=[]),ensure_ascii=False,indent=2));save(F/'source_operations.json','[]')
save(R/'reading-cards/M027.md','''# M027 — 合成抽样与人群推断的边界

## 1. 书目、版本与实际阅读
Emma Rose Madden. Evaluating the Use of Large Language Models as Synthetic Social Agents in Social Science Research. Journal of Social Computing6(4),334–341；DOI10.23919/JSC.2025.0022。[官方题录](https://www.sciopen.com/article/10.23919/JSC.2025.0022)Published2025-12-17。2026-11-26定向读[作者v2](https://arxiv.org/pdf/2509.26080v2)（2025-10-28，24页）§3–6；正式8页版未逐段对照，candidate。页数不同不证明实质内容不同。W仅依据T已读证据重整结构。

## 2. 问题与推断对象
合成输出能支持何种社会科学推断；对象是使用合成主体的研究实践，而非本篇新生成的人群。

## 3. 理论与方法主张
作者区分条件化模式生成与对真人总体的概率推断。贝叶斯一致性的形式化论证需原理论文献另核，本批不认证为普遍定理（§3–4）。

## 4. 模拟设计
不适用为单一新模拟架构；本文讨论既有合成受访者/主体方法，不能据此填入本篇模型、拓扑或状态规则。

## 5. 比较、重复与统计单位
方法批评引用多项实证，未作为本文独立重复计数。对引用研究没有在本批重新提取分母或复跑。

## 6. 测量与判据
作者强调分组校准、离散程度与条件范围（§5，pp12–18）；未在此建立统一数值验收阈值。

## 7. 主要判断及证据位置
作者主张合成输出不自动构成人类总体抽样，域内符合不能直接外推（§3–6）；这属于论证/建议，非作者新基准效果。

## 8. 验证与局限
所读为作者v2，正式全文未比对；被引实证与形式化理论尚未逐项重核，不能把综述性论断升级为新验证。

## 9. 与Agent-EX比较（本项目推论）
独立受访者请求、刻意互动依赖和独立seed/run须分开。主体依赖不直接等于错误；增大AI模拟规模不能单独缩窄对真人的推断不确定性。

## 10. 写作/投稿用途
用于限定研究对象、重复单位和外推主张；不是项目已经通过人群校准的证明。JSC范围/条件适配见evaluation_venue_updates.md。

## 11. 待核、补充与制品
正式PDF、版本对照、原始理论与引用实验仍待核。下载hash与范围见source_acquisition_manifest_T.json。未复跑、未修改冻结协议。
''')
save(R/'reading-cards/M028.md','''# M028 — 研究建议、复现制品与测量验证

## 1. 书目、版本与实际阅读
Suhaib Abdurahman; Alireza Salkhordeh Ziabari; Alexander K. Moore; Daniel M. Bartels; Morteza Dehghani. A Primer for Evaluating Large Language Models in Social-Science Research. Advances in Methods and Practices in Psychological Science8(2),1–25；DOI10.1177/25152459251325174。[出版社](https://journals.sagepub.com/doi/full/10.1177/25152459251325174)首次在线2025-04-16。2026-11-26定向读[个人站点正式版式PDF](https://goytoom.github.io/assets/files/primer.pdf)Table3、pp7–14及Appendix开头；DOI/题名相符，非逐字节同一性认证。W仅依据T已读证据重整。

## 2. 问题与对象
如何开展与评审LLM数据处理/合成人类数据研究；属于研究方法与实践指导。

## 3. 理论与方法主张
透明材料、随机性/版本和任务真值验证共同约束研究解释（Table3）；指南不是通用效度定理。

## 4. 模拟设计
不是一个统一社会模拟平台。文中提示/温度例示与附录假设研究不应被补写为正式群体架构或长期网络实验。

## 5. 比较、重复与统计单位
多次读出和报告变异是建议（pp7–8）；附录为假设案例（p17开头），不能当清单效果的独立试验。

## 6. 测量与判据
任务真值、人工评价和条件相关错误应区分（Table3、pp10–11）；没有可直接移植的统一误差阈值。

## 7. 主要判断及证据位置
清单区分Required/Optional，含可运行制品、版本、验证和错误处理；preregistration列Optional（Table3，已渲染目视核对）。这是作者框架，不是编辑统一政策。

## 8. 验证与局限
没有据本文示范认定清单已经通过独立有效性验证；未复跑引用例子。稳定性和复现须实际检查，不能只由seed参数保证（pp7–8）。

## 9. 与Agent-EX比较（本项目推论）
平均准确率不能排除随条件变化的分类误差；透明记录和清单不能替代独立动态效度，也不能覆盖项目已批准冻结要求。

## 10. 写作/投稿用途
用来说明方法披露与测量核查；官方AMPPS广泛心理学方法门槛另见evaluation_venue_updates.md，不因本文发表就认为当前稿适配。

## 11. 待核、补充与制品
未逐项重核所有引用或运行制品；没有本项目合规完成结论。PDF身份/hash见source_acquisition_manifest_T.json；未改协议或执行新模拟。
''')
print(len(changes),'fields;',len(updates),'records;2 cards restructured')
