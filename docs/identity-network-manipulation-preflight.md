# Stage-A 操纵检验预检组合

`identity_network.preflight.preflight_manipulation` 是只读组合入口，尚非发送CLI。
它接受完整typed authorization/receipt/evidence、实际bundle文件和精确runtime仓库root。

顺序：完整来源/规则/bridge/scoped dispatch receipt重放 → 实际bundle bytes、pack与
reachable tree核验 → 实际clean checkout的HEAD/tree → 新鲜Linux服务身份与health
前后观察 → 再查checkout。审批错误或源码不符时不能到达HTTP。
不接受调用方提供的缓存health/source报告冒充现场观察。

runtime检查拒绝assume-unchanged与skip-worktree隐藏标志。Git读取隔离全局/环境
配置，运行仓库应将必要换行设置明确放在local config；不得关闭干净源码检查来
容忍环境差异。实际Git测试仓库固定local core.autocrlf=false以保证跨平台含义。

仅返回preliminary、formal_parameter_authority=false、dispatch_authorized=false的
哈希观察记录；不创建输出目录、不写发送intent、不调用completion、不重试/启动服务。
现有v1四配对合同可用于组合测试，不能当作用户240请求候选已经实现。

尚未证明：已加载Python模块来自所查checkout、ignored文件不影响执行、目录不会被
并发替换、环境观察是当前真值、检查后服务持续不变。目录、Git及安装的核验程序是
可信边界；此函数不是原子lease或恶意主机防护。最终runner应从批准checkout的全新
Python进程启动，核对执行origin、fresh archive和durable dispatch，并在发送前复查。

本地验证使用真实小Git bundle/checkout和全typed合同，procfs/HTTP为合成模拟。
不构成AutoDL现场验收，暂不需要开启服务器。下一步需接独立证据读取与运行入口，
再按已确认240设计准备实际cases/重复/判定；未决研究参数不得默认填入。
