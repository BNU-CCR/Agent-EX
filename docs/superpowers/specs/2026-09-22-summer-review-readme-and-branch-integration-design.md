---
status: proposed
authority: documentation and repository-integration design; subordinate to the Paper 1 specification and evidence chains
date: 2026-09-22
scope: README rewrite, summer progress review, and branch-consolidation procedure
---

# 暑期项目复盘、README 重写与分支整合设计

## 目标

在不改写研究规范或证据链的前提下，交付两份互补文档，并把暑期工作的完整 Git 历史安全整合回 `main`：

1. 根目录 `README.md` 成为当前项目入口，而不是历史 pilot 使用说明的堆叠；
2. `docs/2026-09-22-summer-progress-review.md` 成为周四组会汇报底稿和后续网页端 GPT 的完整上下文；
3. `main` 以 fast-forward 方式吸收一个经过验证并固定 OID 的 `codex/paper1-phase0` 已提交快照，保留逐提交历史；
4. 合并完成并核验远端后，再删除已经冗余的远端工作分支。

## 权威来源与事实边界

文档只采用可复核来源：Git 提交历史、`AGENTS.md`、`task_plan.md`、`progress.md`、`findings.md`、07-29 Phase 3A 交接、项目 overview、已批准规格/计划，以及云端最终投影和哈希。Codex-mem 服务当前未运行，因此不把不可访问的持久记忆作为事实来源。

所有状态必须明确区分：

- 已提交、已测试且独立复核；
- 已实现但尚未提交或尚待 Linux/独立复核；
- 已完成真实云端运行；
- 仍属于 preliminary / diagnostic / not_frozen；
- 尚未开始的正式主实验。

不得把 N=20 诊断称作正式主实验，不得把单代理 transport smoke 称作真实 20-agent dynamics，不得把未决研究参数写成已冻结参数。

## README 信息架构

README 整体重写为简洁的项目入口，包含：

1. 项目定位与当前一句话状态；
2. Paper 1 核心研究问题和固定 2×2×3 矩阵；
3. 2026-09-22 的真实进度仪表盘；
4. 已完成平台能力与证据链；
5. 仓库目录和权威文档读取顺序；
6. 本地开发、测试与云端执行的安全入口；
7. 当前阻塞项、接下来一周计划及“何时算正式开跑”；
8. 历史 pilot 的只读定位和暑期复盘链接。

旧 README 中仍有价值的历史说明不删除事实本身，而是压缩成归档入口；过时的直接运行命令不继续放在首页冒充当前主流程。

## 暑期全景复盘信息架构

`docs/2026-09-22-summer-progress-review.md` 采用三层结构：

### 第一层：组会一页摘要

- 暑期目标、已经做成什么、现在卡在哪里；
- 可展示的量化事实和真实云端里程碑；
- 周四可讲的核心结论与未来七天计划。

### 第二层：完整技术复盘

- 7月研究收敛与平台规格；
- Phase 3A/4A/4B 各阶段演进；
- domain、artifact、network、schedule、state/feed、prompt、SQLite、checkpoint/recovery、严格串行 engine 与证据链；
- Phase 0A-0、Phase 0A-1 和云端 Qwen/vLLM 部署；
- 797 条盲判最终完成、终态重放验证和哈希；
- 当前 Phase 0B 的真实完成边界；
- 速度问题、额度中断、AutoDL资源变化、错误 runner 识别等关键教训；
- 尚未完成的 N=20 真实 dynamics、参数冻结和正式 N=1000 主实验。

### 第三层：GPT 接续附录

- 当前分支、worktree、关键提交和未提交文件；
- 规范链和证据链读取顺序；
- 不得违反的研究红线；
- 云端位置仅记录非敏感定位和哈希，不记录密钥、密码或原始响应；
- 下一代理应执行的最小步骤和禁止重复的工作。

该附录必须是独立标记的 **Web-safe handoff**。它只能包含仓库相对路径、提交 ID、记录哈希和不透明归档 ID；不得包含用户名、本机绝对路径、SSH 主机/端口、密钥文件名、凭据、原始数据目录或可直接操作云端的命令。私人操作定位保留在不提交、不共享的本地记录中。

## 分支整合设计

初始审计已验证：`main` 与 `codex/paper1-phase4b` 均位于
`092bcac3f6ac14f14b870cf73cc6d2063faa983d`；在本设计提交之前，Phase 0 的
`f60ce2c2e105e43811e29a34ad495a57bd1a967b` 比 main 多 167 个提交。本设计提交
`003c7ca` 后计数自然增加，因此任何合并都不得依赖文档中的静态数量，而应在执行前重新固定
`PRE_MERGE_MAIN` 和 `SOURCE_TIP`。main 目前是 Phase 0 的严格祖先，首选 fast-forward，
不做 squash、rebase 或历史改写。

当前 Phase 0 worktree 还包含与本次文档任务无关、尚未提交的安全标签导出器和 N=20
materializer，以及大量测试临时目录和 bundle。这些内容不得被本次文档任务强制完成、丢弃或
混入提交。文档任务只允许提交明确列出的 README、暑期复盘、设计/计划和必要的进度索引；
实现改动留在原 worktree，另立经过批准的工作包完成、复核和提交。

整合顺序：

1. 盘点 `git status --porcelain=v1 --untracked-files=all`、ignored 文件和所有 worktree；保存但不修改无关实现、bundle、虚拟环境和测试目录；
2. 只用路径白名单暂存本次 README、暑期复盘、设计/计划和必要的进度索引；禁止 `git add .`、`git clean` 或批量移动；
3. 核对 staged diff、文档链接、敏感信息扫描和量化事实来源后提交文档；
4. 记录 `PRE_MERGE_MAIN=$(git rev-parse main)` 与 `SOURCE_TIP=$(git rev-parse codex/paper1-phase0)`；该 SOURCE_TIP 只代表已提交快照，不包含仍留在 worktree 的实现；
5. 更新远端引用后要求本地 `main == origin/main`、`origin/main` 是固定 SOURCE_TIP 的祖先、且 `codex/paper1-phase0 == SOURCE_TIP`；任一 OID 变化均停止并重新审查；
6. 在 main worktree 执行 `git merge --ff-only "$SOURCE_TIP"`；
7. 验证 `main == SOURCE_TIP`、`PRE_MERGE_MAIN` 是 main 的祖先、`PRE_MERGE_MAIN..main` 的提交数量与清单、关键文件树和文档链接；
8. 不使用 force 推送 main，并在推送后核对 `origin/main == SOURCE_TIP`；
9. 删除每个远端分支前，固定其 tip 并证明该 tip 是已验证 `origin/main` 的祖先；明确区分远端 ref、同名本地 ref 和关联 worktree；
10. `codex/paper1-phase4b` 可在上述祖先证明和 worktree保留检查后删除远端 ref；`codex/paper1-phase0` 在未提交实现完成独立处置、worktree解除且无需回退前不得删除；
11. 本地过期 worktree、旧本地分支和损坏的 Codex checkpoint ref 另立清理设计，不与远端合并或文档任务混做。

任何一步发现远端 main 新增提交、固定 source tip 变化、staged allowlist 外出现文件、验证失败或提交关系不再可 fast-forward，立即停止，不自动制造 merge commit。Phase 0 worktree 可以因被明确保留的实现改动而保持 dirty；这本身不是文档快照 fast-forward 的阻断，但会阻止删除该 worktree 和 Phase 0 分支。

## Phase 0A-1 终态证据门

README 和暑期复盘只有在以下证据同时记录时才能写“797 条完成”：

- 2026-09-22（Asia/Shanghai）对云端 durable store 执行 `JudgeRunStore.open` 完整重放；
- `verify_terminal_projection()` 成功生成终态投影；
- exactly 797 item states、797 coded、0 unresolved intent；
- terminal projection record hash：
  `b09e0a242018c1bc48c00fb0af0f87740e8c420080e73e0411de095db761873d`；
- 终态写入前最后一份 projection 文件 SHA-256：
  `6c65dbc6b7d27f709821b8da1751b5eca7b18b6e377efa7b66fde7cae898fd0e`。

文档同时说明：仓库中较早提交的 609/797 快照是当时的阶段证据，并不与后续云端终态冲突；终态脱敏报告仍须经过批准的安全导出链，不能根据完成计数虚构语义结果。

## 验收标准

- README 能让新成员在五分钟内理解项目、当前状态和下一步；
- 暑期复盘能直接作为组会底稿，并让没有聊天历史的 GPT 正确接续；
- 所有量化结论均能追溯到提交、日志、测试或云端哈希；
- 文档不泄露密钥、密码、原始响应或未批准的研究结果；
- `main` 包含固定 SOURCE_TIP 之前 Phase 0 的完整逐提交历史，且保留未提交实现的原 worktree；
- 删除远端分支前已有可验证的 main 远端副本；
- 分支整合不使用 squash、rebase、force-push 或非 fast-forward 覆盖。
- staged diff 只包含明确路径白名单，且 Web-safe handoff 不含私人操作定位。
