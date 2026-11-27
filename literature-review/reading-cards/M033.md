# M033 — 信息不对称：全知模拟的成功能否迁移？

## 1. 书目、版本与阅读范围
Xuhui Zhou; Zhe Su; Tiwalayo Eisape; Hyunwoo Kim; Maarten Sap. Is this the real life? Is this just fantasy? The Misleading Success of Simulating Social Interactions With LLMs. EMNLP2024主会21692–21714；DOI10.18653/v1/2024.emnlp-main.1208。[官方页](https://aclanthology.org/2024.emnlp-main.1208/)与[正式PDF](https://aclanthology.org/2024.emnlp-main.1208.pdf)。2026-11-27定向读PDF pp3–9（§3–6关键段）、p15/AppA、pp21–23/AppE–H；Fig7模拟卡已渲染目视。未全读其他附录/代码。Anthology2024-11与会期Nov12–16不等于首次在线日；Crossref仅2024，建档Nov27不用作发表日，candidate/date_pending保留。

## 2. 问题与对象
全知LLM生成的成功对话能否代表有私有信息的主体互动能力？在Sotopia中比较合作/竞争等合成社会任务；不是自然社会网络或人群纵向轨迹。

## 3. 信息与主体构造
SCRIPT：单模型看到所有人物、私有目标/背景，一次生成全段第三人称对话。AGENTS：各主体只见相应信息，第一人称逐轮互动。MINDREADERS保留主体逐轮方式但开放对方私有信息（pp3–4）。前两模式同时改变信息、生成组织和视角，不能把总差异全认定为信息单因素净效应；MINDREADERS是进一步控制，不等于消除所有提示差异。

## 4. 设计、模型与单位
40人物/90场景，每模型每设置450模拟=每场景5人物配对，主要模型GPT-3.5与Mixtral-8x7B。450不是450独立人群或450seeds。AppF固定gpt-3.5-turbo-0613/gpt-4-0613；主体temperature0.7、评估0，Mixtral经TogetherAPI；精确远端模型revision/随机种子仍未复核。论文报告成对t检验，本轮未复算配对与层级依赖。

## 5. 评价层与真人作用
目标完成0–10由GPT-4评估，作者引用既有与真人相关性的依据，本研究仍承认自动评估偏差。自然度为真人对两份生成对话的偏好，AppE九名英语熟练的美国研究生标注者，主文每比较对30标注不等于30独立标注者。评审者看到场景/背景/私有目标，不等于模拟主体也可见这些信息；也不等于真实参与者完成任务的行为数据。

## 6. 结果与区分性判据
SCRIPT/MINDREADERS一般目标分高于AGENTS，但竞争任务MINDREADERS仍低于SCRIPT；模式效应依任务。自然度偏好、冗长度、目标完成及成交率不是同一效度。首次提共同朋友的位置是泄漏代理，不是逐token来源追踪；成交率高可以反映更易同意，不能单独证明谈判技能。

## 7. 训练与迁移
269新场景生成并保留1252有效SCRIPT episodes，剔除GPT-4无法评价的不完整样本；剔除分布未审。用生成脚本微调GPT-3.5一轮后在AGENTS条件评估：风格/自然度改善与合作任务目标能力分开。自然度p=0.07只是未显著，不作等效性证明；迁移仍是合成任务，不是独立真人能力验证。项目主实验不微调，不将本文训练路线塞回主矩阵。

## 8. 成熟度、报告与限制
empirical_method_test/controlled_comparison，支持信息/模式边界比较，不标validated_workflow或真实社会效度。英文、有限场景、提示与自动judge局限在§6明确；轮流机制、异步/多方/长期记忆等未覆盖。§5.2/AppA的Simulation Card是报告建议，不是会议强制标准，也未验证清单提升复现成功率。

## 9. Agent-EX比较（本项目推论）
分列主体可见信息、生成组织/时序、评价者可见信息和研究者所持真值；信息屏蔽是模型定义而非纯文案。目标高分与信息不可得时的能力分开。卡可提示应披露哪些维度，但不替代冻结协议、实际状态/曝光日志或独立验证。

## 10. 写作与发表用途
EMNLP主会直接方法评价先例，与M031真实历史条件/闭环、M032解析失败动作共同强调评价条件决定主张边界。当前意见演化稿若走NLP路线需实质方法/评价贡献，不能只援引正式先例；后续方法稿可检验信息/评价可见性错配导致何种结论偏差，尚未执行。

## 11. 待核与获取
精确首次在线日、完整prompts/代码/数据及运行版本、有效样本筛选、配对依赖/统计不确定性、自动judge偏差、跨语言和人类真实互动迁移。hash见source_acquisition_manifest_AH.json；未复跑、未改Agent-EX协议。比较综合见information_boundary_comparison.md。
