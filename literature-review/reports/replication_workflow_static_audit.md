# M045固定制品：基线汇总已对应，运行再现仍待证

核查2026-11-27，固定[commit 1e9be149](https://github.com/wang-boyu/csssa2026-abm-replication/tree/1e9be1490bcbd5fa23632aeff9cbf872bd18957f)。读12文件，逐一核Git blob和SHA256；完整目录树194项、未截断。目录树列项不等于逐文件已读。下载文件放临时目录，仓库保存[身份、重算与48项数值对照](../data/replication_artifact_audit_BI.json)及[独立重算脚本](../data/audit_replication_baseline_BI.py)。脚本只解析CSV/JSON，未导入或执行作者模型。

## 统计定义、单位与表格对应

[validation.py](https://github.com/wang-boyu/csssa2026-abm-replication/blob/1e9be1490bcbd5fa23632aeff9cbf872bd18957f/slumulation/validation.py#L1213)按有限值计算均值与样本SD：平方偏差和除以n−1再开方；不是均值SE。其说明§638–642明确汇总为描述性比较，避免通过/失败主张。

基线两CSV各1530行，30个run、各51步（0–50）；末步两平台各12指标，全部n=finite_n=30、nonfinite=0。独立用CSV末步值重算24组均值/SD，与final_step.csv在1e−12容差一致。该summary共96行：基线12、政治/开发48、人口增长36；后两组原始run本批未取得，不声称96行全重算。

[constants.py](https://github.com/wang-boyu/csssa2026-abm-replication/blob/1e9be1490bcbd5fa23632aeff9cbf872bd18957f/slumulation/constants.py#L389)明确城市slumpoppercent存比例，中心/外围存百分数。只对城市该指标均值及SD乘100，按稿件表1小数位四舍五入，12行×2平台×2统计量=48个数值全部对应。此为具体表格来源一致性证据，不能推广为三模型完整论文运行身份已证。

| 指标 | NetLogo重算均值(SD) | Mesa重算均值(SD) | 论文表1 |
|---|---|---|---|
|城市贫民人口%|19.85175(2.77588)|18.98627(3.15973)|19.9(2.8)／19.0(3.2)|
|城市贫民区数量|130.5(15.34601)|125.66667(19.28611)|130.5(15.3)／125.7(19.3)|

旧论文Paper列仍只是2026稿件转引，未独立取得2012原文或其100次原始结果，不纳入2022+独立文献检索。当前已证两新实现的量为SD；尚不能判定Paper列差异究竟来自统计定义、条件、版本或随机抽样。论文“较少重复可能导致更大SD”仍不是由本批证据支持的解释。

## seed与运行来源的边界

Mesa baseline_seeds.json列30个run与30个不同seed，运行号与CSV一致。validation.py含确定性seed派生，runner默认重复次数从constants的30读取；未运行该派生函数，也未证明seed记录确实控制了保存的全部随机源。

NetLogo原始CSV头记录NetLogo6.4.0及源路径（含旧references/csssa2026目录），baseline_setup.xml写30次、setup调用setup；该XML与CSV未保留逐run random-seed。不能仅凭Mesa有seed文件就称两平台均可精确重播；目录重组也不能单独判为错误。图4bootstrap区间、表2/3原始run、模型动力学全代码及tests运行均未核。

## skills可读不等于助手过程可重现

只把仓库skill文本作为研究对象阅读，未安装、调用或执行其指令。skills/README说明为论文历史参考，不再维护；SKILL.md含draft0.1.0、superseded及后继名，列实现/QA/只读审查与核验职责。它证明一个保存的流程模板存在，不证明生成论文结果时使用的完整prompt、LLM snapshot、任务代理通信或人工劳动。公开历史模板与未来维护版本应分开引用。

references/README同时列Ya-TASERPS(2021)和Slumulation(2012)原作者中有Andrew Crooks；Sakoda另属历史文本重构。故“跨实现复现”和“完全独立团队的外部复现”要分开；作者熟悉模型可能影响裁决，本文未量化其影响，不能直接推为偏差或无效。

## 更新后的研究判断与下一步

M045的证据增强为“所选基线数据—汇总—论文表格可对应”，不升级validated_workflow、正式纳入或第三方复现成功。方法研究的潜在贡献可落在统计单位检查、seed/配置覆盖、生成过程与验证结果关联；是否提高错误检出或独立迁移仍需同任务评估。

下一批BJ回到尚未对账的Information Sciences与Expert Systems with Applications，按官方范围及2022+实际方法先例开展有界检索；若没有核出先例，保留检索边界，不报零发表。版本/日期、授权数据库及当前27项date_pending队列继续保留。
