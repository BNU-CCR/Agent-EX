# 新主研究本地准备交接（2026-10-01）

## 历史与研究边界

- 旧源码含完整 Git 父链、main 文档及未提交导出器的原字节归档，已保存到远端
  `codex/legacy-experiment-20261001` 和 `legacy-2x2x3-2026-10-01`。
- 新主分支为 `codex/social-identity-network-2x3`。main 与原 phase0 工作树未被
  覆盖，也未删除任何历史分支。旧模型、运行器、存储、解析器与协议不在本次改动中。
- 原始云端响应、SQLite、模型权重仍属于旧实例/数据归档，Git 快照不是数据盘备份。
- 用户批准的新设计与实现状态必须区分：已有校准与盲判不是新六条件的实证结果。

## 本次准备模块

`platform/src/agent_ex/identity_network/` 是现有平台的增量包，不是复制 platform1。

- `contracts.py`：六个 SIS cell 身份，拒绝身份与因子不匹配。
- `groups.py`：同一初始立场层内 Blue/Green 精确各半；独立 RNG、不可变制品、
  确定性重放与一次验证后的 O(1) 查找。奇数层人数拒绝，不修改原初始立场。
- `prompts.py`：共用基础控制和输入结构；blind 隐藏 self/source 分组元数据，
  salient 显示。完整原帖文本原样保留，不删改自然产生的群组词。保存输入侧
  精确 messages、pre-state、来源组和局部立场上下文。没有一致性指令或迎合分类器。
- `networks.py`：明确 swap target/budget 的连通 double-edge swap；保持每个节点
  度数，允许与原 WS 仍有部分边重合，预算失败不产生制品。记录 clustering、
  average path length、degree sequence、connectivity，验证绑定 matched seed 并重放。
- `manipulation.py`：每个显式 fixture 形成 receiver Blue/Green × source same/other
  四个配对刺激，共用内容、来源、先验状态和采样 seed；自包含基础 messages/evidence。
  固定两阶段，第二阶段只接受 report/criteria 哈希及研究者 no_signal receipt。
  receipt 仅记录归因，**不代表已验证这些报告或获得云端 dispatch 授权**。

制品明确为 `preliminary / not_frozen / formal_parameter_authority=false`。
仅扩展三个新 RNG namespace，不改旧 namespace 的派生算法。

## 已审阅和测试

规格经独立复核批准。实现复核发现匿名来源别名可泄露分组，已通过回归测试修复：
只允许中性 member-number 语法，同一 prompt 内 source 与别名一一对应，同源多帖保留。
跨事件别名固定且不按分组分配，需要后续 population/materializer 显式冻结和验证。

本地测试使用新工作树 PYTHONPATH 和 phase0 的 Python 3.12 测试环境，临时目录
放在系统 TEMP；只跑新增模块与 domain/persona/network/prompt/candidate 专项回归。
最终计数及提交身份记录在本次 progress 条目，不将专项通过描述为全仓通过。

## 下一步：接入运行，而不是继续旧 480-event 主矩阵

1. 基于共享 event-input、vLLM adapter 与 SQLite，增加独立 SIS schema/record union；
   不把六条件送进旧十二条件验证器，不弱化旧 frozen contract。
2. population/materializer 冻结共同 persona、K/B、memory rule、neutral aliases，
   和外生 publication ledger；六条件共享输入，仅改变 salience/network。
3. 提交侧 evidence 完成 post-state/reason/confidence、实际 public output、
   publish flag、prompt/attempt/event/checkpoint 的绑定。当前模块只有输入准备，
   **尚不能证明执行后全链可重建**。
4. 用假 HTTP 测完六条件小 run、失败不更新状态、retry/resume 与只读 verify/report，
   不复制旧主循环，不全仓反复跑。
5. 确认 `SIS_MC_SAMPLE`、`SIS_MC_CRITERIA` 与 `SIS_MODEL_RUNTIME`，
   冻结第一阶段检查配置；再请用户开启云端、验证现有环境/迁移证据、执行检查。
6. 只在预先规定的 no_signal 条件下进入一次固定 framing 第二阶段；不得 prompt 搜索。
7. 用 `SIS_PILOT_CONFIG` 明确批准小规模六条件 pilot。正式 N/T/seeds/primary outcome
   及推断计划仍用 SIS 未决 ID，不能继承旧研究的 N=1000/T=50。

本次未连接 AutoDL、未占用旧服务、未发送模型请求、未创造模拟实证数据。
