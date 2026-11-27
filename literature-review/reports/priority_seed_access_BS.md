# 指定方法种子：正式来源与获取边界

2026-11-27，接续BR九问题综合。实际执行2条检索、3次web打开、1次机构文档链接点击和2次静态请求，共8项分组操作；不把搜索摘要数量或失败次数当论文数。见[操作账](../batches/method_round2/bs_priority_seed_access/source_operations.json)和[静态请求清单](../batches/method_round2/bs_priority_seed_access/static_access_manifest.json)。未新增论文、卡、正式纳入或验证单元。

## M012：找到正式版本托管入口，尚未取得文件

[TU Delft机构页](https://research.tudelft.nl/en/publications/twenty-years-of-the-odd-protocol-development-usage-extensions-and/)可以读取，列出正式版本、13页、4.17MB和CC BY，并链接到[机构PDF](https://research.tudelft.nl/files/316689002/1-s2.0-S1364815226003506-main.pdf)。机构页的文件大小是展示值，不是本批下载大小；发表状态为2026，未列精确首次在线日。

文档链接web获取403；静态请求同为403，5717bytes，HTML类型且无PDF头。失败响应SHA256为`2802dd6851864d431befa7a02a44cc136bee6dc31498718915cf44d97864362c`，不是论文hash。[出版社页面](https://www.sciencedirect.com/science/article/pii/S1364815226003506)搜索可见2027年1月卷期，直接打开403；卷期不得替代首次在线日。ESS预印本检索另显示2026-07-09/v1，不能替代正式版本。

因此M012仍摘要候选，现有机构日2026-10-16继续待正式确认；不新建全文卡、不填其三个空分类字段。CC BY是机构展示的版本许可，未据此宣称已核PDF页内许可或取得所有附件。

## M003：卷期及正式身份仍不足以确认首发日

[出版社摘要页](https://www.sciencedirect.com/science/article/abs/pii/S0304380026001523)搜索返回卷517、July2026、111624，直接web打开403。已有主页面静态请求403，832981bytes HTML；局部检查无Available online、datePublished等日期字段。响应SHA256为`a66a548dfe4f54a2c288b0b71baad8ac87268bc9fd5bdf1810f0bfe6d440d1db`。

两机构检索结果可发现正式版本/卷期线索，但本批没有取得正式正文或新增精确首发证据。保持原作者v2阅读依据、候选与date_pending；不把搜索“4个月前”标签当首发日，也不重述作者版本等价声明为独立校勘结论。

## 判断与接续

本批把M012从泛泛“全文未得”细化为可定位的正式托管入口与文件级失败证据；没有解决全文和日期门。M003同样不能凭重复的卷期元数据升级。两个缺口不阻断其他已批准任务，不继续对同一403链接密集重试。

累计106条、62卡、143证据单元、42正式纳入、1143分组操作；29日期待核和5空分类保持。下一项BT复核M002/M004/M005早期方法卡的实际内容与任务书十一项对应，保留概念批评、经验验证和正式/作者版本区别；如属于首轮保护范围，仅增补伴随文件。优先投稿政策及可访问的新来源继续按队列推进。
