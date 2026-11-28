# 九类验证支持方法：用途、参照与论证边界

2026-11-28，M055 [正式HTML](https://www.jasss.org/27/1/11.html)方法/讨论定向精读；另取得32页正式PDF，仅核p12公式。见[阅读卡](../reading-cards/M055.md)、[九方法用途/局限](../data/validation_support_methods_CY.csv)、[原作者十concern×九方法表](../batches/method_round2/cy_validation_support_methods/table1_author_guidance.csv)。旧示例论文未作为本轮新增文献取得或纳入。

## 方法综述的证据身份

作者刻意选九类方法及代表实例，按经验区分foundational/advanced；并未提供系统检索、九方法效果基准或通用最低标准。Table1的X/x是作者判断的贡献潜力，不是验证通过率。本文按review_or_critique/conceptual_claim编码，不将引用的历史实例算作作者本人的实验。§4.31建议约10%资源、尽可能多种方法，是经验指南，不是本项目新硬性门槛。

|方法|主要用途|必须保留的局限|
|---|---|---|
|数据分析|管理、描述、理解输入/输出/参照资料|清洗与管理完善不等于模型有效，需相应技能与解释|
|Docking|和已有参照模型比较假设/输出|参照可能错，双方可能共享错误假设|
|Empirical/data-driven|比较资料或作者广义中的预期值|作者标签包含expectedvalues，不能直接沿用为独立真人证据|
|Sampling|输入空间、敏感性与交互|OFAT可能漏交互，空间/预算/采样设计限制|
|Visualization|检查、定位、沟通复杂过程|主观/尺度/注意偏差，需原始资料与绘图变换|
|Bootstrapping|已有参照样本的统计不确定性|重采样不是新独立经验样本，多重性仍须正确处理|
|Causal analysis/traces|追踪程序与异常行为的候选来源|共现/调试受逻辑和输入混杂影响，不单独证明真实因果|
|iGSS/EMD|在规则候选空间探索替代生成机制|受预先行为原语和fitness约束，不穷尽所有可能机制|
|Role-playing|真人承担任务/参与模拟后比较选择或结果|任务理解、训练、环境真实性和微观—宏观外推限制|

## 术语和主张不能自动迁移

该文role-playing主要是真人参与实验，与LLM角色提示不同；iGSS包括遗传编程搜索规则，不是LLM的同义词。§3.72关于人类行为难做empirical validation的强断言保留为作者立场，不作为本项目取消真人行为比较的通则。“硬科学是否接受定性方法”“bootstrap接受度”等概括也不当各领域当前共识或期刊政策。

方法/检验要与目标、参照和独立单位对应。M052的judge评价、M053的合成恢复/SBC、M054的数值误差控制，不能因作者都使用validation一词就归成同一种现实效度。跟踪日志可支持执行与规格对应，但统计共现和完整字段不能替代因果或人类效度；这里的traces也不是正式TRACE规范的同义词。

## 正式版本公式核查

§3.52的HTML和[正式PDF](https://www.jasss.org/27/1/11/11.pdf)p12均把(1-alpha)^n标为全族错误率。n=1且alpha=.05给出.95，与单检验错误率.05不符。独立、所有零假设为真且每项实际size相同时，至少一次误拒概率是1-(1-alpha)^n；不将此补式套用于任意相关检验。

[官方统计文档](https://support.minitab.com/en-us/minitab/help-and-how-to/statistical-modeling/anova/supporting-topics/multiple-comparisons/what-are-individual-and-family-error-rates/)也明确单一比较时全族错误率等于该比较alpha。该文档只作统计定义旁证，未作为2022+文献记录；搜索结果中的早期论文未取得/新增。[公式账](../batches/method_round2/cy_validation_support_methods/formula_check.json)保存原式、条件与核对，不沿用原式计算本项目错误率。

## 对研究路线的作用

本文支持按用途和可发现的错误选择互补证据，而不是对所有模型统一打勾。后续方法稿的切口仍是设计—实现—测量偏离能否被检出及其结论影响；应保留每次测试的模型/代码/数据版本。当前应用稿不因此改变冻结实验。JASSS发表方法指南支持共同体判断，不表明其作者须完成九项检查。

本批112条/69卡/175单元，48纳入/54候选/8前沿/2排除，1388分组操作；27日期/3空分类保持。3新增单元是综述指南编码，不是独立实证研究。下一项CZ固定来源，比较M052–M055、M025、EN11、M003的评价对象/参照/单位/允许主张，再更新综合与双轨路线并续目录摘要筛选。
