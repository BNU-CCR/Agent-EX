# 30-case draft review table（结构已确认，正文未生成）

2026-10-02；pending / not_frozen / dispatch_authorized=false。
**这是30个配额槽位，不是已经具备message/reason/persona的30个完整候选case。**
schema设计见 `../superpowers/specs/2026-10-02-manipulation-benchmark-case-design.md`。

## Topic核对：保留未决

- probe包：`platform/configs/paper1/phase0a1-approval-proposal-v2/probe_specification.json`，
  `specification.payload.topic_candidates`中的retirement-delay / gm-soybean-oil /
  ai-net-employment。
- 正式机器配置 `platform/configs/paper1/protocol.yaml` status=draft且topic仍UNRESOLVED，
  新2×3协议也未冻结topic。因此每case的topic_reference为
  `UNRESOLVED[SIS_MC_BENCHMARK_CONTENT]`。不自行选AI、退休或GM，不修改stance mapping。
- 历史具体政策版本另见DR-P1-045；不能自动选它或把两版事实卡合并。
- 没有找到可直接摘录的正式argument pool；mock理由库不使用，历史模型输出也不擅自代替pool。

## 本次固定的结构

按用户2026-10-02确认，focal=4，source分别为4±distance；若需改变baseline必须先报告。
六层各5个独立内容槽位；focal=4仅为MC sensitivity design，不代表正式实验初始stance分布，
不修改study初始化；未取得正文不计算内容hash。
case slot不等于模型repeat，后者为每case四配对中的每个cell两次生成。

所有行共享：topic_reference未决；persona_context暂定为固定neutral but socially situated citizen profile，
不是完全无社会背景，也不得夹带方向立场或群体规范；
具体文本待填；self_history规则统一且无consistency instruction，具体内容/长度不默认。
focal_context、source_message、source_reason、reason_family、argument_provenance均未生成，
human_review=pending。表中“待填”表示这些字段均为
`UNRESOLVED[SIS_MC_BENCHMARK_CONTENT]`，不是可发送文本，不代表待抽正式round0素材。

| case_id | stance_distance | direction | focal→source | 必需正文/来源字段 | human_review |
|---|---:|---|---|---|---|
| MC-D1-U-01 | 1 | upward | 4→5 | 待填 | pending |
| MC-D1-U-02 | 1 | upward | 4→5 | 待填 | pending |
| MC-D1-U-03 | 1 | upward | 4→5 | 待填 | pending |
| MC-D1-U-04 | 1 | upward | 4→5 | 待填 | pending |
| MC-D1-U-05 | 1 | upward | 4→5 | 待填 | pending |
| MC-D1-D-01 | 1 | downward | 4→3 | 待填 | pending |
| MC-D1-D-02 | 1 | downward | 4→3 | 待填 | pending |
| MC-D1-D-03 | 1 | downward | 4→3 | 待填 | pending |
| MC-D1-D-04 | 1 | downward | 4→3 | 待填 | pending |
| MC-D1-D-05 | 1 | downward | 4→3 | 待填 | pending |
| MC-D2-U-01 | 2 | upward | 4→6 | 待填 | pending |
| MC-D2-U-02 | 2 | upward | 4→6 | 待填 | pending |
| MC-D2-U-03 | 2 | upward | 4→6 | 待填 | pending |
| MC-D2-U-04 | 2 | upward | 4→6 | 待填 | pending |
| MC-D2-U-05 | 2 | upward | 4→6 | 待填 | pending |
| MC-D2-D-01 | 2 | downward | 4→2 | 待填 | pending |
| MC-D2-D-02 | 2 | downward | 4→2 | 待填 | pending |
| MC-D2-D-03 | 2 | downward | 4→2 | 待填 | pending |
| MC-D2-D-04 | 2 | downward | 4→2 | 待填 | pending |
| MC-D2-D-05 | 2 | downward | 4→2 | 待填 | pending |
| MC-D3-U-01 | 3 | upward | 4→7 | 待填 | pending |
| MC-D3-U-02 | 3 | upward | 4→7 | 待填 | pending |
| MC-D3-U-03 | 3 | upward | 4→7 | 待填 | pending |
| MC-D3-U-04 | 3 | upward | 4→7 | 待填 | pending |
| MC-D3-U-05 | 3 | upward | 4→7 | 待填 | pending |
| MC-D3-D-01 | 3 | downward | 4→1 | 待填 | pending |
| MC-D3-D-02 | 3 | downward | 4→1 | 待填 | pending |
| MC-D3-D-03 | 3 | downward | 4→1 | 待填 | pending |
| MC-D3-D-04 | 3 | downward | 4→1 | 待填 | pending |
| MC-D3-D-05 | 3 | downward | 4→1 | 待填 | pending |

## 每行完整review template（未填正文，不可执行）

```yaml
case_id: MC-D1-U-01
topic_reference: UNRESOLVED[SIS_MC_BENCHMARK_CONTENT]
focal_stance: 4
source_stance: 5
stance_distance: 1
direction: upward
focal_context: null
source_message: null
source_reason: null
persona_context:
  profile_kind: fixed_neutral_socially_situated_citizen
  exact_profile: null
self_history:
  rule: uniform_no_consistency_instruction
  exact_history: null
reason_family: null
argument_provenance: null
human_review:
  status: pending
  reviewer: null
  notes: null
```

此模板适用于全部30行，只替换表中的ID/distance/direction/source stance。
null均为待审核草稿字段，不是“空history”或“无persona”的执行决定。
BB/BG/GG/GB及两repeat在case审核后派生，当前没有240条request，也没有刺激正文。

## 后续人工审核标准

每条显示：topic原文/version、focal/source label、精确reason/message、persona/history、
pool entry与原文定位、编辑说明、独立内容单元、近重复风险、approve/revise/reject及备注。
逐case检查：distance/direction、reason支持source stance、message自然度、无group cue、
无明显事实错误、source/reason近重复，以及是否过度依赖同一argument。
正文不合格或不足时保留缺口，不复制文本或改ID凑足30。
schema已通过；内容编制须等用户确认topic及题干版本，本轮仍不生成正文。
审核通过仍不等于云端执行授权。
