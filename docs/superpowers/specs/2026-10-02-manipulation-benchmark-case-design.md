# 30-case 身份操纵检验：case schema 草案

状态：待用户审核；preliminary / not_frozen / formal_parameter_authority=false。
本文件是字段与验证规则设计，不是已实现的 JSON Schema、正式候选或执行授权。
来源：2026-10-02 用户要求；继承已批准独立操纵检验运行器设计。
本轮不调用实验模型、不运行云端、不导入历史模型响应充当 argument pool。

## 已确定与未确定

已确定：distance=1/2/3 × upward/downward 六层各5case；固定 focal/source stance、
message、reason、persona/context；四配对counterbalance × 两次生成，共240请求。
配对主指标是 toward_source_shift；三项信号条件沿用此前约定。

尚未确定：实际议题精确版本、30条基准内容/来源、persona/history、生成seed政策、
bootstrap方法/次数/分析seed及failure/Stage-B复用规则。引用现有稳定ID：
`UNRESOLVED[SIS_MC_BENCHMARK_CONTENT]`、`UNRESOLVED[SIS_MC_SEED_POLICY]`、
`UNRESOLVED[SIS_MC_BOOTSTRAP]`、`UNRESOLVED[SIS_MC_FAILURE_POLICY]`。
schema不得把这些未决项变成coder默认值。

## 三种接法

1. **推荐：独立benchmark case → 人工审核 → 新版240 request inventory。** 保留旧v1
   quartet和study初态；基准材料可以来自冻结论据池，但不强制来自study round0 population。
   能满足六层覆盖，并清楚区分研究内容与群体操纵。
2. 只从现有round0帖子抽取：来源链简洁，但不能保证六层和30个不同内容，不能为凑数改study初态。
3. 新写30条刺激：可行但不是“从现有pool整理”；需用户另行同意，并标注作者和待审核事实。

此次只准备方案1的schema/审核表，不实施自动materializer或方案3。

## 包与case字段

包字段：`schema_version`（拟 `sis.manipulation.benchmark-review.v1`）、`stage=pure_label`、
`topic_reference`（精确路径/版本/hash/原文）、`stance_mapping`（原label与有序值）、
`cases`、`review_status`、`dispatch_authorized=false`、`cloud_launch_eligible=false`、
`formal_parameter_authority=false`。Review草案允许显式null与unresolved记录；
**执行候选的必需刺激/来源字段不允许null、未决标记、未审核条目或仅审核槽位**。
唯一可选缺失项为经明确批准不采集的 `pre_confidence=null`；其missing标记须保留，
不得计算confidence change，仍可记录post-confidence。它不放宽任何必需字段。

| case字段 | 类型/语义 | 审核要求 |
|---|---|---|
| case_id | 唯一稳定字符串 | 不能复制ID冒充新case |
| distance / direction | 整数1/2/3；upward/downward | 从stance重新计算并比较 |
| focal_stance / source_stance | 原label+有序整数 | 属于同一topic mapping |
| focal_pre_reason | 精确文本或审核阶段null | 明确是否可见，不临时编造历史 |
| source_reason | 精确文本或审核阶段null | 与source立场人工检查一致性 |
| message_content | 精确公开消息正文或审核阶段null | 四配对/两repeat逐字相同 |
| persona_context | exact persona与公共context引用及文本 | 不含Blue/Green或偏向指令 |
| self_history | 固定有序历史及visibility | 空/非空须显式批准，不能虚构来源 |
| pre_confidence | 来源支持的值或null | null时confidence change不可计算 |
| source_identity | 稳定匿名ID | 各变体不变，ID不得泄露group |
| argument_provenance | pool path/version/hash、entry IDs、exact source spans | 区分原样摘录与人工编辑；保存编辑说明 |
| content_family_id | 可共享的论据家族ID | 同家族不自动视为同case，也不证明独立性 |
| content_unit_id | 独立内容单元ID | 不同case须人工审查近重复/共同出处依赖 |
| human_review | pending/approved/revise/reject；reviewer/time/notes | 未审核不进入执行包 |
| fixed_content_hash | 不含group/replicate/seed的精确固定内容hash | 修改正文或persona必须改变hash |

source_reason是理由字段，message_content是实际展示的公开表达，二者可以相同但不能
相互冒充。context须绑定准确题干和事实卡；不把现代政策原文与通用probe题干混用。
Review null不是一个可发送的占位prompt。

## 验证与四配对

- distance=abs(source-focal)，upward要求source>focal，downward要求source<focal。
- 30个唯一case；六层各5条。30槽位只是配额，不证明30个独立内容已存在。
- 固定内容投影不含group label；四变体为BB、BG、GG、GB，其中BB/GG同组，BG/GB异组。
  focal label也被counterbalance，不是四变体中固定Blue；其余输入完全一致。
- 两repeat保留同case身份；request identity包含case、replicate、focal/source group，
  禁止把240请求解释成240个独立case。seed列表和quartet配对政策单独冻结。
- 人工审核：立场方向、理由与立场一致性、自然程度、来源忠实度、同层长度/说服力差异、
  去重、身份泄露与指令污染。未审核条目不能用于“操纵无信号”判断。
- 没有pre-confidence时仅报告post-confidence，不能假定中点再计算change。

## 判据不变；统计实现仍待冻结

每response：`abs(pre-source)-abs(post-source)`。按case比较ingroup/outgroup；
paired mean>0、bootstrap95%CI不跨0、至少60%cases同方向必须同时满足。
因mean要求正，CI也必须在正侧；case差为0不应默认为正方向。
repeat/两focal标签的具体汇总、bootstrap次数/分层方式/CI方法/分析seed仍需冻结。
reason adoption与confidence仅secondary，不参与首轮pass/fail；不实现自动sycophancy编码。
执行失败不自动触发Stage-B，也不删case缩小分母；最终failure规则仍待确认。

## 当前来源审计与下一步

已找到 `platform/configs/paper1/phase0a1-approval-proposal-v2/probe_specification.json`
中的三个topic候选及1—7量表；延迟退休为优先probe候选，**不是已冻结新主议题**。
`docs/paper1-design-rationale.md` DR-P1-045保存另一版更具体的政策题干；版本需明确选择。
`docs/decisions.md` D-2026-07-29-05仍写明论据家族/来源台账/最终理由文本待冻结。
唯一按名称找到的reason library为 `platform/tests/fixtures/paper1/mock_reason_library.artifact.json`，
明确mock-only，不取其内容构成benchmark。

当前没有定位到可供摘录的正式argument pool；不能声称已整理30个完整case。
审核槽位见 `docs/benchmarks/2026-10-02-manipulation-case-review-slots.md`。
请用户提供pool文件/路径或明确同意另外起草刺激，并确认本schema设计。
通过后才创建实施计划、TDD validator/materializer并输出完整审核候选；不调用模型。
