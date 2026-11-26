# 两篇最相近研究的交叉核查

核查日期：2026-11-26（Asia/Shanghai）。本报告对照出版社主文、方法和图注，以及Agent-EX已发布结果说明；不复算他人数据，不执行新模型实验。判断是文献交叉检查，不是独立人工双人筛选。

**结论：Agent-EX可以提出“固定关系与外生表达安排下，实际接触、个体更新和不同可见意见层怎样连接”的具体增量。不能再把首次网络模拟、首次区分互动与模型倾向、首次网络结构比较或首次发现趋同作为贡献。**

## 来源与阅读范围

- Brockers, V. C., Ehrlich, D. A., & Priesemann, V. (2026). *Disentangling interaction and bias effects in opinion dynamics of large language models*. Nature Communications, 17, 10077. 首次正式发表2026-09-22，DOI `10.1038/s41467-026-77340-3`。已读[出版社主文](https://www.nature.com/articles/s41467-026-77340-3?error=cookies_not_supported)的结果、Discussion、Methods与图注；重点定位Methods “Simulating discussions with LLMs”与“Bayesian model”、Fig.1/3/4/6。
- Piao, J., Lu, Z., Gao, C., Xu, F., Hu, Q., Santos, F. P., Li, Y., & Evans, J. (2026). *Emergence of polarization in networks of large language model agents*. Nature Communications, 17, 11463. [出版社页面](https://www.nature.com/articles/s41467-026-78228-y?error=cookies_not_supported)记首次正式发表2026-10-08、Version of Record为2026-11-06；按前者判定时间。已读主文与Methods M1–M5、Fig.1–4图注；另取得[清华机构PDF](https://fi.ee.tsinghua.edu.cn/~gaochen/papers/Nature2026-LLM-Polarization.pdf)并核对题名/DOI，PDF为14页Article in Press，版本日期以出版社为准。

两篇补充PDF在网页工具中均超时；Piao机构PDF可用，但不能替代其独立Supplementary Information。下表凡涉及补充内容，仅按主文明确指向的范围记录，不声称已独立核查补充实验或代码。

## 关键设计核对

| 项目 | Brockers等 | Piao等 |
|---|---|---|
| 基本过程 | 双人、5轮、12题、6模型；Methods报每题25次双人讨论、每人5种初态 | 主网络N=1000，个体机制实验N=100；多模型补充 |
| 模型对应 | Qwen是Qwen2.5-7B；GPT是gpt-4o-mini，不与本项目Qwen3-8B混同 | 主文GPT-3.5；其他模型见补充实验，不能借作Agent-EX稳健性 |
| 网络 | 固定双人对话，不研究群体拓扑 | WS初始化后自主选择/保留交往关系；另有static/random替代比较 |
| 主要控制 | 正/反命题测量、未初始化topic prior；层级贝叶斯分解互动与三种偏向，另有微调个案 | 同意见双人单步诊断、自我一致性检查/再生成；网络与个体干预 |
| 无社会输入 | 主文未呈现与Agent-EX B0同构的匹配长期无feed条件；“模型单独先验”是另一种控制 | 主文未呈现同构B0；同意见双人诊断仍有交流 |
| 测量 | 五档响应分布的期望与熵；测量问句不写入对话记忆 | 五档自报；polarization指标为距中立点平均绝对距离 |
| 重复与误差 | 对话数据用于层级拟合；25不能直接编码为25 matched seeds | Fig.3部分n=5为末5时点；Fig.4 n=6为6时点，均非6独立seeds；其他图另按事件数 |

表中事实分别见[Brockers Methods与Fig.1–6](https://www.nature.com/articles/s41467-026-77340-3?error=cookies_not_supported)和[Piao Methods M1–M5、Fig.3–4](https://www.nature.com/articles/s41467-026-78228-y?error=cookies_not_supported)。**未在主文呈现不等于研究从未做过**；完整no-social基线与独立运行重复数仍需补充文件/代码核查。尤其不能从图注时点n反推整篇论文没有重复运行。

## 对Agent-EX增量的判定

以下为本次执行者的适配推论，Agent-EX依据为仓库`reports/2026-10-24-n500-results/README.md`、`DATA_DICTIONARY.md`及11-01 `METHODS.md`、RQ2/RQ3 `CORE_FINDINGS.md`和`GAPS_AND_INTERPRETATION.md`。

| 可提出的具体增量 | 目前已有依据 | 必须保留的限制 |
|---|---|---|
| 将模型双人响应问题放到具有实际接触记录的固定关系群体过程中 | 事件前态、已读公开帖、后态、发布标记可连接；退休10 matched seeds | “扩大到网络”本身不足以区别Piao；应突出研究对象与过程比较，而非规模 |
| 在同seed六格共同初态与安排下，估计社会输入条件相对无feed的群体差异 | B0/B1/B2；退休T30四个社会输入−B0方差对比 | B0只能控制该批配置下无社会feed的演化，不能把模型倾向从所有互动过程中剥离，也不代替Brockers的参数分解 |
| 固定WS与逐节点保度随机图，研究全局集中和分布校正后局部相似的不同排序 | 11-01 B1全局收敛较强、B2超额局部相似较强 | B1/B2同时改变实际内容、重复来源、路径结构；不识别“纯聚类效应”，更不宜与动态网络结果简单对立 |
| 明确区分私人状态、当期表达flow、最新公开stock和实际feed | 事件重建、发布滞后、四层分布与分母 | 发布外生，不能称自主沉默螺旋或策略性表达；stock差异不是心理不真诚 |
| 用真实曝光机会分母连接方向性微观更新与群体再分配 | pure3下5→3与pure5下3→5分开，流守恒与终点分布 | 真实feed与历史内生；守恒是核算关系，不是递归放大或说服机制的独立识别 |

## 当前不能写成贡献或结论的说法

1. **“既有研究没有区分互动与模型偏向”。** Brockers直接以此为题；Agent-EX应说明自己采取的是群体条件比较与事件分层，而不是声称完成更彻底的偏向净化。
2. **“既有研究只有少量Agent或没有网络结构控制”。** Piao已覆盖规模、动态关系及静态/随机替代。我们的N500也不能被称为规模超越。
3. **“趋同与极化两种结果相矛盾，因此我们推翻Piao”。** 初态、议题、模型、提示、更新/关系规则和指标不同；私人方差与距中立点距离也可同时下降或上升。先比较操作定义与过程，不能比较术语后直接判冲突。
4. **“身份线索产生心理认同/信任并改变收敛”。** 本项目A/B联合准入未通过；可保留条件差异与零/异质性结果，不把标签操作包装成已验证心理机制。
5. **“已识别迎合、递归反馈的独立贡献，或排除了模型固有方向”。** 现有数值移动和案例库不等于人工语义机制编码；无独立动态内容回流干预，不能把观察到的再暴露机会当作已识别放大效应。
6. **“主研究具有跨模型普遍性或可预测真实公众”。** 本轮当前可引用的已发布Qwen包有模型与议题边界；他人多模型证据不能借作我们的稳健性，双方也均不能由合成系统自动推出真人干预效果。

## 供后续综合报告使用的贡献定位

Agent-EX当前更适合把问题收束为：**在固定传播关系、有限未读接触与外生发布条件下，群体整体集中、网络局部相似和公开可见意见为何呈现不同变化；这些变化如何由有方向的不对称更新逐步积累。**这比“LLM会趋同”更具体，现有数字材料也更能支持。该定位仍是文献比较后的建议，不改写已冻结结果排序或现有论文正文。

优先补齐的是解释和核对工作：统一三篇研究的极化/集中定义；核对两文补充材料的重复与对照；将Agent-EX的操作边界和seed级证据写清。新增自我一致性干预、跨模型试验或固定/动态内容回流对照应单列为后续实验建议，本任务不执行。
