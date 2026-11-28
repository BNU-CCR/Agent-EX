# M012：摘要用途分类与正式版本获取边界（ES）

2026-11-28。复用CJ/CS/DV获取账后，检查出版社摘要、Delft正式版本入口及新增ASU合著者机构记录。未新增论文、全文卡或验证单元。主表237条、67正式纳入、87卡、252单元保持；三项空分类→0，25时间资格待核保持。来源操作增加9组至1780，操作数不是检索式数。

## 已核实与编码

[出版社](https://www.sciencedirect.com/science/article/pii/S1364815226003506)公开摘要/高亮与[ASU机构摘要](https://asu.elsevierpure.com/en/publications/twenty-years-of-the-odd-protocol-development-usage-extensions-and/)共同说明本文回顾模型描述规范的发展、使用与扩展，讨论规范如何支持交流与透明报告。由此暂定core_level=method_validity，primary_purpose与simulation_purpose=method_evaluation；后者编码本文的评价用途，不声称本文执行了模拟实验。依据限摘要，method_coding_status改为abstract_provisional；原core_method/报告规范标签保留。

摘要能建立“研究做什么”，不足以证明“方法有多成熟、获得何种验证”。成熟度/证据等级仍unclear，可迁移性和正文方法待核；无11项全文卡，不增加验证单元。该处理遵守既有分类规则的摘要暂定编码，并非为消除空值设研究默认值。日期资格与内容分类分别审计。

## 获取与版本

Delft记录列出13页、4.17MB、CC BY最终发表版本；指定PDF本次web不可达、静态请求403，5717字节HTML，响应hash见[获取账](../batches/method_round2/es_odd_abstract_classification/acquisition_manifest.json)，不是论文hash。UFZ ODD页只给2006/2010旧PDF，2026目标指向题录；这些旧文未作为本轮新读文献。Thünen定向搜索未返回结果，不记作该机构无文献。ASU新增机构入口可读摘要与卷期2027-01-01，没有直链正文。

ASU的2027卷期日期与KNAW的2026-10-16 early-online可同时成立；前者不能覆盖后者。出版社精确首发/正文未核，10月10日与16日差异继续保留。不能因为卷期2027排除已存在的2026在线版本，也不能将目录元数据当全文。

## 判断与后续

ODD叙事概览和技术描述可作为LLM模拟报告设计的候选参照；摘要尚不能证明提示、模型版本、失败恢复等LLM专属项已经被本文覆盖。用途分类补齐不表示内容验收完成。缺口仍是正式正文、补充文件、首发冲突和具体迁移边界；无新增合法可读入口前，不再反复请求同一Delft403。

下一项ET转向M003已取得作者版本与正式题录的资格/版本证据，按批准日期回退规则判断，不增设出版社PDF独占门槛；仍不执行作者模型或模拟代码。
