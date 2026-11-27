# 方法用途与正式获取：CJ

2026-11-27。未新增论文或全文卡；本批23分组操作含5检索、网页获取/定位、3静态请求与1本地编码，不把超时或find当独立检索。见[操作账](../batches/method_round2/cj_purpose_access/source_operations.json)、[获取账](../batches/method_round2/cj_purpose_access/acquisition_manifest.json)、[字段决策](../batches/method_round2/cj_purpose_access/coding_decisions.json)。

|记录|实际证据|本批处理|
|---|---|---|
|M012|Delft文件403，5717bytes HTML，无PDF头；UFZ元数据未给新正式首发证据|三个空分类及日期/全文pending保持，失败响应hash不是论文hash；不再密集重试同链接|
|M018|正式摘要/订阅预览，2023-07-24首发；133既有研究、36关键词/4簇是作者报告|simulation_purpose=method_evaluation，编码综述自身用途，不把所述理论发展统一赋给全部语料；abstract_provisional保持|
|M019|正式页本次可读摘要/引言，首发2024-04-14；后续正文定位超时，静态403|simulation_purpose=method_evaluation；评价ChatGPT由叙事生成DES/SD/ABM代码，区别于LLM作为社会主体；不记全文精读或升级成熟度|

M019引言注明最后输出2022-12-16，摘要的不可执行/不简洁结论限早期版本与该叙事任务，不能外推当前LLM均不能建模；未审方法/结果/附件，不建十一项全文卡。M018133篇不是本库检索量，其历史语料不新增2022年前独立记录。M012的出版身份与2027卷期不代替首次在线日。

107条/64卡/157单元、42纳入/56候选/7前沿/2排除保持，1251分组操作。空分类5→3，均在M012；29日期待核不变。仅两个明确摘要用途编码，非方法效度或完整语义验收。64卡结构识别不变，原保护文件保持。

下一项CK转向未决正式日期队列，先核M020/AAMAS与M024/SIGDIAL的正式发布证据与日期规则；不能以会议起止日、仓库commit或PDF生成日冒充首发。M012/M019合法全文继续列缺口，不围绕同一失败入口重复请求。
