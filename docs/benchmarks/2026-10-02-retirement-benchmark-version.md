# Retirement benchmark：通用版本确认与构念边界

状态：用户2026-10-02已确认本benchmark采用通用版本；新主实验topic尚未因此冻结。
此记录不生成执行授权，不修改legacy protocol或stance mapping。

## 两版本差异

| 维度 | proposal 通用版本（本次采用） | DR-P1-045 具体版本（本次不采用） |
|---|---|---|
| 评价对象 | 逐步提高法定退休年龄的总体政策方向 | 中国具体渐进式年龄调整方案的继续实施 |
| 核心题干 | 总体而言，我支持逐步提高法定退休年龄。 | 总体而言，我支持中国继续实施上述渐进式延迟法定退休年龄方案。 |
| 事实卡 | 不要求判断具体实施年份、幅度或某一群体例外 | 历史文档包含调整周期、不同年龄类别和弹性安排 |
| 回答含义 | 对通用方向的支持度 | 对已列具体方案的支持度，可能包含对参数的评价 |
| MC取舍 | 便于在同一态度轴上控制刺激；外推限于通用题干 | 更具体，但参数和利益位置可能引入额外判断 |

因此“proposal题干＋DR边界”不是把两份事实卡拼接：保留proposal事实卡原文；
只采用DR关于测量对象的排除规则，不展示其具体政策数字、不写成“继续现行方案”。

## 本次绑定的原文

topic candidate：`retirement-delay`。

construct：对逐步提高法定退休年龄这一政策方向的支持程度。

statement：**总体而言，我支持逐步提高法定退休年龄。**

fact_card：**本题讨论是否逐步提高法定退休年龄。评价对象仅是对这一政策方向的总体支持程度；不要求判断具体实施年份、幅度或某一群体的例外安排。**

stance mapping（不改序、不倒分）：

| 值 | 原标签 |
|---:|---|
| 1 | 非常不支持 |
| 2 | 不支持 |
| 3 | 比较不支持 |
| 4 | 中立或不确定 |
| 5 | 比较支持 |
| 6 | 支持 |
| 7 | 非常支持 |

用户通过异步问题明确确认以上组合；不是根据probe结果选择或自动推广为formal topic。

## 从 DR-P1-045 借用的边界

- 不测个人何时退休或个人是否愿意延迟退休。
- 不把养老金信心当作测量对象，不询问政策是否会实施。
- 不把最低缴费年限等配套政策捆绑进核心题干或态度轴。
- 事实卡不夹带利弊框架；论据放入独立source_message。
- 刺激中的资源、公平、劳动等论点只是政策支持理由，不增加第二个要求回答的构念。
  不把这些价值判断或条件性后果写成已核验事实，也不引用无来源数字。

## 后续审核边界

focal=4仅为MC sensitivity design，不代表正式初始分布。
固定neutral but socially situated citizen profile与uniform history的精确稿仍待审核。
30-case draft的内容与论据强度未经验证；全部human_review=pending，不生成240请求。

来源：`platform/configs/paper1/phase0a1-approval-proposal-v2/probe_specification.json`
→ `specification.payload.topic_candidates[candidate_key=retirement-delay]`；
`docs/paper1-design-rationale.md` → DR-P1-045。比较历史文本，不宣称核验当前法规。
