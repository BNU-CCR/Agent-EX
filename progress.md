# 进度日志

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
  - 确认 `platform/` 尚不存在，当前运行依赖未锁定，pilot-3.0 Notebook 是实际实现。
  - 写入分阶段、逐模块、测试先行的实施计划。
  - 第一轮计划审阅发现官方API发现滞后、执行参数库存不全和大规模矩阵编排缺失。
  - 已增加 Phase 0B 官方API/依赖 gate、完整 unresolved inventory 与 formal-required 校验、registry/worker/矩阵审计/盲态扩样 orchestration 阶段。
  - 第二轮独立计划审阅结果为 `Approved`。
  - 代码实施目前仅被 worktree 位置选择阻塞；未修改 pilot 或创建 platform。
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
| 我在哪里？ | 阶段 3：书面规格审阅 |
| 我要去哪里？ | 知识归档 → Paper 1 协议 → 平台实现 → 正式实验 |
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
