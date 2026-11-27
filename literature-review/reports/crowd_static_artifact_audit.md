# Crowd固定代码快照：模型边界从哪里进入？

2026-11-27批次AF。公开仓库bilkent-sna/crowd固定为`6536588ccb056897f3b88b28dba82dcde6752e2b`（2025-07-15）。此提交晚于首次发表2025-06-04、早于December卷期；没有证据把它等同论文运行版本。8个源码/配置文件的Git blob及SHA256已核，见[crowd_artifact_audit_AF.json](../data/crowd_artifact_audit_AF.json)。未安装、导入、调用模型或运行实验；以下是静态控制流/配置判断，实际触发频率与结果影响未测。完整仓库、GUI和NDLib依赖未审。

## 模型输出到动作的边界

[gen_agents.py:147–162](https://github.com/bilkent-sna/crowd/blob/6536588ccb056897f3b88b28dba82dcde6752e2b/crowd/docs/examples/generative_epidemic_agents/gen_agents.py#L147-L162) 先判断响应是否包含no、再判断yes，否则返回False；位置更新在 [gen_agents.py:110–119](https://github.com/bilkent-sna/crowd/blob/6536588ccb056897f3b88b28dba82dcde6752e2b/crowd/docs/examples/generative_epidemic_agents/gen_agents.py#L110-L119)，False意味着grid/外出。缺少Response字段与异常默认值能进入实际行为，不能将其统一统计为正常“选择外出”。这不是失败率测量，也未证明论文使用该路径。

[gen_agents.py:204–280](https://github.com/bilkent-sna/crowd/blob/6536588ccb056897f3b88b28dba82dcde6752e2b/crowd/docs/examples/generative_epidemic_agents/gen_agents.py#L204-L280) 外层异常写一次等待重试，但底层生成异常被捕获并返回None，随后解析异常置No；通常这条失败路径不会触发外层异常重试。不能仅见“Retrying”字符串便认定完整可靠重试。保存Prompt/Output与具备严格schema、失败状态和幂等恢复是不同能力。

## 调度、状态和计数

[project.py:298–321](https://github.com/bilkent-sna/crowd/blob/6536588ccb056897f3b88b28dba82dcde6752e2b/crowd/crowd/project_management/project.py#L298-L321) 将疫情例映射到DiffusionNetwork。其 [DiffusionNetwork.py:78–151](https://github.com/bilkent-sna/crowd/blob/6536588ccb056897f3b88b28dba82dcde6752e2b/crowd/crowd/models/DiffusionNetwork.py#L78-L151) 在epoch0跳过前/后钩子而仍调用扩散迭代；[BaseDiffusion.py:121–178](https://github.com/bilkent-sna/crowd/blob/6536588ccb056897f3b88b28dba82dcde6752e2b/crowd/crowd/models/BaseDiffusion.py#L121-L178) 第一次迭代仅返回初态。故“50 epochs”不能未经检查就称50轮LLM决策，已读控制流最多49次before钩子（若未早停/异常）。这是静态上界，不是已确认调用量，更不据此推翻论文实际5000调用记录。

BaseDiffusion在循环中即时改graph节点属性，数值status字典循环结束才整体替换；不能笼统称所有可见状态都同步或都有事件原子保证。CustomSimNetwork另一条路径为随机顺序执行agent方法、共享可变图，不能与Diffusion路径混为一套调度。

## 配置、运行版本与复现

[gen_agents.yaml:1–24](https://github.com/bilkent-sna/crowd/blob/6536588ccb056897f3b88b28dba82dcde6752e2b/crowd/docs/examples/generative_epidemic_agents/gen_agents.yaml#L1-L24) 显示Susceptible→Infected依赖location/grid和概率，未在配置中指定感染邻居条件；映射见 [DiffusionNetwork.py:286–298](https://github.com/bilkent-sna/crowd/blob/6536588ccb056897f3b88b28dba82dcde6752e2b/crowd/crowd/models/DiffusionNetwork.py#L286-L298)。未固定NDLib版本并核其实现前，不声称完整传播机制或真实输出已被证明错误。示例脚本还加载已有llm2项目，创建/加载本YAML的代码被注释，因此不能认定这份配置就是实际运行所用。

示例明确Mistral-7B-Instruct-v0.3及采样温度0.1/do_sample，但没有固定权重revision。[setup.py:5–20](https://github.com/bilkent-sna/crowd/blob/6536588ccb056897f3b88b28dba82dcde6752e2b/crowd/setup.py#L5-L20) 依赖无精确版本；BaseDiffusion默认seed=None且上层构造未传具体seed，所读初始化/示例使用Python/NumPy/模型采样的多重随机源，未核到完整冻结清单。README的安装方法不是论文环境锁；这些仍是复现缺口，不是已经重建失败。

## 方法与投稿判断

与M003规格—代码—输出分离和M030观测分布范围相连：框架钩子、配置文件、日志是审计入口，不能独立证明模型实现忠实、错误处理无偏或结果可复制。后续方法稿可研究解析失败被转换为实质动作时的误差，以及观察边界与提交语义如何影响可复现主张；目前只是研究需求，未改Agent-EX冻结协议或执行实验。

本批0新增文献/卡/纳入，新增4静态证据单元（非实验）、14来源操作。下一批AG继续41命名入口，优先ACL/EMNLP正式方法评价先例与官方投稿/制品规则；不反复展开同一失败下载。
