# 三项正式出版月资格：FB

2026-11-28。三条出版社登记Crossref均200，题名/作者/载体核对通过，published与published-print分别给出正式出版月；没有published-online。依原任务书§3.2，在首发日未知时用可核实正式出版日期回退，不将created、DOI后缀、稿面日期或版权年当首发日。

|记录|正式出版月|本批资格|全文/版本与筛选|
|---|---|---|---|
|R005 RoleSimLLM|2026-07|confirmed|仅摘要，仍candidate；不能从时间合格推断验证内容|
|M025 网络咨询ABM|2024-01|confirmed|既有作者托管正式版式全文/方法卡，现included；横截面拟合与选择局限保持|
|M031 双主体行为校准|2026-10|confirmed|已读作者v1，但正式摘要增加ML基线，仍candidate；数值只归原版本|

来源：[R005登记](https://api.crossref.org/works/10.1016/j.ipm.2026.104689)、[M025登记](https://api.crossref.org/works/10.1016/j.socnet.2023.09.001)、[M031登记](https://api.crossref.org/works/10.1016/j.trc.2026.105818)。[获取账](../batches/method_round2/fb_formal_month/acquisition_manifest.json)保存响应hash与题录日期；本次未新增正文获取。M025复用CF十页PDF，再核首页DOI/作者/卷页/许可并目视；首页没有精确在线日，不据其2023版权猜日。此前两卡Git原字节归档。

时间字段online_first_date沿用既有兼容字段保存回退年月，date_basis明示formalpublicationmonthfallback，不能读成该月即最早在线月；来源分布/引用据可核准精度报告。M031有已知实质版本差异，与M003作者声明仅排版分页不同的情况不同，不能因为合法作者稿可用就抹掉基线变化。R005时间合格也不替代全文。

M025保留application/empirical_method_test/empirical_validation，只说明已有经验网比较，不升级为独立纵向或多场景效度。未加新卡/矩阵单元或执行模型。Social Networks仍单一传统ABM先例/条件观察，不因新增纳入数提高推荐。

当前238条：69included/159candidate/8frontier/2excluded；87卡/252单元保持。当前正式期刊50记录/30来源，另19会议；55发表载体/30条件投稿刊不变。日期待核24→21；1842→1847分组来源操作。下一项FC按相同原规则核官方会议出版年/月队列M020/M021/M036/M037，先确认正式轨道与已取得正文，未证正式身份者仍待核；不把会期直接当出版日，也不再增加精确日硬门。
