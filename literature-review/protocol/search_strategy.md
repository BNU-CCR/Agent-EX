# 检索策略与校准规则

执行日及截止日：2026-11-26，Asia/Shanghai；统一下限2022-01-01。性质为可审计的分阶段文献梳理；尚无全学科穷尽检索声明。

## 词表

方法：社会模拟、社会仿真、仿真模拟、计算实验、行动者模型、基于主体、主体建模、多主体、多智能体、计算模拟、ABM；social simulation / agent-based modeling / agent-based modelling / agent-based simulation / multi-agent / multiagent / computational modeling。

问题：意见演化、意见形成、舆论演化、社会影响、选择性接触、信息扩散、沉默螺旋、公开表达、极化、趋同、共识、群体规范；opinion dynamics / opinion formation / social influence / selective exposure / information diffusion / spiral of silence / polarization / polarisation / convergence / consensus / expression / social conventions。

生成式模型：大语言模型、生成式人工智能、生成式智能体、语言智能体、合成人群、模拟受访者；large language models / generative agents / LLM agents / language agents / synthetic populations / synthetic respondents。

校准新增词：argumentative opinion dynamics、norm diffusion、endogenously evolving network、conversational bias、friendship paradox、identity bias、pluralistic ignorance；它们分别补充理由生成、规范、网络反馈、模型倾向、网络验证、身份与私人/公开差异路径。不能要求三个词组同时命中，避免漏掉传统ABM和标题未出现LLM的研究。

## 三条路径与平台语法

1. 逐刊：公开网页使用 `site:<publisher domain> "<journal title>" ("agent-based" OR "social simulation" OR "opinion dynamics")`，中文使用刊名与“仿真/多主体/计算实验”等组合。实际已执行式以search_log为准，检索式中的年份文字仅为发现提示，不能充当数据库日期过滤。
2. 主题：`"opinion dynamics" "LLM"`、`"agent-based" "opinion" "2022" "JASSS"`、`"social identity bias" "2023"`；再到官方论文页、机构合法全文或出版社元数据核查。
3. 引文：指定六种子、项目已有Cau/Steiglechner/Starnini线索的参考文献、相似文章及后续正式版。仅追踪2022起合格发表；遇到更早引文只保留背景关系。

待权限可用时：WoS Advanced Search以 `SO=("journal") AND PY=(2022-2026) AND TS=("agent-based" OR "social simulation" OR "multi-agent" OR "opinion dynamics")` 为入口，之后单独补查Early Access首发；检索结果导出须含DOI、TI、AU、SO、AB、DE、PY、EA。CNKI高级检索以来源刊名字段+主题方法词组+2022起发表区间，按平台实际字段界面执行，不把WoS语法照抄入CNKI。上述两条尚未执行，不能计为完成。

## 筛选与日期

题名摘要→全文两阶段。首次正式在线日优先；仅有卷期年但疑有更早online-first则date_pending。官方论文集月份可以保留年月精度，不补造日。预印本与正式版以work_id关联，不重复计研究数。Crossref created是注册时间，不能作为发表日；published-online是出版社存入的日期，冲突须保留证据而非静默覆盖。

对象（人类社会过程模拟/AI群体行为/人机混合/其他）与用途（理论探索/机制检验/经验再现预测/方法评估/系统开发）独立编码。survey模拟不是互动网络；新传刊物中工程网络词语命中不自动纳入。方法批评与分化结果纳入反证检查。

## 检索日志口径

search_id稳定，平台搜索总数无法可靠读取时result_count留空；retrieved_count为保存候选条数而非数据库总命中。公开补查状态public_supplement_only；受阻access_blocked；部分partial；只有覆盖限定年份/字段/分页完成才可complete或searched_zero。元数据核查与来源访问是verification类记录，不能充当逐刊系统检索完成量。

## 执行调整

- 2026-11-26：正式版Betz 2022可纳入，尽管预印本2021；借此检验版本规则。
- 2026-11-26：RoleSimLLM有官方摘要/节选但全文未得，不制作完整卡；Crossref仅卷期2026-07，不用created=2026-02-23冒充online-first。
- 2026-11-26：部分Springer/Nature初次cookie跳转失败，公开正式页与机构全文替代；PMC验证码不代表论文不存在。
- 2026-11-26：Crossref部分429保留失败记录，已可用的出版社页继续核查，不高频重复请求。

第二轮X已实际补validation of generative social simulation、LLM agent calibration、stochastic reproducibility LLM agent simulation、theory formalization agent-based model四组公开查询，精确式在S-M2-X-Q01–04。年份文本不作数据库过滤，字面词匹配不作召回率；后续由真实命中/去重和官方全文推进，见reports/theme_search_followup.md。

ER执行校准（2026-11-28）：上文既有正式出版日期回退/会议年月精度规则继续有效；七篇ACL正式全文官方年月已核，按任务书3.2改时间资格confirmed并纳入，精确在线日未知不新增为硬门。online_first_date沿用年月，date_basis明示formalpublicationfallback，不猜日/不采用created。其他25日期未决不自动放宽。见reports/conference_date_precision_ER.md。


ET执行校准（2026-11-28）：M003正式出版月2026-07经出版社登记与作者机构核准，依原3.2回退确认；合法作者v2对应正式DOI，作为已读版本保留，不假称已取得正式排版PDF。精确日/独立校勘未完成是来源限制，不新增为所有纳入文献的硬门。其他24时间资格逐项审查。见reports/odd_formal_qualification_ET.md。


FB日期回退（2026-11-28）：三出版社正式出版月R0052026-07/M0252024-01/M0312026-10核准；首发日缺失按原3.2回退并注明精度。只有M025因已有合格正文纳入；另两摘要/已知版本差异候选保持。不是将DOI/created当日期，也不是统一解除全部待核。


FC会议日期精度（2026-11-28）：官方已出版档案/BibTeX提供出版年时，按原3.2回退保留年精度，不把会期当发布日期、不猜月日。M020/M036/M037结合已有正式阅读纳入；M021精确登记2026-05-25和新正式PDF取得仅先确认身份，待正文对照。非仅会议节目/归属声明即可放宽，须有正式档案。
