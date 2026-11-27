# M037 — 信任行为：历史经验参照与认知机制的距离

## 1. 书目、版本与阅读范围
Chengxing Xie; Canyu Chen; Feiran Jia; Ziyu Ye; Shiyang Lai; Kai Shu; Jindong Gu; Adel Bibi; Ziniu Hu; David Jurgens; James Evans; Philip H.S. Torr; Bernard Ghanem; Guohao Li. Can Large Language Model Agents Simulate Human Trust Behavior? NeurIPS2024 Main Conference Track；DOI10.52202/079017-0501。[官方页](https://proceedings.neurips.cc/paper_files/paper/2024/hash/1cb57fcf7ff3f6d37eebae5becc9ea6d-Abstract-Conference.html)、[正式PDF](https://proceedings.neurips.cc/paper_files/paper/2024/file/1cb57fcf7ff3f6d37eebae5becc9ea6d-Paper-Conference.pdf)。2026-11-27取得56页全文，定向读pp1–10,18–21,23,26–29,51–54,56；p20附录C/D已渲染目视。不是全部附录逐例精读；正式首发日仍date_pending/candidate。

## 2. 问题与理论
以Trust Game及变体检验LLM行为是否出现信任，并与既有人类研究的互惠预期、风险感知、亲社会偏好与重复博弈模式比较。BDI用来组织模型输出的信念/欲望/意图解释；本项目区分理论启发、文本解释和被独立识别的认知机制。

## 3. 构件与模型
CAMEL框架，GPT-4生成53个persona（姓名/年龄/性别/地址/职业/背景）；不等于53真实被试或人口代表样本。多GPT3.5版本、GPT-4、Llama2和Vicuna，temperature1；正文GPT-4称呼未给精确snapshot，远端revision和seeds未审。本文不调权重；BDI输出和CoT提示是行为生成条件，不是直接观测模型内部心理过程。

## 4. 任务与测量
初始$10、发送N、接收3N、可返还；Dictator移除返还机会；另MAP/Risky Dictator、两种Lottery、重复Trust。VRR量合法金额输出，不等于信任动机或现实外部效度。正文一方面将信任条件设为正金额，另一方面VRR按金额落在初始范围计；零值的解析/分类规则须代码核，不能据两段文字自行统一。

## 5. 人类参照及程序差异
对照来自既有研究而非本研究新招真人；p56人类实验/IRB自报NA。G1明确16组人类重复轨迹来自Cochard等2004图，再由作者代码重画；本轮只读2024论文该说明，没有独立检索或纳入2022年前作品。数字化误差和原始数据未复核。

AppD承认人类直接报告最低可接受概率P*后推导trust rate，而LLM因理解困难改在p=.1至1.0的十组提示逐点回答。二者有相关的风险问题，却不是完全相同的引出程序。不能把曲线相近归结为精确程序复现，也不据此认定结论无效。

## 6. 对齐的证据强度
互惠比较人类约6.0 vs3.6，GPT-4约6.9 vs6.3；各自方向/显著性相似不等于效应量等价（数值为论文四舍五入）。正文报单尾独立样本t检验、AppE逐模型p值；未复算persona跨条件配对、独立性或多重比较。Lottery人类54% vs29%，GPT-4 72% vs21%；同方向仍可有分布/幅度差异。未见所读部分给出统一预注册等价阈值，不以未检验等价说完全不相似。

## 7. 动态与机制
16组/模型的重复游戏为同模型不同persona配对；七轮例图不是网络长期过程。三模式出现比例GPT-4为87.5/87.5/100%，GPT3.5为62.5/56.25/43.75%；返还/3×发送相邻变化≤10%为“稳定”判据（末轮另处置）。这些是作者选定模式的符合率，不是逐轨迹预测误差或统一人群距离。BDI片段可解释行动，但一致叙事不排除事后合理化，也不独自证明人类同源认知或因果机制。

## 8. 敏感性与社会对象
性别/种族标签、信任/不信任指令和CoT改变发送行为，支持模型/提示条件依赖。H3的“LLM对象”与“真人对象”是文字告知的操纵，不是重新招真人并与模型实际交互的实验。不能把模型表述的人类偏好直接认定为真人—AI合作效益。

## 9. 成熟度与可复现性
empirical_method_test/empirical_validation，限简化博弈的历史参照，不标一般validated_workflow。AppC承认复杂/动态环境不足。已提供多任务提示；清单自报可复现Yes且出现未解析Section??，代码链接尚未审。自报Yes是报告证据，不是独立重建成功；未审完整制品、模型冻结身份、失败/重试和计算预算，未复跑。

## 10. Agent-EX与投稿用途（本项目推论）
经验对照应分别报告方向、效应幅度、分布、轨迹和机制，而不是单一“对齐”；程序变更须披露。合成persona不以N充当独立seed；文本化解释不当因果证明。NeurIPS正式方法验证先例可用于发表地图，但不据其标题或作者外推认证网络意见演化能力，也不改项目冻结协议。

## 11. 缺口与获取
精确首发日、历史数据获取/数字化、引出程序可比性、独立性/效应等价、persona选择与模型snapshot、完整代码/运行环境及人类真实互动迁移。PDF5121261bytes/56页/SHA256见source_acquisition_manifest_AO.json。批次AN摘要状态历史保留；本批仅升级实际阅读与有界编码，正式纳入数不变。

AP制品后续：固定a3f14f0d（2026-07-11）13文件blob/SHA256；53角色/32配对角色已核。当前非fc解析test=True返回1、10轮默认与抽查旧53多值/7轮结果不同，不能反向归责论文；零值会进入critic后备，未证改值。历史版本/VRR映射未闭合，详见trust_static_artifact_audit.md；AO未审代码是历史状态，本次仍未安装/复跑。
