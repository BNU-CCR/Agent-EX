# MC离线物化与统计实现记录

截至本次本地实现：30case正文不变；240条是离线试次身份，**不是已发送request或真实结果**。
冻结benchmark hash为9c2345580024523794a2d433500229d55e166414f18f5c0bd06baba893c8eb10。

## 物化

入口：`platform/src/agent_ex/identity_network/benchmark_trials.py`。
冷验证正文后，每case固定内容只存一次；顺序为case冻结顺序→repeat1/2→BB/BG/GG/GB。
生成240个trial ID，四变体只在group labels不同，共用case/repeat seed；source_id不随group改变。
不包含服务地址、模型generation参数、wire body或dispatch receipt，不能当真实运行包。

seed派生精确定义：项目canonical JSON SHA-256，输入namespace=sis-mc-stage-a-v1、
case_id、repeat_id；取前8个hex字符为big-endian uint32，再按位AND 0x7fffffff。
实际60个seed无碰撞；碰撞拒绝、不换seed。无prompt结果或stance效应参与派生。
生成算法不保证vLLM在不同prompt下共享随机路径或硬件确定性。

seed表/算法、bootstrap实现及inventory hash保存于
`platform/configs/identity-network/manipulation-retirement-20261008/seed-analysis-implementation-v1.json`。
inventory payload hash：6aba583ad74921a4a3d0e9822b985d6385176fd04e31e1db7eea901473336e6f。
可从冻结benchmark完全重建，重哈希的篡改trial仍须冷重放拒绝。
10-08原analysis-policy.json作为研究决定快照保留；其中派生实现UNRESOLVED已由本版本化扩展绑定，
没有静默覆盖旧hash，也没有授予cloud或Stage-B权限。

## 统计

入口：`platform/src/agent_ex/identity_network/benchmark_analysis.py`。
输入为规范化trial_id/status/post_stance，必须先冷重放inventory，拒绝未知/重复ID或非法stance。
缺项/INVALID只返回INCOMPLETE，无substantive信号或CI；完整240 VALID才计算。

按已批准shift/ingroup-outgroup/repeat均值/30case等权公式；case>0计正，要求至少18。
六strata各有放回抽5，10,000次，analysis seed20261008；实现为CPython3.12.14
stdlib random.Random MT19937/randrange，按distance升序、direction词典序固定抽样顺序。
percentile端点采用h=(n-1)*p的线性插值，p=0.025/0.975。
分层、distance及direction均值只描述，不增加判据。

数学报告明确transport_evidence_verified=false、stage_b_dispatch_authorized=false。
它不验证真实模型attempt/response来源；未来CLI须先验完整durable transport链，
不能拿合成outcomes产生的数学PASS冒充实证结果或激活Stage-B。
共享argument family的统计依赖限制仍保留，case级bootstrap不是独立性的证明。

## 验证与下一断点

41项专项通过：20内容校验、8离线试次、13合成统计；Ruff与diff check通过。
独立限定审查未发现重要问题。无云端、无模型请求、无原始response读取。
下一项为版本化retry存储/transport/CLI：同request最多3attempt，完整证据保留，
歧义INTENT不得盲目重发；后续Linux锁/来源/服务验收尚未完成。现在无需开服务器。
