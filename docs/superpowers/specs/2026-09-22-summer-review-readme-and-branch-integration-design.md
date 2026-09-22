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
3. `main` 最终以 fast-forward 方式吸收 `codex/paper1-phase0` 的全部提交，保留逐提交历史；
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

## 分支整合设计

已验证：`main` 与 `codex/paper1-phase4b` 均位于 `092bcac`；`main` 是 `codex/paper1-phase0` 的严格祖先，Phase 0 分支比 main 多 167 个提交。因此首选 fast-forward，不做 squash、rebase 或历史改写。

整合顺序：

1. 在 `codex/paper1-phase0` 收口当前未提交的安全标签导出器、N=20 materializer 和本次文档；
2. 对各自专项测试、Linux-only 安全测试和文档链接进行验证；
3. 提交所有已验证改动，确保 tracked tree clean；
4. 更新远端引用并确认 `origin/main` 仍是本地 main 的同一祖先；
5. 在 main worktree 执行 `git merge --ff-only codex/paper1-phase0`；
6. 验证提交数量、关键文件、测试证据和 `git diff main^..main` 范围；
7. 推送 `main`；
8. 远端 main 核验成功后，删除冗余 `codex/paper1-phase4b`；
9. Phase 0 分支在确认无需回退且相关 worktree解除后再删除；
10. 本地过期 worktree、旧本地分支和损坏的 Codex checkpoint ref 单独审计清理，不与远端合并混做。

任何一步发现远端 main 新增提交、tracked worktree 脏、测试失败或提交关系不再可 fast-forward，立即停止，不自动制造 merge commit。

## 验收标准

- README 能让新成员在五分钟内理解项目、当前状态和下一步；
- 暑期复盘能直接作为组会底稿，并让没有聊天历史的 GPT 正确接续；
- 所有量化结论均能追溯到提交、日志、测试或云端哈希；
- 文档不泄露密钥、密码、原始响应或未批准的研究结果；
- `main` 最终包含 Phase 0 的完整逐提交历史；
- 删除远端分支前已有可验证的 main 远端副本；
- 分支整合不使用 squash、rebase、force-push 或非 fast-forward 覆盖。
