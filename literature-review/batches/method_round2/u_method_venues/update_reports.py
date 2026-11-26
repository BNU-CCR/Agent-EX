import pathlib
R=pathlib.Path(__file__).resolve().parents[3]
def edit(name,pairs,extra=''):
 p=R/name;t=p.read_text(encoding='utf8')
 for old,new in pairs:assert old in t,(name,old);t=t.replace(old,new,1)
 p.write_text(t.rstrip()+'\n'+('\n'+extra+'\n' if extra else ''),encoding='utf8')
edit('README.md',[('30载体（21刊/8会议入口/1仓库）','32载体（23刊/8会议入口/1仓库）')],'批次U：[方法评价期刊补查](reports/evaluation_venue_updates.md)，JSC/AMPPS官方范围、目标指南与费用分列；32载体、22刊条件表。不是32个成熟共同体或原41入口完整覆盖。')
edit('GOAL.md',[('85条、44卡与30载体地图','85条、44卡与32载体地图')],'批次U新增JSC/AMPPS范围与条件条目，32载体/22刊；正式纳入仍32。M027出版社PDF未取得，下一批V按任务书全项审计当前覆盖与缺口，再处理版本/日期队列。')
edit('reports/method_venue_landscape.md',[('30载体地图','32载体地图'),('20刊双轨表','22刊双轨表'),('21期刊、8会议入口、1预印本仓库','23期刊、8会议入口、1预印本仓库')],'U补[JSC/AMPPS官方范围](evaluation_venue_updates.md)：JSC为交叉计算社会入口，AMPPS需跨心理学方法实践价值；单先例不推为持续专门共同体。')
edit('reports/method_landscape.md',[
 ('截止2026-11-26，73条工作记录中core_method25、method_validation17；只有正式纳入且全文支持的核心10、验证8。其余应用5、直接对照15、外围11保持分层。总量含首轮两条排除项与前沿候选，不能说73篇全部纳入或全部精读。','截止2026-11-26，85条工作记录中core_method29、method_validation24；只有正式纳入且全文支持的核心10、验证14。其余应用6、直接对照15、外围11保持分层。总量含首轮两条排除项与前沿候选，不能说85篇全部纳入或全部精读。'),
 ('|数据/理论/规范的透明转译|M010 RAT-RS，THEMP等先例|可追溯模型构造；框架示例与独立方法效果检验分开|','|数据/理论/规范的透明转译|M010 RAT-RS，THEMP等先例|可追溯模型构造；框架示例与独立方法效果检验分开|\n|经验异质性与目标拟合|M023经验策略类型、M025咨询网络生成|同目标建模/搜索与独立检验分开；宏观拟合不唯一识别机制|\n|组件与测量验证|M024情绪组件、R014对话偏差、M026人格心理测量|回答/分类器/构件层证据不自动变成动态外部效度|\n|合成推断与研究实践|M027作者v2批评、M028报告primer|主体抽样、互动依赖与独立run分开；建议/示范非新效果验证|')
 ],'U综合更新：方法发展不限于更复杂平台；校准目标、测量反馈、假设范围、独立重复与复现制品共同限定可主张的知识。当前47个证据单元是定向文献依据，不是领域总体成熟率。更多细节见[sampling_and_reporting_boundaries.md](sampling_and_reporting_boundaries.md)；此前段落“本批/下一批”是历史阅读接续，当前队列以progress为准。')
edit('reports/two_track_submission_strategy.md',[
 ('现有38单元矩阵','现有47单元矩阵'),
 ('T新增方法评价/报告规范阅读证据，见[sampling_and_reporting_boundaries.md](sampling_and_reporting_boundaries.md)。未把指南清单当已验证方法贡献；JSC/AMPPS范围留U核查，尚未加入载体地图/投稿表。','T新增方法评价/报告规范阅读证据，见[sampling_and_reporting_boundaries.md](sampling_and_reporting_boundaries.md)。U已核JSC/AMPPS范围并加入地图/条件表，实际边界见[evaluation_venue_updates.md](evaluation_venue_updates.md)。'),
 ('下一批补Social Science Research有界目录检索、未核载体范围，以及M003/M005/M012/M014/M025日期或版本、CCR正式PDF/网页冲突。','Social Science Research有界检索已做、目录仍403；下一批V对任务书全项逐一核当前证据与缺口，再处理M003/M005/M012/M014/M025日期或版本、CCR正式PDF/网页冲突。')
 ],'U渠道判断：JSC可条件比较受控AI社会过程贡献；AMPPS对当前单应用稿适配较低，后续方法稿须跨心理学读者价值与适当验证。两刊已核费用不改变证据门槛，亦非录用概率建议。')
edit('progress.md',[
 ('|T|两篇方法批评/指南精读、下载核验与5证据单元|提交后回填|','|T|两篇方法批评/指南精读、下载核验与5证据单元|1bbf98a（已推送）|\n|U|JSC/AMPPS官方范围、指南与费用；方法地图综合更新|提交后回填|'),
 ('发表地图30载体=21刊','发表地图32载体=23刊'),('537条累计检索/来源获取操作','551条累计检索/来源获取操作'),
 ('1. 批次U核Journal of Social Computing/AMPPS官方范围与方法发表入口；M027正式PDF有界获取/版本对照，更新方法地图与双轨策略。M027已读作者v2，M028已读正式版式；SSR目录、M025首次在线日与SOCNET范围仍缺。','1. 批次V依METHODS_FIRST_REORIENTATION全部编号要求与GOAL完成定义审计当前交付证据，生成可恢复的验收/缺口表；据此排序下一批版本/日期/载体检索。M027正式PDF、SSR目录、M025首次在线日与SOCNET范围仍缺。')
 ],'### 批次U发现与限制\n2026-11-26：JSC/AMPPS官方范围、目标指南与费用核实，地图32载体/22刊，551日志，主表85条/44卡/47单元/32纳入不变。M027Crossref定位正式IEEE但页面机器人检查、PDF502/连接重置，未强升。AMPPS单应用限制与跨心理学方法价值分开，JSC无作者费并不降低研究证据要求。更新方法地图当前统计与双轨策略；41命名入口不因额外两刊自动完成。完整目标继续进行。')
