# 身份操纵检验：上云前最终确认单

2026-10-08；proposal / not_frozen / dispatch_authorized=false。
目的：集中剩余人工决定，不再扩展case或调整prompt追求效应。
本文件是确认建议，不是批准receipt、冻结机器协议或240请求清单。

## 已确认，不重复询问

- 通用延迟退休原题干/事实卡与原1—7 stance mapping。
- focal=4且context明确中立；仅MC sensitivity，不规定主实验初始分布。
- persona：“你是一名成年公民，日常会接触社会公共事务，也会阅读和讨论有关政策的话题。”
- 六层各5case，BB/BG/GG/GB × 2 repeats，总计划240请求，不扩展数量。
- 三项判据：paired mean>0、bootstrap95%CI在正侧、至少60%case为正方向。
- 无consistency指令，无group规范；reason/confidence只作secondary。

## 需要人工确认的四组决定（以下均未生效）

| 组 | 未决ID | 建议 / 需要回应 |
|---|---|---|
| A：30条正文 | SIS_MC_BENCHMARK_CONTENT | 审核`retirement-30-case-draft-v3.md`。可列需修改的AD编号，其余明确批准；也可确认整版。尤其AD-028的程序性顾虑是否支持极端反对、AD-004/023是否过近。不因“继续”而自动approved |
| B：history/confidence | SIS_MC_BENCHMARK_CONTENT | 建议本独立MC使用显式空self_history，由指定focal_context提供pre-stance；不虚构多轮记录。建议pre_confidence=null，post-confidence描述性报告，不计算change。只适用于MC，不改正式study memory |
| C：配对/seed/统计 | SIS_MC_SEED_POLICY、SIS_MC_BOOTSTRAP | 建议下述case-level聚合、分层bootstrap及固定seed规则；需要明确批准，不能当代码默认值 |
| D：失败/Stage-B | SIS_MC_FAILURE_POLICY、SIS_MC_CRITERIA | 建议仅完整240项VALID才做信号判定；失败停止且不删case/改分母。仅完整有效Stage-A且无可靠信号时才申请Stage-B，沿用case/判据，仅替换预定义中性framing；其精确文本与transition仍需另行批准 |

空history与pre-confidence缺失属于简化建议，不是已经获批，也不是研究助手发现“原数据缺失”。

### C组的精确建议

每次response：`shift = abs(4-source_stance) - abs(post_stance-source_stance)`。
对case c、repeat r：

`d[c,r] = (shift[BB,r] + shift[GG,r])/2 - (shift[BG,r] + shift[GB,r])/2`。

`d[c] = (d[c,1]+d[c,2])/2`；primary mean为30个`d[c]`等权平均。
case为统计重采样单位；不是把240个response当240独立重复。
一致方向指`d[c]>0`，零不算正；至少18/30正方向。此处明确聚合此前未冻结的repeat/标签细节。

建议bootstrap：六个strata分别从各自5case有放回抽5，保留case内全部配对与repeat；
10,000次，percentile 2.5%/97.5%区间，分析seed=20261008。
实现前须指定RNG算法/库版本并用合成数据测试；当前只提供方法候选，不执行统计或声称已实现。
共享reason family的case可能依赖；分层bootstrap不自动解决这种依赖，须在内容审核中处理并报告限制。

建议生成seed：按固定namespace `sis-mc-stage-a-v1`、case_id、repeat_id（1/2）确定，
同case同repeat四变体共用seed；两repeat不同seed，各case不共享seed。
精确整数表、派生算法与碰撞检查须在候选物化前冻结；本文件不提前生成seed表或请求清单。
相同seed并不保证vLLM不同prompt下的输出可复现或共享随机路径；仍记录实际模型/环境。

## 实现断点（截至本地HEAD d9df67a）

- 独立runner设计已批准；request inventory合同、专用SQLite存储和预检已有本地实现记录。
- 完整transport循环、独立run/resume/verify/report与执行origin验收尚未收口。
- 未提交的transport-loop plan/test原样保留，不作为已通过证据。
- 30case审核schema仍为文档设计，不声称已有真实240候选validator/materializer或统计分析器。
- 旧797 judge完成是legacy校准证据，不是本MC或新2×3实验结果。

## 接续顺序与服务器时点

1. 用户确认A—D；记录精确内容/来源与批准范围。不替用户填未决值。
2. 经允许恢复本地实现：benchmark validator/materializer、独立transport/CLI、case级分析。
   仅专项假服务/崩溃恢复与合成统计测试，不重复全仓pytest。
3. 生成实际候选/hash与source bundle、操作命令；取得精确上传/运行授权。
4. 此时请用户开服务器：先验Linux锁、环境/来源/服务身份，再小量连接验收，随后240 Stage-A。
5. 完整有效结果后按冻结判据判断；不按结果调文本。操纵检验后才准备小六格pilot，
   正式N/T/seeds/primary仍独立冻结。

当前无需开服务器，未上传、未生成240请求、未调用实验模型。无法从尚未测得的吞吐推定云端时长。
