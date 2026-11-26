import pathlib
R=pathlib.Path(__file__).resolve().parents[3]
def edit(name,pairs,extra=''):
 p=R/name;t=p.read_text(encoding='utf8')
 for old,new in pairs:assert old in t,(name,old);t=t.replace(old,new,1)
 p.write_text(t.rstrip()+'\n'+('\n'+extra+'\n' if extra else ''),encoding='utf8')
edit('README.md',[('新增26项工作、补读5条原记录，现83条、42张全文卡；31项正式纳入、44候选','新增28项工作、补读5条原记录，现85条、44张全文卡；32项正式纳入、45候选'),('42个证据单元','47个证据单元'),('书目仅31项正式纳入','书目仅32项正式纳入')],'批次T：[合成抽样与报告边界](reports/sampling_and_reporting_boundaries.md)，M027作者v2/M028正式版式两卡，5个概念证据单元；下载身份/hash分列，未复跑。最新累计见progress，历史批次数字保留。')
edit('GOAL.md',[('当前83条、42卡与30载体地图已经保存','当前85条、44卡与30载体地图已经保存')],'批次T完成M027/M028定向精读，85条/44卡/47证据单元、32正式纳入；M027正式全文版本待核。下一批U核JSC/AMPPS官方范围和正式PDF，并更新方法地图/双轨策略，目标继续进行。')
edit('reports/method_validation_matrix.md',[('42个证据单元','47个证据单元')],'T新增VC43–47，涵盖合成抽样与互动依赖、测量误差及建议/政策边界；conceptual guidance不算新实验验证。详见[sampling_and_reporting_boundaries.md](sampling_and_reporting_boundaries.md)。')
edit('reports/claim_evidence_readiness.md',[('依据现有阅读卡与38单元矩阵','依据现有阅读卡与47单元矩阵')],'T补[抽样与报告边界](sampling_and_reporting_boundaries.md)：更多AI重复不自动消除真人目标错配；报告充分性、独立测量和动态效度须分别证明。')
edit('reports/agent_ex_method_positioning.md',[],'T补[合成抽样与报告边界](sampling_and_reporting_boundaries.md)，区分独立受访者抽样、主体互动与独立run；不把指南Optional覆盖本项目冻结规范。')
edit('reports/two_track_submission_strategy.md',[],'T新增方法评价/报告规范阅读证据，见[sampling_and_reporting_boundaries.md](sampling_and_reporting_boundaries.md)。未把指南清单当已验证方法贡献；JSC/AMPPS范围留U核查，尚未加入载体地图/投稿表。')
edit('progress.md',[
 ('|S|Social Science Research官方范围与有界目录审计|5a85687（已推送）|','|S|Social Science Research官方范围与有界目录审计|5a85687（已推送）|\n|T|两篇方法批评/指南精读、下载核验与5证据单元|提交后回填|'),
 ('主表83条：included31、candidate44','主表85条：included32、candidate45'),('方法核心29、方法验证22、应用6','方法核心29、方法验证24、应用6'),('核心10、验证13','核心10、验证14'),('42张全文卡含前沿','44张全文卡含前沿'),('不能等同42项正式纳入或42篇出版社版','不能等同44项正式纳入或44篇出版社版'),('验证矩阵42证据单元，不是42次独立实验','验证矩阵47证据单元，不是47次独立实验'),('522条累计检索/来源获取操作','537条累计检索/来源获取操作'),('Bib仅31项正式纳入','Bib仅32项正式纳入'),
 ('1. 批次T先查重并核Evaluating the Use of Large Language Models as Synthetic Social Agents in Social Science Research（10.23919/JSC.2025.0022）与A Primer for Evaluating Large Language Models in Social-Science Research（10.1177/25152459251325174）的正式日期/全文；作为方法验证和报告规范线索。SSR先例/目录、M025首次在线日与SOCNET范围仍缺。','1. 批次U核Journal of Social Computing/AMPPS官方范围与方法发表入口；M027正式PDF有界获取/版本对照，更新方法地图与双轨策略。M027已读作者v2，M028已读正式版式；SSR目录、M025首次在线日与SOCNET范围仍缺。')
 ],'### 批次T发现与限制\n2026-11-26：新增M027/M028两卡、VC43–47。85条/44卡/47单元/30载体、537操作，32纳入/45候选/6前沿/2排除。M027正式2025-12-17但所读作者v2、正式版本对照待核；M028首次在线2025-04-16，个人站点正式版式与官方身份互证。两者是批评/指南，非新工作流验证。Table3已渲染目视核Required/Optional；下载200/PDF头/页数/hash保存，未复跑或改协议。工具连接失败及403独立记录；21日期未决保持。首轮保留检查通过，导出核验后补记。')
