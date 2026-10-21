# Stage-B真实操纵检验完成：结果、备份与后续边界

2026-10-21，北京时间。独立benchmark，不是六格网络pilot或正式主实验。

## 执行事实

- 用户明确批准运行单全部绑定，48小时receipt截至2026-10-23T09:06:49Z。
- 客户端干净source af08446623021450f57dfa5ea802186116445d16；复用服务PID9943，
  无重启/采样修改。Qwen3-8B BF16/non-thinking，固定revision和runtime同A。
- B独立技术预检2/2 VALID，5.412秒；完整原始本地备份及逐文件SHA通过后，
  stage-b控制12629于北京时间17:09:27开始，240/240 VALID，480 journal transitions。
- run、冷验收、打包共165.868秒（约2分46秒），controller exit0；无pending response。
  该时长不是纯解码时间，也不能直接外推到长上下文、多事件、正式网络实验。
- 不修改/覆盖A store；B入口每次run/verify冷验A实际证据，不套用A preflight或receipt。
- 30case×4×2与同seed/原统计规则不变，仅加入原冻结stable-group self frame和来源前缀。

## 预冻结三项联合标准

| 标准 | 观测 | 满足？ |
|---|---|---|
| case等权mean>0 | 0.450000 | 是 |
| 六层内bootstrap 10,000次percentile95%CI不跨0 | [0.275000, 0.616667] | 是 |
| d[c]>0至少18/30 | 12/30=40% | 否 |

结论：B完整执行，但未通过三项联合信号标准。代码NO_SIGNAL是联合规则标签，
不等于证明零效应；不能只取正均值/正CI宣称操纵通过，不能事后下调18/30门槛。
12个case为正，其余18为0，无负case；共享argument family的独立性限制仍保留。

描述性分层（不是额外pass/fail）：distance1/2/3均值为0.65/0.50/0.20；
upward/downward为0.1333/0.7667。confidence仅描述，没有pre-confidence，不能算change。
本轮没有自动sycophancy/reason adoption编码，不把意见变化解释为已验证机制。

## A/B并列汇报（不合并样本，不作未注册的跨stage效应检验）

| 阶段 | 有效请求 | mean | 95%CI | 正方向case | 联合判定 |
|---|---:|---:|---|---:|---|
| A纯标签 | 240/240 | 0.6083 | [0.5333,0.6917] | 15/30=50% | 未通过 |
| B固定小组框架 | 240/240 | 0.4500 | [0.2750,0.6167] | 12/30=40% | 未通过 |

合计480条真实benchmark请求，另有4项独立技术预检。A/B使用相同30case/seed，
不能将480当独立重复数、不能合成60个独立case，也不能由均值大小直接断言B更弱。
这些已是可汇报的真实操纵检验数据，但不是正式2×3网络动力学结论。

## 终态与本地完整备份

- packet canonical hash：4ac85e6605c7df7dcf967a39f06220a006e557bae4b49d57e515c3ec2ca3cfe8。
- terminal journal tail：f1ea6a3e4cf2b7a71fe209c74b2e4aa7b6422dc25df6a494c11a3848e60d9ae8。
- report文件SHA256：bac18fba8f04c0d9af46f764f94879762d79c2983c0bc8c215d94a4ab3945845。
- 完整原始证据tar612,504字节：
  C:/Users/Bai Yuexi/Agent-EX-evidence/2026-10-21/stage-b-evidence.tar.gz。
- 本地/远端包SHA一致：5d2ff837082538fe1e2ab78b5bec74138a319c1e465ddbe7e59609a997e68326。
- 归档含B原始SQLite/intent/response/result、包/receipt、runtime/服务观察/启动来源、
  冷report及逐文件清单。两个run文件（SQLite和0字节锁）SHA/大小/数量均匹配；
  备份完成北京时间17:12:32，本地watcher26248正常结束。
- 作为B前提的A完整归档仍在同目录，实际重核SHA仍为
  ddaf37487812f6f11cf2fdb85c90ee18ff801b32b42c2bae14f66910ba5f0211。
- 原始SQLite/tar不进Git，不在对话中读取/输出raw response/public_reason。
  当前目录仅保留安全汇总、参数/绑定和原始证据定位。

## 下一步需要研究决策

两个预设阶段均未通过联合标准，不能自动Stage-C、改prompt追效应、挑case/分母或改判据。
当前也不能把后续六格主实验写成“已通过social identity salience操纵检验”。

可供人类决定的下一步：

1. 保留本轮失败准入结果，先做明确标注的六格探索性/技术pilot，验证网络事件、轨迹和吞吐，
   不把它当通过身份操纵的confirmatory主实验；pilot具体N/T/seed、topic、K/B、图参数、
   attention/publication等仍需显式候选绑定，不能由旧legacy默认补齐。
2. 先做方法复盘并重新讨论构念/操纵方案；如研究方向或准入规则有变，另建新规格/注册，
   不追改本轮A/B结果，也不暗中开始新的prompt搜索。

本轮不替人类选择路径，不自动发新请求。当前服务仍保持运行，但无benchmark run在执行；
所有新证据已完整备份。部署心跳暂停以免空转，长期目标尚未完成。
