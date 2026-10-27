# P1｜第二模型选型与部署准备

状态：官方文档与只读硬件初审完成；未下载模型、未启动服务、未实测吞吐或输出有效率。候选不是部署批准。

## 已核实的本机资源（2026-10-27）

RTX5090，32607MiB显存，当前已用29278MiB/剩2834MiB。Qwen原服务占用GPU，localhost:8000，max-model-len8192、max-num-seqs8、GPU利用预算0.9、BF16/non-thinking、revision b968826d9c46dd6066d109eabc6255188de91218。PyTorch2.11.0、vLLM0.23.0、Transformers4.57.6，驱动595.71.05；CUDA构建身份仍需部署前单独记录，不从torch版本推断。云数据盘214748364800字节/余6504673280；V盘余134027993088。均为时点快照，不是未来容量保证。

端口8000已用；独立服务候选8001只能在实际启动前再检查占用。额外端口不提供额外显存。现状不允许并行BF16第二模型，不停止或缩减Qwen的显存配置。

## 候选对比与来源

| 项目 | GLM-4-9B-Chat HF | Gemma3-12B-IT |
|---|---|---|
| 官方仓库 | zai-org/glm-4-9b-chat-hf | google/gemma-3-12b-it |
| 规模/架构 | 9B名义规模、GlmForCausalLM | 12B名义规模、Gemma3ForConditionalGeneration，多模态模型仅做文本 |
| 中文依据 | 官方卡标中英；不代替本研究实测 | 官方卡多语言；不代替中文议题/七档格式实测 |
| vLLM依据 | 0.23.0支持表列该HF型号 | 0.23.0列Gemma3ForConditionalGeneration；精确12B仍须本机验收 |
| HF兼容 | 官方示例Transformers≥4.46.0 | 官方说明≥4.50.0 |
| 上下文 | 官方示例131072；实验候选8192，逐请求核验 | 官方4B/12B/27B输入128K；实验候选8192，逐请求核验 |
| 精度/权重空间 | BF16仅权重粗估18GB，不含KV/运行时/缓存 | BF16仅权重粗估24GB，不含KV/视觉组件/运行时 |
| 许可 | GLM-4专用许可须逐条核实研究及发布义务 | Gemma条款与获取条件须人工接受核实 |
| 未知项 | revision/全成员hash/延迟/有效率/峰值显存 | revision/全成员hash/延迟/有效率/峰值显存 |

建议首先为GLM HF准备部署审定资料（参数规模较接近、权重估算较小）；Gemma保留跨家族备选。不能把原custom-code GLM与HF版本默认为同一冻结对象。最终选择仍为 `UNRESOLVED[SIS_NEXT_SECOND_MODEL]`，revision为 `UNRESOLVED[SIS_NEXT_MODEL_REVISION]`，未填充任何伪hash。

一手资料（访问2026-10-27，文档标称能力不等于本机能力）：

- [原GLM模型卡：建议HF兼容版本](https://huggingface.co/zai-org/glm-4-9b-chat)
- [GLM HF模型卡](https://huggingface.co/zai-org/glm-4-9b-chat-hf)
- [Gemma3-12B-IT模型卡与条款入口](https://huggingface.co/google/gemma-3-12b-it)
- [本机vLLM对应0.23.0支持表](https://docs.vllm.ai/en/v0.23.0/models/supported_models/)

## 部署选择与存储门

优先独立GPU/实例，保留现有Qwen不动；若分时切换，必须获得独立停止/恢复授权并冻结恢复配置，当前不得执行。量化不是无成本替代：不同精度属于新的模型处理条件，需另行批准。32GB卡能否单独承载候选8192并发仍须测量，不保证Gemma BF16可用。

只为未来测量提供容量规划：GLM至少预备约35–45GB可用磁盘、Gemma约45–60GB，覆盖权重、下载临时空间、运行缓存及小pilot余量；这是估算非下载许可/实际shard大小。按官方精确revision逐文件清单重新投影后才能准入。两候选不同时下载。新研究DB按独立矩阵额外计，不包含在权重估算里。扩盘不能解决当前GPU余量。

API仅为备选，不指定未经核实的服务商/价格或自动更新别名。若采用，必须绑定provider、snapshot/version、计费、限速、data retention、采样参数支持与实际响应版本，不能用API alias假装固定权重。当前无API调用批准。

## 冻结与验收顺序

1. 冻结精确仓库revision、license审核、权重/配置/tokenizer/template逐文件SHA；批准下载目标与容量上限后才下载。依赖隔离新venv，不升级原环境。
2. 独立GPU/实例或获批分时合同；新端口与只读健康检查，禁止Qwen原服务变更。
3. native chat template、system支持、stop tokens、最大输入/输出、thinking行为独立记录。原七档输出parser保留，若adapter必要变更采用新版本且逐case审查，不靠相同temperature名称宣称分布等价。
4. 候选技术门：7档/中文/边界文本离线渲染均通过；真实格式pilot候选100次、预算含一次性失败，不自动重发。预注册格式有效率至少99/100、transport/source mismatches0、重复发送0；任一身份失配立即停发。统计应同时报原parser有效率，不能用强制grammar掩盖模型无效输出。
5. 若格式不足，仅作失败候选报告；不能反复调prompt直到达标。修改需新版本、事先批准新预算，按质量规则非意见方向选择模型。
6. 后续N100/T10候选：两既有题×六格×2seed×1000=24000研究事件，加上述100技术为24100总请求；尚未授权。先单run持久化/歧义恢复验收，再冻结科学pilot身份与预算，不能当完整跨模型结论。
7. 每阶段报告实际墙钟、请求并发、tokens、格式有效率、错误率及峰值GPU/磁盘，给出正式矩阵估算。上述未知性能一律“未测”，不编造benchmark。

输出合同最终选择为 `UNRESOLVED[SIS_NEXT_SECOND_MODEL_PILOT]`。P1本轮验收是可追溯候选表、资源限制与未来门槛齐全，不是服务可用；与P0/P2准备互不阻塞。P3/P4当前仅backlog。
