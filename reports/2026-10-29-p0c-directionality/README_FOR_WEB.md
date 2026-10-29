# Agent-EX｜P0-C方向性机制讨论包

建议顺序：[统一诊断](RESEARCH_DIAGNOSIS.md) → [C1材料审计](C1_STIMULUS_AUDIT.md) → [C2真实事件](C2_NETWORK_EVENT_DIAGNOSTICS.md) → [C3编码/顺序设计](C3_ENCODING_CONTROL_PLAN.md) → [C4反馈设计](C4_FEEDBACK_PILOT_PLAN.md)。字段见[字典](DATA_DICTIONARY.md)。

本轮离线工作覆盖1890000不重复历史事件，恢复331案例/453实际feed槽位/88原DB。P0-B全部1526实际wire与冻结材料相等。新模型请求0，未修改任何原科学输入/服务；C3/C4候选真实预算均未授权。

全部七档原命题语义保留。事件前态不等于Round0，实际feed不等于潜在邻居帖子，后台群体标签不等于模型看到的标签。历史关联不等于单条信息因果或反馈效应；样本比例不是总体率。

## 独立复算

使用本包FILE_MANIFEST.sha256中的外部SHA值：

`python -B verify_public.py . --manifest-sha256 EXTERNALLY_VERIFIED_SHA256`

这会验证公开文件exact cover/hash、1890000事件聚合分母、七类总体/配额、331索引与恢复特征、453实际槽位及88原DB前后hash证明。它不访问私有理由或调用模型，也不声称仅靠公开汇总重新证明私有内容。原数值源完整重建另见platform/scripts/sample_p0c_events.py及V盘受控源定位。

## 交给网页GPT的指令

请先读本README及RESEARCH_DIAGNOSIS，再按C1–C4报告和CSV核对。区分原命题语义、命题同意度和显示码；不要把AI题高分解释为支持AI，不要把P0-B固定low/high当成对所有前态都同方向的刺激。分析方向性迁移时明确前态机会分母、feed方向、seed/cell/窗口及历史暴露，不能只比5→3和3→5的原始次数。

请将“证据支持的描述”“仍有混杂的解释”“需要新干预的问题”分开回答。C3/C4仅是待授权方案，不得假定已执行或已有结果；不要把样本数/Agent/事件当独立重复，不声称正式显著性或数学稳态。若链接或字段缺失请指出，不编造原始理由。

公共文件不含完整prompt/reason、SQLite、API凭据或大型原始运行归档。私有恢复和完整数值源保留V:/Agent EX/Agent-EX-evidence/2026-10-29/p0c-directionality-v1。Git只同步此精简包、离线工具/测试、授权边界与进度。
