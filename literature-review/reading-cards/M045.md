# M045 — LLM辅助复现：跨平台对应与助手效果的区别

## 1. 书目、版本与范围
Boyu Wang; Andrew Crooks。Large Language Model-Assisted Workflows for Replicating Agent-Based Models。CSSSA2026官方节目已列题名/作者；实际读作者博客公开链接的17页稿件，非已核正式Springer章节。博客2026-10-26不是首次正式出版日期；固定README仍称currently under review，正式DOI/日期待核，candidate保留。全文来源及hash见获取清单BH；本批读pp1–15主文与表图，pp15–17参考仅定位，不另检索2022年前背景文献。

## 2. 问题及LLM角色
研究LLM能否帮助将既有ABM重实现为Mesa。LLM承担规划、实现、评价或协调的研究者助手角色；三套生成的模型不是以运行时LLM作为社会主体。跨语言/框架的模型对应是主要评价对象，不是人类社会外部效度。

## 3. 两工作流与比较设计
§2/图1：Ya-TASERPS用researcher-mediated；规划/评价LLM与实现LLM分工，人类监督并裁决歧义，文字记录任务/进度/决定。Sakoda与Slumulation用skill-assisted；预定义skills供协调LLM分派任务、生成子任务代理，歧义升级给人。流程、案例和可用来源同时变化，未报告同案例两流程或无LLM基线的交叉比较。三案例支持可行性，不能识别哪个流程更优或LLM的净收益。

## 4. 来源与实现权威
Ya-TASERPS以NetLogo v1.0.0为行为权威，论文/ODD辅助；Sakoda仅原文规则/八情境；Slumulation用论文及NetLogo实现。源代码、文档和原文的可获得程度决定能比较什么。作者§4承认按代码复刻可能连原bug一起继承；跨平台一致不能独立证明原理论正确。

## 5. Ya-TASERPS验证与分母
§3.1：空间/人口/风险初始化和school→after-school→evening→day时序检查，尤其回家移动与随后at-home更新。60天定向检查输入25/50/75，五类情境；完整实验六输入各三水平，3^6=729组合，每组合10次、1800天，即每被报告实现7290次运行。图2是分布形状与响应对应，不是729个独立模型/人类实验，亦未给统一数值等价阈值。作者明确结果非精确数值同一。

## 6. Sakoda验证边界
§3.2：8×8棋盘，两组各六主体，八情境各五次，共40次；按文中移动惯例、态度矩阵及距离权重检查。图3展示代表棋盘，比较空间模式，不是完全坐标或逐周期轨迹匹配。原文明确未作数值同一或统计比较，不将40次视觉检查变成统计通过率。

## 7. Slumulation验证及统计警点
§3.3/图4/表1–3：年内顺序、租金扩散与贫民区定义检查；基线30次轨迹/分布，图4部分均值有95%bootstrap区间。原论文100次的汇总与NetLogo/Mesa各30次比较；表2比较政治干预×开发活动四条件，表3人口增长2/3/4%。这些实验与基线可能重叠，未跨表加总独立run数。均值接近是所选输出/情境的描述对应，未核预设等价界限或全参数敏感性。

表1目视确认括号标standard deviation：城市贫民人口19.0(0.3)、19.9(2.8)、19.0(3.2)；城市贫民区数量125.0(2.0)、130.5(15.3)、125.7(19.3)。作者p9将较大SD可能归因于30而非100次；本项目判断：样本数较小本身不推出SD系统增大，SD和均值标准误要区分。当前未核原研究/制品中的统计定义，不能据此判定原文把SE误写SD或模型有错；保留为需核分母、聚合单位和字段来源的警点。

## 8. 成熟度与作者明确限制
empirical_method_test/ worked_example，限三个辅助重实现案例及其比较证据；不是validated_workflow或已证效率改善。§4明确没有记录研究者劳动/耗时、模型和工具用量（调用/token/runtime）或费用，因而不能确定是否减少时间、劳动、成本。没有完整敏感性测试；模型相对简单、外部数据较少，向复杂GIS模型迁移待测。稿件未给可核的完整LLM snapshot/配置账。

## 9. 制品与复现状态
论文链接[代码仓库](https://github.com/wang-boyu/csssa2026-abm-replication)，BH固定commit 1e9be1490bcbd5fa23632aeff9cbf872bd18957f（2026-10-04）。BH只读固定README：三实现、tests、skills、结果和NetLogo参照路径；说明NetLogo结果另行产生，summary命令组合既有NetLogo与Mesa结果。README hash已存，但未查代码、原始结果或paper版本对应，没有执行安装/测试/仿真。仓库有命令不能当复跑成功。BI续读12固定文件，核两平台各30run×51步；24组末步均值/样本SD重算与summary一致，城市比例乘100后表1两实现48数值按舍入对应。仅基线算术一致，不代表全论文重跑。

## 10. 对Agent-EX的方法启发（本项目推论）
这提供LLM研究助手工作流的实际案例，修正“全周期建议只有概念、没有任何实践”的过强概括；本库此前并未据选定11卡宣称全领域空白。可研究的更精确问题是：在同一建模任务、来源与资源条件下，辅助流程是否减少设计—实现—测量偏离，以及是否改善独立复现，而不是单纯增加日志或让模型自评。与Agent-EX运行时社会主体研究分轨，不修改冻结协议。

## 11. 获取、缺口与下一步
17页/1685932bytes/SHA256 89a521b3aa24f274b3bea0f02ae7d9281e43450f4e8d0a9fcb08b85b52ca1914。Dropbox预览HTML与dl=1实际PDF分别记账；下载HTTP头未保留，不能补造状态码。正式出版身份、paper对应commit、LLM配置/交互记录、Slumulation统计量/运行对应待核。BI已完成限定静态核查，详见[制品报告](../reports/replication_workflow_static_audit.md)。旧Paper列统计定义、NetLogo基线逐runseed、助手实际配置及表2/3原始结果仍待核；未执行作者代码。下一批BJ补Information Sciences/Expert Systems with Applications。
