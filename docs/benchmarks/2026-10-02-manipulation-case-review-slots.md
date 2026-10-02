# 30-case 审核槽位与来源缺口

2026-10-02；pending / not_frozen / dispatch_authorized=false。
**这是30个配额槽位，不是已经具备message/reason/persona的30个完整候选case。**
schema设计见 `../superpowers/specs/2026-10-02-manipulation-benchmark-case-design.md`。

## 可用议题来源

- probe包：`platform/configs/paper1/phase0a1-approval-proposal-v2/probe_specification.json`，
  `specification.payload.topic_candidates`中的retirement-delay / gm-soybean-oil /
  ai-net-employment。
- 延迟退休probe陈述：“总体而言，我支持逐步提高法定退休年龄。”
  mapping：1非常不支持、2不支持、3比较不支持、4中立或不确定、5比较支持、6支持、7非常支持。
- 历史具体政策版本另见DR-P1-045；不能自动选它或把两版事实卡合并。
- 没有找到可直接摘录的正式argument pool；mock理由库不使用，历史模型输出也不擅自代替pool。

## 供审核的stance配额示意

下表**建议**暂统一focal=4，source分别为4±distance，便于镜像控制；这不是用户已冻结的
baseline，也没有声称这种中立起点代表正式动力学。若需要不同focal基准，审核时修改，
仍须保持六层各5及有效量表范围。未取得正文前不计算内容hash。

所有槽位的message_content、source_reason、focal_pre_reason、persona/context、history、
argument_provenance均为 `UNRESOLVED[SIS_MC_BENCHMARK_CONTENT]`，不是可发送文本。

| 槽位ID | distance | direction | 建议focal→source | 内容/来源 | 审核 |
|---|---:|---|---|---|---|
| MC-D1-U-01 | 1 | upward | 4→5 | 待pool | pending |
| MC-D1-U-02 | 1 | upward | 4→5 | 待pool | pending |
| MC-D1-U-03 | 1 | upward | 4→5 | 待pool | pending |
| MC-D1-U-04 | 1 | upward | 4→5 | 待pool | pending |
| MC-D1-U-05 | 1 | upward | 4→5 | 待pool | pending |
| MC-D1-D-01 | 1 | downward | 4→3 | 待pool | pending |
| MC-D1-D-02 | 1 | downward | 4→3 | 待pool | pending |
| MC-D1-D-03 | 1 | downward | 4→3 | 待pool | pending |
| MC-D1-D-04 | 1 | downward | 4→3 | 待pool | pending |
| MC-D1-D-05 | 1 | downward | 4→3 | 待pool | pending |
| MC-D2-U-01 | 2 | upward | 4→6 | 待pool | pending |
| MC-D2-U-02 | 2 | upward | 4→6 | 待pool | pending |
| MC-D2-U-03 | 2 | upward | 4→6 | 待pool | pending |
| MC-D2-U-04 | 2 | upward | 4→6 | 待pool | pending |
| MC-D2-U-05 | 2 | upward | 4→6 | 待pool | pending |
| MC-D2-D-01 | 2 | downward | 4→2 | 待pool | pending |
| MC-D2-D-02 | 2 | downward | 4→2 | 待pool | pending |
| MC-D2-D-03 | 2 | downward | 4→2 | 待pool | pending |
| MC-D2-D-04 | 2 | downward | 4→2 | 待pool | pending |
| MC-D2-D-05 | 2 | downward | 4→2 | 待pool | pending |
| MC-D3-U-01 | 3 | upward | 4→7 | 待pool | pending |
| MC-D3-U-02 | 3 | upward | 4→7 | 待pool | pending |
| MC-D3-U-03 | 3 | upward | 4→7 | 待pool | pending |
| MC-D3-U-04 | 3 | upward | 4→7 | 待pool | pending |
| MC-D3-U-05 | 3 | upward | 4→7 | 待pool | pending |
| MC-D3-D-01 | 3 | downward | 4→1 | 待pool | pending |
| MC-D3-D-02 | 3 | downward | 4→1 | 待pool | pending |
| MC-D3-D-03 | 3 | downward | 4→1 | 待pool | pending |
| MC-D3-D-04 | 3 | downward | 4→1 | 待pool | pending |
| MC-D3-D-05 | 3 | downward | 4→1 | 待pool | pending |

## 正文到位后的人工审核表

每条显示：topic原文/version、focal/source label、精确reason/message、persona/history、
pool entry与原文定位、编辑说明、独立内容单元、近重复风险、approve/revise/reject及备注。
正文不合格或不足时保留缺口，不复制文本或改ID凑足30。审核通过仍不等于云端执行授权。
