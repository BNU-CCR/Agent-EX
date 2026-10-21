# Stage-A真实操纵检验：完成、备份与判定

日期：2026-10-21（北京时间）。这是独立身份操纵检验，不是六格网络pilot或正式主实验。

## 执行事实

- 实际源：干净8d0682a002be931e7f36dccda9c9460d26afbec6；新机52439。
- 模型Qwen3-8B BF16/non-thinking，revision b968826d9c46dd6066d109eabc6255188de91218。
- 原启动失败证据保留；用户补批新launch hash后仅新增原生采样开关，未改研究参数。
- 服务PID9943在16:20:03启动；实际cmdline、环境及models endpoint通过核验。
- 独立预检2/2 VALID，运行/冷验证约1.934秒；不计入240。
- 预检完整原始证据本地备份/包与文件SHA通过后，16:23:09启动240项。
- Stage-A为30 case×4配对×2重复；240/240 VALID、COMPLETE、480 journal transitions，
  无saved response pending。运行、终态验证及打包共151.340秒，约2分31秒。
  不将这个时长直接外推到六格多事件实验，也不声称它是纯模型解码耗时。

## 冻结判据（必须三项同时满足）

| 判据 | 本次结果 | 是否满足 |
|---|---|---|
| case等权primary mean > 0 | 0.6083333333 | 是 |
| 六层内各抽5case、10,000次bootstrap percentile 95%CI不跨0 | [0.5333333333, 0.6916666667] | 是 |
| d[c]>0至少18/30（60%） | 15/30（50%） | 否 |

结论：完整执行，但未通过预冻结的三项联合信号标准。不能事后把60%改为50%，
不能只凭正均值/正CI宣布操纵成功。代码signal_status=NO_SIGNAL是该联合规则的标签，
不应转述成“没有任何效应”或“证明零效应”。15个case为正，其余15为0，无负case。

描述性分层（不增加pass/fail标准）：distance1平均0；distance2平均0.325；
distance3平均1.5。upward平均0.4167、downward平均0.8。
小型敏感度benchmark不代表正式初始stance分布；case也不等于30个统计独立argument。
confidence仅描述，不能计算pre_confidence=null的confidence change。

## 终态身份与备份

- runtime canonical hash：7b907741fc7c2065435539bb1d07c3a958ab915ea784b7ad67910164ba98c5cf。
- Stage-A packet hash：1ee01aeee8fed0162d1f47b26652f8d80c363df960630fff81d642c8d1d9d328。
- terminal journal tail：914857264a46ba3c6384da57eb769f7f318e89b2b0cf03f2613757bf293f9fa7。
- 脱敏报告stage-a-verified-report.json文件SHA256：
  81ce61cd06caf3db184095ddf2b2d4796736dc8febaa10f2ceaf0fa7142ed80f。
- 完整原始tar（含SQLite响应/intent/result与批准/request/runtime/实际服务证据）585,565字节：
  C:/Users/Bai Yuexi/Agent-EX-evidence/2026-10-21/stage-a-evidence.tar.gz。
- 本地远端包SHA256一致：ddaf37487812f6f11cf2fdb85c90ee18ff801b32b42c2bae14f66910ba5f0211。
- 包内2份run文件（SQLite与0字节持久锁）逐文件SHA/大小/数量均符合清单；
  报告、清单、controller result也独立核对本地/远端文件SHA。备份16:26:14北京时间完成。
- 原始回复未在对话中读取或输出，原始SQLite/tar不进入Git。此目录只保留安全汇总、
  请求包/renderer、runtime、hash与归档定位；不把完整权重下载到本地。

报告顶层transport_evidence_verified=true来自存储冷重放。嵌套analysis为纯数学函数输出，
其transport_evidence_verified=false只声明它自身不做传输核验，不是顶层验收失败。

## 下一步及边界

完整有效Stage-A未满足三项标准，满足预冻结Stage-B的研究激活条件，但不等于运行授权。
下一步按已冻结stance-neutral stable-group framing准备独立Stage-B renderer/request绑定，
保持原case/采样/seed/统计规则，不临时优化prompt。当前8d运行入口明确禁止Stage-B，
不能伪装成stage-a模式发送；需最小实现/专项验收并列出新source/packet/launch绑定后再请批准。
不自动进入Stage-B，不先跑六格pilot，不修改正式SIS_*未决项。

Stage-A本地/云端后台控制均已正常终止；服务仍健康保留，不因数学NO_SIGNAL停服务或改参数。
30分钟部署心跳到此实质里程碑暂停，避免无任务轮询；长期目标仍保留，未标记完成。
