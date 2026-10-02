# 进度日志

## 2026-10-02：v2方向通过；v3最终人工小修

- focal_context改为明确中立（4分），persona/topic/原量表及六层30case保留。
- AD-025改为条件性人手需求、AD-022改为日常交往、AD-028改为发言空间；
  其他27条message/reason沿用v2，保存实质修订及剩余语义风险，不扩展case。
- 独立保存retirement-30-case-draft-v3.md，保留v1/v2；正文仍pending。
  无实验模型调用、240请求或代码功能扩展，history与统计细节仍未决。
- 只读核对通过：原30ID/六层各5、指定persona/context、两句式及理由精确摘录，
  仅022/025/028正文变更；19个上位family、最高频3，不等于统计独立性或强度等值。

## 2026-10-02：结构通过；30-case内容修订v2

- 按用户要求保留30case/六层/原ID与stance，独立保存retirement-30-case-draft-v2.md，不覆盖v1。
- 改为公开交流语气；reason为message第二句原文。区分或替换渐进调整与经验类论据，
  保存实质修订台账与剩余近重复风险，不靠改family名称宣称独立。
- persona逐字采用用户指定成年公民版本；D3保留极端立场标签但不堆叠强烈修辞，
  不声称论据说服力已匹配。结构批准不等于内容批准，全部正文pending。
- 无模型调用、240请求、云端或代码功能扩展；history与统计细节继续未决。
- 只读结构验证通过：原30个case/unit ID保留、六层各5、全部pending，reason逐字等于
  message第二句，无完全重复正文/理由；family最高频为3。未做效度/说服力等强度证明。

## 2026-10-02：通用退休benchmark获确认；交付30条内容审核稿

- 用户明确确认proposal原题干/原事实卡，仅采用DR-P1-045排除边界；保存版本比较与
  D-2026-10-02-03，不改legacy protocol，不把MC topic推广为正式主研究topic。
- 编制六层各5条内容草稿，明确助手拟稿而非argument pool摘录，全部human_review=pending。
  source_message与reason分别记录，focal4仅MC sensitivity；共同persona/context待审核，
  history不默认空值。标出论据近重复与自愿工作/法定年龄构念漂移风险。
- 尚未确认独立性或说服力匹配，不生成240请求，不调用实验模型或云端服务。
  原有未提交loop plan/test保留不动；本轮仅研究文档修订。
- 本地结构检查：30个唯一case/content unit，六层各5；所有审核状态pending，
  message立场措辞对应六层，message/reason无检查词表中的group cue且无完全重复。
  这不是语义去重或效度验证。git diff --check通过；未跑无关代码测试。

## 2026-10-02：schema获批，读取三topic并等待具体题干版本确认

- 完整读取protocol.yaml、proposal v2三个topic与DR-P1-045及相邻046/047；formal机器
  topic仍未决。输出比较表，区分设计/文献台账与未找到的完整argument正文，未查网页。
- 发现GM proposal测个人购买意愿而046测市场销售支持；AI proposal测广义AI净增加，
  047测生成式AI在中国净减少。不是同义版本，不能只按topic名称绑定或自动倒分。
- schema与审核表补充focal4仅MC sensitivity，不代表正式初始分布；persona暂定
  neutral but socially situated citizen，具体社会背景仍待审核，不默认利益/立场。
- 保存D-2026-10-02-02。等待用户确认topic及题干版本；没有生成message/刺激/请求，
  没有模型、云端、运行功能或额外测试。已有未提交loop plan/test保持不动。

## 2026-10-02：按用户最终规则收口30-case draft review table

- 用户确认schema并锁定独立MC用途/六层/focal4/source4±distance/中性群体四配对/
  固定neutral citizen与统一无consistency的history；限定本轮不扩展功能、不生成刺激。
- 核对formal机器配置为draft且topic仍UNRESOLVED，新2×3协议也未冻结topic；保留
  topic_reference未决，不自行选择三个probe候选，不改stance mapping或旧protocol。
- 更新schema为用户指定字段名stance_distance/focal_context/source_message/reason_family，
  与source_reason分别保存；30行draft table统一待填，附每case完整review template。
  不将30slot当有效case，不将null当empty history，不生成240请求。
- 更新D-2026-10-02-01与未决登记；精确刺激、persona/history、seed、bootstrap/failure
  规则仍未决，设计确认不变成执行授权。无模型/云端/额外测试/源码功能改动。

## 2026-10-02：优先准备30-case schema与人工审核素材

- 用户明确优先schema与从现有议题/argument pool整理30候选；六distance/direction strata
  各5、固定内容、四配对×两repeat、既有三项primary判据与secondary边界不变。
  本轮不调用实验模型，不继续执行运行循环实现，不启动云端。
- 已核对三个probe议题包，延迟退休是优先候选但不是新主议题正式冻结；历史DR-P1-045
  与probe题干存在版本差异，不能混用。当前checkout及已检查本地源目录中未定位
  正式argument pool；按名称找到的理由库明确mock-only，不用于候选case。
- 保存case schema书面草案和六层各5审核槽位；两者明确pending，不是机器validator，
  不声称已有30条完整正文。统一focal=4仅为未批准的镜像建议，不能默认进入执行包。
- 等用户提供pool文件/路径或明确批准另外起草刺激，并审核schema后，才进入
  validator/materializer实施与完整候选文本整理。未决seed/bootstrap/failure规则不默认。

## 2026-10-01：独立操纵检验专用 SQLite 证据存储

- 延续6263b14与active长期目标，在现有隔离分支实现 manipulation_store/evidence，
  不修改legacy、六格共享状态或797盲判store。独立SQLite保存完整来源绑定计划、
  有序试次与hash-chain；intent在发送前提交，typed response在解析前提交。
- 完整冷重放核验metadata/inventory/schema/每条request与transport/parser证据，
  保存响应仅本地terminalize；无响应intent不重发，INVALID停止后续试次。
  summary只输出计数/阶段/hash与preliminary/not_frozen/false-authority标记。
- 正常写入复用一次核验请求与增量前缀，不逐请求重建全包。专项覆盖外部DB变化、
  stale caller、BEGIN竞态和一致冷读；独立规格审查发现post-COMMIT缓存代际漏洞，
  以外部metadata/旧记录修改复现2 failed，再保留已验证data_version并在保护读快照
  比较变化，针对性5 passed。限定规格复审与独立质量审查均无剩余严重问题。
- 本轮还实际复现排序JSON重开改变message键顺序而导致wire哈希漂移；仅请求构造/
  冷返回统一role/content键顺序，sorted roundtrip RED→GREEN，研究消息/seed不变。
- 控制器最终专项40 passed、2 Linux-only skipped（122.48s），Ruff check/format与
  git diff check通过。用真实SQLite、完整输入来源和合成响应；lease为明确OS模拟，
  不称Linux内核/目录fsync验收，不称真实模型检验或速度实测。
- 下一步独立transport loop与假HTTP崩溃恢复，之后CLI/源码origin/真实授权根目录与
  服务预检组合。实际240内容、seed、bootstrap与failure规则仍未冻结；v1禁止云启动。
  无云端/上传/推送、无新真实实验数据；目标继续active，服务器仍无需开启。

## 2026-10-01：长期目标恢复，独立运行器单写者锁

- 上轮585546a为实质进展；本轮get_goal确认active，继续既定完整目标，不收窄为锁。
  请求清单专项重新验证3 passed（16.97s）。使用现有隔离worktree，无legacy改动。
- 新增 manipulation_lock：Linux-only、flock EX|NB、持久非截断0600锁文件，
  fd/path常规文件与inode核对、PID/root/closed/未取得锁检查；整个会话保留fd。
  close只关fd、不LOCK_UN；上下文进入校验失败同样清理，防止锁残留。
- TDD覆盖missing feature、直接构造非held以及审查发现的context-entry泄漏。
  专项11 passed、2 Linux-only skipped；独立规格与质量审查发现entry清理问题后
  经RED→GREEN修复并限定重审。真实Linux内核竞争/进程死亡/symlink/FIFO验收未执行。
- 本机WSL只返回安装帮助、无可用Linux环境，不为此安装或开启云端；模拟测试不称
  Linux验收。完整SQLite store/runner/CLI尚未完成，下一步不可变计划和durable
  intent/response/terminal及前缀重放，之后接独立运行循环与执行来源检查。
- 未上传/推送、未开启云端、无新真实实验数据；v1仍禁止云启动，240来源与研究
  未决选择不默认。目标继续active，服务器仍无需开。

## 2026-10-01：独立运行器获批，完成来源绑定输入组件

- 用户批准独立运行器设计；只授权本地实现，不等于上传/上云或研究参数冻结。
- 新增 manipulation_requests 与专项测试：完整来源/授权一次冷重放，精确有序
  typed request 与 wire hash，冷读取完整比较；热路径复用不可变请求 tuple。
- TDD 初始3项缺模块失败后实现通过；禁止v1云启动的标记先失败再修复。
  最终专项3 passed（17.00s），Ruff lint通过；限定独立审查无Important/Critical，
  新标记独立闭环复验1 passed（5.09s）。重算消息/seed/policy等哈希仍拒绝替换。
- v1仅合同测试，不是240请求实现。完整runner未完成，下一步为专用SQLite与恢复。
  未开启云端、未上传/推送、未修改legacy，无新真实实验数据。
- 长期目标服务仍显示blocked（先前等待设计批准）；当前实现已继续，但工具不能
  恢复目标状态，需用户在界面恢复或明确继续目标。

## 2026-10-01：独立操纵检验运行器的完整书面设计

- 上轮d015b17为实质进展；本轮检查共享StudyRunStorage、dispatch、Phase0B adapter/
  evidence/parser与上位MC规格，确认check trial不该假扮study event或797 judge item。
- 新书面设计推荐专用SQLite，复用typed loopback transport/parser，独立immutable
  inventory与READY→INTENT→RESPONSE_STORED→VALID/INVALID；intent在HTTP前commit，
  savedresponse只本地恢复、ambiguity禁重发、Linuxkernel writer lock覆盖运行。
- 设计含fresh interpreter/module origin、真实preflight/receipt、冷重放与增量前缀、
  run/resume/verify/report及crash/performance专项要求，避免每请求扫描全包。v1仅test
  fixture；240重复/统计/seed/content和Stage-B不默认，不用执行失败冒充无信号。
- brainstorming限定spec review为Approved，无严重规划缺口。规格仍待人类书面确认，
  确认前不写新runner实现；未启动新测试/云端/上传/推送，legacy未改，diff检查通过。
- README修正受控初始化/预检已完成的旧next-step描述。目标active；下一步用户确认
  运行器规格后创建实施计划并TDD实现。服务器仍无需开，暂无新真实实验数据。

## 2026-10-01：完整证据冷读取与独立预检命令

- 上轮4f40e07为实质进展；新增preflight_cli完整request serializer/parser。精确root/
  evidence/service字段，candidate不重复；原envlock保留，current observation经本次intent
  绑定EnvironmentLock规范排序后冷还原。JSON strict bounded reader沿用，拒绝额外字段/
  重复键/改hash后current authorization不匹配；最终调用完整preflight而非仅parse。
- TDD3 missingmodule RED；规范环境tuple排序导致原对象直接相等断言不适用，改为
  逐个完整artifact/其余证据完全相等+完整current EnvironmentLock相等，并执行全预检。
  fresh3 passed in16.97s；包含真实独立Python子进程对错误receipt拒绝、没有HTTP。
  独立限定review无确证Important/Critical，3 passed in16.77s；Ruff lint/format与diff通过。
- CLI stdout只有false-authority观察，stderr仅异常类别；真实tinyGit、mock procfs/health，
  不是云端Linux/模型验收。用法docs/identity-network-preflight-cli.md。
- 无run/dispatch/自动重试，无云端/上传/推送，legacy未变。执行origin、独立runner日志/
  fresh archive及240设计/实际case仍待；长期目标active，服务器尚不需开。

## 2026-10-01：Stage-A只读预检组合

- 上轮1dd9f00为实质进展；preflight完整重放来源/preregistration/bridge/dispatch receipt，
  实际bundle pack/tree、精确clean runtime root HEAD/tree、fresh Linux服务health前后观察，
  再查runtime。只返回hash观察、dispatchFalse，尚无run/独立CLI/输出目录/发送日志。
- TDD组合fixture先因start inspection错配修正；随后4项missingmodule RED→4GREEN。
  Windows用户global autocrlf与sanitized Git差异暴露，测试仓库local autocrlf=false后
  保持严格clean检查。审批/bundle错误不得HTTP，health期间runtime变更必须拒绝。
- hidden tracked edit先DIDNOTRAISE RED；新增ls-files拒绝assume-unchanged/skip-worktree。
  独立review也复现同一Important，修复后独立2 passed,6 deselected in2.29s确认关闭。
  fresh preflight/source_bundle/health相关26 passed in50.64s；Ruff lint/format、diff通过。
- 实际tinyGit内容核验、typed全部证据；procfs/HTTP模拟，不是云端验收。执行origin/
  ignored code/current环境真值/fresh archive/durable dispatch与最终CLI仍待接；v1四trial
  不是240实现。详见docs/identity-network-manipulation-preflight.md。
- 无云端/上传/推送，legacy未变；目标active，尚不需开服务器。240确认/实际case仍待。

## 2026-10-01：服务健康观察与独立命令入口

- 上轮e3f0980为实质进展；本轮service_health将Linux recorded PID/listener观察置于
  固定loopback /health请求前后。禁环境proxy/HTTPredirect，只接受200；body8192上限，
  仅输出SHA/大小。无completion请求、无stop/start、无任何dispatch授权。
- TDD模块缺失5 RED→17相关GREEN；独立CLI缺main RED→18GREEN，补初始身份异常
  不得触及HTTP后fresh19 passed in2.39s。独立限定审查无确证Important/Critical；
  CLI闭环独立1 passed,5 deselected in0.70s。Ruff lint/format与diff check通过。
- 合成procfs/mock HTTP，不是Linux现场验收。socket timeout5秒非全程硬截止；
  瞬时观察不是lease/model身份/审批替代。用法docs/identity-network-health-observation-cli.md。
- 无云端/上传/推送，legacy不变。真实发送入口组合source/runtime/bridge/approval仍待
  完成；240重复/统计设计确认及实际benchmark内容仍待。目标active，暂无需开服务器。

## 2026-10-01：Linux只读host/service观察入口

- 上轮413d5ea为实质进展；本轮继续不依赖240统计选择的service_live collector与
  独立CLI。host=boot/container hash不输出hostname；服务核对record PID、proc field22
  （comm允许空格与右括号）、NUL cmdline SHA/exe、非Z/X、start<=observation时间。
- 当前PID与客户端netns相同且稳定；IPv4loopback8000全部listener inode由其FD持有，
  两次PID/tick/command/exe/listener/FD/host一致，拒绝PID重用、wildcard、foreignowner。
  不发health/HTTP、不读取环境变量/socket/响应、无GPU/服务stop/start/kill动作。
- TDD10项missingmodule import errors（功能缺失）→10 passed；补namespace中途变化
  与standalone CLI缺入口2 RED→fresh12 passed in1.42s；独立限定12 passed in1.40s，
  无确证Important/Critical。Ruff lint/format与diff check通过。
- 仅合成procfs/readlink边界和Windows拒绝路径，不是Linux现场证据。瞬时观察不是
  lease/health/dispatch授权，真实runner须发送前重查，并继续核对source/environment/
  human receipt。用法见docs/identity-network-linux-observation-cli.md。
- 无云端/上传/推送，legacy未变；长期目标active，服务器暂不需开。240设计细节仍等
  用户确认；下一步startup/dispatch串接已核验source、bridge与真实观察。

## 2026-10-01：独立Git bundle内容核验入口

- 上轮e9fda5b为实质进展，240统计/seed增补尚待确认；本轮推进不依赖这些研究选择
  的source_bundle/source_cli。size/hash及fullcandidate/intent/scoped receipt精确匹配，
  bundle头部/prerequisites/head、真实pack/commit/reachable tree均核验；不上传或启动。
- TDD7 missingmodule RED→7 GREEN；独立CLI缺入口RED→8 GREEN，正例使用真实小Git
  full/incremental bundles，整个原仓库文件字节快照未变，输出无源码/persona/作者信息。
- 独立review找到Important：broad alternates可用原仓库expected commit遮盖无关PACK。
  两种正确header+无关合法PACK/只有commit缺tree负例先2 RED DIDNOTRAISE，再移除
  broad alternates，只导出声明prereq reachable graph，verify-pack查本次pack确含commit。
  后续fsck/tree纯隔离repo完成。两负例GREEN，独立闭环4 passed,6 deselected in4.96s。
- 补linked-worktree增量base正例；fresh source/launch专项27 passed in21.77s，Ruff lint/
  format及diff check通过。临时核验objects仅写自建目录，原repo不导入、不checkout。
- 该入口不证明批准签名、当前runtime clean checkout或现场服务状态；Linux现场复验
  仍待以后上云。无云端/上传/推送，legacy不变；长期目标active，暂不需开服务器。
  用法见docs/identity-network-source-bundle-cli.md；后续现场观察与独立运行入口仍待接。

## 2026-10-01：首阶段发送前授权合同与240请求候选增补

- 上轮263451d为实质进展；manipulation_authorization新增研究者显式sample/analysis/
  success/no_signal文字规则的preregistration，绑定case/trial counts、seeds/order，不
  默认任何研究值或自动评估文字规则。完整来源包与service bridge分别独立重建。
- stage1 target绑定来源/规则/bridge/adapter/start、inventory和endpoint/archive/generation；
  exact diagnostic_dispatch人类receipt必须符合target/scope/time；builder自身仍无发送权。
  StageTwoReceipt形状不能绕过真实stage1结果门，当前stage1 gate拒绝StageB dispatch。
- TDD8 missingmodule RED→8 passed in33.32s；补StageB拒绝后fresh9 passed in41.54s。
  独立限定stage1 cold/stage2拒绝复跑2 passed,7 deselected in7.31s，无确定Important/
  Critical。Ruff lint/format及diff check通过；仍不证明服务现场truth或批准真实性。
- 用户明确新增候选：30case/六distance-direction strata各5，四label cells各2生成共240；
  toward_source_shift及mean>0/paired-bootstrap95%CI不跨0/>=60%方向一致三条件。
  已准确记录research-qa与240-candidate设计稿，不把v1单quartet解释成240实现。
  replicate层、case级聚合与bootstrap/seed/content细节须书面确认后实现；不擅自freeze。
  限定书面复核无直接矛盾，补独立case操作定义、缺失不删样本/不触发无信号、StageB
  同样本规则复用及confidence baseline不可猜测等待确认边界。
- 无云端/上传/推送，legacy不变。长期目标active。暂不需开服务器；待确认增补接法，
  后续versioned重复/统计、独立runner与现场collector仍有实质本地工作。

## 2026-10-01：操纵检验样本的候选来源绑定

- 上轮7905c91为实质进展。本轮manipulation_sources以完整六格candidate和显式
  case/receiver/source/seed selections物化round0 controlled-check；来源不同且属于
  candidate，统一persona/初态/build_memory_view初始历史，实际初始PublicPost与alias。
  不选network邻居、不抽样、不把初始记忆人工填满K，四pair共享完整基准内容。
- 独立candidate冷读取重建完整source wrapper及pack，拒绝renderer合法、全hash一致
  但替换persona的来源；stage2素材仍仅记录receipt，不授权真实第二阶段。
- TDD12项missingmodule RED；初次实作PublicPost author字段误用，确认state定义后
  修正为author_agent_id，12 GREEN；补合法全重哈希替代persona、多case/stage2排序覆盖。
  fresh sources/manipulation/candidate专项36 passed in12.14s；独立限定14 passed
  in9.63s，无確证Important/Critical。Ruff lint/format与diff check通过。
- 仅合成来源fixture，不是已选定真实候选或实证数据。SIS_MC_SAMPLE/CRITERIA、
  实际来源人类核验、独立run入口、最终dispatch gate与现场collector仍待接。
  无云端/上传/推送，legacy未变，长期目标active；下一步受控独立操纵检验运行入口。

## 2026-10-01：操纵检验包冷重建核验

- 上轮6ebfadd为实质进展；新增validate_manipulation_pack，严格fixture/receipt字段，
  独立typed topic校验base renderer，完整重建四配对trial及seed/order/envelope。
  不把有效hash或自行构造receipt当作来源真实性、研究批准或stage-one结果证据。
- TDD新增9项缺函数RED；12项GREEN覆盖两stage冷JSON往返、重哈希trial seed/
  order/metadata/extra字段，以及完整重建但非法system/fact card基准输入。
- fresh manipulation/prompts/execution相关专项40 passed in0.71s；独立限定复核
  12 passed in0.15s，无确证Important/Critical；Ruff lint/format及diff check通过。
- 实际来源绑定、SIS_MC_SAMPLE/CRITERIA选择、独立MC runner和dispatch gate仍待接；
  测试仅合成数据，不是实证结果。无云端、上传或推送；legacy不变。长期目标active。
  下一步实际来源case绑定与受控独立检验入口，暂不需开启服务器。

## 2026-10-01：SIS新服务空闲/启动/运行环境证据桥

- 上轮bb4ca84为实质进展。新增service_bridge纯合同：vacancy要求loopback8000无
  监听、GPU compute空观察，绑定intent/inspection/host/time；start-first记录必须
  匹配当前intent/config/inspection、PID/tick和approval/vacancy/start/observation顺序。
- 固定environment lock仅提供已绑定model/install profile，不覆盖旧authorization。
  当前EnvironmentObservation派生的新记录绑定本次SIS intent；clean源码commit必须
  与intent一致，模型/tokenizer制品、package/image/vLLM/chat/non-thinking render及
  serve args与profile一致，并要求loopback/8000/servedname/explicit BF16。
- TDD11项缺模块RED；正例wheel hash不一致拒绝，修正合成fixture而非放宽检查。
  新BF16 wrong-profile RED后加精度检查；当前环境授权RED后绑定新intent。
  独立review发现equals-form flag覆盖，四项完整profile匹配RED复现并拒绝覆盖。
- fresh相关专项42 passed in31.98s；Ruff lint/format/diff通过；独立限定闭环
  5 passed,11 deselected in6.92s，无该范围剩余Important。未宣称真实host collector、
  live PID验证、旧797迁移或dispatch权限完成；所有输入仍为合成测试。
- 无云端、上传、GitHub推送或未决参数默认值；legacy不变。长期目标active，
  下一步final dispatch gate、真实操纵检验/独立run入口与观察接线；暂不需开服务器。

## 2026-10-01：SIS服务启动意向与分作用域人类批准合同

- 上轮6a2b937为实质进展；继续新SIS启动边界，不改变旧Phase0B scope/合同。
  launch.py以完整固定来源投影、source commit/bundle大小与SHA、精确服务配置和
  专属归档子目录构造自包含pre-service intent，不依赖未来start身份。
- StudyApprovalReceipt使用SIS schema，明确service_start/diagnostic_dispatch scope、
  target/hash、人类归属及UTC时间；formal始终false。create只用于记录可信人类批准，
  自行构造receipt不是取得批准。start validator独立重放意向、冷核验receipt，并
  核对实际bundle字节/hash/大小与调用者观察commit，不代替Git bundle内部核验。
- TDD16项缺模块RED→16 passed in7.46s；fresh intent/service source/candidate
  专项36 passed in15.78s；独立限定复核16 passed in7.92s，无确证Critical/Important。
  Ruff lint/format及diff check通过。测试仅为合成纯合同，不证明服务/批准真实性。
- 真实service bridge、最终dispatch授权/独立run入口与真实identity check仍未接齐。
  无云端/上传/推送或formal参数默认值；legacy不变。长期目标active，暂不需开云。
  接线边界见docs/identity-network-launch-boundary.md。

## 2026-10-01：服务启动前固定输入与启动后身份解耦

- 上轮cef5fd3为实质进展。本轮检查legacy service bridge/intent不能直接授权新SIS：
  scope固定旧N20/T2/12格，不能改它的含义。现SIS完整candidate含adapter start hash，
  真实start记录仅启动后出现，必须避免用尚未知的最终候选hash反向授权启动。
- 新增service_inputs.py，完整cold验证后投影全部固定population/execution/schedule/
  六格binding；只移除未来start身份及依赖其派生wrapper/record/common hashes，
  保留模型revision/环境/profile、初态/persona、排程/feed/memory与图等完整来源。
- bind_candidate_service仅以显式SHA机械重建population/common及六bindings，
  并要求重建前后固定来源投影完全一致。不读服务/HTTP/文件、不授权；draft中
  declared start hash不代表observed evidence，最终候选仍须独立receipt和service核验。
- TDD：10项缺模块RED；首GREEN两fixture错误（memory/feed加1落到不允许值），
  改为相邻有效挑战值加2，不修改shared参数限制。fresh相关专项62 passed in12.19s；
  独立限定复核10 passed in6.10s，无确证Critical/Important；Ruff lint通过。
- 仍未实现SIS launch intent、human receipt、真实handover/启动CLI及identity-check
  真实执行。此源码阶段不使用云端、不推送；长期目标active，服务器仍可关闭。

## 2026-10-01：可移植候选初始化与只读命令入口

- 上轮c593770为实质进展；本轮复查clean工作树，新增candidate_cli模块入口，
  prepare/resume-init/check-initial三命令。全量来源及显式context通过后先保存fsync计划，
  再创建独立六格SQLite。首次目录必须全新，resume须与原request/plan完全一致。
- 提取共同初始化preflight供只读initial verifier使用；check不填缺失agent、
  不创建缺失数据库、不持有writer lease、无模型/云端操作，检测读取期间DB变化。
  candidate CLI明确拒绝非空authorization hash，不把来源初始化当真实启动授权。
- TDD首8项缺模块RED；真实SQLite、独立Python子进程、归档逐文件字节不变、
  创建/初态中断接续、错请求零创建和原request漂移保留证据通过。路径静态拒绝
  symlink/reparse，但Windows缺symlink权限导致两项skip，待Linux补验。
- fresh专项52 passed, 2 skipped in37.34s；Ruff lint通过。独立限定复核8 passed,
  2 skipped in16.28s，未发现确证Critical/Important；未宣称敌对路径竞态沙箱或
  真实服务验证。使用说明见docs/identity-network-local-candidate-cli.md。
- 尚无实际研究配置/人类receipt/真实操纵检验请求；声明模型/环境不等于现场观察。
  无上传、GitHub推送或云端连接，legacy未变。长期目标保持active，下一步独立
  SIS真实启动/服务交接gate与identity check执行接线；目前无需开启服务器。

## 2026-10-01：完整候选包的受控六格初始化

- 新增initialization.py：fresh manifest来自完整六格source candidate，而非legacy spec；
  显式核对环境锁/Python、Git及六格nonce/URI，未决provenance拒绝。候选协议hash
  是来源标识，不是正式协议冻结；authorization hash只是引用，不代表human receipt。
- caller创建独立SQLite并拥有全部lease；family统一核对binding/source/完整既有初态，
  再从共同initial updates派生state/public post/pointer/cursor并封存。无attempt才可初始化；
  重复调用不写，注入中断保留证据、下次只补缺失初态，不删除或重建数据库。
- 首轮10项缺模块RED；修正lock负例与fixture真实hash相同问题。独立审查发现外部合法
  manifest可绕过builder环境检查，补三个late-store模型/锁/Python漂移RED，再加baseline
  manifest来源核对；全部漂移在任何六格写入前拒绝。独立限定闭环3 passed in3.48s。
- fresh初始化/候选/存储相关专项44 passed in20.28s；Ruff lint/format与diff check通过。
  120初态仅为20人×6格合成测试，不是真实模型请求或实验结果。
- 无云端、HTTP、上传或GitHub推送；legacy/main未动。下一步可移植文件入口、真实
  receipt/服务交接边界、identity check候选；长期目标active，服务器仍无需开启。

## 2026-10-01：排程来源重放与完整六条件候选包

- 上一目标轮为实质进展：人口/persona来源物化已提交20ecc6d；本轮先核对clean
  工作树及现有交接，继续其未完成的schedule来源和全家族组合。
- 新增schedule_sources.py，所有注意/表达/激活/发布参数显式传入；复用未修改
  的shared generators，保留正权重sum=N、hurdle–Beta independent expression、
  weighted activation及外生publish。包保存完整参数与四来源制品、FrozenSchedule。
  cold validator完整重建并核对SIS seed/有序roster/全部slot。
- 源provenance含Python implementation/version/random，不要求同一OS；runtime不
  匹配在重建前拒绝，不能在换机后重新抽样或把新hash冒充同一来源。没有设置研究
  参数默认值或正式权限；来源仍candidate_unattested。
- 新增candidate.py，将人口/persona来源、schedule来源与canonical六格binding
  合成自包含候选包。先核验共同来源，再从唯一A0B0 base派生六格；完整cold读者
  拒绝缺格/错序/duplicate、权限漂移和完整重哈希的合法late-cell alias漂移。
- TDD：schedule源17项缺模块RED、组合层9项缺模块RED；补完整late-cell测试。
  fixture中的publish flag篡改必须取反而非固定False，避免没有实际变化的假负例。
  最新相关专项152 passed in33.78s，Ruff/format/diff通过；独立限定复核schedule
  17 passed in1.28s、组合层10 passed in2.97s，无确证Critical/Important。
- 无文件/DB创建能力、无HTTP/云端/GitHub操作，来源包不是human receipt。
  仍需接受控六格初始化、独立真实启动/服务交接与可移植CLI，以及真实identity
  check候选。当前无需开启云服务器，长期目标保持active。

## 2026-10-01：长期目标与候选人口/persona来源物化

- 按用户请求设定活跃长期目标：持续推进新2×3本地前置工作，直到需要开启
  云服务器进行真实身份操纵检验；不自动上传/启动，不填未决研究参数。
- 新增materialization.py，从完整显式candidate donor frame、TRS权重/约束/容差
  机械重建population；固定identity-present/continuity-absent persona，复用共同
  execution inputs。来源包绑定full frame、人口、模板/实际rendered persona、
  round-0 updates、理由类别标签、群体平衡计数及共同输入hash；六格包完全一致。
- 冷validator完整重建后核对严格envelope，不仅比较调用者提供的hash。
  未决输入、exact-cover不符、重新哈希的派生制品/摘要/权限篡改均拒绝。
  source_authority=candidate_unattested：不验证donor真实性或研究者理由编码。
- 12项缺模块RED→GREEN；扩展人口审计reason_family同名字段隔离测试。
  独立审查发现额外字段数值1与文本"1"分类折叠，先RED再改为类型保真JSON类别键；
  不收紧legacy donor schema。最新专项及相关回归108 passed in4.48s，Ruff通过。
  独立限定闭环复核14 passed in1.24s，无剩余确证Critical/Important；format/diff通过。
- 本阶段无数据库/文件创建、HTTP、云端操作或GitHub推送；运行器尚未强制接收
  该来源包。下一阶段接attention/expression/外生schedule来源重放和独立launch gate，
  不将population来源验证说成全部输入来源验证完成。

## 2026-10-01：六条件有界运行原语与只读verify/report

- 新增identity_network/runner.py；六格在首次发送前统一核对common、封存初态、
  候选授权引用和独立SQLite/journal。显式stop ordinal控制前缀，已完成前缀不
  重发；已保存响应本地reconcile，失败停止全族，未决dispatch不自动重发。
- 本地六格各20人×2轮共240个合成事件通过现有vLLM adapter假连接链路，完整
  关闭重开核验；另覆盖部分前缀、失败/发送后中断、跨格错误和共享日志拒绝。
- 独立审查指出后面cell缺授权/已有失败不能在前面cell发送后才发现，两项已
  RED→GREEN闭环。读侧审查又指出guard之后重新读取baseline hash的窄race；
  改用已捕获cell记录，新增RED→GREEN负例。最终这项修复没有再次独立复核：
  审查代理额度不足，未重复启动；本地对应两项测试通过。
- 独立CLI只有verify/report，严格六格归档索引与目录内相对路径；缺数据库不
  创建、失败不输出raw。摘要无响应/reason文本，保持preliminary/not_frozen、
  formal_parameter_authority=false及transport unattested。读侧变化拒绝摘要。
- 最新runner专项19 passed in104.82s；合成240事件不构成新研究实证结果。
  相关新旧存储/dispatch/adapter回归444 passed, 2 skipped in108.89s；两项仍为
  Windows符号链接权限与POSIX no-follow环境skip。Ruff/format/diff通过。
  未真实HTTP、未开启AutoDL、未全仓pytest、未推送GitHub。
- 下一步：候选输入来源物化、SIS独立真实启动receipt/服务交接及可移植运行入口，
  再做真实identity manipulation check。正式参数未冻结，不填研究默认值。

## 2026-10-01：SIS durable dispatch 与保存响应本地恢复

- 新增StudyDispatchJournal，绑定run/study/baseline manifest、request及actual
  wire bytes hash，前序record hash构成链；intent在callback返回前flush/fsync，
  Linux另刷目录。resolution只接受已经SQLite落盘的相同response，无raw入journal。
- reconcile_study_event没有HTTP能力；保存响应可恢复解析/终态/derived提交，
  progress写中断可用同一response继续；失败保留并停止，未决发送不重发。
  PENDING仅分类不发送，缺历史intent/半条日志/跨run条目均拒绝。
- 12项缺API RED→12 passed，边界扩展暴露缺历史cover；独立审查另发现bool数字
  loose equality、duplicate keys及全历史response重扫。均补RED→GREEN：严格
  JSON+类型敏感hash，安全文件/DB缓存，intent/unresolved索引与IN_PROGRESS
  rowid增量覆盖；trusted新提交不能绕过历史gate。最终聚焦复核无剩余
  Critical/Important，审查者hot-cover负例1 passed。
- 六格均经过现有vLLM adapter+FakeConnection callback和本地reconcile；假响应
  fixture补齐实际provider的usage/finish_reason后六格6 passed。fsync失败时
  尚未创建连接；热缓存仍核对新响应的精确wire bytes，不只比较semantic JSON。
- 最终专项及新旧存储/adapter回归444 passed, 2 skipped in97.05s；Windows
  symlink权限与POSIX no-follow仍为两环境skip。Ruff/format/diff通过。
  未真实HTTP、未启动AutoDL、未全仓pytest、未推送GitHub；不构成新研究结果。
- 后续：完整六条件run/verify/report、明确失败重试授权和独立SIS真实启动
  审批，再运行identity manipulation check。完整runner性能仍需实测，候选
  authorization hash不充当human receipt，不新增研究参数默认值。

## 2026-10-01：SIS derived 成功提交与历史输入重放

- commit_study_success仅接受当前durable SUCCEEDED attempt_id，从精确input/request/
  invocation与独立bounded parse派生private update/state、外生发布分支、cursor。
  复用共享SQLite事务一次提交event/私人/公开/游标/progress/chain；generic commit
  仍关闭。失败不能推进，progress写中断全回滚，保留terminal即可重试提交，无HTTP。
- cold replay一次前向重建历史receiver pre-state/cursor/previous chain，actual public
  source/private history严格截到event之前；exact prompt/common/source验证继续执行。
  shared parent仍独立验证状态/公开帖子/游标/event-chain exact cover，未修改legacy逻辑。
- 新8项缺API RED→8 passed。扩展到11项包括六格各2事件public/private split、
  单格WS-salient 20agents×2sweeps/40事件全程合成响应提交、重复接收者私人memory、
  完成重开、重哈希历史chain拒绝及evidence references。标准引用入口暴露missing
  evidence_id RED后补computed SIS stored-input ID，nested输入schema不变。
- 独立审查无Critical/Important，审查者8项通过；本地最终commit专项11 passed
  in20.04s。新旧存储相关回归402 passed, 2 skipped in83.75s，环境skip仍为
  Windows symlink权限及POSIX no-follow；Ruff/format/diff通过。
- 未真实HTTP、未启动AutoDL、未全仓pytest、未推送GitHub。合成响应完整单格
  流程不是六格真实实验。后续接发送intent/reconciliation、失败收口/重试授权、
  六格runner与真实identity manipulation check；完整运行器性能仍需实测。

## 2026-10-01：SIS 响应与成功/失败终态落盘

- 新增start_diagnostic_attempt，只接受当前已落盘精确PENDING，保存IN_PROGRESS，
  不发送HTTP、不授权真实运行。普通append及commit仍关闭；advanced ordinal仍拒绝。
- invocation从durable input/request重建准备对象并复用bounded finalizer，核对
  actual source/common、exact wire/messages/settings/seed；parse/terminal在原v6
  事务原子落盘。成功和失败六格均关闭重开核验，状态/游标/ordinal保持不变。
- terminal拒绝调用者提供的loose parse（越reason上限却被通用解析器判成功）；
  插入中断不留下parse/terminal部分行。共享diagnostic topic引用改为受保护
  input projection，默认legacy类型约束不变。
- 审查发现wire模型名未绑定served_model、cold invocation漏比授权，均先复现
  RED再修复：统一live/cold验证；成功provider响应须声明同一模型。wrong wire、
  rehashed model/authorization及bounded parse负例拒绝。独立复核4项通过，无
  剩余Important/Critical。14项缺接口RED→14 passed；最终response新增20项。
- 最终新旧存储相关回归391 passed, 2 skipped in85.21s；环境skip仍是Windows
  symlink权限与POSIX no-follow。Ruff lint/format及git diff check通过。
  所有响应为合成测试provider数据；未云端运行，未全仓pytest，未推送GitHub。
- 下一步：historical causal input replay与成功state atomic commit，再接发送
  intent、失败收口/重试授权和六格runner。IN_PROGRESS重开仍需provider reconciliation，
  不自动重发；本阶段不等于完整实验/断点恢复，服务器仍无需开启。

## 2026-10-01：SIS 请求前 PENDING 原子前缀

- 新增 StoredStudyInput（stored-event-input.v2），保存typed SIS input与完整causal
  snapshot；共享diagnostic存储通过受保护投影接入，默认legacy输入类型仍严格。
- manifest保存完整共同执行制品及候选authorization hash引用；写入前/冷重开
  均核对actual round-0、state/chain/schedule、source rows、有限feed/memory、
  group/alias/persona prompt与model/policy。候选hash引用不是正式运行审批。
- 六格input/policy/adapter/request/PENDING在同一SQLite事务落盘，重复写幂等；
  请求插入中断全部回滚，关闭重开可核验。输入hash/缺request/重哈希round0引用/
  不同modelseed/不完整manifest负例均拒绝且不推进state/cursor/ordinal。
- 测试先行缺失API RED→8 passed，扩大负例18 passed。审查发现IN_PROGRESS
  冷重开越阶段接受，补RED→GREEN的显式PENDING-only guard及response writer gates；
  独立复核无剩余Critical/Important，审查者最小复验2 passed。
- 最终相关新接口与旧存储回归371 passed, 2 skipped in64.66s；两skip为Windows
  symlink权限与POSIX no-follow。Ruff lint、format、git diff check通过。
  未跑全仓pytest、未联系云端、未发送真实HTTP；本轮提交只在本地新分支。
- 下一步接dispatch intent与response/finalization，扩展已提交历史输入重放及
  diagnostic topic引用，再开放atomic commit/后续事件/六格runner。当前仅支持
  未提交当前事件的PENDING，不能称完整恢复或正式实验可运行。

## 2026-10-01：共同执行输入制品与静态校验缓存

- 新增 execution_inputs.py，六条件共用同一候选ArtifactEnvelope：完整rendered
  persona、round-0 PrivateUpdate、显式feed/memory/parser、generation settings、
  每个event的model seed、DiagnosticAdapterBinding与DiagnosticAttemptPolicy。
  共同身份包含seed、roster/alias、topic/groups/schedule及两种图，不含cell以保持配对。
- common_inputs_hash 明确引用本制品output_hash；完整重建校验拒绝重哈希后的
  nested contract/metadata/envelope/共同身份篡改。严格完整人口和schedule-seed覆盖。
- 新增 prepare_bound_snapshot_event：核对actual round-0完整update，再只从共同
  制品解析请求参数，通过当前数据库快照核验生成候选请求。此入口没有SQLite写入，
  不授权dispatch/retry，不代表正式冻结。attention/expression生成provenance还需
  materializer明确绑定，durable input/policy/intent与成功事件提交仍未接通。
- 测试先行：15项缺失模块RED→15 passed；扩大负例后28 passed。静态重复校验
  计数RED：两次准备执行2次整包校验/4次round-0扫描，修复为1次/1次。
  不可变制品与binding按object identity缓存；每次先核验SQLite签名，same/external
  connection篡改均被拒绝，unsealed partial检查仍保留，重开重建缓存。
- 独立审查两轮无Critical/Important；审查者复验47项。Ruff/format/diff通过。
  最终新接口与旧存储回归353 passed, 2 skipped in 64.05s；环境skip是Windows
  符号链接权限和POSIX no-follow专项。没有跑全仓pytest或启动AutoDL。
  尚未进行完整事件循环性能测量，不能声称旧797云端慢速问题已全部解决。

## 2026-10-01：数据库快照到SIS请求的读侧连接

- 新增 prepare_snapshot_event：持有lease，按显式persona/feed/memory参数重新构造
  当前数据库完整快照，逐字段/制品身份比较后从CURRENT快照生成PreparedStudyEvent。
- 拒绝重新哈希的run/event/receiver/chain/publication/round0/binding/prompt/source rows/
  selection/metadata篡改，以及不同persona/capacity/window复用快照。
- RED 16项因缺失接口失败；GREEN 16项通过。随后六格加入实际adapter代码的假HTTP
  响应/finalization验证和附加篡改负例，最终接口专项101 passed in 20.40s。
  Ruff/format/diff check通过；独立专项审查无Critical/Important，19项新测试复验通过。
  没有发送真实云请求、没有写入SQLite事件。
- 模型seed/settings、parser、attempt index仍显式给入；本接口不是运行授权或重试
  审批，不替代完整共同制品、durable prefix与dispatch intent。下一步仍需接入
  这些持久化合同及成功事件原子提交；云服务器继续不需要开启。

## 2026-10-01：SIS 数据库因果输入快照

- 新增 StudyRunStorage.snapshot_next_input：持有 writer lease，在一个只读 SQLite
  transaction 内复核完整性、按已绑定图/节点映射读取公开未读帖子和接收者私人历史，
  复用原有限 feed 与 memory 选择后生成 exact SIS prompt。
- 快照保留 potential neighbors、原帖子/历史、候选/过期/选中及槽位顺序、游标前后
  候选、pre-state、前一事件链 hash、发布标记、完整 prompt 和 source groups。
  游标后值只是候选，不写入库；外层标记 preliminary/not_frozen/committed=false。
- RED 为7项缺失接口失败；最终专项114 passed in 24.18s，Ruff/format/diff check通过。
  覆盖六格真实SQLite初始输入、重开一致、render中断回滚及非法候选参数不写入。
  独立审查无Critical/Important；补齐degree=8/capacity=4过期帖子覆盖，选中与过期
  集合严格不相交且精确覆盖所有候选。
- 这是读侧连接层，不是请求前持久化或完整恢复。SIS模型事件写入仍关闭，
  尚未产生新研究真实模型数据；不需开启AutoDL。

## 2026-10-01：六条件 SQLite 运行绑定与初始事务

- 新增 StudyRunBinding / StudyRunStorage，完整绑定 matched seed、分组、topic、
  中性别名、图节点到 agent 的映射、冻结日程及 WS/randomized 图。绑定保存在
  run_spec，参与 manifest/run 身份；common_inputs_hash 只是显式候选引用，不是
  正式协议冻结或已获准服务身份。
- 复用 SQLite v6 原表、单写者 lease、数据库身份与事务；共享 RunStorage 仅增加
  可覆写的 exposure 验证策略，默认仍执行原十二格校验。旧入口仍拒绝 SIS。
- 六格分别真实创建本地 SQLite，初始化20个测试 agent、封存、关闭并重开；
  非法初始立场、manifest/网络/日程漂移拒绝，写入及 seal 中断回滚。
- 审查发现未封存的部分初始化库漏查 SIS 初始状态，先复现 RED 后修复；
  wrong stance/topic 部分重开负例通过，独立审查收口。
- 存储相关回归 **265 passed, 2 skipped in 32.45s**；最后修复后新存储/输入/事件
  接口专项 **64 passed in 4.40s**；Ruff通过。两项跳过仍为Windows符号链接权限
  和POSIX专项。未全仓测试、未启动云端。
- 本阶段原子事务是 round-0 初始化/封存，不是模型事件提交。SIS event writes
  仍关闭；下阶段接 causal prefix、响应落盘、成功事件提交与完整恢复。

## 2026-10-01：SIS 可恢复输入与存储读取分流（Step 5b-1）

- 新增 StudyEventInputEvidence，保存完整 TopicPackage、parser limits、原私人状态
  和 exact prompt evidence；不包含 request/attempt，六条件重试输入哈希保持相同。
- 共享 storage 新增精确 schema decoder；旧输入保留原类型，未知 schema 拒绝。
  旧 RunStorage 仍明确拒绝 SIS，不借用十二格验证授权六格执行。
- 独立审查发现嵌套权限/字段、历史语义以及重复帖子/别名读取漏洞；分别先用
  协调重哈希负例复现，再补齐共享投影校验，最终审查收口。
- 存储及新模块回归 290 passed, 2 skipped in 29.32s；两项跳过分别为 Windows
  无符号链接权限和 POSIX no-follow 专项。最后一处修复后接口专项
  52 passed in 0.80s。未跑全仓 pytest、未启动 AutoDL。
- 当前完成的是可重建输入与读取边界，不是 SIS SQLite 写入/断点运行。
  下一步新增 SIS run binding、原子提交与串行恢复，然后接六条件 materializer。

## 2026-10-01：新 2×3 单事件接口收口（Step 5a）

- renderer v2 改为绑定 TopicPackage 的文字 stance labels 和整数 1–5 confidence，
  修复旧版新 prompt 与共享解析器的格式冲突；旧解析器与旧实验执行代码未改。
- 新增 prepare_study_event / finalize_study_response，复用共享 vLLM adapter、
  DiagnosticParseEvidence 和私人状态/公开帖子类型；失败保留原状态，重试保留事件身份。
- 六条件假 HTTP 专项通过。独立审查指出可见 prompt 与后台证据、实际 wire body
  与请求身份两处绑定缺口；均先复现失败，再修复并通过复核。
- 最终相关专项 **106 passed in 1.42s**；Ruff check 通过。未运行全仓 pytest，
  未向 AutoDL 发送请求。输出明确是 prospective / committed=false，不代表持久化提交。
- 下一阶段为 SIS 专属 SQLite 输入/记录 union、原子提交、重开恢复与六条件
  materializer；实际模型身份、跨事件来源/alias 和 manipulation 参数仍须绑定。
- 交接：`docs/2026-10-01-identity-network-event-boundary-handoff.md`。

## 2026-10-01：旧实验归档与新 2×3 主研究本地准备

- 用户十项决策批准，旧 2×2×3 作为 legacy pilot/supplementary。合并 main 文档
  到完整 phase0 历史，归档提交 `91661b4` 已推送；固定标签
  `legacy-2x2x3-2026-10-01` 和远端归档分支保留。未覆盖 main 或旧工作树。
- 新分支 `codex/social-identity-network-2x3` 写入设计、协议、SIS 未决 ID、
  决策和协作路由。新增六条件、正交平衡 groups、blind/salient prompt、
  连通度数保持重连以及四向配对 manipulation 输入包；旧运行器不改。
- 测试先观察缺模块 RED，后专项 GREEN。独立实现复核指出匿名别名可泄露群组；
  增加失败回归后限制中性别名、一一对应并保留同源多帖，复核收口批准。
- 最终专项：新增四文件加 domain/persona/network/prompt/phase0b_candidate_config，
  **217 passed in 22.56s**；新增模块/测试与 rng 的 Ruff check 通过，
  新增十个 Python 文件 format check 通过，git diff check 通过。未跑全仓测试。
- 已实现的是输入和制品准备，不是六条件云端运行：尚待共享 runtime/SQLite union、
  post-state/confidence/actual-public-output 提交日志、跨事件 alias 冻结与假HTTP六格验证。
  manipulation check 和新 pilot 均未真实执行；本轮不需要开 AutoDL。
- 详细交接：`docs/2026-10-01-identity-network-preparation-handoff.md`。

## 2026-09-24：judge 迁移副本的完整文件树比对（本地）

- 新增 `phase0b/archive_copy.py` 的只读 `inventory_tree`/`verify_tree_copy`：源与目标根目录下所有目录（包括空目录）、常规文件相对路径、大小与流式 SHA-256 必须完全一致；拒绝软链接与特殊文件。不读取或输出 raw response 文本，也不执行复制。
- 先见缺模块 RED，后见归档专项；独立复核发现 Windows 联接点和扫描期路径替换风险，新增两个负例先 RED 后 GREEN。归档专项 `7 passed, 1 skipped`，连同原冷关机/正常停机合同最终合跑 `35 passed, 1 skipped`；Windows 无法创建真实软链接的负例须在 Linux 上补验。Ruff lint/format 和 diff 检查通过。**这不是目标端 judge journal 重放，也不证明源本来完整；源/目标必须保持静止。**
- 接下来需在目标端调用现有 `JudgeRunStore.open` 复核精确目录布局与 journal/projection 重放，并绑定迁移桥；旧实例和新实例均未启动实验。

## 2026-09-24：Phase 0B 冷关机缺席合同（本地）

- 按先测后实现新增 `phase0b/cold_handoff.py`：独立 `cold-poweroff-observation.v1` 记录不能冒充旧 judge 正常 stop；要求进程和端口缺席、GPU compute-process 空观测哈希，并绑定原服务启动记录、旧 manifest/lock、797 项 coded 且无 unresolved 的终态投影与外部重放哈希。旧 normal-stop 桥未改。
- 两次 RED 分别验证缺模块/缺核验函数，另以无效日历日期验证校验漏洞；独立代码复核又发现 manifest/lock/授权链与 797 唯一 ID 缺口，先加负例后修复。当前 cold + 原服务桥专项 `28 passed`，Ruff lint/format 与 diff 检查通过。pytest 有项目配置 `cache_dir` 的非失败警告。
- 这仅证明本地合同对合成证据的验证，不证明旧实例已重启、旧进程真实缺席或迁移归档完整。下一步仍是目标端完整性/重放与跨主机桥；尚未启动云端真实 N=20 请求。

## 2026-09-24：保留旧实例的 Phase 0B 换机交接设计

- 用户确认旧 AutoDL 实例目前关机但仍保留实例，并批准“旧服务若仍运行则正常停止；若已消失则如实记录冷关机观测”的双分支迁移设计。已写入 `docs/superpowers/specs/2026-09-24-phase0b-retained-instance-migration-design.md`，并修订启动身份桥和 Phase 7 路线；独立书面复核提出的原始启动/投影身份链、目的地完整性与重放要求均已补入并复审通过。完整书面修订仍待用户审阅，尚未实现冷关机证据合同。
- 本轮未启动旧实例、未连接新实例、未搬运数据、未发送模型请求。797 项 judge 的历史终态证据仍需在保留实例上重新核验；真实 N=20/T=2 尚未运行。

## 2026-09-23 晚：N=20 真实运行准备

- 提交 `6448e8f`：Phase 0B 脱敏 SQLite 报告现在先核验 12 格、480 个成功事件，再从已提交私人状态、公开帖子、暴露与用量证据计算逐格/逐 sweep 描述指标；来源哈希绑定实际证据，与仅表示完成数量的摘要哈希分开。公开帖子必须与已发布更新逐条一致；缺帖、错帖拒绝生成报告。
- 本地假 HTTP 矩阵专项 `13 passed`，Ruff、格式和 diff 检查通过；该结果只证明代码路径与报告边界，不是云端 Qwen 实证数据。Windows/OneDrive 的 pytest 缓存目录仍有权限警告，但不影响本轮测试结论。
- 当前下一关是同一授权与证据身份下的安全恢复/重试合同、Linux 复验和精确审批包；随后才可做独立两事件云端预检及 480 事件真实 N=20 诊断。此时尚未启动新的 Phase 0B 云端请求。
- 随后补入真实 SQLite 纯成功前缀的单格/12 格恢复路径：先验证同一授权、矩阵内容哈希、模型绑定和策略；独占锁覆盖整批预检与执行；逐事件复核 dispatch 与 checkpoint，拒绝未决 intent、PENDING/IN_PROGRESS/FAILED 或任何身份漂移，已成功事件不重发。历史 checkpoint 也须与 SQLite 对应前缀一致，12 格静态图输入在首个新请求前全部验证。恢复专项 `11 passed`，Ruff/格式/diff 检查通过。**失败事件同一 event retry 仍未实现，也未授权自动恢复此类前缀。**

## 2026-09-23：AutoDL 到期与用户自主运行交接

- 核对 AutoDL 官方保留、计费、同地区克隆及文件存储文档；确认包周到期不等于实例立刻释放，重要结果仍需在释放或换机前验证备份。
- 只读检查旧实例：judge v2 持久化目录存在且约 2.1 GB、端口 8000 仍监听、数据盘 150 GB/已用 61 GB/剩余 90 GB；`/root/autodl-fs` 未挂载；未读取 raw response、未停止服务。
- 新增 `docs/2026-09-23-autodl-expiry-and-self-run.md`，写明 SSH、只读状态命令、tmux 断线继续、备份/克隆顺序和 Phase 0B 当前不可自助启动的边界。等待用户在 AutoDL 控制台确认释放倒计时及换机路线；正式运行卡须等本地真实 runner 与授权哈希完成。

## 会话：2026-07-14

### 阶段 1：项目盘点与审计
- **状态：** complete
- 执行的操作：
  - 读取本地仓库结构、README、设计文档、日志、pilot 代码和正式结果汇总。
  - 读取 Notion 2026-06-12 研究页和 2026-06-25 基金页。
  - 核对个人仓库、BNU-CCR 组织仓库与本地 Git 哈希。
  - 完成代码、实验方法、统计和文档一致性三路只读审计。
- 创建/修改的文件：
  - 无项目代码修改。

### 阶段 2：总体架构确认
- **状态：** complete
- 执行的操作：
  - 提出“旧 pilots 原地冻结 + 新建 platform + Paper 1 协议作为执行真相”的总体设计。
  - 用户确认首先实现 Paper 1，同时建设长期复用实验平台。
- 创建/修改的文件：
  - `task_plan.md`
  - `findings.md`
  - `progress.md`
  - `docs/superpowers/specs/2026-07-14-agent-ex-paper1-platform-design.md`

### 阶段 3：书面规格审阅
- **状态：** in_progress
- 执行的操作：
  - 写入正式设计规格。
  - 第一轮独立审阅识别出协议 schema、运行身份追溯和失败终态三个实现阻塞项。
  - 已补充结构化协议契约、run/event/attempt 身份模型和运行状态机。
  - 第二轮复审发现旧幂等键表述与新 `event_id` 契约冲突，已统一为 `event_id` 唯一幂等键。
  - 最终独立规格复审结果为 `Approved`。
  - 用户确认总体平台规格，并要求按既有研究脉络进一步收束 Paper 1。
  - 回读 Notion v2.0、Paper 1 收口页、2026-06-12 最新页和本地历次方案，确认主线为 persona 条件化与多轮网络互动下的意见形态。
  - 新建 Paper 1 聚焦研究规格，明确不把真人网络、动态重连、RLHF 和 N=1000 纳入主实验。
  - 第一轮独立审阅发现连续性操作重叠、shuffled exposure 不可执行和 primary estimand 未排序三个阻塞项。
  - 已将 continuity 限定为先前立场/理由/发言的连贯性；明确 cell 内 degree-matched 置换算法；将 primary outcome 收束为 `Δ log(B/W)`，primary estimand 收束为 continuity 对 `WS - shuffled` 的 matched-seed 调节效应。
  - 第二轮独立复审结果为 `Approved`。
  - 用户确认聚焦设计，并最终确定分级实现与 N=1000 正式主实验。
  - 将正式规模更新为 N=1000、T=50、12 cells；先10个 matched seeds，再按盲态功效重估扩展至最多20个。
  - 规模方案复审发现 pooled within-cell variance 不适用于 matched-seed DiD；已改为直接估计每 seed 主对比 `z_s` 的中心化方差，并固定 α、power、MDE、取整、上限和首批数据纳入规则。
  - 复核三轮 pilot 代码，写入可迁移机制、禁止直接复用部分和测试先行的迁移边界。
  - 最终规模与迁移方案独立复审结果为 `Approved`。
  - 用户已确认该方案；下一步进入 Paper 1 protocol 与逐文件实施计划。
- 创建/修改的文件：
  - 待审阅后更新设计规格。

## 测试结果
| 测试 | 输入 | 预期结果 | 实际结果 | 状态 |
|------|------|---------|---------|------|
| Git 远端一致性 | 个人与 BNU-CCR 仓库 | 与本地已提交版本一致 | 均为 `5c31951` | 通过 |
| pilot-3.0 N 扩展静态审计 | `n_agents=1000` | 创建1000个Agent | 角色池只有20条，无法运行 | 发现阻塞 |
| 配置传递审计 | `top_p=0.9` | 进入模型请求 | 未进入 `LLMClient.generate` | 发现阻塞 |

### 阶段 4：实施计划
- **状态：** in_progress
- 执行的操作：
  - 按 make-plan 规则完成文档、代码和方法/统计三路 Phase 0 发现。
  - 2026-07-14 当时确认 `platform/` 尚不存在、运行依赖未锁定，pilot-3.0 Notebook 是实际实现。
  - 写入分阶段、逐模块、测试先行的实施计划。
  - 第一轮计划审阅发现官方API发现滞后、执行参数库存不全和大规模矩阵编排缺失。
  - 已增加 Phase 0B 官方API/依赖 gate、完整 unresolved inventory 与 formal-required 校验、registry/worker/矩阵审计/盲态扩样 orchestration 阶段。
  - 第二轮独立计划审阅结果为 `Approved`。
  - 2026-07-14 当时代码实施仅被 worktree 位置选择阻塞；该阻塞已于 Phase 3A 解决。
- 创建/修改的文件：
  - `docs/superpowers/plans/2026-07-14-paper1-platform-implementation-plan.md`
  - `task_plan.md`
  - `progress.md`

## 错误日志
| 时间戳 | 错误 | 尝试次数 | 解决方案 |
|--------|------|---------|---------|
| 2026-07-14 | 并行审计网络断连 | 1 | 重试后完成 |
| 2026-07-14 | OneDrive CSV 读取超时 | 2 | 停止重复读取，改用已获取证据交叉验证 |

## 五问重启检查
| 问题 | 答案 |
|------|------|
| 我在哪里？ | 正式平台阶段 3；Phase 3A 已完成，Phase 4 尚未开始 |
| 我要去哪里？ | Phase 4 模块实现 → mock/真实模型校准 → 有限规模 gate → 正式实验 |
| 目标是什么？ | 建成以 Paper 1 为首个协议的长期复用实验平台 |
| 我学到了什么？ | 见 `findings.md` |
| 我做了什么？ | 见上方记录 |

## 会话：2026-07-29

### Phase 3A：协议、领域与运行证据基础
- **状态：** complete
- 执行的操作：
  - 从 `c050655` WIP checkpoint 恢复，确认原 78 个失败同时来自旧 wheel 污染和待实现 release-hardening 测试。
  - 修复 editable install 与 pytest 临时目录，建立普通 import、root/platform 双入口和隔离 wheel smoke。
  - 完成协议/schema gate、decision value hash、human summary 同步和 Unicode placeholder 防绕过。
  - 完成领域记录、分层运行身份、FrozenSchedule、RunManifest、恢复游标、证据图与严格 JSON round-trip。
  - 经过多轮独立发布验证、边界审计和代码质量审查，逐项修复测试外绕过。
- 验证结果：
  - `353 passed`
  - Ruff check/format、`pip check`、`git diff --check` 通过
  - schema 镜像与17项依赖锁一致
  - 最终三路独立审查均为 PASS，无 blocker/major
- 边界：
  - 未修改旧 pilots。
  - 未运行 formal，未伪造审批记录。
  - 未实现真实 model adapter、engine 或正式实验。
- 下一步：
  - Phase 4：population、persona、network/exposure 与 mock fixtures。
  - formal-required 研究决策与 provider/runtime gate 继续保持 blocked。
  - 代码位置和恢复命令见 `logs/2026-07-29-phase3a-handoff.md`。

### Phase 4A：文献驱动的决策准备
- **状态：** in_progress
- 执行的操作：
  - 建立逐项“决策—支持/反对/边界文献”台账。
  - 将 Phase 4A 拆为议题、量表、目标人口、人口字段、初始状态、Persona、WS 网络、
    激活/暴露/记忆八个检索模块。
  - 用户要求重新开放议题选择，并要求平台支持可替换 topic package。
- 当前工作：
  - 首先检索并比较适合多轮 LLM-agent 舆论演化实验的候选议题。
  - 已重新打开原“AI 就业替代”主议题决定，完成核能、AI就业替代、指定场景人脸识别、
    气候政策的第一轮比较。
  - 当前建议先完成核心比较池的精确构念审查，再选择不超过三个候选做目标模型无网络
    topic probe，不在看到网络演化结果后再选题。
  - 已记录声明式 `TopicSpec`/`TopicResources`/`PopulationSpec` 分层建议，尚未冻结。
  - 用户要求保留 AI 就业替代并扩展社会议题候选；新增评估转基因食品、延迟退休、
    生育支持、算法推荐治理、疫苗和内容审核。当前建议核心比较池为 AI就业替代、
    转基因食品、延迟退休、生育支持政策；核能和人脸识别暂存，待统一判断。
  - 已按同一七维加权框架统一审查 AI就业、延迟退休、转基因、生育支持、核能和
    人脸识别六项。建议三项进入 topic probe（延迟退休、转基因、AI就业），Paper 1
    最终采纳两个议题资产，但只让一个运行完整12-cell主矩阵，另一个用于缩减稳健性。
  - 用户已确认延迟退休、转基因食品和AI就业替代进入Phase 0 topic probe。决定已
    记录为 `D-2026-07-29-01` 和 `DR-P1-043`；最终主议题及稳健性议题仍未冻结。
  - 已完成模块2的会审建议包并记录为`DR-P1-044`至`DR-P1-048`：三题均采用
    “中性事实卡+单一核心陈述”；建议共用1–7全标签有序立场量表、独立1–5
    confidence审计字段和`stance → confidence → public_reason`固定输出。
  - 延迟退休限定为对现行渐进式年龄调整方案的支持；转基因限定为依法标识的
    转基因大豆油市场销售支持；AI限定为未来10年生成式AI对中国就业岗位总量造成
    净减少的预测。三者均明确排除了容易混入的相邻构念。
  - 已起草每题两个同方向等义改写、7点与0–10挑战者比较、字段顺序检查及统一冻结
    判据。阈值被明确标为项目操作建议而非既有文献结论，须在比较候选结果前冻结。
  - 用户已于2026-07-29批准模块2方案；已记录为`D-2026-07-29-02`，并将
    `DR-P1-044`至`DR-P1-048`更新为“已确认方向”。模块2的研究设计完成。
  - 已进入模块3并完成目标人口与数据来源建议包`DR-P1-049`至`DR-P1-051`。
    当前推荐三议题共用“中国大陆18岁以上、过去半年使用互联网的家庭/社区居民”
    总体，不设64岁上限；在线资格不等于发帖或每轮激活。
  - 数据建议采用四层分工：NBS 2025提供最新总体边际、七普2020提供详细交叉结构、
    CNNIC第57次提供网民定义/边际、CFPS2022提供加权联合微观供体；CGSS2021和
    CLDS仅作一般成年人及劳动子群外部验证。
  - 已明确人口配额只控制模拟输入组成，不能据此宣称Agent代表真实中国民意；正式
    数据必须保存版本、许可、下载日期、变量crosswalk、权重、hash和校准误差。
  - 用户已于2026-07-29批准模块3方案；已记录为`D-2026-07-29-03`，并将
    `DR-P1-049`至`DR-P1-051`更新为“已确认方向”。模块3的研究设计完成。
  - 已进入模块4，开始审查人口字段在配额、prompt可见和分析专用三层中的不同用途。
  - 模块4建议包已形成：新增`DR-P1-052`至`DR-P1-055`，并把原三层结构扩展为
    校准、身份可见、分析审计和议题扩展四类用途。共同身份卡建议只显示年龄段、
    调查记录性别、教育、当前城乡、主要活动和就业者宽职业组。
  - 身份卡被界定为捆绑的实验处理，而非真实群体意见复刻；姓名、精细地点、收入、
    户口、婚姻、民族以及态度/价值近邻变量默认不显示。硬校准只使用能与成年网民
    总体兼容的高质量边际，不做全字段笛卡尔积配额。
  - 用户已于2026-07-29批准模块4方案；已记录为`D-2026-07-29-04`，并将
    `DR-P1-003`、`DR-P1-052`至`DR-P1-055`更新为“已确认方向”。模块4完成。
  - 已进入模块5，开始审查初始立场分布、人口—立场关联、跨cell匹配和初始理由来源。
  - 模块5建议包已形成：新增`DR-P1-056`至`DR-P1-060`。建议N=1000在1—7量表上采用
    `[50,100,200,300,200,100,50]`受控对称单峰分布；初始立场与人口约束正交，
    同matched seed跨12 cells逐Agent匹配。
  - 初始理由建议采用“来源支持的论据家族+冻结模型受控改写+机器/人工审计”的离线
    理由库；每个Agent都有一条round-0理由，不再概率性缺失。该建议包正等待用户会审，
    尚未写入正式决策，也未冻结任何机器参数。
  - 用户已于2026-07-29批准模块5方案；已记录为`D-2026-07-29-05`，并将
    `DR-P1-056`至`DR-P1-060`及关联队列项更新为“已确认方向”。模块5完成。
  - 已进入模块6，开始审查identity有/无、continuity有/无四个Persona模板的基线
    等值性、唯一允许差异、措辞强度和模板制品治理。
  - 模块6建议包已形成：新增`DR-P1-061`至`DR-P1-065`。建议四条件由单一共同骨架
    确定性插入identity和continuity两个因素块；absent条件真省略，不用“普通人”
    “中立公众”或等长语义placebo。
  - identity建议使用结构化最小人口字段卡并禁止补写身份故事；continuity建议对
    保持/改变提供对称许可，只要求解释连贯，不设置反向证据门槛。建议包包括旧pilot
    禁用词、三路操纵检查、锁死gate、顺序/改写挑战、模板ID/hash与变更治理，正等待
    用户会审，尚未冻结模板原文。
  - 用户已于2026-07-29批准模块6方案；已记录为`D-2026-07-29-06`，并将
    `DR-P1-061`至`DR-P1-065`及关联队列项更新为“已确认方向”。模块6完成。
  - 已进入模块7，开始审查WS网络的`k`、`p`、图方向、连通要求、非法图处理和
    N=1000下每轮曝光/推理成本。
  - 模块7建议包已形成：新增`DR-P1-066`至`DR-P1-070`。建议主图采用无向、简单、
    全连通且T=50固定的标准WS骨架；同matched seed的图和Agent—node随机映射跨12
    cells完全复用。
  - N=1000纯结构预计算建议以`k=10,p=.05`为主锚点，并用
    `k={6,10,20} × p={.02,.05,.10}`做不调用LLM的结构挑战。参数只能按聚类、路径、
    small-world指标、连通与资源gate冻结，不得按极化结果选择；当前等待用户会审。
  - 用户已于2026-07-29批准模块7方案；已记录为`D-2026-07-29-07`，并将
    `DR-P1-066`至`DR-P1-070`及关联队列项更新为“已确认方向”。模块7完成。
  - 已进入模块8，开始审查全体/子集激活、同步提交、三种曝光的数量匹配、邻居消息
    排序和记忆窗口，并核算N=1000×T=50×12 cells×seeds的真实推理规模。
  - 模块8建议包已形成：新增`DR-P1-071`至`DR-P1-077`。建议主实验使用全体同步，
    每轮激活当前N的全部Agent；正式10个matched seeds预计600万次生成，扩至20个为
    1200万次，资源不足不得静默改成子集激活。
  - 建议E2读取全部一阶邻居，E1逐Agent按WS度数精确匹配，并同时保持发送者出度；
    消息使用稳定中性成员编号、文字立场标签和上一轮理由，槽位按独立seed随机化。
    shuffled映射应以严格受约束b-matching预生成，不可行则在运行前失败。
  - 建议证据链保存全部历史，但模型只见最近3轮自身立场/理由，并在Phase 0以
    K=1/3/5做不读取意见结果方向的构念与资源挑战；不使用LLM自动摘要。该建议包正
    等待用户会审，尚未写入正式决策或机器协议。
  - 用户指出Paper 1核心更偏向真实舆论过程仿真，因此否决全员同步作为主过程。
    补充文献审计显示，在线讨论存在沉默多数、活跃少数和爆发性发帖，异质节点活动
    还可能改变共识速度与碎片化；原模块8建议因此正式重开。
  - 用户已于2026-07-29批准新的过程架构，并记录为`D-2026-07-29-08`及
    `DR-P1-071`至`DR-P1-072`：固定WS关系不变，每个Agent具有冻结的长期活跃权重，
    每次事件按权重有放回抽取一个Agent并即时提交；同matched seed的12 cells共享
    权重和完整激活序列。
  - T=50现解释为50个sweeps，每sweep包含N次事件；正式run仍为50,000次生成，10个
    matched seeds仍约600万次。全员同步降为稳健性上界，不以减少调用量为选择理由。
  - 活跃权重分布/校准目标仍未决；E1/E2事件级最近帖子语义、来源映射和自身记忆单位
    也已重开。上位规格、纸面协议、schema和代码尚未修改，formal配置继续fail closed。
  - 用户已进一步批准“私人意见更新—公开表达”两阶段设计，并记录为
    `D-2026-07-29-09`、`DR-P1-078`：每次激活用一次LLM调用更新私人状态，预生成的
    `publish_flag`决定是否替换最近公开帖子；E1/E2只能读取公开帖子。
  - 注意/更新活跃权重与公开表达倾向必须使用独立制品并跨12 cells复用。精确表达
    分布、结构性潜水比例、贡献Gini、top-user份额，以及私人/公开结果的分析排序仍
    保持未决；当前没有修改schema或事件引擎。
  - 用户已批准私人/公开分析排序并记录为`D-2026-07-29-10`、`DR-P1-079`：全部
    Agent的私人意见分布为唯一primary；公开存量、公开流量和私人—公开表达偏差为
    强制预注册secondary。不得在结果出来后用更显著的公开结果替换私人primary。
  - 用户已批准hurdle–Beta公开表达结构并记录为`D-2026-07-29-11`、`DR-P1-080`：
    所有Agent均有正注意权重；结构性潜水者round 0后不发帖，其他Agent的表达倾向
    来自Beta分布。主模型注意权重与表达倾向独立，正相关只作预注册敏感性。
  - 用户已批准注意权重分布族及校准框架并记录为`D-2026-07-29-12`、`DR-P1-081`：
    主模型为正截断对数正态并归一化`sum(w_i)=N`，截断Pareto为重尾敏感性，等权
    为无异质性机制基线；校准只看激活过程统计，不读取意见演化结果。
  - 用户已批准E1固定shadow graph并记录为`D-2026-07-29-13`、`DR-P1-082`：
    每个matched seed生成一张全程固定、逐节点保持WS度数、排除自环/重边/真实WS边
    且全连通的对照图；E1/E2都保留稳定关系，动态换人不进入主矩阵。
  - 用户已批准有限未读feed并记录为`D-2026-07-29-14`、`DR-P1-083`：每次激活只
    考虑游标后的邻居新公开帖，取最新至多B条，超量过期、不用已读帖回填；入选按
    新近性，prompt槽位另行冻结随机化。B及精确过程gate进入Phase 4A批量审阅。
  - 用户要求停止逐小点审批；后续将所有剩余Phase 4A事项整合为一次性决策包，整体
    批准后转入书面规格与实现计划。
  - 已完成Phase 4A剩余项清仓盘点：将机制/接口、Phase 0校准制品以及统计/运行时
    后续gate分层；补证TRS人口整数化、seed间重新抽样/common random numbers、私人
    更新记忆窗口和参与不平等边界。下一步仅等待用户对整包一次性审阅。
  - 精确潜水比例、Beta参数、注意权重参数、相关敏感性强度和校准容差仍保持未决；
    参数必须匹配零新帖比例、Gini、top-user份额和每sweep发帖量等过程统计，不能按
    意见结果选择。
  - 用户已于2026-07-29整包批准Phase 4A剩余建议。新增`D-2026-07-29-15`至`19`与
    `DR-P1-084`至`088`，并形成
    `docs/superpowers/specs/2026-07-29-paper1-phase4a-completion-design.md`。
  - 整包确认三议题probe及预先优先级、TRS恰好N与seed间重新抽样、最近K次成功私人
    更新记忆、失败不变式/同事件恢复，以及B=6/K=3主候选与Phase 0挑战集合。
  - 已同步修订研究问答、纸面协议、07-14聚焦规格和平台规格，清除正式路径中的旧
    全员同步提交语义。下一步是整份书面规格复核；复核前不实施schema或事件引擎。
  - 独立规格审查共完成三轮。已修复有放回激活下`round+agent_id`事件键碰撞，统一为
    连续全局`event_ordinal`；按component区分matched-seed common RNG scope与
    cell-specific scope；恢复只接受连续、无缺口、全部succeeded前缀。
  - 同步清除旧平台规格中的同步测试/迁移要求，明确failed即原位停止、excluded只属
    分析层、Paper 1主路径禁止imputed/fallback；B稳定旧ID被明确解释为消息容量并把
    B/K最终冻结gate移至Phase 0B。独立审查提出的blocker/major均已逐项关闭。
  - 随后按用户要求从传播学审稿人与ABM方法专家角度复核Phase 4A。结论为
    `major revision`而非设计作废：工程可追溯性很强，但研究问题与primary estimand、
    identity/continuity构念、LLM行为效度、拓扑—消息剂量识别和真实舆论表述仍需修订。
  - 识别出若干实施前必须解决的问题：public post事件/stock语义、shadow graph结构
    目标、WS-shadow实际曝光剂量差异、稳定来源记忆缺失，以及baseline分组导致
    `log(B/W)`初始值机械偏高。完整证据和建议记录于`findings.md`。
  - 用户批准不改机制、不增加真人的Phase 4A.1方法论重构。新增方法规格
    `docs/superpowers/specs/2026-07-29-paper1-phase4a1-methodological-reframing-design.md`、
    决定`D-2026-07-29-20`和依据卡`DR-P1-089`。
  - 修订将Paper 1定位为理论驱动的生成式舆论动力学计算实验；收窄identity、
    continuity、private/public和network术语；将`WS-shadow`解释为两个网络约束
    暴露系统的总效应，并建立四级验证与三层主张边界。实验机制和12-cell矩阵不变。
  - 独立规格首轮审查发现旧协议与新规格形成双重primary，并指出“同步上界”会暗改
    引擎。已将旧continuity DiD降为关键secondary、将四persona等权`WS-shadow`设为
    primary estimand，重开单一primary outcome，并以严格串行`w_i=1`基线取代同步
    稳健性；generated summary/schema迁移明确留给Phase 4B且当前继续fail closed。
  - 第二轮审查发现07-14旧规格仍残留“主检验/相同消息数量”措辞，且`epsilon`和
    有限规模gate仍占用旧primary路径。已把continuity DiD统一为关键secondary总效应，
    将`epsilon`迁移为候选组际结构路径，并要求scale gate在新primary outcome盲态
    冻结后检查其四persona等权`WS-shadow`对比。
  - 第三轮审查发现稳定旧ID`P1_GATE_DELTA_STABILITY`仍会把scale gate绑定旧ΔS。
    已新增`P1_GATE_PRIMARY_OUTCOME_STABILITY`，旧ID明确降为候选组际结构secondary
    诊断；schema/YAML字段迁移仍留给Phase 4B。三轮审查上限已到，最终修订待用户书面
    复核，不声称获得第四轮独立批准。
  - 用户已完成Phase 4A.1书面规格复核；提交`0600e2a`及此前Phase 4A提交已直接推送
    至GitHub `origin/main`。
  - 按make-plan要求完成Phase 4B三路只读文档发现。确认当前platform只有协议验证和
    不可变证据地基，不存在population/network/feed/memory/adapter/engine/checkpoint
    实现，且旧event/schedule/state/exposure语义与Phase 4A存在结构冲突。
  - 使用旧Phase 3A Python 3.12.13环境运行基线：`342 passed, 11 failed`；Ruff check
    和format check通过。11项失败来自已批准研究文档与尚未迁移schema/QA路径的预期
    不一致，Phase 4B-1必须先恢复全绿。默认Python 3.14无pytest/ruff，不可作为项目
    环境。
  - 新增
    `docs/superpowers/plans/2026-07-29-paper1-phase4b-implementation-plan.md`，
    将Phase 4B拆为环境、协议迁移、domain v2、研究制品、网络、schedule、feed/memory、
    mock adapter、事务engine/recovery及三档mock集成十个连续工作包。
  - 用户整包批准Phase 4B：4B保持mock-only、不保留旧同步API兼容层、每run使用独立
    SQLite事务库并生成不可变证据导出，按4B-0至4B-9连续执行，仅在新增研究参数或
    重大范围变化时暂停。决定与工程依据记录为`D-2026-07-29-21`和`DR-P1-090`。
  - Phase 4B-0完成：在当前隔离worktree建立项目本地`platform/.venv`，Python为
    `3.12.13`；按`requirements-dev.lock`安装并通过`pip check`。基线精确复现
    `342 passed, 11 failed`，11项均为Phase 4A/4A.1已批准文档与旧schema/YAML的
    预期迁移RED，不存在导入或依赖失败。
  - Phase 4B-1进入TDD：先新增新primary层级、严格串行有放回激活、private/public、
    finite unread feed及event/checkpoint协议测试，定向运行得到`3 failed`，失败原因
    分别为旧estimand、缺`feed_message_capacity`和缺activity-weight结构，确认RED有效。
  - 已迁移canonical/mirror schema、draft YAML、research-QA路径和generated summary
    投影；旧`Δlog(B/W)`移至`outcomes.group_structure`，新primary outcome保持
    `UNRESOLVED[P1_PRIMARY_OUTCOME]`，新primary estimand为
    `P1_PRIMARY_WS_SHADOW_AVERAGE_EFFECT`。中间全套测试达到`353 passed, 2 failed`，
    仅剩generated summary漂移；随后调用`update_human_protocol_summary(...)`重生成，
    相关定向测试`2 passed`。
  - Phase 4B-1首次实现验收：格式化后fresh全套为`357 passed in 13.13s`；Ruff check、
    Ruff format check、`pip check`和`git diff --check`均通过；canonical与packaged
    schema字节一致，SHA-256均为
    `A057D5D52AFFD146631BE8C7AC7ECA04EB62A0423EC69A55D5B3223E30E1CB6E`。
  - 独立规格审查要求修正三处candidate约束：`memory.window`不得保留旧
    `all_history`；`activation_count`必须固定为每sweep N=1000次；尚未决的
    `generation.seed_pairing`不得被schema预先锁成唯一resolved答案。三个最小回归
    测试先得到`3 failed`，分别确认旧值被错误接受及其他可审计resolved值被错误拒绝；
    随后只修改schema，定向GREEN为`3 passed`。
  - 修订后使用显式`--basetemp .pytest-tmp\phase4b1-fix`完成fresh验收：
    `360 passed in 12.18s`；Ruff check、Ruff format check、`pip check`、
    `git diff --check`和旧语义扫描均通过。canonical与packaged schema字节一致，
    SHA-256均为
    `150A34E0D6F79A666E4FFA1104D7F1FC3FB60D757DC945EA19B5E3A855B15D3A`。当前等待
    规格复审，复审关闭前不进入4B-2。
  - Phase 4B-1规格复审已`APPROVED`。随后代码质量审查发现JSON Schema只能约束
    数值类型和区间端点，不能保证activity-weight最小值严格小于最大值，也不能保证
    calibration `[lower, upper]`顺序；同时人类协议手写区仍保留机器迁移未完成的
    过期说明。本轮按质量审查意见进入语义验证与文档状态修订，完成前继续停留4B-1。
  - 质量修订先以真实`validate_protocol`路径建立9项RED：activity-weight
    `minimum == maximum`、`minimum > maximum`，六个calibration区间倒置及人类协议
    stale blocker均被旧实现错误接受。新增集中语义排序验证后定向GREEN为`9 passed`；
    `minimum < maximum`使用严格关系，range使用`lower <= upper`，只在相关值已解析为
    数值时比较，不填任何研究默认值。
  - 质量修订fresh验收使用
    `--basetemp .pytest-tmp\phase4b1-quality-fix`：`369 passed in 12.07s`；Ruff
    check、Ruff format check、`pip check`、`git diff --check`、schema镜像/hash、
    旧同步语义扫描和stale blocker扫描均通过。schema未改，SHA-256仍为
    `150A34E0D6F79A666E4FFA1104D7F1FC3FB60D757DC945EA19B5E3A855B15D3A`。当前停止
    修改并等待代码质量复审。
  - Phase 4B-1规格复审与代码质量复审均已`APPROVED`。提交前fresh验证再次得到
    `369 passed in 12.27s`；覆盖率套件同为`369 passed`，总覆盖率`91%`；
    Ruff check、Ruff format check、`pip check`、`git diff --check`、draft验证、
    formal fail-closed smoke及schema字节镜像均通过，两个schema的SHA-256均为
    `150A34E0D6F79A666E4FFA1104D7F1FC3FB60D757DC945EA19B5E3A855B15D3A`。4B-1
    已进入精确文件提交状态；4B-2尚未开始实现。
  - Phase 4B-2进入严格TDD实现时先建立未审查安全checkpoint。首组RED确认旧
    `derive_event_id(run_id, round, agent)`与schedule v1
    无法表达有放回事件；迁移后`event_ordinal`从0连续，schedule v2显式记录
    sweep/draw/agent/publish与算法版本，支持同Agent同sweep重复，并通过N=1000、
    T=50的50,000-slot轻量构造。
  - 新增版本化`ArtifactEnvelope`与`RNGProvenance`：制品ID绑定内容、算法、输入hash
    与RNG证据；seed由matched seed、注册namespace和稳定coordinates确定性派生，
    事件级namespace必须含`event_ordinal`，禁止`attempt_index`推进重试seed。
  - domain主路径已破坏性迁移为ordinal事件：运行态仅保留
    `pending/in_progress/succeeded/failed`，`excluded`不再是事件终态，
    `imputed/fallback`不再存在于Paper 1运行链；recovery cursor仅含
    `next_event_ordinal`和当前`event_id`。Exposure基础允许空社会feed和同发送者多帖，
    evidence graph只要求来源事件在ordinal上更早，不再硬编码“恰好上一轮”。
  - 旧`test_domain.py`的同步/round+agent契约被整体迁移，首次fresh全套为
    `174 passed`。测试总数从4B-1的369下降，不是功能性失败，而是删除了约200项已经
    失效的schedule v1、round cursor、同步AgentState及disposition兼容契约测试；
    protocol/installation测试保持全绿。随后补上attempt/event严格JSON round-trip、
    hash漂移和重试model-seed回归，当前全套为`177 passed`，覆盖率套件同为
    `177 passed`、总覆盖率`84%`。
  - 已在台式机以Codex bundled Python 3.12.13重建`platform/.venv`，按
    `requirements-dev.lock`安装17项精确版本依赖；`pip check`通过，lock SHA-256为
    `13878C75C775657BBFB0896AE858645C0FE37CC4C3717EDD5FBAD4833B6FD292`。台式机fresh
    基线精确复现`177 passed in 11.35s`与总覆盖率`84%`。
  - 本轮继续以五组可复现RED→GREEN补强domain失败关闭：拒绝不由event identity派生的
    attempt IDs；恢复manifest模型/环境复现身份必需字段及非空字符串；拒绝JSON boolean
    冒充单槽`schedule_count`；拒绝object键冒充`event_ids`数组；拒绝纯空白
    `launch_nonce`。定向domain回归为`41 passed`。
  - 同步修正Phase 4B计划中的低层笔误：`event_ordinal`应从0连续到`N×T-1`，与
    Phase 4A权威规格、代码和测试保持一致；attempt index仍从1开始，二者不得混淆。
  - 本轮fresh验收得到`183 passed in 11.62s`；覆盖率套件同为`183 passed`，总覆盖率
    从`84%`提高至`85%`。Ruff check、Ruff format check、`pip check`与
    `git diff --check`均通过。
  - 独立代码质量审查发现P1：`rng.py`只拒绝顶层`attempt_index`，嵌套object/array
    可改变同一event的model seed。两个参数化回归先得到预期RED：`2 failed`且均为
    `DID NOT RAISE ValueError`；最小GREEN在严格JSON transport校验后递归拒绝任意
    层级该键。定向RNG回归为`7 passed`，domain回归为`43 passed`。当时4B-2尚未
    关闭并等待该审查项复核，未进入4B-3。修复后的fresh完整套件与
    覆盖率套件均为`185 passed`，总覆盖率`85%`；Ruff check、Ruff format check、
    `pip check`与`git diff --check`均通过。
  - 当时checkpoint尚未通过独立规格审查与代码质量复核，因此未标记4B-2 complete。
    fail-closed补强后进入独立规格/反模式审查与代码质量复审；最终关闭情况见下方
    Phase 4B-2收口记录。
  - Phase 4B-2代码质量审查的四项修订已按严格TDD实现；当时继续等待复审。
    定向RED为`7 failed`，覆盖provider响应证据字段缺失、FAILED真实响应被拒、冻结typed值
    无法复用，以及非法`rng_provenance`错误类型不明确；最小GREEN为`7 passed`。
    `GenerationAttempt`现恢复4B-1的provider metadata/headers、HTTP status、usage、
    finish reason及对应hash，并拒绝空`model_identity`；FAILED允许保留真实raw response
    及元数据但禁止parsed success。RNG/Artifact typed构造现支持自身冻结值及
    `dataclasses.replace`，而`from_payload`严格JSON边界不变；artifact工厂在派生ID前明确
    校验provenance类型。实现代理的fresh全套为`194 passed in 12.92s`；其coverage
    coverage运行报告使用了与最终独立全量验证不同的统计口径，不作为4B-2最终
    覆盖率。待复审关闭前未进入4B-3。
  - Phase 4B-2独立规格审查与反模式审查均为`APPROVED`，独立代码质量复审为
    `APPROVED`。RNG嵌套`attempt_index` P1以及provider证据、FAILED响应保存、冻结typed
    值复用、provenance错误合同四项质量修订均已关闭。
  - Phase 4B-2最终fresh验证为`194 passed`，无skip、无xfail；独立全量coverage为
    `1245 statements / 187 missed / 85%`。Ruff check、Ruff format check、`pip check`、
    `git diff --check`、schema镜像、draft gate和formal fail-closed gate均通过。
  - 文档收口前验证快照的Git diff SHA-256为
    `481BFA0FB75EEFC9E438732B9CF3A93FC889BB19DFA061E9ACAD545DC215B081`；这是
    pre-documentation verification hash，文档修改后会变化，不是最终提交hash。
  - Phase 4B-2状态已更新为`complete / independently reviewed`。在Phase 4B-2收口时，
    下一工作包是4B-3且尚未开始；该次收口未新增研究参数，也未填补任何
    `UNRESOLVED[...]`。
  - Phase 4B-3按四组严格TDD进入实现。TopicPackage组由缺模块RED开始，完成严格JSON
    round-trip、版本合同、七档标签、固定输出字段顺序与canonical package hash；定向
    GREEN为`7 passed`。TRS/population组同样先确认缺模块RED，随后实现exact-N、非法或
    未缩放权重、结构零、缺失、不可实现约束与超容差fail closed；定向GREEN为
    `14 passed`。
  - 初始化组先冻结N=20/100/1000接口与期望分布；实现N=1000批准精确人数
    `[50,100,200,300,200,100,50]`以及明确标记mock的small-N最大余数缩放规则。人口—
    立场使用joint-stratum受约束整数分配并报告字段级count error；round 0制品同时保存
    私人立场/理由和一条必发公开初始帖。初始化定向GREEN为`10 passed`。
  - Persona组先确认缺模块RED，再实现共同骨架机械插入identity/continuity块、absent
    真省略、analysis-only字段隔离、禁用锁死措辞和四条件自动diff；因素块外任意字符
    变化都会fail。Persona定向GREEN为`6 passed`。
  - 新增5个`platform/tests/fixtures/paper1/mock_*.artifact.json`版本化fixture envelopes，
    覆盖topic、人口框、理由库、Persona模板和N=20/100/1000 scale cases。首次整合时
    PowerShell控制台编码破坏Unicode，ArtifactEnvelope以output-hash mismatch正确拒绝；
    最终文件改为经`apply_patch`落盘的ASCII-safe JSON，fixture/公开API整合为
    `42 passed`。该事件未改变研究参数，也未放宽hash校验。
  - 首次fresh全套发现旧公开API集合测试未纳入4B-3接口，结果为`235 passed, 1 failed`；
    按已由RED测试冻结的公开边界更新集合后，定向API回归为`2 passed`。在首轮实现
    checkpoint，4B-3尚未经过独立规格、反模式或代码质量审查，因此当时保持
    `in_progress / unreviewed`并停止于4B-3边界，未进入4B-4。
  - 4B-3实现代理最终fresh全套为`236 passed in 13.77s`，无skip/xfail；coverage套件
    同为`236 passed`，`1723 statements / 250 missed / 85%`。Ruff check、Ruff format
    check、`pip check`、`git diff --check`均通过；schema镜像、draft unresolved登记和
    formal fail-closed定向gate为`3 passed`。上述证据只表明首轮实现可交付审查，不把
    4B-3标记complete。
  - Phase 4B-3独立审查修订以三组RED→GREEN实现。Population的`3 failed`确认TRS
    source counts/residual draw count/tolerance未进入制品且不同tolerance共用envelope；
    修订后这些审计值进入payload，约束与tolerance共同绑定input hash，round-trip保留。
    Persona/空块的`7 failed`确认模板可扩张越权身份字段、空denylist可清空平台禁语、
    present块及四条件diff可接受空串；修订后平台固定现有六字段allowlist，平台禁语独立
    强制，identity/continuity present块均非空。未写formal默认、未改变TRS语义，也未为
    无fractional residual的官方scale fixture伪造seed差异。
  - 审查修订后fresh全套为`246 passed in 11.92s`；coverage同为`246 passed`，
    `1735 statements / 251 missed / 86%`。五模块/fixture交叉回归`52 passed`；platform
    范围Ruff、format、pip check、diff check以及schema镜像/draft/formal三个gate均通过。
    该阶段性检查点继续保持`in_progress / review fixes pending re-review`，当时等待独立
    复审、未提交且未进入4B-4。
  - Persona policy复审继续按严格TDD修订：参数化恶意模板及直接差异校验回归先得到
    `9 failed, 15 passed`，证明平台不可覆盖禁语仅含“never change/永不改变”且差异校验
    未执行同一政策。最小GREEN将已批准的抗从众/不受影响、固定原有价值方向、最大一步
    变化和永不改变逐字短语提升为平台不可清空常量，模板denylist仍可追加更严格禁语；
    render与validate共用同一fail-closed检查。Persona定向为`24 passed`，五模块/fixture
    交叉回归为`62 passed`。格式化后fresh全套与coverage均为`256 passed`，coverage为
    `1742 statements / 252 missed / 86%`，persona为`82%`；Ruff check、19文件format
    check、pip check、diff check与schema/draft/formal三门禁全部通过。该阶段性检查点
    当时仍为`in_progress / review fixes pending re-review`，未提交且未进入4B-4。
  - 最终规格复审继续发现`docs/decisions.md:306-307`四个canonical逐字禁语尚未提升为
    平台常量。identity/continuity恶意块对render与直接validate的回归先得到
    `8 failed, 24 passed`；最小GREEN仅加入“坚持、捍卫、忠于、除非证据确凿”，不扩展
    语义分类。Persona定向为`32 passed`，五模块/fixture为`70 passed`；fresh全套与
    coverage均为`264 passed`，coverage仍为`1742 statements / 252 missed / 86%`，
    persona为`82%`。Ruff、19文件format、pip、diff与三门禁均通过。该阶段性检查点
    当时继续保持`in_progress / review fixes pending re-review`，未提交且未进入4B-4。
- 边界：
  - 模块2虽已批准，但population、persona及其他Phase 4A模块尚未完成；当前不实现
    topic package，也不修改正式实验代码。
  - 本次批准不等于机器协议字段冻结；最终主议题、稳健性议题、目标模型probe结果、
    最终题干原文、量表实际值和hash仍保持未决，formal配置继续失败关闭。
  - 模块3的批准不等于人口制品冻结；CFPS筛选变量、精确人口字段、交叉约束、
    N=1000整数化和容差属于模块4/实现规格，当前没有填入coder默认值。
  - 模块4批准不等于字段或Persona制品冻结；正式身份模板原文、source-variable
    crosswalk、人口百分比、校准容差和审计阈值尚未写入机器协议。
  - 模块5批准不等于初始化制品冻结；正交容差、初始化RNG、论据家族、理由文本、
    judge阈值、人工编码规则和hash仍保持未决，formal配置继续失败关闭。
  - 模块6批准不等于Persona模板冻结；最终逐字原文、顺序挑战、操纵检查阈值、
    template ID/token计数/hash仍保持未决，formal配置继续失败关闭。
  - 模块7批准不等于网络制品冻结；NetworkX版本、精确k/p、正式图seed、结构阈值、
    edge list、Agent—node映射和hash仍保持未决，formal配置继续失败关闭。
  - 模块8机制设计已经批准，但B、K、活跃/表达分布参数与过程阈值仍只是Phase 0
    候选；它们在真实gate冻结前继续保持`UNRESOLVED[...]`。当前未修改schema、
    formal YAML或实验运行代码。
  - Phase 4B-3代码质量审查的五项发现已按严格TDD关闭：理由按立场确定性洗牌并无放回
    分配、容量不足fail closed，显式mock理由fixture含1,000条唯一记录；Persona对归一化
    payload/envelope做严格diff，身份模板以`Formatter`解析并恰好使用六个允许字段；供体
    schema必须同构并给出精确missing/extra诊断；人口制品同时保存target、weighted与
    integerized边际/联合计数及calibration/TRS误差。
  - 独立规格审查、反模式审查与代码质量复审均为`APPROVED`，没有开放审查项。质量定向
    回归为`72 passed`；最终fresh全套为`274 passed`，无skip、无xfail；coverage套件同为
    `274 passed`，`1817 statements / 257 missed / 86%`。platform Ruff/format、pip、diff、
    schema镜像、draft unresolved、formal fail-closed与generated human-summary同步gate均通过。
  - 文档收口前验证快照的Git diff SHA-256为
    `57de0f024bbf41ba8b46335d593f90a5617578536824ba12450cee999db4fa5d`；这是
    pre-documentation verification hash，文档修改后会变化，不是提交hash。
  - Phase 4B-3状态已更新为`complete / independently reviewed`。1,000条理由与其他
    fixture值继续明确为`mock_only / not_frozen`，本轮未填补任何`UNRESOLVED[...]`；
    Phase 4B-4尚未开始。
  - Phase 4B-4按严格TDD进入实现。第一组RED在收集期得到
    `ModuleNotFoundError: agent_ex.network`；随后实现并公开导出WS、shadow、Agent-node
    mapping五个最小接口。WS专项先达到`13 passed`，network专项首轮为`19 passed`。
  - 工程gate将NetworkX 3.6.1写入Python 3.12锁文件并实际安装；初稿曾以独立工程ID
    登记版本、WS/shadow算法和mock预算。审查已判定该旁路无效并迁移为schema正式
    `P1_*`决策ID；draft继续为`UNRESOLVED[P1_*]`，未把工程候选升级为研究冻结。
  - shadow采用版本化、有界、确定性的forbidden-edge connected double-swap：从WS副本
    逐步消除全部WS边，每个接受交换即时验证连通，始终保持简单图与逐节点度数；预算
    耗尽立即fail closed。后续三组hash/downstream回归先得到`3 failed`，补充下游绕过
    完整WS验证得到`1 failed`，修复后分别为`3 passed`与`1 passed`。matched-seed混搭
    回归先得到`1 failed`，修复后相关范围`4 passed`；shadow与mapping现在都拒绝跨seed
    输入。
  - N=1000、`k={6,10,20}`、`p={.02,.05,.10}`、三个预登记mock seeds的27张WS纯结构
    gate全部连通且边数严格为`N*k/2`，无失败seed。锚点`k=10,p=.05`三seed的聚类为
    `.5620/.5621/.5741`，平均最短路为`5.086/5.059/5.247`，直径均为9。对应三张shadow
    均首attempt成功、度数逐节点匹配、全连通且WS边交集为0；耗时20.77至21.80秒。
    gate只读结构、连通、耗时与制品大小，未读取意见或调用LLM。
  - 首次fresh全套为`285 passed, 12 failed`：旧精确公开API集合缺五个新接口，且最初
    使用未获协议链覆盖的工程ID污染schema decision ID集合。首轮临时隔离后
    protocol/wheel/API定向为`144 passed`；随后审查要求并已完成正式`P1_*`迁移。修复后的fresh全套为
    `299 passed in 42.91s`；coverage同为`299 passed`，`2081 statements / 297 missed /
    86%`，新network模块`85%`。
  - Phase 4B-4五类P1 review fixes已按严格TDD实现：mapping三制品绑定、正式`P1_*`
    schema/QA/YAML迁移、纯结构D-07 gate、WS严格审计与shadow严格审计。network定向
    `39 passed`、protocol `139 passed`；分拆fresh全套合计`314 passed`，coverage `86%`。
    当前保持`in_progress / review fixes pending re-review`；未提交、未进入Phase 4B-5。
  - Phase 4B-4后续multi-attempt audit与代码质量修复均按严格TDD关闭。独立规格、反模式与
    代码质量审查最终均为`APPROVED`，无开放审查项。最终network专项为`43 passed`，
    protocol/schema gates为`143 passed`；连续fresh全套为`318 passed in 31.25s`，无skip/xfail；
    coverage套件为`318 passed in 97.43s`，`2237 statements / 323 missed / 86%`，
    `network.py`为`84%`。
  - N=1000锚点由独立验证重算通过：WS、shadow、D-07结构gate及绑定population、round-0与
    WS的Agent-node mapping均通过builder/validator合同。shadow output hash相较早期checkpoint
    的变化只来自新增完整multi-attempt audit；图结构和交换计数未变。全部制品与hash仍为
    `mock_only / not_frozen`工程证据，所有精确`P1_*`机器值继续保持`UNRESOLVED[...]`，
    不构成formal freeze。
  - 完成文档更新前的已验证代码/测试工作树快照SHA-256为
    `B19E18908FEA12EC605310A096CCFC9A0A58FB3CEF9A9F6DED4766B55A1661DB`。这是
    pre-documentation verification hash；文档更新后最终release verifier会产生新快照，
    它不是提交hash。
  - Phase 4B-4现已关闭为`complete / independently reviewed`。本轮未调用真实模型、未填补
    `UNRESOLVED[...]`、未冻结formal参数；Phase 4B-5尚未开始。
  - Phase 4B-5已按严格TDD完成首轮attention、hurdle–Beta expression、weighted-with-
    replacement activation与预生成publish FrozenSchedule实现。RED依次覆盖模块/接口缺失、
    Pareto/equal能力、审计诊断、公开API与hash-consistent attention伪造；后续审查修复补齐
    有限预算截断、逐event provenance、三源强绑定、runtime/diagnostics重封装及canonical
    12-cell/expected-seed门禁；后续复审又以RED确认lognormal location此前被隐式固定为0，现已
    改为显式未冻结参数并进入payload/hash/RNG/replay合同。终审继续补齐Beta严格内点有限budget、
    N/T/event能力上限和紧凑event RNG ledger；最终又移除stdlib无界`betavariate`，改用自有bounded
    gamma-ratio Beta，并把raw ledger入口迁移为trusted validation→typed O(1)读取。schedule专项
    最终34 passed。
  - 同matched seed的12 cells必须逐字复用attention、expression、activation与publish四制品；
    validator会确定性重算全部RNG序列、source/input hash和最终schedule hash。跨seed绑定、
    伪造activation/expression/publish payload以及运行后更改publish flag均fail closed。
  - 2026-08-18从断点恢复后又按严格TDD关闭最终三个P1：普通调用无法再伪造
    `ValidatedEventRNGLedger`，可信核验后才签发sealed capability；截断lognormal改用每attempt
    两次uniform的显式Box–Muller，Pareto改用每attempt一次uniform的inverse CDF，均不调用
    stdlib隐藏循环；N>1000在attention/expression sampling以及activation/publish source replay
    前统一fail fast。三项均先观察到针对旧实现的RED，再完成最小GREEN；Beta sanity降至N=1000。
  - postfix代码质量复审继续以严格TDD关闭两个容量P1：oversized不可物化Sequence原先在N门禁
    前触发元素访问，12组attention/expression/activation/publish oversized或bool envelope原先
    在全cell预检前触发replay；修复后先用`len`/raw声明完成N≤1000、T≤50、events≤50,000
    bool-safe门禁，再执行物化、深层语义校验和确定性重放。
  - 后续1P1+1P1+P2继续先RED：raw ledger的int→float/bool可在strict type gate前进入rebuild，
    len=1000 Sequence会被tuple探测index 1000，删除10类preflight必需字段会进入replay。GREEN
    引入strict-JSON canonical类型敏感比较、`range(validated_len)`物化，以及records/N/T/slots/
    ledger count必需且`N×T`一致的全cell preflight。
  - 最终独立验证：连续full为`402 passed in 69.92s`，coverage为
    `402 passed in 204.17s`、`2876 statements / 419 missed / 85%`，`schedule.py`为
    `638 statements / 96 missed / 85%`；定向验证为`275 passed`。N=1000/T=50显式mock
    23.765秒构造50,000个连续ordinal；activation/publish JSON为4,110,564/5,132,825 bytes，
    JSON round-trip一致。ledger一次可信验证为3.193秒，验证后ordinal 49,999读取约47微秒，
    且禁止digest重扫后仍成功；未调用LLM。
    最新N=1000/T=50 gate再次为`1 passed in 28.18s`。
  - 独立规格/反模式与代码质量复审均为`APPROVED`，独立release verification为`PASS`；
    所有定向攻击、Ruff/format、依赖、diff、schema镜像及Git hygiene gate通过。最终验证快照
    候选canonical snapshot SHA-256为
    `dc1b81a27919ec9e606c58342fb8771ba6e5ba962bf6c20006ba8f3168d6ea2c`；它是完成文档
    更新前的已验证代码/测试候选，文档后release会生成新的最终snapshot。两份schema镜像
    SHA-256均为`3db603ea0c8303a061838cd962db687a6d5ab616bacc78dd1876b007d7a5783e`。
  - draft仍含88个`UNRESOLVED[...]`。所有mock参数均须调用者显式传入，产物保持
    `mock_only / not_frozen`，formal继续fail closed；上述快照与schema hash不构成formal
    freeze或提交hash。
  - Phase 4B-5现已关闭为`complete / independently reviewed`。本轮未调用真实模型、未产生
    研究结果、未冻结formal参数；Phase 4B-6尚未开始。
  - 2026-08-18 Phase 4B-6已进入严格TDD实现；验收边界限于private/public
    状态、有限未读feed、memory与可追溯exposure记录。当前状态为
    `in_progress / implementation complete / pending independent review`。state/memory/feed/
    domain/initialization定向为97 passed，fresh全套435 passed，coverage 3688 statements /
    519 missed / 86%；Ruff、format、pip、diff、schema/draft/formal/human-summary门禁通过。
    本轮仍未进入4B-7/4B-8，未调用真实模型，未冻结B/K或任何formal参数。
  - Phase 4B-6首轮独立审查复现了来源字段可重封装、selection缺少可信输入重放、
    round-0证据跳过及累计public log造成长期O(E²)调用形态。修复严格按A-E分组先建立
    RED，再加入TopicPackage/七文字标签、state/post/memory exact replay、incremental
    unread slice、稳定round-0排序、selection exact replay，以及带source post/update hash、
    graph/capacity/round-0 provenance的ExposureRecord；evidence graph现绑定manifest seed并对
    round-0 trusted evidence fail closed。
  - 修复后state/memory/feed/domain/initialization定向`110 passed`；N=1000/T=50调用形态以50,000次
    event-local空未读切片在`15.81s`通过；fresh full为`448 passed in 72.43s`，coverage为
    `448 passed in 225.28s`、`3838 statements / 549 missed / 86%`。Ruff、format、pip、diff、
    schema镜像、88个draft unresolved、formal fail-closed、human-summary与安装门禁通过。
    当前为`in_progress / review repairs implemented / pending independent re-review`，不标
    complete、不提交、不进入4B-7/4B-8。
  - Phase 4B-6最终复审继续以严格TDD关闭1P1+2P2：普通selected source和全部expired
    round-0 candidates现在都必须提供真实typed `PublicPost`/`PrivateUpdate`映射及TopicPackage，
    并完整重放seed/topic/agent/hash、实际成功source event ID/ordinal、publish flag与attempt；
    跨seed、event漂移及SimpleNamespace伪证据均fail closed。新增latest-public pointer可信post/
    previous-pointer replay validator并进入公开API；neighbor集合在hash/replay前按Agent ID规范排序，
    同集合反序得到相同selection ID/hash。
  - 最终复审修复后定向为`114 passed in 16.97s`，fresh full为`452 passed in 78.83s`；
    coverage为`452 passed in 249.49s`、`3879 statements / 557 missed / 86%`，domain/feed/
    memory/state分别为81%/84%/87%/88%。状态仍为pending independent re-review，不标complete。
  - 最后两项P1继续先RED后GREEN：event-backed update必须绑定source event末次且成功attempt，
    不能绑定最终成功前的FAILED retry；ExposureRecord新增完整有序`candidate_post_hashes`，
    全部expired round-0也逐ID/hash核验，因此同ID替换内容、缺失/错序/伪hash/bool均失败。
    最终full为`455 passed in 84.92s`；coverage为`455 passed in 255.29s`、`3893 statements /
    557 missed / 86%`。状态继续pending independent re-review。
  - 对最后一项普通expired-event candidate P1先撤回过早生产改动，恢复455-pass快照后再
    建立专门RED；缺typed maps、同ID内容替换、跨seed及FAILED attempt绑定均确认旧实现接受。
    GREEN统一遍历全部ordered candidate ID/hash并执行typed post/update、topic/seed、actual event
    与末次成功attempt重放；selected arrays只作额外显示/source核对。最终定向`119 passed in
    16.70s`，full`457 passed in 79.11s`，coverage`457 passed in 229.82s`、`3918 statements /
    567 missed / 86%`，状态继续pending independent re-review。
  - 最后一项round-0分类P1先RED确认：合法expired round-0记录可清空其round-0 IDs/RNG并
    重封装后被旧实现接受。GREEN从typed candidates按原顺序重建真实round-0 ID元组并与记录
    精确比较，receiver-self/round-0规则作用于真实集合；event帖错标round-0同样失败。最终定向
    `120 passed in 14.64s`，full`458 passed in 77.25s`，coverage`458 passed in 219.41s`、
    `3924 statements / 568 missed / 86%`，继续pending independent re-review。
  - 最后一项receiver-self P1专门RED确认：普通event-backed候选可在过期后继续由receiver自身
    署名，只要另有合法selected来源，旧验证仍接受。GREEN将self-source检查前移到all-candidate
    typed replay的round-0/event分支之前，因而selected/expired与两类namespace全部统一拒绝；
    原有event错标round-0攻击保留非self来源以独立验证分类。最终定向`121 passed in 14.31s`，
    full`459 passed in 73.82s`，coverage`459 passed in 219.14s`、`3922 statements / 566 missed /
    86%`；N=1000/T=50为`1 passed in 13.21s`，五项protocol gate、四项installation测试及全部
    静态/协议/卫生门禁通过，状态继续pending independent re-review。
  - Phase 4B-6最终独立规格/反模式与代码质量复审均为`APPROVED`，release verification为
    `PASS`，阶段关闭为`complete / independently reviewed`。最终连续fresh full为
    `459 passed in 68.59s`，coverage为`459 passed in 218.13s`、
    `3922 statements / 566 missed / 86%`，feed/memory/state/domain分别为84%/87%/88%/81%；
    定向回归121 passed，补充攻击套件18 passed及2 passed，protocol/installation 144 passed，
    N=1000/T=50增量调用形态为`1 passed in 12.99s`。完成文档前候选canonical snapshot
    SHA-256为`3563f328c7f749b423b7e8bb01aa99d7bf20ffe92d458c454f9f6a67ccf9fe36`，两份schema
    镜像SHA-256均为`3db603ea0c8303a061838cd962db687a6d5ab616bacc78dd1876b007d7a5783e`；文档更新后
    release将生成新snapshot。draft仍含88个`UNRESOLVED[...]`，所有产物保持
    `mock_only / not_frozen`，B/K未冻结且只能显式作为mock挑战输入。本阶段未调用真实模型、
    未产生研究结果；Phase 4B-7尚未开始。
  - 2026-08-18 Phase 4B-7按严格TDD完成首轮实现，状态为`in_progress / implementation
    complete / pending independent review`。三个模块的首个RED均为预期的模块缺失；随后
    分切片完成PromptView、严格parser和provider-neutral deterministic MockAdapter。Prompt
    以typed GenerationEvent绑定event/attempt上下文，并绑定seed/cell/topic/persona/current
    private state/memory/exposure/template；visible projection不含候选/过期帖、内部hash/RNG、
    cell/mode标签、他人private state、数字社会立场或confidence，社会消息只按4B-6已有
    display slots排列。
  - parser严格接受ordered `stance/confidence/public_reason`，并拒绝数字或未知label、bool/
    nonfinite/越界confidence、空/控制字符理由、缺失/额外/重复字段、代码围栏、尾随文本和
    模型覆盖`publish_flag`；成功与失败均保留raw response及hash，失败不产生parsed内容。
    MockAdapter只消费从PromptView派生的request和显式script/mock seed，response绑定
    request/event/attempt/script/model/runtime及全部hash；它不联网、不重试、不改变state/cursor。
  - 新增定向32 passed；最终连续fresh全套为`491 passed in 74.37s`，coverage为
    `491 passed in 225.44s`、`4492 statements / 638 missed / 86%`，新增adapter base/mock、
    parser、prompt覆盖率分别为88%/88%/89%/83%。N=20/100/1000 prompt+render工程基准分别
    为0.072/0.373/3.484秒。Ruff、format、pip、diff通过；schema镜像hash未变且draft继续
    含88个`UNRESOLVED[...]`。阶段尚待独立规格/反模式、代码质量和release复审，不标记
    complete、不提交、不推送、不进入4B-8。
  - Phase 4B-7首轮独立审查为FAIL（7项P1与1项P2）。随后严格按A-G分组建立RED并修复：
    complete pending event与ExposureRecord现绑定topic/run/receiver event；完整successful
    private-update history重放state与latest-K memory；population artifact、persona template与
    cell condition机械重放；所有自然文本进入单一deterministic JSON data payload并使用显式
    mock context/parser limits；AdapterRequest改为factory-sealed capability，response与parse
    evidence加入trusted replay validator；parser绑定topic/response/request/event/attempt并对
    UTF-8、bytes、depth、duplicate/order/extra/bool/nonfinite严格fail closed。
  - 修复后定向`125 passed in 17.68s`，fresh full为`500 passed in 79.99s`；coverage为
    `500 passed in 250.21s`、`7647 statements / 697 missed / 91%`，adapter base/mock、parser、
    prompt分别为89%/86%/88%/82%。N=20/100/1000 prompt+render为
    0.1029/0.5574/5.486秒；10,000层JSON攻击0.0078秒返回depth evidence，50,000字符理由在
    显式预算内0.0098秒成功。Ruff/format/pip/diff、schema镜像与88个UNRESOLVED gate通过。
    状态为`in_progress / review repairs implemented / pending independent re-review`；未提交、
    未推送、未进入4B-8或真实模型。
  - Phase 4B-7第二轮独立复审再报4P1+2P2，全部按RED→GREEN修复：PromptView和
    AdapterResponse的普通构造/from_payload现均为untrusted，必须分别对完整topic/persona/
    population/history/state/memory/exposure selection/source/event/limits或request/script/runtime
    重放后才返回sealed capability；AdapterRequest/parser拒绝unsealed输入。ExposureRecord现
    同时调用4B-6 selection与record validators，hash-consistent rendered social攻击失败。
    system role改为固定静态常量，persona及全部自然文本只在单一user JSON data object中。
    PromptLimits在JSON序列化前检查每个字符串与memory/social count；ParserLimits先检查字符数，
    再建立有限UTF-8副本并检查bytes。
  - 第二轮修复后定向`128 passed in 16.25s`，fresh full `503 passed in 76.34s`，coverage
    `503 passed in 228.98s`、`7762 statements / 710 missed / 91%`；base/mock/parser/prompt为
    89%/86%/87%/82%。N=20/100/1000为0.1562/0.7716/7.0455秒，10,000层JSON为
    0.0106秒失败关闭，50,000字符理由为0.0092秒。状态继续pending independent re-review；
    未提交、未推送、未进入4B-8。
  - 2026-08-27从暂停断点恢复4B-7。保留RED
    `test_prompt_requires_manifest_bound_run_cell_and_frozen_schedule_provenance`先复现缺失
    `RunManifest`参数，再最小GREEN：prompt view现hash绑定typed manifest，并核验run/seed/
    canonical cell/recovery cursor/current frozen slot；全部非round-0 private/social source须属于
    同run成功前缀、严格早于receiver、匹配冻结slot并绑定final successful attempt。四种I×C
    persona静态mock控制复归通过，population/persona自然文本仍只在user JSON data。
    focused为52 passed，final fresh full为511 passed in 73.83s，production coverage为511 passed in
    234.59s、4898 statements / 710 missed / 86%；N=1000 prompt+render为8.9075秒，深层攻击
    focused通过，50,000字符理由为0.0131秒。Ruff/format/pip/diff、schema镜像、human summary、
    wheel/formal fail-closed与Git hygiene均通过。状态仍为pending independent re-review；未提交、
    未推送、未进入4B-8。
  - 4B-7最终review repairs继续逐项RED→GREEN。四个I×C cell现在共享完全相同的静态system
    合同；版本化`trusted_control`仅携带从cell和已验证persona重放得到的布尔控制，I0/C0为
    真省略而非负向指令，C0仍接收与C1相同的private state/memory。每个非round-0 own/social
    `PrivateUpdate`的stance/confidence/reason严格绑定其final SUCCEEDED attempt的
    `parsed_response`，publish状态继续绑定冻结schedule/event及PublicPost。新增一次性
    `ValidatedPromptRunContext`：raw manifest只在context创建时roundtrip/hash并预建schedule、
    event-ID set、source event/attempt索引，随后每prompt只按当前与可见source查询；N=50000
    context验证0.317秒，三次稀疏lookup约6.8微秒。HMAC seal文档已修正为反序列化/意外变异
    完整性哨兵，不声称对任意同进程Python代码构成安全边界。focused 118 passed；fresh full
    514 passed in 80.54s；production coverage 514 passed in 248.34s、4981 statements /
    729 missed / 85%，base/mock/parser/prompt为90%/87%/87%/80%；N=1000 prompt+render
    8.827秒。protocol/install 144 passed；Ruff、format、pip、diff及schema镜像/88 unresolved
    gates通过。状态保持pending independent re-review；未提交、未推送、未进入4B-8。
  - 2026-08-27复审追加三项P1均严格RED→GREEN：`ValidatedPromptRunContext`的可见seal不再
    是可复制身份对象，而是对manifest/run/cell/recovery、schedule slots、event-ID set及
    source event/attempt索引做canonical摘要的closure-held HMAC完整性哨兵，消费者逐次复验；
    domain graph与prompt撤销未获`P1_MODEL_SEED_PAIRING`批准的同event retry seed相等约束，
    仍逐attempt严格记录整数seed；prompt以O(candidate_count)逐条重放全部candidate的typed
    post/update，expired round-0内容漂移亦失败关闭。定向145 passed，三项追加回归9 passed；
    final fresh full 522 passed in 75.45s；production coverage 522 passed in 232.90s、5004
    statements / 728 missed / 85%，prompt 81%；N=1000 prompt+render 10.001秒，N=50000
    context验证0.903秒、三次lookup 3.1微秒；10,000层攻击gate通过，50,000字符理由0.0153秒。
    状态仍为pending independent re-review；未提交、未推送、未进入4B-8。
  - 2026-08-28最终2 P1 + 2 P2继续严格RED→GREEN：新增四项回归先稳定得到`4 failed`，
    分别证明consumer仍重序列化完整source graph、FrozenSchedule缓存hash可掩盖反射漂移、
    未决`model_sampling`仍可派生，以及parser超长字符在门禁前进入seal/hash。最小GREEN将
    context改为独立typed schedule/manifest/event/attempt snapshot的`id + weakref` exact-owner
    registry，consumer O(1)查找且仅使用snapshot；weakref回调按exact stored ref清理，复制/
    replace/跨cell失败关闭。公共RNG namespace移除`model_sampling`，未冻结时明确失败；parser
    在seal/hash前执行strict string、character、单次有界UTF-8和byte gate。focused
    prompt/parser/mock/domain/feed为`151 passed in 16.29s`；此前522/full/coverage仅为旧snapshot
    历史证据，当前snapshot待独立复审后只跑一次final full+coverage。未提交、未推送、未进入4B-8。
  - 2026-08-28生命周期复审的3 P1 + 1 P2已收口：run context公共handle只保留scalar
    identity/metadata，完整schedule/event/attempt/index只在exact-owner registry；新增原子
    `advance_validated_prompt_run_context`，同一handle可连续推进成功event，仅按本event attempt
    数量校验，失败不移动cursor或prefix commitment，且不约束不同event/attempt的显式model
    seed。PromptView新增logical context ID与current prefix hash，manifest hash明确为恢复时baseline。
    prompt source exact-cover使用`len + expected-ID point lookup`，不再全量遍历调用者map；parser
    在UTF-8编码前先用字符数保守拒绝必然超过byte budget的输入。50,000-slot连续三event结构
    回归通过；恢复context初始索引另需exact-cover manifest完整成功前缀，防止遗漏未来可能读取
    的旧source。追加恢复一致性测试先得到`2 failed`，证明live advance与checkpoint恢复算法
    不同且恢复prefix未绑定attempt内容；现统一stable genesis + ordinal event hash + ordered
    attempt hashes fold，同证据恢复得到相同logical context ID/prefix，内容变化则prefix变化，
    仍不冻结model-seed pairing。两项GREEN `2 passed in 0.55s`、context focused
    `15 passed in 1.44s`；prompt/parser/mock/domain/feed focused为`159 passed in 18.42s`，Ruff/format/diff
    通过。本修复按计划未跑full/coverage，状态仍为pending independent re-review；未提交、
    未推送、未进入4B-8。
  - 2026-08-28并发一致性P2已用无sleep的Event协调回归完成RED→GREEN：RED明确观察到旧
    event cursor绑定advance后新prefix，metadata也没有单次原子版本捕获。GREEN改为每context
    writer lock与不可变`cursor + prefix`版本最后发布；prompt/metadata reader每次只捕获一个
    版本，append-only indexes不会跨旧cursor可见，不复制完整prefix且不占用全局跨run长锁。
    新增`2 passed in 0.61s`，context focused `17 passed in 1.41s`，扩展focused
    `161 passed in 18.74s`，Ruff/format/diff通过；未跑full/coverage、未提交、未推送、未进入4B-8。
  - 2026-09-02恢复长线执行。Phase 4B-8C-3 Task 8在公开reconciliation与checkpoint
    version split修复后通过独立规格和质量复核：新checkpoint写v4，legacy v3按历史policy
    projection验证exact/stale-prefix；公开pipeline必须显式传reconciliation，真实close/open后
    zero-resend提交。主会话fresh full为`979 passed, 2 skipped in 162.83s`，Ruff/format/pip/diff
    全绿；提交`705b9a8`已推送，local/upstream一致。
  - Task 9新建`logs/2026-09-01-phase4b8c3-evidence-pipeline.md`，记录Task 1-8提交边界、
    五类durable crash prefix、v6/v4/v3边界、失败/重试/篡改证据与4B-9剩余门禁。三路最终
    release reviewer启动即被workspace credits阻断；未将该日志或整个4B-8误标为最终批准，
    主会话转入4B-9既有批准边界的详细规划发现。
  - 依据07-29已批准Phase 4B计划与`D-2026-07-29-21`，完成4B-9详细设计草案
    `docs/superpowers/specs/2026-09-02-paper1-phase4b9-mock-integration-design.md`和逐任务TDD计划
    `docs/superpowers/plans/2026-09-02-paper1-phase4b9-mock-integration.md`。设计只新增pure matrix
    contract、调用既有pipeline的thin run harness和v6只读process audit；N=100完整执行12 cells，
    N=1000/T=50分为12-cell shape gate与单stress-cell真实50,000-event mock gate。所有B/K/T/
    stress cell值只存在版本化mock-only/not-frozen fixture，不进入formal默认。两份文档已通过
    主会话placeholder/diff自检，仍待额度恢复后的独立规格复核；未开始4B-9生产代码。
  - 子任务额度恢复后补齐Phase 4B-8C-3 Task 9最终三路release gate。独立verification、
    specification/anti-pattern和code-quality均`APPROVED`、P0/P1/P2无；三路fresh full分别为
    `979 passed, 2 skipped in 152.89s`、`172.39s`和`166.74s`，Ruff check/format（47 files）、
    pip check与diff check全绿。保留P3仅为白盒测试私有helper/connection、少量fixture close
    维护性，以及checkpoint evidence逐点查询需在4B-9真实50,000-event gate测量。4B-8现可
    标记`complete / independently reviewed`。
  - 4B-9设计规格完成三轮独立复核。首轮修正COMPLETE态审计、
    `exploratory/process_diagnostic`标签、hash-bound版本化术语映射与pipeline独占时钟；
    第二轮按现有8C-3实现校准fresh/retry/pending、IN_PROGRESS、failure、landed-success和
    already-complete的精确clock消费；第三轮`APPROVED`且P0-P3均无。
  - 4B-9实施计划独立复核发现并关闭4项P1与1项P2：checkpoint ordinal/path及written-key
    exact-cover、run/audit typed composite边界、50,000-event默认排除与唯一显式执行、每个
    command block的fresh workdir，以及Phase 4A.1中文术语原文映射。复核最终`APPROVED`，
    P0-P2均无；唯一P3（Task 4 Files漏列可选窄只读`storage.py`）已补齐。尚未开始生产代码。
  - 2026-09-04完成4B-9 Tasks 1--7。提交链为`9011cd3`、`c76c294`、`44ef94c`、
    `0c4ec46`、`c128ca8`、`c5e071f`、`7749609`，均已推送到
    `origin/codex/paper1-phase4b`。N=20覆盖六类durable crash prefix；N=100完整12 cells
    共1,200事件；N=1000/T=1恢复在post-invocation断点证明zero-resend并与连续run投影一致。
  - N=1000/T=50的12-cell shape通过；显式`P1-I1-C1-E2` release run真实调用mock pipeline
    50,000次，最终`1 passed, 4 deselected in 20708.39s`。观测为执行计时20555.347秒、
    Python tracemalloc峰值3,236,920,043 bytes、SQLite 2,969,907,200 bytes、单checkpoint
    20,405,320 bytes、audit 98,414,822 bytes。临时数据库与checkpoint在SHA-256核验后删除，
    未进入Git。
  - 首次50,000-event运行在事件全部提交后发现checkpoint v4有序证据payload超过旧16 MiB
    I/O上限。新增RED稳定复现，最小GREEN将仍有界上限调整为32 MiB；checkpoint全套
    `101 passed`，原2.9 GB数据库重开并生成`complete/current` checkpoint，随后干净重跑
    端到端通过。Task 7 focused为`4 passed, 1 deselected`，matrix/run/audit为`130 passed`，
    Ruff/format/pip/diff通过。现进入Task 8最终full/coverage、文档、协议/安装/Git门与三路终审。
  - 2026-09-04 Task 8规格终审指出N=100仍缺独立close/open恢复比较。已按严格TDD先得到
    `NameError` RED，再新增单cell 0--49执行、close/open、50--99续跑门禁；恢复阶段恰好
    50次adapter调用且最终投影等于连续100-event control，定向`1 passed in 19.72s`。
    同步修正reproducibility与handoff，明确N=20六断点恢复调用数，避免把50,000-event
    release gate误述为自身包含close/open。
  - Task 8代码质量终审发现外部SQLite篡改可能在下一写事务被错误重新认证、终点重复三次
    全量recovery replay，以及checkpoint v4对合法retry历史容量不足。三项均先复现RED：
    篡改后写入曾继续提交、snapshot计数为3、按50k×每event一次retry估算远超32 MiB。
    修复后`BEGIN IMMEDIATE`锁定快照内强制重验，终点snapshot计数降为1；新写compact
    checkpoint v5只保留历史证据有序hash与最小因果引用，legacy v3/v4继续验证。真实构造的
    50k个连续event identity×每event一次授权retry envelope为81,119,908 bytes，在96 MiB
    文件上限与1.5 GiB峰值预算下完成typed构造、atomic write/load round-trip；并直接验证
    legacy full-history v4 stale prefix（合计`2 passed in 94.19s`）。checkpoint全套
    `102 passed in 89.92s`，storage/mock-run/N100 recovery交叉套件`250 passed, 2 skipped`。
  - Task 8稳定快照的串行最终full为`1124 passed, 2 skipped, 1 deselected in 1031.80s`；
    coverage为`1124 passed, 2 skipped, 1 deselected in 2940.43s`，production
    `10,795 statements / 1,589 missed / 85%`。六个协议/schema/summary/formal/wheel
    精确节点最终独立复验为`6 passed in 6.39s`，tracked-artifact hygiene无命中。规格与代码质量复审均
    `APPROVED`且P0-P2无；尚待最终verification reviewer对稳定快照复核后提交推送。
  - 最终verification reviewer复核Task 8完成标准、提交清单、文档边界与Git卫生后为`PASS`，
    P0-P3均无；其发现的旧09-02 handoff路径和漏列checkpoint/storage修复文件已更正并复审关闭。
    Phase 4B-9及整个Phase 4B现达到`complete / independently reviewed`工程边界；下一步进入
    Phase 0A/0B与真实模型N=20/50/100校准，formal矩阵仍保持fail closed。

## 会话：2026-09-05至2026-09-09

### Phase 0A-0：离线 probe 骨架

- **状态：** complete / independently reviewed
- 按批准规格与逐任务计划完成独立 `agent_ex.calibration` 包：不可变 specification、
  816-case 确定性展开、request/response/parse attempt 证据、可恢复 runner、质量门、
  盲态语义复核、precommitted selection、无正式权限的 freeze proposal、11文件不可变
  bundle 和只接受 scripted adapter 的离线 facade。
- Tasks 0--8 主提交链从 `ada2f1c` 至 `4fbd193`；Task 9终审修复为 `1ef0946`、
  `9e998c1`和`6af2ff1`。终审修复实际施行 timeout/Retry-After/backoff、扩展异常
  snapshot、把全部 policy-bound 语义维度接入 gate、限制无确定性门的 proposal、修正
  1--7草案长度并严格拒绝非法标签容器。
- 修复后 full 为 `1463 passed, 2 skipped, 1 deselected in 4601.94s`；coverage 同计数，
  `14,600 statements / 2,102 missed / 86% in 11635.94s`。计划指定专项为
  `163 passed in 1606.39s`，最终验证员独立复跑为 `163 passed in 1630.74s`；Ruff、
  format、pip和diff门均绿。
- 三路终审均为 `APPROVED`，P0--P3为零。工作只用 scripted synthetic responses，
  未联网、未调用真实模型、未写入凭据或正式权限，`docs/decisions.md`仍为`records: []`。
- 四 replicates 共816个逻辑 cases（144 topic quality、96 identity、576 continuity），
  正常all-pass run为816 attempts和2,448条request/response/parse证据；不得把2,448称为
  case数。报告状态为`proposal_only`。
- 下一步为Phase 0A-1。开始前仍需owner批准议题/persona文本候选、runtime policy、
  semantic-review policy、Qwen/vLLM候选栈、云端凭据和外部归档位置；不得直接进入
  正式N=1000/T=50主实验。

### Phase 0A-1：2026-09-10 checkpoint

- Phase 0A-1 design approved and independently reviewed。
- 云端只读预检已完成，SSH免密连接通过；观测环境为RTX 5090 32GB、Ubuntu 22.04、
  Python 3.12.3、PyTorch 2.8.0+cu128及150GB数据盘。
- 尚无真实模型响应、运行时冻结、decision record或正式实验。
- Phase 0A-1仍在推进，尚未达到阶段验收边界。

### Phase 0A-1：2026-09-14 本机发布验证

- **状态：** Task 8 complete；Task 9云端预检与10条真实smoke尚未执行。
- 以`672687e765320238bdbeb362b13e66cc43e9bd36`为比较基线，祖先检查通过；
  验证实现HEAD为`277f9ef7159759d8d868ce72b6e99a63d741db63`。
- Phase 0A-1专项为`86 passed in 351.37s`；fresh full为
  `1580 passed, 2 skipped, 1 deselected in 3815.22s`；fresh coverage为同计数，
  `16,991 statements / 2,693 missed / 84% in 10743.04s`。
- Ruff、format（91 files）、pip、baseline/current diff检查均通过；tracked runtime artifact
  扫描无命中。credential正则仅命中既有内部validation/placeholder `token`变量；经源代码与
  baseline diff核验，不是凭据或secret value，Phase 0A-1生产代码未引入凭据赋值。
- 本机发布证据见`logs/2026-09-10-phase0a1-local-release.md`。云服务器继续保持关闭；下一步
  仅在用户重新开机并提供当前SSH端点后执行Task 9的版本化只读preflight，再安装锁定环境、
  下载固定revision并运行10条真实smoke。816-case probe仍受六组exact-hash批准门阻断。

### Phase 0A-1：2026-09-17 真实 smoke 与六组审批提案

- **状态：** 真实10请求smoke通过；816-case尚未获批、尚未执行。
- AutoDL固定Qwen3-8B revision在`d99819a`完成3项transport diagnostics和
  `9 -> stop -> recovery -> 1`共10条唯一首试成功响应；最终smoke hash为
  `4eee264bad889d17582d535dc688310a4b7b665c173c187cd8289fc45b39e53e`，环境锁为
  `c4070d3848da73aa0a16fa1db0c9a4755bdc0238c12b7e84499bbbf00e7d3e91`。服务随后关闭。
- 审批包物化时发现量表锚点此前未进入请求文本；已用TDD补入七个1--7文字锚点及0/10
  端点锚点，逻辑inventory仍为816。
- 六组proposal通过生产loader，精确计数为144/96/576；combined packet hash为
  `57abb85edbb7b1d28949ca523abaef6c4c4639a7744ca3bc7b5f5f57056f44bc`。runtime v2同时
  绑定整次运行的attempt硬上限、累计请求时间与输入/输出token的下一次派发停止阈值、
  以及磁盘安全下限；不会把只能在响应后得知的实际token/耗时误称为单次硬上限。它仍是
  proposal-only，必须获得六组完整hash书面批准后才能建立新环境锁并执行。
- 启动制品已移除generation placeholder例外，直接绑定校准候选`temperature=0.7`、
  `top_p=0.8`、`max_tokens=128`与逐case `requested_seed`；`formal_parameter_authority=false`不变。新执行与恢复
  均在journal绑定前尊重既有terminal，vLLM adapter以单一monotonic deadline覆盖连接、发送、
  response headers与body，trickle response不能绕过overall timeout；terminal/build/seal均拒绝
  尚无durable attempt的indeterminate dispatch intent。
- 详细证据和六组hash见`logs/2026-09-17-phase0a1-smoke-pass-and-approval-packet.md`。

### Phase 0A-1：2026-09-18 首个816-case云端诊断run

- **状态：** 816个唯一case全部执行完成，但因统一测量合同缺陷标记为
  `diagnostic incomplete`，禁止进入候选比较。
- 云端源提交为`34cc5d49e275b26d48bd6eed6ff06a0d8ed19e6c`；environment lock为
  `3ac170ee330bf409c2525aca8c958ce0a6ffc0d7f2a1517b3571ef3770d1d6b9`，run manifest为
  `1811a2e4eedddebdacd4954103d2926e6540c8860265403679481f6787ac05af`。
- durable store包含816个case、1,511次attempt（816 semantic + 695 format repair），
  1,511次transport全部返回response，且每次均有intent/attempt/resolution证据。
- 最终仅142个case parsed，674个`parse_failed`。根因是request未声明独立
  `confidence` JSON整数`1..5`合同，且repair请求未携带首次raw answer作为
  assistant history；这是所有候选共同的工具缺陷，不是议题质量结论。
- run已不可逆标记`incomplete`；terminal hash为
  `78e521c40d638022be429ad6862b29d60740b96f0d186132c6ecf61d54250cd4`，audit report为
  `6e010a4d18d8a825bab01936623410d4a95122eb129812db25ee0110bd399f19`。
- 下一步必须统一修订prompt/repair合同、重新物化并审批六组hash，然后全量重跑816；
  不得只补跑失败case，不得将本诊断run混入新run或正式分析。详细见
  `logs/2026-09-18-phase0a1-first-816-diagnostic-run.md`。

### Phase 0A-1：2026-09-18 confidence contract v2 本机发布

- **状态：** 本机实现、独立复核和发布验证完成；等待最终bundle与六组hash书面批准，
  尚未上传或执行replacement 816。
- 统一response contract明确stance量表、独立confidence `1..5`、理由长度和精确JSON
  字段顺序；`probe-request.v2`把format repair绑定到首个失败semantic attempt、原始响应、
  parse evidence和直接前驱，并在retry/replay/resume/cloud/review全链路fail closed。
- v2 packet保持816个cases（144/96/576），combined hash为
  `3023380d393b4e1a50fbc6ae174281712111f706d2ffa6dce337419c7cf5e5b0`；目标archive为
  `/root/autodl-tmp/agent-ex-phase0a1-probe-816-v2`。v1诊断archive继续不可变且禁止混入。
- focused为`237 passed in 375.98s`；修复两个独立baseline问题后，fresh full为
  `1819 passed, 2 skipped, 1 deselected in 3535.09s`。Ruff lint、pip check和diff check
  通过；本次触及文件format通过，全树仅保留未修改的历史
  `platform/tests/test_phase0a1_cloud_scripts.py`格式基线。
- 规格与代码质量独立复审均`APPROVED`、P0--P3为零。详细提交、六组hash、验证边界和
  后续审批门见`logs/2026-09-18-phase0a1-confidence-contract-revision.md`。

### 2026-09-20：双轨快进切换

- 用户将当前优先目标明确切换为：尽快取得可用于开学汇报的初步真实数据，同时后台
  补齐正式证据链。
- 前台轨复用816条真实校准响应生成`preliminary / diagnostic`摘要，并准备真实Phase 0B
  N=20最短启动路径；后台轨继续797条独立模型盲判，不合并已停止的v1证据。
- 优化后的judge v2绑定提交`bf2f63a3144b4bb9a69337c2cfde159e0ea0cc58`与manifest
  `2cf46ae940d904383881ac74e4cc64d1f9bd3cdd623c67e56c52f04a06a567f1`。该运行保留为
  正式证据轨，不再让其墙钟时间阻塞前台诊断交付。
- 长期目标界面仍保留未完成且暂停的旧目标，系统不允许直接改写未完成目标；本次用户
  恢复与切换指令以本计划、进度记录和实际执行优先级为准，旧目标不得虚假标记完成。
- 前台A已从816-case v2 durable evidence生成不含原文的机器聚合：797 parsed、19
  parse-failed（97.67%），841 responses、0 transport errors、381,664 tokens、墙钟
  1386.418秒，请求延迟p50/p95为0.894/1.173秒。远端聚合文件SHA-256为
  `a099c45e57eaf965e2f9e24abd806fc2836ed9fb5dcd1ae1afeb1e14c4d999d9`，记录hash为
  `fb40c60199398b8f50294ffdc0f792327e15733130f24cf0a14bf339388dc8c1`；详细边界见
  `logs/2026-09-20-preliminary-report-fast-track.md`。
- N=20快线路线已形成并通过独立复核：`N=20,T=2,12 cells`，480个逻辑事件；复用
  现有串行engine和SQLite恢复链，新增honest diagnostic-real vLLM event adapter及
  SQLite v6 diagnostic-v2 schema union。计划明确legacy byte-for-byte replay、端口8000
  服务所有权交接与`preliminary/not_frozen/formal_parameter_authority=false`边界，见
  `docs/superpowers/plans/2026-09-20-phase0b-n20-fast-track.md`。
- 797 judge v2最近只读检查为132/797、无未决dispatch、服务健康。云端程序独立后台运行，
  不依赖本地对话或额度；监控已从20分钟降频为每小时，仅在完成、失败或需处置时通知。
- 开学汇报图表已在额度恢复后从已绑定的脱敏JSON生成并通过独立复核：中文一页brief、
  `parse-success.png`与`runtime-profile.png`位于
  `reports/2026-09-20-phase0a1-preliminary/`。制品未读取raw response，且明确标注为
  `preliminary / diagnostic`，不能据此比较或选择议题。
- Phase 0B快线合同层已落地到`platform/src/agent_ex/phase0b/`：新增
  `DiagnosticAttemptPolicy`、`DiagnosticAdapterBinding`、`DiagnosticRunAuthorization`
  与`DiagnosticTerminalReport`，绑定`N=20,T=2,12 cells`、480事件、最多960次transport、
  Qwen/Qwen3-8B、loopback vLLM端点、B=6/K=3候选值和`not_frozen`边界。合同拒绝
  UNRESOLVED、Git内归档路径、unsafe external archive URI、bool inventory count、
  非canonical cell prefix、complete/incomplete terminal count不一致和递归UNRESOLVED。
- 合同测试文件为`platform/tests/test_phase0b_contracts.py`。本机目标pytest显示32/32
  测试体通过，但pytest进程在收尾阶段未退出，已按节省额度原则停止追查测试运行器挂起；
  代码直接编译通过，`platform/.venv`下Ruff lint与format check通过，合同对象可直接
  创建并生成content-addressed record hash。
- 为节省额度，三路独立复核子代理在workspace credits耗尽后停止，不再立即重启。后续优先
  本地最小验证与可恢复提交；云端797盲判继续独立后台运行，最近只读检查为约192条attempt、
  vLLM服务健康。
- Phase 0B矩阵入口已新增`platform/src/agent_ex/phase0b/matrix.py`：生产代码不导入
  `tests`，而是接收显式传入的候选制品并复用既有严格矩阵验证器，再额外锁死
  `N=20,T=2,12 cells,480 events,960 transport ceiling`。测试覆盖精确inventory、
  authorization artifact hash映射、非N20拒绝和生产代码无测试依赖；合同+矩阵专项为
  `36 passed in 1.27s`，Ruff lint通过。
- Phase 0B真实事件adapter边界已新增`platform/src/agent_ex/phase0b/vllm_event_adapter.py`：
  只接受`http://127.0.0.1:8000/v1/chat/completions`，请求体字段锁死为
  `model/messages/temperature/top_p/max_tokens/seed/chat_template_kwargs`且
  `enable_thinking=false`，未绑定durable pre-dispatch journal时fail closed。响应证据保存
  request id、HTTP状态、headers、provider request id、原始bytes及SHA-256、usage、
  finish reason、latency和typed error；测试覆盖success、非法endpoint、hook-before-send、
  非法generation key、invalid JSON、429、500、OOM、redirect和response size limit。
  相关专项为`48 passed in 1.87s`，Ruff lint与format check通过。
- Phase 0B dispatch journal已补为append-only JSONL安全件：adapter可在HTTP发送前调用
  `record_before_dispatch`写入request hash与request body SHA-256；如果崩溃后只存在intent
  而没有resolution，`assert_no_unresolved_dispatches`会阻止自动重发。新增测试证明intent
  写入发生在fake connection收到任何HTTP请求之前，且resolution写入后未决集合清零。
  合同+矩阵+adapter+journal相关专项为`49 passed in 1.57s`，Ruff lint与format check通过。
- Phase 0B runner/storage最小垂直切片已新增`platform/src/agent_ex/phase0b/run.py`：
  提供`preflight_diagnostic_run`、`Phase0BJsonlStagingStore`和
  `run_fake_diagnostic_slice`。当前实现只作为`preliminary` JSONL staging，不冒充正式
  SQLite v6 diagnostic store；预检绑定authorization、matrix、adapter binding和attempt
  policy hash，拒绝changed authorization hash、重复launch root和未决dispatch。fake slice
  可构造Phase0B vLLM event request、通过dispatch journal写intent/resolution、写入脱敏
  attempt摘要、projection hash和`DiagnosticTerminalReport`，不写入raw prompt/response。
  新增测试`platform/tests/test_phase0b_run.py`。Phase 0B四组专项为`54 passed in 1.85s`；
  Ruff lint与format check均通过。正式SQLite v6 diagnostic schema union、真实event pipeline
  wrapper和云端480-event runner仍待下一步接入。
- Phase 0B真实事件pipeline桥已新增`platform/src/agent_ex/phase0b/pipeline.py`：它仍明确
  `preliminary/not_frozen/formal_parameter_authority=false`，不把真实vLLM响应伪装成
  MockAdapter脚本；当前提供一个最小单Agent事件桥，能从现有`Phase0BVllmEventRequest`
  生成真实请求，接收真实vLLM response中的`choices[0].message.content`，按既有
  `stance/confidence/public_reason`合同解析，并只在解析成功后推进私有状态、feed cursor、
  `next_event_ordinal`和可选公开帖。timeout或malformed JSON仅生成失败evidence，状态、
  cursor和ordinal保持不变。新增测试`platform/tests/test_phase0b_pipeline.py`先RED后GREEN。
  Phase 0B专项（contracts/matrix/vLLM adapter/run/pipeline）为`57 passed in 2.39s`；
  Ruff lint与format check均通过。pytest默认cache目录仍受Windows/OneDrive权限锁影响，
  本次验证使用全新`--basetemp`规避，属于测试临时目录问题而非代码失败。下一步仍需把该
  桥接接入480-event云端runner/外部归档，而不是直接声称正式实验完成。
- 同一桥接模块随后补入`run_diagnostic_vllm_event_loop`，可按显式`publish_flags`连续准备
  和应用多个真实vLLM事件，并在首个未提交事件处停止，保留已成功提交的严格前缀状态。
  新增测试证明三步中第二步malformed JSON时，只保留第一步成功状态且不继续第三步。Phase 0B
  专项更新为`58 passed in 2.44s`，Ruff lint与format check通过。
- Phase 0B runner/export继续补齐12-cell本地全量编排：`run_fake_diagnostic_matrix`
  按canonical cell顺序执行12×40个事件，复用dispatch journal写入intent/resolution，
  生成脱敏attempt JSONL、projection和complete `DiagnosticTerminalReport`；`verify_diagnostic_matrix_run`
  只读durable staging核对exactly 12 cells、480 committed events、480 transports、每cell
  40 attempts、0 unresolved dispatch，并拒绝terminal/projection/hash漂移或raw内容泄露。
- 新增`platform/src/agent_ex/phase0b/report.py`，从已验证staging生成
  `preliminary/not_frozen/formal_parameter_authority=false`的安全JSON摘要，包含completion、
  provider failure、retry、usage totals和per-cell counts，不包含raw prompt、raw response或
  `public_reason`文本。新增测试`platform/tests/test_phase0b_report.py`覆盖完整报告和
  缺失attempt篡改拒绝。Phase 0B专项（contracts/matrix/vLLM adapter/run/pipeline/report）
  为`62 passed in 37.06s`；Ruff lint与format check通过。当前仍未启动云端Phase 0B真实run；
  下一步是把本地runner从fake transport切换到真实event pipeline/adapter、生成审批包，并等待
  judge服务交接后上云执行480-event诊断。
- Phase 0B快线已补入真实adapter形状的480-event runner和审批包helper：
  `run_real_adapter_diagnostic_matrix`按12个canonical cell各40个事件调用
  `Phase0BVllmEventAdapter`同形接口，绑定dispatch journal、pipeline parse/commit evidence、
  projection和terminal report；测试中使用fake adapter，不联系真实vLLM。新增
  `materialize_diagnostic_approval_packet`，输出source commit/dirty/diff hash、authorization hash、
  matrix hash、adapter/policy hash、480/960 inventory、archive root、endpoint、served model和
  `preliminary/diagnostic/not_frozen`标签，不包含raw prompt/response/reason text。Phase 0B专项更新为
  `64 passed in 47.07s`；Ruff lint与format check通过。下一步是生成实际云端授权/审批包并在judge
  服务交接后执行两事件preflight与480-event真实诊断run。

### 2026-09-23：Phase 0B 真实存储前缀接续

- 云端 Phase 0A-1 judge v2 已确认客户端退出，797条 attempt、dispatch、reconciliation 齐全；最终 projection 文件 SHA-256 为 `6c65dbc6b7d27f709821b8da1751b5eca7b18b6e377efa7b66fde7cae898fd0e`。vLLM仍监听端口8000，尚未做 Phase 0B 服务交接。
- 审计发现已提交的 `run_real_adapter_diagnostic_matrix` 仍以每cell单个占位Agent连续执行40次，不能作为真实N=20网络实验。当前未提交的materializer已构造12-cell、每cell20 Agent/40事件和独立SQLite v6 round-0 store；其本地专项通过，仍待与runner连接。
- 提交 `3f8bbf7` 增加 SQLite v6 diagnostic-v2 的请求/策略/绑定及真实响应持久化前缀，保持已有mock行的旧schema读取；新增prepared、tamper、post-response重开测试。`test_storage.py`与新增专项为`220 passed, 2 skipped`，Ruff lint/format和diff check通过。该提交只覆盖发送前和收到响应后的可恢复前缀，**尚未**实现真实响应解析后的原子终态提交、checkpoint/replay完整验证或N=20 runner接线。
- 下一步先把diagnostic解析/终态证据、SQLite事务提交及重开校验补齐，并做旧mock字节级回归；然后接入materialized schedule/persona/E0-E1-E2 feed，验证两事件真实preflight，再申请/生成精确诊断授权包和云端服务交接。不得将现有单Agent占位runner产物视为网络实验结果。
- 本轮提交 `2279251` 新增与真实 vLLM 响应 hash、原始body SHA、topic及parser limits绑定的独立 `DiagnosticParseEvidence`，不借用mock parse schema。提交 `267e4b8` 增加 SQLite v6 真实响应成功终态的原子 parse+attempt 写入、重开回放和跨variant拒绝；篡改provider绑定先拒绝且不产生部分终态。存储/证据专项 `249 passed, 2 skipped`，Ruff与diff check通过；仅有Windows/OneDrive pytest缓存目录权限警告。
- 后续专项又确认已成功的真实响应可以经既有 `commit_success` 推进私有状态和feed cursor，并在重开后保持ordinal=1；测试仍使用明确标记的合成候选状态。此里程碑**尚未**覆盖 diagnostic 失败终态、公开状态分支、完整checkpoint/resume、N=20真实事件循环、Linux复验或云端两事件preflight；AutoDL服务保持原状，未上传、未启动新实验。下一步按此顺序接线并做最小复验，绝不能把当前单事件测试等同于480-event实验完成。
- 提交 `235125b` 为diagnostic-v2补上失败解析的原子终态写入与重开校验，测试证明畸形真实响应留下FAILED attempt和failure evidence，而私有状态、feed cursor、ordinal不前进。存储相关专项`223 passed, 2 skipped`。
- 提交 `a821dd7` 把原有社会曝光/记忆/persona/prompt构造提取成无发送的共享事件输入步骤；新 `phase0b/real_pipeline.py` 将冻结N=20排程对应的Agent生成真实vLLM请求与diagnostic-v2证据。两条真实响应形状的测试依次提交不同Agent、第二条经过fake HTTP dispatch journal，证明不再是单Agent占位循环。同期修正IN_PROGRESS先于实际网络发送的时间戳先后约束。专项`91 passed`。
- 提交 `b10c589` 增加单格40事件及12格480事件的一次性真实事件编排原语；假HTTP全量跑通并产出24个扫次checkpoint，关闭重开12个SQLite后只读核对480个成功事件、请求/响应/parse/dispatch exact cover。过程中发现真实attempt须保留topic id/hash在完整解析记录中，否则社会候选帖的因果校验会拒绝后续事件，现已修复。相关专项`80 passed`，全矩阵专测另`1 passed`。**以上均为本地假HTTP响应，不是云端真实Qwen实验数据。**
- 尚需失败/未决dispatch恢复合同、真实SQLite脱敏报告、Linux验证、精确授权哈希与服务交接。AutoDL在本轮未使用；旧vLLM服务保持原状。云端预检和480真实请求未启动。

### 2026-09-24：Phase 0B 服务启动身份桥接

- 用户批准独立预启动意向方案。确认现有服务生命周期在启动前要求 `manifest_hash`，但 Phase 0B 授权依赖启动后才出现的服务身份；不能把最终授权哈希作为启动输入，也不能复用旧 judge 身份。
- 新增 `docs/superpowers/specs/2026-09-24-phase0b-launch-identity-bridge.md` 并修订 Phase 0B 快线计划的云端顺序：先预启动意向哈希，再完成 judge 服务交接，生成新服务身份，派生最终授权/矩阵并再次核对审批，最后独立两事件预检和 480 事件运行。
- 本轮云端只读检查：SSH 可达、judge store 在、旧 vLLM 仍监听 `127.0.0.1:8000`、`/root/autodl-tmp` 约剩 90 GB；未停止、重启或启动任何云端进程。真实 N=20 实验仍未启动。
- 提交 `464a8fc` 实现独立 `Phase0BLaunchIntent`，在服务启动前绑定source bundle、显式候选配置/11类工件、模型/环境/服务配置与两个互不重叠外部归档根；最终授权与服务启动身份不能提前进入此记录。专项测试 fresh 18 passed，Ruff/format/diff check通过，规格与质量复核均可继续。首次复验尝试关闭pytest cache plugin触发项目配置 `cache_dir` unknown，改用独立临时cache后成功；云URI百分号编码别名是非阻断后续加固项，当前限定本地 `/root/autodl-tmp` 归档。
- 提交 `ddb434f` 实现显式 `Phase0BCandidateConfig` 与跨进程冷重建，不内置任何候选数值；质量审查发现可接受 topic 指向与实际 round-0 理由库不同的两份独立有效制品。提交 `b9a95cc` 以先RED后GREEN的回归测试补上跨制品 ID 校验；fresh 24项合同专项、Ruff/format/diff check通过，质量复核确认无剩余重要问题。尚无云端请求。
- 本轮在本地新增 Phase 0B 服务身份桥合同：只接收已核验的 797 项终态 judge projection 哈希、旧服务启动/停止证据、真实 preliminary environment inspection、新服务 start-first 身份及预先绑定的服务配置；检查旧进程退出、8000端口释放、GPU空观测哈希、新服务 manifest/inspection/PID/命令哈希一致性。先见缺模块 RED，再见命令身份与GPU空观测的两个针对性 RED，最终桥接+意向+候选配置专项 35 passed；Ruff lint 与 git diff check通过。桥接记录仍需在云端用真实证据实例化；本轮未停止旧服务、未上传、未发送 Phase 0B 模型请求。
- 用户确认原 AutoDL 云服务器已到期。本地继续补齐两事件真实适配器前缀的只读验收：`verify_two_event_diagnostic_prefix` 在不联系模型的情况下重放存储和dispatch证据，只接受精确2条成功提交、2次transport，输出绑定授权/adapter/服务启动身份及两个已提交事件哈希的脱敏 `not_frozen` 摘要。先见缺函数RED，再见缺preliminary标签RED；恢复专项在独立系统临时目录为13 passed。首次未指定`--basetemp`时被OneDrive遗留`.pytest-tmp`权限锁拦截，未进入测试体；已改用全新系统临时目录，未删除旧目录。本轮未连接到期服务器，也未产生真实Phase0B数据；完整云端预检仍缺归档路径与最终授权/启动入口交叉绑定。
