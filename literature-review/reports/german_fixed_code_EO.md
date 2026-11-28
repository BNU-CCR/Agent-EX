# EO：德国开放意见固定代码与公开汇总表核查

截止2026-11-28，作者仓库soda-lmu/llm-opinion-german固定main提交`8af633a8383d4bab63eba52e0c21e3b638f62914`，committer2025-08-03。完整递归树267项、truncated=false；18选定文件取得，SHA256与Git blob长度/内容核实，范围见清单。原代码、notebook、公开原CSV缓存放临时目录，不提交第三方源码/原始调查。本批只读选定代码/125-cell notebook中相关单元，未逐行审全库或执行任何作者模块/训练/生成。

## 已取得的分类拆分与测量链

README推荐`mixed`和resample。train.py的mixed入口：真人GLES以wave12为外部test，其余波文本去重后取10%（sample无显式random_state），再加合成标注80%训练；合成20%test按行random_state42。内部prepare_train_dataset再80/20切分，未显式seed。现在可确认合成按行留出，并非按模型/波次/人分组；同一研究实际.93加权F1对应的checkpoint/划分计数与类别性能仍待日志。不能再笼统说“公开代码没有拆分”，也不能说split已证明独立外部效度。当前训练入口与正文“以合成1500条训练”的简述范围不同，不据此猜测论文实际用了哪个训练模式。

固定map有17个ID，0–16，含refusal；Table9的16个粗类与工具图增加refusal的差异现有具体来源。分析默认取`bert_mixed_coarse_resample20240708_195103`的输出，但权重/config/run原件未取得，不能仅由名称认证准确版本。阈值为sigmoid>.5。批处理若无类过阈值，备用argmax写入pred_label_names/probs，却没有修改原predictions全零向量；multilabel分析读取后者，multiclass从已选名字概率取最高。两路线于是有条件地将同一条输出视为零标签或一个标签。没有原始逐响应输出，不能估计该情况频率或它对论文模型排序的影响。

分析概率保留14实质类别，排除refusal、未指明与不知道。multilabel以正标签出现总数作分母；同一回答多个主题可贡献多次，全零不贡献。multiclass对最高类别在14类内的回答计value_counts。故两者都不是全体受访者、包括所有拒绝/未知的回答概率；未知/拒绝发生率需另报，不能默认为“无影响”。这些规则已经定位，不仍统称完全未知。

## 公开汇总数值的可复核结果

选取四个固定CSV：两种multiclass/multilabel、各LLM/survey人口PMF，每份十波。使用本项目独立算式读取这些汇总值，归一后计算base2 entropy与自然对数JS距离，未调用/导入作者代码。multiclass十波的LLM entropy、survey entropy、JS共30个值全部在两位小数重现论文表2；用汇总PMF精度算surveyentropy–JS Pearson=-0.350877，重现作者约-.35。EN按印刷值算-.3242的差异因精度得到解释，不再把系数数值本身列未解错误。

但方向解释并未被修复：JS越小越相符，负相关不支持该段“总体多样性更高则更不代表”。这与子群跨均值的其他关系分开。wave13的LLM entropy .58209、survey2.02003支持EN已识别的列混淆；多标签版本的LLM entropy1.36767，不是表2的.58。因此论文表2对单类别读出的对应已确认，不能把它概括为所有开放文本/多标签多样性。此仅验证“发布汇总表→论文表2”的算术，不验证“原始GLES→生成→BERT→汇总”的完整链，也不重演25次生成。

代码jensenshannon没有显式base；[SciPy官方说明](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.distance.jensenshannon.html)确认省略时使用entropy默认底。本次独立自然底算值与论文表2匹配：wave12 .287107，对应base2应.344851；自然底最大值sqrt(ln2)，不可在跨研究比较时无条件套0–1的base2端点。仅共同换底会同比缩放距离、不会倒转同一数据的排序。entropy函数则明确base2，不能因同在一表就假设JS也base2。

“APE”仍有多条路径：metrics helper是100×sum(abs(p−q))，即200×TVD（P/Q已归一且同标签时），不是Eq9逐类除真实频率的相对误差；notebook cell109的mean APE确有abs((p−q)/q)按波均值，另APE汇总行又用L1。表7带负数的行尚未精确映射计算入口，不称已经解决，也不把所有APE结果合成同一指标。

## 制品与论文运行的边界

README所称experiment_config_paper当前为Gemma2-2B、wave10，非论文三模型清单/wave12主比较；llama_config为temperature1/do_sample/max_new_tokens300、8bit、batch8，正文报告batch16。只说明当前文件不能当逐run冻结配置，不推断全部发表结果实际采用这些不同设置。主load_model未指定revision，GLES原数据需注册获取，权重/原输出/训练日志与论文运行映射未取得。

判断：可复核性已有实质增量，尤其表2算术与单类别读出、标签分母和训练拆分已定位；完整独立复现仍未建立。更新M180卡、既有VC248/249/250/252，未新增研究/卡/单元/等级。237条/87卡/252单元、60纳入保持；八来源分组操作后1758。下一项EP把M179概念倡议与M180经验/实现证据整合进方法地图与双轨贡献，随后按既有覆盖/版本队列推进，避免单篇无界追代码。32日期/3空分类、授权检索和独立WoS缺口仍开放。
