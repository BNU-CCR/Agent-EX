# 特征提取论文：参考文本、模型范围与指标制品

2026-11-28。作者公开仓库固定至[180c617e](https://github.com/siamak-khatami/QA-ABM-Extraction/tree/180c617e82e95ff21bd2a0767ed2e3bc86cab2f3)，提交时间2025-02-16。完整树元数据9276项/9231文件，非截断；本轮只取得七份源码/说明及两份JSON样本，均核Git blob与本地SHA256。没有下载四个旧模型PDF、模型权重、完整结果库或缓存，也未导入作者代码/反序列化pickle。当前快照不等价论文实际运行版本。

| 核查对象 | 发现 | 可作判断 | 仍未建立 |
|---|---|---|---|
| 参考答案 | Constants.PsAndOutputs按九prompt×四活动ABM提供36固定文本，评分直接读取 | 参考文本和使用路径可查 | 独立人工gold、来源/标注史 |
| 模型范围 | 分析列表十开放标签，另GPT4o；结果目录11模型 | 文字十开放模型有配置支持 | Figure8 DeepSeek额外行、全部snapshot |
| 结果索引 | 每模型180JSON路径，共1980；两样本各有0–9键 | 已存文件网格/两样本结构 | 19800有效、独立或已认证调用 |
| 统计单位 | 五温度相似度先合并，方差写入Std列 | 温度与重复波动混合；Std名称需谨慎 | 已发表图/缓存与该代码一一对应 |
| 纳入筛选 | commercial仅保留首行精确JSON围栏的回答，空集可写零 | 格式筛选可能改变分母 | 逐格有效量、零等同事实错误 |
| 新生成与缓存 | 生成JSON；开放模型无缓存分析路径期待TXT；树中无结果TXT，缓存优先读取 | 新生成路径与分析需对接，旧缓存需来源链 | 已实测复现失败或原论文结果无效 |

配置中commercial有gpt-4o、gpt-4-0125-preview、gpt-3.5-turbo-0125；main只选首个。生成LLMModels与分析LLMModels_不同，前者还存在相邻字符串拼接；不据此推断作者历史执行失败。模型加载有4bit NF4与RAG配置，但未固定revision；Requirements未锁版本。文件数量、代码可见和路径可查，均不能替代原始运行—缓存—论文结果对应。

详细行号与边界见[七项发现表](../batches/method_round2/dc_feature_extraction_artifacts/artifact_findings.csv)、[36参考单元索引](../batches/method_round2/dc_feature_extraction_artifacts/reference_inventory.csv)、[来源hash](../batches/method_round2/dc_feature_extraction_artifacts/acquisition_manifest.json)及[M056卡](../reading-cards/M056.md)。只细化VC176–178，不升级纳入/成熟度/效度，也不新增论文/卡/单元。当前114条/71卡/181单元、50纳入，1416分组来源操作；27日期/3空分类保持。

本批判断：辅助建模的评价链应记录参考文本、答案选择分母、温度与重复聚合、实际统计量及缓存来源。对于Agent-EX，保持既定协议和seed/run独立单位；不将此文的文件网格或cosine指标直接移作社会模拟有效性标准。

下一项DD回到CU剩余十项优先题名的摘要筛选，选择与方法/验证最相关的正式来源补入，避免以深入复现审计代替检索覆盖。上述未决项作为有界缺口保留。
