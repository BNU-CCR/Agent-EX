# Retirement MC：研究材料冻结记录

2026-10-08，用户明确批准A—D，决策D-2026-10-08-01。
这里只冻结研究材料；不是源码bundle、云端receipt或dispatch授权。

## 正文

`platform/configs/identity-network/manipulation-retirement-20261008/benchmark.json`
为最终30条精确正文。v3其余29条不变；仅AD-028改为：

> 我非常不支持逐步提高法定退休年龄。我觉得什么时候退出长期工作应该尽量给个人留出选择，而不是统一把法定退休年龄往后推。

reason_family=选择自主：退出工作选择。004/023的shared_reason_family_ids同时为
`age-rule-justification`；统计独立arguments声明为false。旧草稿保留历史pending原义。
全部最终正文human_review=approved，self_history=[]、pre_confidence=null；
post-confidence仅描述性，不算change，不修改正式study memory。

## Stage-B精确文本

Blue：

> 你属于蓝组。蓝组是本次讨论中的一个固定讨论小组，你的组别在整个讨论过程中保持不变。

Green：

> 你属于绿组。绿组是本次讨论中的一个固定讨论小组，你的组别在整个讨论过程中保持不变。

来源显示精确模板：`蓝组成员 Member {source_id}` / `绿组成员 Member {source_id}`。
source_id跨同case quartet保持同一匿名身份；不以group产生ID。
只替换群体framing/来源标签，不改case、理由、persona/history或seed规则。
没有trust/norm/共同立场/护群指令。未运行Stage-B；只有完整有效Stage-A不满足三标准，
且服务/dispatch授权齐备时才允许启动，不自动切换。

## Hash口径

canonical hash：项目canonical_payload_hash，即UTF-8、ensure_ascii=false、sort_keys=true、
separators=(',', ':')、allow_nan=false的JSON编码SHA-256。
它绑定完整研究JSON对象，不等于某一条prompt或最终服务request hash。
file hash为当前文件字节SHA-256；Git CRLF转换可能改变file hash而不改变canonical hash。

| 文件 | canonical SHA-256 | 当前file SHA-256 |
|---|---|---|
| benchmark.json | 9c2345580024523794a2d433500229d55e166414f18f5c0bd06baba893c8eb10 | 81a603f6fb9dc3e2ab7df848ea0a7e74ddde8457f33d5db7e804eca8cf18c459 |
| stage-b-framing.json | 65a5707ca065bc719f747801231d919f8b5a0fa9c7c50041afa4d068f342f5bf | c6d4000691ebb102ade19b15e60376f9a0154eb73b3e96e83be48f5253816bcb |
| analysis-policy.json | 06cde384ae6bcd89f77deb628110dad5a8777f7bbdfc21e9f2505c5e894093c0 | aeab0cc7789d1fb36300c321d06e84045390fba284cc6eb6963faacac4cad60e |

analysis-policy记录已批准统计规则；生成seed的精确派生实现仍为
UNRESOLVED[SIS_MC_SEED_POLICY]，这不表示已批准的配对/namespace规则未决。
后续补派生算法/RNG版本会产生新的policy hash，必须记录版本，不静默覆盖本快照。
30case文本与Stage-B精确framing不因此继续优化。

## Retry实施边界

研究规则已允许2次额外retry，总最多3attempt，同logical request identity与同prompt/参数/seed。
attempt须单独编号、保存每次intent/response/parse证据，不擦除失败attempt。
明确技术失败才可以按冻结规则重试；超时/进程死亡若不能确认服务是否处理，
归为未决dispatch，保留证据，不盲目重发。不得把保存的response重新送模型。
耗尽后Stage-A=INCOMPLETE，无实质pass/fail、无Stage-B、无删换case。
旧runner/storage零retry合同不会因文档批准自动迁移：须新增版本及崩溃/恢复专项测试。

## 当前实现

纯benchmark validator已完成首轮TDD专项；不会产生HTTP或启动权限。
retry store、materializer、独立CLI与统计报告尚未全部实现；没有真实240结果。
本地准备完成后再申请开启服务器和运行Stage-A。
