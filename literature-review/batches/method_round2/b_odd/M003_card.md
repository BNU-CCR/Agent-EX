# M003 阅读卡草稿

**Fachada et al., Can large language models implement agent-based models? An ODD-based replication study.** Ecological Modelling 517 (2026),111624. DOI [10.1016/j.ecolmodel.2026.111624](https://doi.org/10.1016/j.ecolmodel.2026.111624)。

读本为[作者终稿 arXiv v2](https://arxiv.org/html/2602.10140v2)，已读正文第1–7节。正式期刊工作与预印版本按同一工作处理。期刊卷期2026年7月已核，首次正式在线具体日待核，不能用Crossref建档日期代替。补充包入口已看，未下载、未运行。

## 方法定位

这项研究让LLM依据ODD写规则ABM代码。**LLM不充当模拟内部社会行动者**；生态捕食模型的代理仍遵守预设规则。它验证规格到代码的忠实度，适合作为Agent-EX实现审计的方法先例，不构成人类社会行为的外部效度证据。

## 设计和可支持结论

17个模型各生成6次。可执行实现再以两组参数、每组30次随机运行，与参考实现比较多变量时序。分阶段评分区分语法、运行、格式与动力学错误，说明程序跑通只是一层证据。多重校正后的统计检验用于识别输出差异；不能把未拒绝差异解释为全参数空间严格等价。证据定位：方法与评价节、结果节。

## 限制与迁移

基准只有一个已知模型、一个提示、两组参数，存在训练接触可能；模型快照具有时效性。托管与本地模型差异混合了模型能力差异，不能解释成部署效应。对本项目最有用的是分别保留规格、实现、运行输出和比较程序，并冻结状态更新及调度语义。拥有日志与可运行代码仍不足以证明实现忠实或行为真实。

## 分类建议

method_validation；reproducibility_and_reporting / validation_and_external_validity；empirical_method_test；controlled_comparison（参考模拟输出比较，非人类数据验证）。原始响应/代码/输出补充包未独立审核，复现与可运行性不作已验证声明。
