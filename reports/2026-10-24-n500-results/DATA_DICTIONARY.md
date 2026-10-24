# 数字数据字典与复算口径

每seed（20261201–20261210）包含：

- `summary.json`：本批schema `sis.n500-core.seed-summary.v1`，终点各格方差、同seed配对contrasts、primary_contrasts及云归档backup_sha256。
- `verification.json`：六个run的15000/15000事件数、pending0、状态及链头；核验scope原文保留，不等于所有早期快照都逐事件重新完整构造。
- `trajectories.csv`：6条件 × 31观测点（Round 0..30）＝186行，10seed合计1860行，不是1860独立统计重复。

## 字段

| 字段 | 含义 |
|---|---|
|matched_seed|匹配重复单位；同seed六格配对|
|cell_id|SIS-A0/1-B0/1/2；见结果页条件映射|
|sweep_index|0为初始库存/私人状态，1..30为已提交观测边界|
|private_mean|全部500名Agent当前私人1–7立场的均值|
|private_variance|总体方差，分母500，不是样本方差|
|public_mean/public_variance|每名Agent最近公开帖构成的500人公开库存分布|
|private_hist7/public_hist7|分别按1..7档的7个整数人数，JSON数组字符串，每行和为500|
|flow_mean|该sweep实际新增公开帖的立场均值；空值为没有新帖，不填0|
|flow_count|该sweep新增公开帖数，不含Round 0库存|
|gap_mean|500人平均(private_i−latest_public_i)|
|gap_absolute|500人平均abs(private_i−latest_public_i)，不是abs(gap_mean)|

## 计算

对每seed、cell单独计算终点，再对10seed等权汇总；不把Agent或事件当独立重复。

`mu = sum(k*n[k])/500`

`variance = sum(n[k]*(k-mu)^2)/500`

其中k=1..7。七档为有序量表，使用方差引入等距数值化假设，因此须同时看完整直方图。

对固定A，primary配对差为`V[A,B1,30]−V[A,B0,30]`和`V[A,B2,30]−V[A,B0,30]`。

identity差为同seed `V[A1,B]−V[A0,B]`；DiD为`(V[A1,B]−V[A1,B0])−(V[A0,B]−V[A0,B0])`。

结果页±是10个seed指标的样本SD（分母9），不是标准误、CI或run内500人SD。方向计数也是10seed计数，不是检验p值。相对B0降幅为“两个跨seed平均方差之差 / 对应平均B0方差”，不是逐seed百分比的平均。

每条件的终点直方图占比为10个run对应档人数之和/5000。因每run N相同，等于逐seed比例均值；这只用于描述比例，不将5000视为独立样本。

汇总表达流mean时用flow_count加权；Round 0不计入后续发布率。库存取边界状态，不能把各sweep库存相加当帖数。

文件完整性见`FILE_MANIFEST.json`，其中source_sha256与repo_sha256相等。该manifest绑定数字副本，不替代Git外原始链及云归档验证。
