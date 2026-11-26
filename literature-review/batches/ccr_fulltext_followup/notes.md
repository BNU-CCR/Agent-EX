# CCR正式全文入口补查与版本冲突

日期：2026-11-26（Asia/Shanghai）。只补查EN03/EN04，不修改主表或英文批次。状态：**取得正式PDF入口及部分页面内容，尚未完成整篇精读，不升级为全文已核查。**

## 有效入口

Crossref实际返回的`link`字段包含VoR crawler PDF链接。`requests`对AUP均403，但`web.open`实际取得PDF；因此403不是资源不存在。

- EN03：[正式PDF](https://www.aup-online.com/content/journals/10.5117/CCR2026.2.9.HUAN?crawler=true&mimetype=application/pdf)，40页，首页标`COMPUTATIONAL COMMUNICATION RESEARCH 8.2 (2026) 1–40`、DOI `10.5117/CCR2026.2.9.HUAN`，题名为*Influence in Motion: Tracing Persuasive Dynamics via LLM based Multi-Agent Networks*，Ming Huang、Zi-Ke Zhang，浙江大学。网页工具初次成功后再次find出现超时；未完成全部方法/结果读取。
- EN04：[正式PDF](https://www.aup-online.com/content/journals/10.5117/CCR2026.2.8.LI?crawler=true&mimetype=application/pdf)，29页，首页标`COMPUTATIONAL COMMUNICATION RESEARCH 8.2 (2026) 1–29`，题名、作者与DOI一致。已定向核查pp.11–18方法/验证部分，未全篇精读。

## 必须集中校正的差异

1. **EN03网页摘要与正式PDF首页摘要不一致。** 网页摘要突出三阶段、H1/H2/H3与persuasive influence；PDF首页突出Parsons/Coleman框架，明确是`exemplary simulation run`与preliminary方法展示。不能直接把网页摘要的验证强度或全部发现移到PDF卡。需重新读正式方法、运行数和结论，再统一最终记录。本轮仅标冲突。
2. **EN04的2024预印本不能代替2026正式版。** [arXiv:2410.13909v1](https://arxiv.org/abs/2410.13909)由相同四位作者发布于2024-10-16，题名缺`Fake`，只有v1可见；正式关系尚未见Crossref relation声明。2024 HTML的Implementation使用GPT-3.5-Turbo-1106、网络规模含288/300，而正式PDF pp.11–12为gemini-2.5-flash-lite、三种合成网络均300。正式版p.17报告Higgs 1,905人子图、8独立模拟；因此这是明显有实质差异的版本线索，**不合并为“同版本作者稿”，也不新增独立研究计数**。
3. 正式版EN04 p.16–17把经验验证限定为face validity，未有逐用户分享真值；这比“真实用户行为已验证”更窄。p.13还存在移除Big Five后扩散未启动的提示消融，应在后续正式卡中核对，暂不据此完成机制评判。

以上PDF事实依据为各自正式来源；未读字段保留pending。访问链与HTTP结果见[attempts.json](attempts.json)。不保存临时带expires/checksum的docserver跳转为长期入口。

## 日期提醒与接续

Crossref两文deposit有`published-print=2026-09-14`，但无`published-online`；AUP页面存在其他时间字段。不能据Crossref印刷日期覆盖已核验在线首发，正式首次日期仍由root集中协调现有英文记录。下一步是正式PDF全文与网页摘要的逐项核对，再决定修订阅读状态、数据和卡片；本轮不静默升级。
