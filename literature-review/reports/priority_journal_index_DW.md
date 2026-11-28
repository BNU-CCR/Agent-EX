# 两本优先期刊的独立索引证据

2026-11-28，DW。仅核JASSS、Computational Communication Research（CCR），不将两刊结果推广至其余条件候选。核查按ISSN匹配；文件来源、响应、字节数和SHA256见[获取清单](../batches/method_round2/dw_priority_journal_index/acquisition_manifest.json)，匹配行见[DOAJ](../batches/method_round2/dw_priority_journal_index/doaj_matched_rows.json)、[Scopus](../batches/method_round2/dw_priority_journal_index/scopus_matched_rows.json)及[结构化结论](../batches/method_round2/dw_priority_journal_index/index_evidence.json)。约26MB的原始CSV、约27MB的XLSX只在本地临时目录，未进入Git；匹配行和hash可用于复核快照，不能保证官方未来下载仍返回同一字节。

| 刊物/ISSN | DOAJ官方公开CSV | Elsevier官方Scopus名单 | WoS具体子库 |
|---|---|---|---|
| JASSS / 1460-7425 | 精确命中 | source ID 15591；Active；coverage 2000–2026；主表Excel第23469行 | 出版者自述SSCI保留；本次未独立确认 |
| CCR / 2665-9085 | 精确命中 | source ID 21101152530；Active；coverage 2019–2026；主表Excel第10051行 | 未独立确认；不写“未收录” |

DOAJ文件的HTTP Last-Modified为2026-10-28 23:36:19 UTC，下载日为11月28日。[DOAJ公开CSV说明](https://doaj.org/docs/journal-csv)说明其公开文件可能滞后，故这里只确认该快照有相应目录记录。[Elsevier官方Scopus内容页](https://www.elsevier.com/en-au/products/scopus/content)实际链接到`ext_list_Oct_2026.xlsx`；取得文件后读取所有工作表，两刊均命中`Scopus Sources Oct. 2026`主表，非仅“已接受待加入”表，且两行的discontinued字段为空。官方说明名单按月更新；不把October快照称为实时November源页面核验，也不据coverage年份推断每篇论文都已入库。名单的2000起始年属于刊物索引元数据，不是把2022年前论文纳入研究库。

## 字段冲突与使用判断

DOAJ的JASSS出版者为European Social Simulation Association，Scopus该行仍为University of Surrey；保留原值，不自行认定转移日期或替代更新。DOAJ费用字段列EUR1000、GBP800、USD1300，而本次再次取得并阅读的[JASSS官方提交指南](https://www.jasss.org/v02/page_content_includes/_include_submit.html)仍为EUR800，另加适用VAT，与BU一致。投稿预算依据当前刊方指南；目录旧费用不覆盖该指南。减免须按指南条件申请，未推断作者资格。DOAJ行中的周期等自报元数据不是本项目测量的审稿时间，不作投稿速度估计。

这些结果补强两刊的可见度证据，但不证明文章质量、接受概率或Agent-EX投稿适配，不改变两轨策略的选题与验证要求。DOAJ与Scopus也不能证明SSCI、SCIE或ESCI归属，JIF不作子库替代证据。

## 未能核实的边界

[MJL](https://mjl.clarivate.com/home)通过网页工具只返回交互壳；[JASSS ISSN记录](https://portal.issn.org/resource/ISSN/1460-7425)与[CCR ISSN记录](https://portal.issn.org/resource/ISSN/2665-9085)返回Anubis访问阻止。尝试在应用内打开MJL时工具报告本聊天本地浏览器不可用，未创建可操作页面，未绕过访问限制。搜索缓存中的ISSN索引列表只作发现线索，不当作实时Scopus核验；本批已用Elsevier原始名单补足Scopus证据。WoS子库缺口仍保留，不由检索未命中反推不存在。

## 交付与接续

两张方法发表表仅更新两刊的索引证据、日期、待核事项和说明；文献230条、79卡、213验证单元、57正式纳入及分层/成熟度均未改变。新增9项分组来源操作，总数1656，非9条检索式或全部工具调用计数。DV验收及词标表保留为固定历史快照，不悄改其旧统计。

下一项DX精读M147的参数识别与恢复验证，区分参数恢复、行为拟合和现实外推；现有索引访问边界不阻塞方法主线。实际投稿前须再核目标刊索引及政策。本次没有运行实验或改动冻结研究协议，完整长期目标仍进行。
