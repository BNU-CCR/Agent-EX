# 模型清单、结果表与固定制品的对应

2026-11-28。复用CS已保存的作者v2与Zenodo v3；本批新访问仅[版本元数据](https://zenodo.org/api/records/19915447/versions)。没有运行模型或统计检验。[机器核查](../batches/method_round2/ct_model_result_correspondence/correspondence_audit.json)与[逐模型对应](../batches/method_round2/ct_model_result_correspondence/model_correspondence.csv)保存范围和hash。

核对后的判断比CS更精确：作者Table3的16模型×6试次共96个评分，全部与固定包results_final.csv一致。Qwen3在Table1列出，却也没有进入Table3；因此目前不是“已发表结果表与补充包96行冲突”，而是模型范围清单与所展示结果范围未闭合。原因未说明，不推断被隐瞒、表现差或结果错误。

35个实现目录各有两个参数组、每组30个CSV，合计2100。所有这些CSV均有4001行数字记录和六输出列（另含CSV索引列）；这里只检查表头和行数，未复算数值、Energy检验或认证独立运行。形状合格与统计/机制忠实是不同证据。

官方版本接口列出2026-02-08、03-30、04-30三条版本，文件hash彼此不同。只读元数据，未下载旧ZIP；不能用相近大小断言内容相同，也未在这些记录描述中找到Qwen3解释。正式期刊文本仍未取得。

当前108条/65卡/163单元、44纳入不变；细化VC161而不新增“独立实验”，来源操作1338。下一项CU转JASSS2022年以来官方目录的有界检索与现有库对账，补足发表共同体覆盖；M003原因列待核，避免重复追查同一访问障碍。
