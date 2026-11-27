# TMP-ODD02 阅读卡草稿

**Grimm et al. Using the ODD protocol and NetLogo to replicate agent-based models.** Ecological Modelling 501 (2025),110967. DOI [10.1016/j.ecolmodel.2024.110967](https://doi.org/10.1016/j.ecolmodel.2024.110967)。

[White Rose出版PDF](https://eprints.whiterose.ac.uk/id/eprint/220675/1/1-s2.0-S0304380024003557-main.pdf)，CC BY。首次在线为2024-12-06（文章首面），卷期2025年2月。正文8页及表2–3全读；补充报告和代码链接已记录，未获取、未运行。**复现练习实际发生于2009年**，正式论文首次发表仍在2022+范围内；不能描述成2024年新实施的实验。

## 设计与结果

18个模型来自多领域，以未参与原模型开发者为复现者。任务包括重写ODD、用NetLogo实现、复制至少一项主要结果，并记录耗时与困难。15个成功、2个部分成功、1个失败；部分缺口需原作者帮助。多数模型较简单，平均5天（范围2–12天）不适于外推复杂模型。定位：第2–3节、表2。

## 有用的方法内容

缺参数、规则或调度说明会阻断复现。表3把完整模型说明、代码对应命名、运行环境、情景参数及分析脚本串成可检查材料。复现既可发现实现歧义，也可能为后续改变假设提供起点。标准不自动消除语言细节与平台默认行为，需要检验关键子模型。

## 证据边界与迁移

这不是有无ODD随机分组实验，不能把成功率与耗时解释成ODD的净因果作用。复制原模型输出亦不等于验证其现实解释。对Agent-EX可迁移的是把更新顺序、初始化、参数、代码映射和输出处理作为复现材料；不要求把现平台改成NetLogo。

## 分类建议

method_validation；reproducibility_and_reporting / theory_to_model_translation；empirical_method_test；controlled_comparison（与原模型示例结果比较，无无ODD对照组）。不因多模型多领域就自动标multi_context_validation。
