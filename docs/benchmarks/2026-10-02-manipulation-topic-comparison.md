# Manipulation benchmark：三个topic比较与待确认版本

2026-10-02；仅本地材料审计，不是topic冻结、不生成message/刺激或请求。

## 当前配置结论

完整读取 `platform/configs/paper1/protocol.yaml`：status=draft，topic.id/statement/hash、
stance.construct/scale仍为UNRESOLVED；该12格配置属于legacy，不能授权新2×3。
当前新study也没有冻结topic。benchmark topic_reference继续
`UNRESOLVED[SIS_MC_BENCHMARK_CONTENT]`。

实际读取：proposal v2 `probe_specification.json` 的
`specification.payload.topic_candidates`；DR-P1-045及相邻046/047（同一rationale文件）。
下表区分设计文档、来源线索和可直接使用的最终argument pool；来源线索不是已审核刺激。

## 比较表

| topic | proposal现有stance mapping / 测量对象 | available argument source（已有本地线索，非完整刺激池） | 是否已有正式研究材料 | 作为manipulation benchmark的优缺点（设计判断，未经本次实证检验） |
|---|---|---|---|---|
| AI-net employment (`ai-net-employment`) | 1完全不同意、2不同意、3比较不同意、4中立或不确定、5比较同意、6同意、7完全同意；同意“未来十年AI广泛应用增加总体就业机会” | DR-P1-047列净替代/创造题型、自动化经历与总体预测区别、再培训/补偿等边界；列PNAS 2026净就业题型、Sun et al. 2025、Magistro et al. 2024为来源线索。未找到30条冻结argument正文 | 有议题构念、事实卡、核心陈述与文献台账；无已冻结formal topic/最终benchmark刺激池 | 优：贴合AI主线；未来净效应不是单一已知事实，适合比较对相同信息的响应。缺：净创造/任务替代/个人风险容易混淆，信息不确定性可能主导响应；需固定AI范围/地域/时间窗及命题方向 |
| Retirement delay (`retirement-delay`) | 1非常不支持、2不支持、3比较不支持、4中立或不确定、5比较支持、6支持、7非常支持；对“逐步提高法定退休年龄”的政策支持 | DR-P1-045：政策事实边界来源为2024决定，Zeng et al. 2024提供框架/锚定/公平感研究线索；台账支持后续整理政策接受理由，但不是现成30条刺激 | 有较详细设计、事实卡、核心陈述与来源说明；历史probe优先候选；仍未正式冻结topic或argument pool | 优：政策态度轴清晰，分配/公平相关论证适合审核。缺：年龄/职业背景可能改变切身利益，固定persona需要谨慎；政策事实卡与利弊argument须分开，避免测成个人退休意愿 |
| GM soybean oil (`gm-soybean-oil`) | 1完全不愿意、2不愿意、3比较不愿意、4中立或不确定、5比较愿意、6愿意、7非常愿意；个人购买食用明确标识产品的意愿 | DR-P1-046：标识管理材料界定对象；Hu et al. 2020、Jin et al. 2022列风险/收益、态度/购买、信任/情感的研究线索；未找到完整冻结argument正文 | 有构念、事实卡、核心陈述及来源台账，但proposal与rationale构念不一致；无已冻结formal topic/刺激池 | 优：具体产品对象便于固定；不同信息与理由容易作人工对照。缺：安全知识/规范性回答可能压过group cue；价格口味偏好会影响购买意愿，不能与市场准入支持混用 |

以上是本地文档中的来源线索，不声称本轮已核验论文全文、法规当前有效性或由其提取具体刺激。
没有读取或把旧797/816原始模型response当作argument材料，也没有调用模型。

## 三处关键版本差异

1. **Retirement：** proposal是通用政策方向题；DR-P1-045是具体渐进式方案的继续实施支持，
   包含更详细历史事实卡。二者不能自动合并。这里复述历史设计，不重新验证现行政策。
2. **GM：** proposal是个人购买/食用意愿；DR-P1-046是允许依法标识产品销售的政策支持，
   且明确不测个人购买。它们是不同构念，不只是paraphrase。
3. **AI：** proposal是广义AI、未来十年、总体就业**增加**；DR-P1-047是生成式AI、
   中国、未来十年、岗位**减少多于创造**。地域/技术范围不同且命题方向反转。
   1—7仍表示对各自原命题的同意度；不能把同一数值理解成同一就业预测，不能自动倒分。

focal=4仅是MC sensitivity design，不代表正式opinion dynamics初始分布。选择topic/version
后再绑定其原始mapping；本轮没有修改任何mapping。

## 供用户确认

请选择topic及**具体测量对象/题干版本**，不只确认candidate_key。
- 若优先复用较成熟政策态度设计，可考虑retirement，但仍需在proposal与DR-P1-045间明确版本。
- 若优先贴合AI研究主线，可考虑AI；须先固定广义/生成式、地域与净增加/净减少方向。
- GM可作为具体风险传播对象，但须先选择购买意愿或市场销售支持。

以上是基于现有材料的取舍，不自动决定topic；也未依据旧run结果对三个topic排序。
确认后才进入30-case正文编制与人工审核，不提前调用实验模型。

## 本地来源定位

- `platform/configs/paper1/protocol.yaml`：机器topic/stance未决。
- `platform/configs/paper1/phase0a1-approval-proposal-v2/probe_specification.json`：三个实际probe包及完整1—7标签。
- `docs/paper1-design-rationale.md`：DR-P1-045/046/047的构念、题干、台账与边界。
- `docs/decisions.md`：D-2026-07-29-05记录论据家族/最终正文仍待冻结。
