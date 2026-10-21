# Stage-B benchmark：最小独立接入设计

状态：用户2026-10-21明确确认Stage-B同30case×四配对×两重复=240，同seed/判据，
仅加入预冻结群体框架，独立请求与存储。设计为已确认提案的实施规格，不授权上云。
依据：reports/2026-10-21-cloud-deployment/stage-b-next-step-proposal.md、
stage-a-result-brief.md、2026-10-08 stage-b-framing.json。

## 冻结与兼容

Stage-A与legacy原义保持：默认pure_label inventory、原renderer、wire、packet均保持原hash。
Stage-B独立stable_group inventory/request/event/attempt身份，与A和各自技术预检均不重叠。
seed仍复用既有namespace派生的60整数，不能更改派生或作为跨阶段独立重复解释。
同benchmark正文/stance/persona/空history，完整source_message，不展示重复source_reason。

Stage-B只从固定hash的stage-b-framing.json提取精确self_frames和source_templates：
结构中增加self_group_frame，来源member_id按“蓝组成员 Member 001”模板显示，
保留相同匿名编号与source_group；不添加trust/norm/consistency，不改变system/采样。
将framing hash与renderer version写入B packet，不改A payload。

## 研究与运行门

只接受相同benchmark/runtime绑定的完整Stage-A：240/240 VALID、COMPLETE、
顶层transport_evidence_verified=true、无pending response、math execution complete、
按冻结三项规则未全通过。通过A、缺失、INCOMPLETE、歧义或runtime不符全部拒绝B。
B packet绑定完整安全A report（journal tail/outcomes/packet/approval哈希及其数学判定）。
离线构造可验证报告结构，实际run/resume/verify必须重新冷验A store并与绑定报告比对，
不能把用户自行填的数学汇总当真实执行证明。运行时传入stage_a_root，不依赖可伪造路径字符串。

B采用preflight-b（2）和stage-b（240）两个mode，独立packet/receipt/store。
receipt保留现有schema，mode严格等于对应packet；A receipt不能借用。
B正式run要求同B renderer/runtime/source的完整B preflight；不能借用旧A预检。
同一run root只能持有一个packet；错误包在网络发送前拒绝。A数据/receipt不可覆盖。

## 数据流与组件

- benchmark_trials：显式支持pure_label/stable_group，保持默认hash；seed/四配对不改。
- benchmark_stage_b：固定framing与A证据门；只负责验证/投影，不承载网络循环。
- benchmark_transport：仅B modes增量渲染/独立身份和framing绑定；保留默认A路径。
- benchmark_run：可构造带A证明的B包；run/resume/verify对实际A store冷核验；
  独立B preflight检查；分析复用同公式，但使用B inventory，不混合A观察。
- benchmark_store：区分四mode及精确2/240长度，继续复用SQLite/lease/journal，
  不引入新的表或放松现有重开/重试验证。
- benchmark_cli：B materialize/inspect/run/resume/verify/report需--stage-a-root；
  仍不创建人类receipt，不自动授权B。

## 失败与分析

同prompt/seed最多2次额外retry，只对已知parse/429；歧义停止，不自动resume或重发。
240全VALID前不做substantive判断；primary/10,000分层bootstrap/seed20261008/18正case不变。
B结果标注stage=stable_group，A/B分别汇总；不自动Stage-C/六格实验。
冻结framing、系统或参数变化必须失败；绑定报告/packet/receipt篡改在HTTP之前拒绝。

## 验收与交付

先失败测试再最小实现，仅运行相关专项：A固定hash回归，B240/三attempt精确wire、
同case/repeat四配对共同seed、A/B与preflight身份隔离、允许字段外无变更；
完整A门与错误报告/通过A/部分A拒绝；B SQLite无歧义重开/已存response恢复/次数上限；
真实adapter形状假HTTP两事件/240流程、CLI冷重建与报告，不调用模型。
使用合成A证据的测试必须显式标明synthetic，不能作为真实Stage-B结果。
本地专项/格式/diff通过后交付新源码commit/bundle及候选runtime/request hashes；
上传/服务变更/真实B请求需单独批准。云端实际身份/Linux专项未验证不能声称已准备正式运行。
