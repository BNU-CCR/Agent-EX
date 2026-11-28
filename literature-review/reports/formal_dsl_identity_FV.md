# FV：形式DSL模型生成的正式对照与版本日期

2026-11-28。新增M184候选与TOMACS发表地图条目，不新增全文卡/验证单元或投稿候选。论文为Using (Not-so) Large Language Models to Generate Simulation Models in a Formal DSL: A Study on Reaction Networks，Justin Noah Kreikemeyer、Miłosz Jankowski、Pia Wilsdorf、Adelinde M. Uhrmacher，DOI10.1145/3733719，TOMACS35(4)Article31。

## 正式身份、来源与实际阅读
[作者页面](https://justinnk.net/research/kreikemeyer2025using/)200明确链接[PDF](https://justinnk.net/research/kreikemeyer2025using/kreikemeyer2025using.pdf)、同一DOI、Zenodo15198397和text-to-crn仓库。PDF200，1281993字节，SHA256 c66ba818fa0203d42bda4b2677aa821d09b9ed0937e59b99e9f862841763f901；28页=ACM封面1页+文章27页，PDF正文CC BY4.0；作者网站页脚CC BY-NC-SA不覆盖PDF自有许可。

目前只读封面与第2页摘要/许可，封面已目视；方法、数据分割、指标、基线与用户研究尚未读。不把取得全文当完成全文阅读。

[出版社登记Crossref](https://api.crossref.org/works/10.1145/3733719)200匹配题名/作者/期刊，published-online为2025-09-12，print2025-10-31。PDF封面另标OnlineAM2025-05-28、Published2025-09-12；主表按最早出版社标示OnlineAM记2025-05-28，明确它是出版社接受稿公开阶段，非作者预印本，后续正式排版日期另列。两个阶段均在2025，时间资格不依赖把AM等同最终版；实际读本为后续正式排版，AM正文差异未校勘。不会删除较早AM或用VoR-only门槛筛除论文。

作者页面StartedJan1year0001是模板值，Nov1,2025是网页标记、Jul5,2026为页面更新；PDF下载Dec27,2025也不是论文首次在线日，均未拿来替代出版阶段。

## 方法相关性与尚待核准的主张
摘要称将Mistral7B微调为自然语言到反应网络DSL生成器，合成数据用于训练/评价，报告最高84.5%的ground-truth模型恢复及小规模用户研究，并承认小模型仍不及大模型。这些目前只是作者摘要主张，尚未核其分母、恢复等价性、训练/测试隔离、模型/提示版本或用户研究设计，保持candidate/abstract_checked/unclear。

该工作作为method_validation层的生成形式模型对照，不是LLM承担社会主体或人类外部效度证据。微调权重路线是其研究对象，不进入Agent-EX主矩阵或改变“不微调”边界。可迁移的潜在评价问题是语法、可执行、语义/动态一致、人工任务表现各自如何定义，需正文判断。

## 发表地图边界
TOMACS首次加入本库地图，仅凭这一篇正式方法先例；不认证持续LLM社会模拟共同体，不加入31条件投稿候选。两条定向ACM检索返回不相关结果，不能推断scope/指南或无相关论文。范围URL登记为待核入口，费用/索引/指南未核。作者材料链接不等期刊强制资料政策，代码与制品未下载或运行。

当前241条=78纳入/154候选/7前沿/2排除；91卡/267单元，62载体=41期刊/20会议入口/1仓库、31条件项；13日期待核，1954分组来源操作。正式纳入来源仍55期刊记录/35来源刊+23会议。

下一项FW直接精读已取得M184正式PDF：合成训练/测试构造、真模型恢复判据、基线/重复与用户研究，核84.5%分母及形式等价的实际含义，再决定纳入/等级并补方法综合。M019稳定全文另待新合法入口，完整目标未验收。
