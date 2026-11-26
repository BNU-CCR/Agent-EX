# 投稿制品政策与科学效度分开

2026-11-26批次R定向核官方政策，逐条来源、语气与核查范围见[政策证据表](../data/journal_policy_audit.json)。这是渠道证据补齐，尚未逐项审计Agent-EX稿件或运行制品。

|载体|官方要求/期望|官方建议|不能推出什么|
|---|---|---|---|
|PLOS ONE|最小复现数据与DAS；作者代码有发表时开放期望，核心代码可成为发表条件；限制须说明|持久标识仓库、明确许可和运行文档|无例外公开所有原始资料；一个GitHub链接已充分复现|
|Scientific Reports|DAS、投稿审稿访问；核心自编代码/算法须按编辑/审稿人请求提供，Methods有Code availability及限制说明|公开仓库；正文4500词和11排版页为建议尺度|所有代码均无条件开源；正文4500是无例外硬性总字数上限|

来源：[PLOS数据](https://journals.plos.org/plosone/s/data-availability)、[代码](https://journals.plos.org/plosone/s/materials-and-software-sharing)、[指南](https://journals.plos.org/plosone/s/submission-guidelines)；[Scientific Reports政策](https://www.nature.com/srep/journal-policies/editorial-policies?error=cookies_not_supported)、[指南](https://www.nature.com/srep/author-instructions/submission-guidelines?error=cookies_not_supported)。目标段落见证据表；不同条款的例外/强度不能混写。

本项目推论：需要能够把论文图表追到分析输入、冻结版本和对应运行制品；Git不收大规模原始结果不妨碍在适当归档提供数据，但manifest/hash/定位本身是否足以重现每项结论仍须实际检查。代码可取得解决的是检查条件，不能代替正确实现、稳健性、经验校准或独立外部效度。此处没有新增实验、修改机器协议或判断项目已经满足投稿条件。

还缺两刊APC、独立索引及其他文章类型细则；Nature Communications详细政策未在本批核查。下一批S从Social Science Research官方目录、范围和2022+方法先例开始，保留有界检索结果与获取失败；再回到版本/日期缺口。
