# EcoLANG公式与公开实现：已澄清方向，尚未复建论文运行

2026-11-27批次AK。仓库xymou/EcoLANG固定`00878bc4ef6a1dc2fe470ac33a9740e559003b83`，提交2025-05-13；README指向May预印本，早于November正式Findings版。11源码/配置/说明文件Git blob与SHA256已核，见[制品清单](../data/ecolang_artifact_audit_AK.json)。未安装、执行、调用模型、反序列化数据或运行包。此快照与正式论文实际运行对应关系未证。

## 公式方向的核实结论

[code/myselect.py:219–272](https://github.com/xymou/EcoLANG/blob/00878bc4ef6a1dc2fe470ac33a9740e559003b83/code/myselect.py#L219-L272) 把completion token数除以同组最大值；fitness为`w1*alignment/5 - w2*token_score + w3*expressiveness/5`。缓存重评分同样使用负token项（371行），高分降序选择（396行）。[code/scripts/evo_persona_pheme_vocab.sh:10–20](https://github.com/xymou/EcoLANG/blob/00878bc4ef6a1dc2fe470ac33a9740e559003b83/code/scripts/evo_persona_pheme_vocab.sh#L10-L20) 给w1=1,w2=0.6,w3=0.6；HiSim脚本相同。因此所读公开实现惩罚较长生成，不是在奖励长文本。

正式PDF式2却正号加入normalized token count，AppA给正0.6，且没有明确表现代码中alignment/expressiveness的除5。结论是打印表达与公开实现不一致；静态阅读已解决“公开代码是否奖励长文本”的疑点，但不能认证正式运行究竟用哪版，也不将其称已复跑成功或错误算法的实证结果。

## 预算与解码操作

[code/chat_simulation.py:95–112](https://github.com/xymou/EcoLANG/blob/00878bc4ef6a1dc2fe470ac33a9740e559003b83/code/chat_simulation.py#L95-L112) 汇总主体usage并保存对话token计数；这不独立证明judge/交叉变异/所有搜索成本已进入表1的下游模拟分母。AI的成本重算边界保留。[pkg/logits_processors/logits_processors/vocab.py:1–22](https://github.com/xymou/EcoLANG/blob/00878bc4ef6a1dc2fe470ac33a9740e559003b83/pkg/logits_processors/logits_processors/vocab.py#L1-L22) 对完整logits加允许token的mask，不是裁剪模型权重；不能凭词表更小就直接认定显存减少，也不声称未读包内绝无其他裁剪路径。

## 可获取与可复建之间的缺口

README引用requirements_vllm.txt/requirements_evo.txt/requirements_simu.txt，但固定的非截断树中未列requirements文件。README明确给出vLLM开发版本并要求修改vLLM/Camel/OASIS；部分ZIP在仓库，vLLM包是外链文本，本批未取得/审包。故不能笼统称完全无版本，也不能称环境已核齐。HiSim原始文本因来源条件未随仓库公开，README列需联系作者；本批未联系、未取得。服务命令指向本地Llama-3.1路径，配置用服务别名，不是权重revision/hash；cache_seed=None也不是完整随机种子冻结。

这些是明确的获取/溯源边界，不是已尝试复建失败。公开数据文件、ZIP、完整评估模块未全审；只核11文件，源码能读不等于正文结果已重建。修改M035卡与VC73，原待核表述在Git及变更账保留；新增两个静态证据单元，不新增论文/卡/纳入。下一批AL回到命名入口覆盖，优先TACL官方范围/制品要求和已在库R010；避免继续只扩同一小组案例。
