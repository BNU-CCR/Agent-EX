# Agent-EX：文献检索项目定位

核对日期：2026-11-26（Asia/Shanghai）。仓库 `BNU-CCR/Agent-EX`；分支 `codex/social-identity-network-2x3`；读取基线 HEAD `dd4190c2ac380997149c29b5bcede104b6f95b83`。该提交已包含任务书，晚于其准备基线 `8a7fe80063cc44898c3fa42027ef6acb3423366c`。本页是既有材料的研究定位，未重新运行模型、复算原始实验或核验私有原始数据库。

## 当前研究问题与设计

研究对象是合成 LLM-agent 讨论网络中的意见与表达过程，主线为“信息接触→私人意见更新→公开表达→后续实际接触→群体意见结构”。当前主矩阵为**中性群体标签可见性 2 × 社会输入/网络结构 3**：A0 隐藏、A1 显示自身与来源 Blue/Green 标签；B0 无社会 feed、B1 逐节点保度随机网络、B2 固定 WS 网络。同 seed 共用人口背景、初态、分组、激活与外生发布安排；人口 persona 和近期私人历史保留，explicit consistency 关闭。标签可见性不是心理认同，WS 与随机图之差也不是单独的聚类因果效应。

已完成核心批次是 Qwen3-8B BF16/non-thinking、退休议题、N=500、T=30、10 matched seeds、60 runs、900,000 成功研究事件。每 sweep 为 500 次加权有放回激活，不能说每人更新一次。近期私人记忆 K=3，有限未读 feed B=4；所有人有 Round 0 公开帖，模型更新私人立场，只有外生 publish flag 为真才替换公开帖。该批 primary 是 sweep30 私人总体方差的同身份、同 seed 网络−B0 对比。它不改写 legacy 12-cell 协议，也不等于完成验证性主研究。

## 已有发现与解释边界

- 退休 T30 的四个社会输入条件均较匹配 B0 更不分散，平均方差降幅约 47%–51%；主要集中在 3/5 两档，4 分很少，故不能由方差下降直接命名中立共识、极端双峰极化或群体对立。原 Stage-A/B 身份操纵联合准入均未通过，不能以网络结果追认通过。
- 11-01 后处理拓展至退休 T60 延续 3 seeds，GM 与 AI 就业议题各 T60/2 seeds；102 个 horizon 轨迹共享部分前缀，仅有 1,890,000 个不重复网络事件。种子是独立重复单位；延续窗口、Agent、事件与 feed 槽位均不能增加独立样本数。
- 后处理将实际纯 3 feed 下的 5→3 与镜像 3→5 机会分开，报告方向性更新不对称；B1 的总体收敛较强，而 B2 的控制群体分布后的局部相似较强。两种结果可以并存。接触与历史内生，这些条件率不识别单条消息说服因果。
- 私人状态、当期公开 flow、每人最新公开 stock、实际读入 feed 是四个分母不同的层次。stock 滞后和私人—公开 gap 与外生发布/保留机制有关，不能直接证明策略性沉默、欺骗或迎合。150 事件理由案例库有文本，但语义机制编码尚待人工评估；不声称已证实迎合、信任或论据质量中介。

## 文献检索应优先回答什么

1. 传统 ABM 与 LLM 网络模拟怎样把微观更新规则、信息接触、公开表达和宏观意见分布联结起来；同化、从众、选择性赞同与迎合分别需要什么证据。
2. 无社会输入基线、固定消息/动态消息、模型/议题/初始化/量表映射控制如何区分社会互动与模型倾向；不能将递归训练的 model collapse 当作本项目固定权重讨论的已识别机制。
3. 全局集中、局部同质性、分群和极化如何分别定义；网络邻接与实际接触、标签与认同、私人态度与可见意见气候如何分别测量。
4. 人设、记忆、有限未读 feed、重复来源、陈旧公开帖及外生发布会怎样改变外部效度、解释与复现。真实公众和真人—AI 混合场景属于后续外推问题。

## 现有书目中的 2022 年起线索

两份英文 proposal 的 References 明列以下条目；下列为**项目书目线索，尚须出版社核对首次正式发表日期、作者和版本，不能仅据此计为已确认纳入**：

| 条目 | 项目书目所列载体/年份 | 项目书目 DOI | 对话价值 |
|---|---|---|---|
| Cau, Pansanella, Pedreschi, & Rossetti, *Selective agreement, not sycophancy: Investigating opinion dynamics in LLM interactions* | EPJ Data Science, 2025, 14:59 | `10.1140/epjds/s13688-025-00579-1` | 区分趋同与迎合，直接比较 |
| Steiglechner, Smaldino, Moser, & Merico, *Social identity bias and communication network clustering interact to shape patterns of opinion dynamics* | Journal of the Royal Society Interface, 2023, 20:20230372 | `10.1098/rsif.2023.0372` | 传统 ABM 的身份偏向×网络聚类种子 |
| Starnini et al., *Opinion dynamics: Statistical physics and beyond* | Reviews of Modern Physics, 2026, 98:035004 | `10.1103/j1zg-ddqv` | 意见动力学概念、方法和结果分类 |

Postmes et al. (2000) 仅是已有理论背景，不进入本轮独立检索或阅读卡。`paper-revision/` 属于另篇“生成式把关”理论论文，未作为 Agent-EX 当前结果来源。

## 实际阅读与缺口

已核对任务书第 2 节全部指定 Markdown，五份 `submission/` DOCX 的正文/参考文献文本，以及 `paper-revision/` 论文、memo 和修订问题资料；详细范围与冲突处理见 [project_material_audit.md](../reports/project_material_audit.md)。研究事实优先依据 10-24 结果包和 11-01 方法/发现/缺口说明；README 历史状态及 proposal 中与此不一致的说法保留为历史表述。本轮未查私有完整文本档案或 Gemma 后续成果，也未复核 DOCX 图像中的数据与 PDF 版布局。
