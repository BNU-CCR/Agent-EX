# IPM方法路线、日期与全文边界

核查截止2026-11-27。复用R005/RoleSimLLM和M047/From rules to reasoning原ID，不新增重复记录或全文卡。

## 官方范围与投稿判断

[Elsevier商店官方描述](https://shop.elsevier.com/journals/information-processing-and-management/0306-4573)直接HTTP200，强调计算与信息科学交叉处的理论、方法与应用，涉及social computing等领域；列research、methods、review和critical application四类。它为社会信息过程和可迁移模拟方法提供范围依据，不等同所有ABM论文均适配。

ScienceDirect专门scope与guide均403。当前篇幅、数据/代码具体强度、费用资格和独立MJL索引不猜填；商店的索引自述仅为出版社声明，不升级独立索引核验。方法地图新增IPM，条件期刊表新增一项；当前稿需说明信息科学问题与过程/指标，后续方法稿需跨任务效度或计算方法比较。以上适配为本项目推论，不是编辑保证。

## 首次在线日期不能由索引推定

| 工作 | 已核来源 | 仍未解决 |
|---|---|---|
|R005 DOI10.1016/j.ipm.2026.104689|Crossref卷期2026-07，created2026-02-23；作者站列63(5),104689|Crossref无published-online；作者站无精确首发/全文链接|
|M047 DOI10.1016/j.ipm.2026.105184|BJ已核卷期2027-02，created2026-09-18|正文Article history及精确首次在线日未取得|

OpenAlex分别报publication_date2026-02-23和2026-09-18，与上述登记日一致；数据来源转换未核，不能当独立出版社首发证据。本批两项仍date_pending/candidate，所读仍摘要。2027卷期本身不能排除2026已上线，也不能反向证明已上线日期。

## 合法全文路径实际结果

两篇ScienceDirect文章直开403。R005[第一作者出版页](https://starkkkk.github.io/publications/)只有DOI链接；未读同页其他工作的代码作为R005制品。OpenAlex snapshot两项均无best_oa_location；R005仅DOI位置，M047另列[NTU handle10356/232982](https://hdl.handle.net/10356/232982)，未提供PDF地址。

NTU在web工具不可达，静态访问重定向dr.ntu.edu.sg/handle/10356/232982后HTTP429/0bytes，未获取元数据或PDF；不再连续重试，不称机构库不存在全文。OpenAlex closed状态不是全互联网无合法稿件的证明；只记录本轮未取得。未使用付费代取、请求他人发送或绕过授权。

## 摘要声明与下一步

R005的角色共享、百万级数据、AUC/MLSE与成本比例仍是摘要声明；角色分布采样与逐人LLM、校准/测试分割及预算分母需正文。M047的1064研究、跨范式比例与时间控制亦待全文，不能替代本库2022+检索。两项不升成熟度或正式纳入。

下一批BL补Political Communication、Journal of Communication的官方范围与2022+实际方法/应用先例，区分已有首轮记录、真实研究与评论；继续日期/版本队列。两篇IPM暂待新的可访问作者/机构稿或正式Article history来源，不以局部访问障碍停止其他工作。
