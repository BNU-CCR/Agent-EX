# 项目材料核对与版本边界

日期：2026-11-26（Asia/Shanghai）。读取分支 `codex/social-identity-network-2x3`，HEAD `dd4190c2ac380997149c29b5bcede104b6f95b83`。所有路径相对仓库根目录。本报告仅审阅既有研究说明与书目，不重新判断原始数据正确性，不修改实验、协议或论文正文。

## 实际阅读清单

| 文件或材料 | 实际读取范围 | 用途与权威边界 |
|---|---|---|
| `AGENTS.md` | 当前 10-01 路由与全部规则 | 新六格研究覆盖旧12格主矩阵；旧约束保留其历史含义 |
| `README.md` | 最新结果入口及新主研究段；历史快照标识 | 10-24 最新入口优先于本页较早“尚未运行”等文字；历史段落不作为当前结果 |
| `literature-review/CODEX_TASK_2022_ONWARD.md` | 第1–2节及研究范围要求 | 批准任务边界；唯一检索下限2022-01-01 |
| `docs/superpowers/specs/2026-10-01-identity-network-2x3-design.md` | 全文 | 2×3研究定义、共同输入、标签投影、保度随机化、串行事件、外生发布、操纵检验与冻结边界 |
| `docs/identity-network-protocol.md` | 全文 | 简短人类协议仍保留formal未决参数；不能把它当10-24批次精确参数表 |
| `reports/2026-10-24-n500-results/AI_HANDOFF.md` | 全文 | N500核心结果的范围与解释约束；无原始理由/曝光复算声明 |
| `reports/2026-10-24-n500-results/README.md` | 全文 | 实际批次设计、10seed终点/对比/轨迹概要、A/B未通过、表达层区别 |
| `reports/2026-10-24-n500-results/DATA_DICTIONARY.md` | 全文 | 方差、直方图、stock/flow/gap分母、配对差与统计重复单位 |
| `reports/2026-10-29-p0c-directionality/RESEARCH_DIAGNOSIS.md` | 全文 | P0-B固定材料诊断与331恢复案例；当时C3/C4为后续提议，不能写成已实施机制试验 |
| `reports/2026-11-01-ica-rq2-rq3-work/README.md` | 全文 | 后处理交付总览，102 horizon/1,890,000 unique events |
| `reports/2026-11-01-ica-rq2-rq3-work/METHODS.md` | 全文 | 历史事件重建、机会分母、seed汇总、后验置换、四种信息层与效度限制 |
| `reports/2026-11-01-ica-rq2-rq3-work/GAPS_AND_INTERPRETATION.md` | 全文 | 原身份操纵未通过、无已完成Gemma证据、无语义人工编码、内生接触与重叠horizon |
| `reports/2026-11-01-ica-rq2-rq3-work/progress.md` | 全文 | 已交付与远端同步说明，承接方法/结果的执行范围 |
| `reports/2026-11-01-ica-rq2-micro-macro-v1/CORE_FINDINGS.md` | 全文（65行） | 事件流守恒、议题差异、实际纯feed下方向性更新，作者解释与竞争机制 |
| `reports/2026-11-01-ica-rq3-communication-structure-v1/CORE_FINDINGS.md` | 全文（119行，首轮工具输出截断后补读） | B1全局收敛/B2超额局部相似、身份异质性、私人/flow/stock/feed分层 |
| `submission/` 五份DOCX | `word/document.xml`正文与References，检查footnotes；英文稿补读中间设计/结果段 | 只提取研究表述与书目，未检查图像内文字或版式；未视为已核查最终稿 |
| `paper-revision/paper.md` | 全文文字 | 另一篇《从流通阻断到生成置换：生成式把关与数字拟态环境的概率重塑》；不是当前网络实验稿 |
| `paper-revision/memo.md` | 会话日期、原稿引用与修订讨论相关段，未逐字审阅1555行历史会话 | 3月理论稿修订背景；不是11月实验交接 |
| `paper-revision/question list.md` | 核心问题与优先级、状态；未逐字审阅全部332行 | 理论稿修订问题，不转化为本任务的新增正文修订 |
| `paper-revision/revision-reports/paper_revision_context.md` | 全文 | 明示该目录为生成式把关理论稿 |
| `paper-revision/revision-reports/修订反馈报告.md` | 全文 | 原理论稿的概念、技术和引用风险，仅作背景 |

未读取/未核查：`submission/Peng_Zhang_DigitalJournalism_Sycophancy_Proposal.pdf` 的PDF版、DOCX图片内数据、`submission/ChatGPT 图像 2026年9月30日 11_33_41.png`、所有原始SQLite/模型响应全文、Git外受控理由库、后续本地未提交材料。没有把未读取材料写成已核验。

## 当前材料的承接与替代关系

1. 10-01规格与当前分支AGENTS明确新主矩阵为2×3，替代未来主研究的旧I×C×E 12格；未重命名或追认旧run。10-24结果包记录已绑定的N500/T30批次及其primary，不以10-01仍未冻结的概述否定批次已完成，也不宣称formal总协议已全部准入。
2. 10-24完整10seed结果替代更早两seed的局部观察作为退休T30总结。11-01分析在同批冻结数据上加入退休延续及另两议题，新增微观—宏观和传播结构解释；它扩展分析范围，不删除或重新授权10-24结果。T60退休前缀与T30重叠，不合并成独立重复。
3. 10-29诊断是当时可支持的证据与候选控制设计。11-01分析明确排除后续P0c与Gemma，因此不能把C3/C4提议、模型修复状态或另一历史任务结果混入本次Qwen比较。
4. 版本历史显示`submission/`与`paper-revision/`最近归档于10-01提交`91661b4`，`paper-revision/`最初分离于04-03提交`2a0f0d1`；结果材料最近有效更新为11-01 `c6de9ea`及交接`8a7fe80`。这个内容与历史证据比本地复制时间、文件名或文档标题更能判断是否为当前稿。

## 投稿材料逐件判断

| 文件 | 可提取内容 | 不可直接用于当前结果的内容 |
|---|---|---|
| `submission/从条件化生成到网络意见演化：大语言模型Agent如何重塑公共讨论多样性.docx` | 信息暴露—回应—再暴露问题链与多样性问题 | 写旧2×2×3、persona/连续性作用及Agent自主决定公开，不能描述当前六格结果 |
| `submission/从微观迎合到群体规范：大语言模型Agent网络中的社会影响与意见主流化.docx` | 迎合与网络递归影响的待检验问题 | 写旧12格并把缺乏新增依据的迎合、规范形成与论据收缩写成已发现；当前数据不支持这些机制断言 |
| `submission/选择性赞同还是迎合？大语言模型Agent网络中的社会影响与意见动力学.docx` | 2×3研究问题、区分趋同与迎合、私人/曝光/公开/理由联合检查的设想 | 早期身份强化“显著提高持续性”不是当前最小群体标签操纵通过的证据；“正式研究”字样不代表当前批次验证性准入 |
| `submission/Selective Agreement or Sycophancy Social Influence and Opinion Dynamics in Networks of LLM Agents.docx` | 2×3研究框架、四篇References中的三个2022+线索 | 早期200人/30轮weak vs lifelong图仍是旧pilot；“decide whether to express”不符合当前外生publish安排 |
| `submission/Peng_Zhang_DigitalJournalism_Sycophancy_Proposal.docx` | 同上，另有针对Digital Journalism的提案语境 | 标题中micro-level sycophancy是研究动机，不能用作已识别机制；200人pilot与当前N500批次不得混合 |

本任务不修改上述正文。投稿适配应依据实际已完成Qwen结果和现有分析，未识别的心理机制、真实社会效应及新增控制实验分别列建议。

## 现有书目线索与检索编码建议

三篇直接线索已列于[项目定位](../protocol/project_context.md)。其中Steiglechner等2023是补充传统规则式ABM种子的优先对象，可避免把2022年后误解成只收LLM。Cau等2025需要重点比较“向他者移动”与“缺乏事实依据的迎合”如何判定；Starnini等2026可提供概念分类，但综述不替代具体实验比较。

英文proposal中Postmes等2000保留为原文理论背景，排除本轮独立检索。理论稿memo另有Argyle等2023、Voinea2025、Simon2024等线索，未由本任务做外部书目或首发核验；只有对当前微观—宏观模拟、模型效度或传播情境有明确关联时再纳入，不因旧稿引用自动进入核心库。理论稿`paper.md`当前正文无完整规范References清单，不能把memo中的旧版引用当成当前已核查书目。

建议主表将“实际读入消息”与“网络潜在邻居”分别编码，将私有状态/flow/stock/feed分层；把初始态度、量表方向、模型偏好、议题语义、重复激活、发帖滞后作为机制比较字段。每篇文献按原文给出的趋同/共识/极化定义记录，不把终点方差自动翻译成心理认同或经典双峰极化。

## 本次核对没有完成的验证

- 未独立复算数字表或检查原始事件；报告中的数值均转述明确列出的已发布研究说明。
- 未确认现有引用的首次正式在线日期，三条线索不能仅据此进入“date_verified”计数。
- 未证明proposal中的200人pilot确实对应已归档原始run；因此只称proposal所述历史pilot。
- 未将11-01报告“无完成Gemma证据”推广为截至今日整个项目永远没有Gemma；本轮读取资料范围不足以评价后续外部分支或Git外数据。
