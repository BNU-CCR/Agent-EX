# MetaAgents正式出版日期与副本差异

批次BA，2026-11-27。既有[M042阅读卡](../reading-cards/M042.md)与27页出版排版副本复用，不重复下载作者文件或重做正文精读。

[Crossref正式记录](https://api.crossref.org/works/10.1145/3711032)由ACM登记：published-online、published-print、published及issued均为2025-05-02；created为2025-05-03，deposited为2025-08-21。采用明确published-online字段，不以注册/更新日期替代出版。响应HTTP200/20,212bytes，原响应SHA256及保留字段见[日期证据](../data/metaagents_date_evidence_BA.json)。web读取同API失败与实际HTTP200是不同操作，均记账。

作者托管副本首页/页脚标April2025，27页、DOI/作者/题名/卷期/文章号与正式题录对应，属于已读出版版式副本；这一日期显示与注册题录不同，保留在related_versions/date_basis及本报告，不静默改写PDF。实际出版社题录与PDF当日均403，不能声称取得ACM官方PDF或已逐字节认证副本。与既有M028同样，正式版式副本的身份对应不要求虚构“已核官方文件同hash”。

按[检索规则](../protocol/search_strategy.md)对published-online的规定，M042日期改confirmed/2025-05-02；结合AY已读出版排版全文，进入included。代码/精确模型snapshot、指标条件分母及内部文字差异仍未解决，不升级方法成熟度或人类效度。当前99条/58卡/117证据单元/43载体，41纳入、50候选、6前沿、2排除；日期待核26项。

AZ机器对照的candidate/date_pending和卡hash是该批快照，来源commit为edcf9ca；不回写成“当时已解决”。当前主表状态由BA变更账维护，hash可按相应commit读取核验。

下一批BB转WWW正式社会模拟方法先例及官方范围/当前要求；先去重既有记录，区分主会/伴随/研讨会，不把ACM共同出版或会议日期当足够证明。
