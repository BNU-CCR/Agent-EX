# CCR两项直接对照：正式身份与全文获取不是同一门

2026-11-27，BV。12项实际操作包括2次OJS文章页读取、2次PDF按钮点击、2次静态跟随跳转、2条查询、2次AUP页面读取和2次页面定位检查。最后两项为工具内页面检查，不是额外独立网络查询；累计1167分组操作不能解释为检索式数量。见[操作账](../batches/method_round2/bv_ccr_direct_comparator_access/source_operations.json)与[失败响应清单](../batches/method_round2/bv_ccr_direct_comparator_access/static_access_manifest.json)。

|记录|正式元数据与实际阅读|PDF路径及结果|
|---|---|---|
|EN03，[Influence in Motion](https://journal.computationalcommunication.org/article/view/9217)|官方OJS Published2026-04-21；两作者、DOI与GenAI专刊身份已重核；只读摘要|OJS`9217/7993`→DOI→AUP正式页；web跳转失败，静态最终403/5606bytes HTML，无PDF头|
|EN04，[Fake News Diffusion](https://journal.computationalcommunication.org/article/view/9203)|官方OJS Published2026-04-21；四作者、DOI与同专刊身份已重核；只读摘要|OJS`9203/7994`→DOI→AUP正式页；web跳转失败，静态最终403/5600bytes HTML，无PDF头|

AUP[EN03](https://www.aup-online.com/content/journals/10.5117/CCR2026.2.9.HUAN)与[EN04](https://www.aup-online.com/content/journals/10.5117/CCR2026.2.8.LI)经web可读摘要、OA标记和卷期，正文位置仅显示加载占位；静态403与web可读摘要分开记录。不能将OA标记、PDF按钮或“Full-Text”标签当全文已经取得。两个失败响应SHA256分别为`68f6d1597033f9d08f718671acb62c627a4c6a58e6e5a99853ffb5fd189985cc`与`002c4d4057d6adfa73a6879d69ff4fee7754995d9ad3f5f8ce8b4c51eb234514`，不是论文PDF hash。

## 摘要提出了什么，尚不能判断什么

EN03摘要强调语言主体、内生小世界重连、社区与说服影响。它是动态网络方法的直接邻接先例；这些是作者摘要主张，当前不据此认定因果识别、独立seed设计或现实验证已经成立，也不把重连塞入Agent-EX冻结矩阵。

EN04摘要强调不同网络下的转发决定、规则基线、Higgs来源社区和干预。实际网络拓扑、主体校准、真人资料比较口径、定量误差与留出设计仍需全文。经验网络作为环境，不自动证明生成行为或干预结论有外部效度；这只是待检验区别，不能在未读正文时断言作者做错。

OJS早期发表日不被AUP卷期、页面额外日期或搜索“几个月前”标签覆盖。两项继续candidate/摘要阅读，成熟度与证据等级未补；主表只扩展获取证据定位，未新建全文卡。当前106条/62卡/143单元、42纳入不变。

下一项BW取得并定向阅读EN04已有arXiv作者版本，明确其题名/方法与正式摘要关系；若不能取得，转其余可用方法卡。作者版本可以支持限定版本的比较，但不能替代未取得的正式全文，也不把正式摘要新增内容倒填旧稿。
