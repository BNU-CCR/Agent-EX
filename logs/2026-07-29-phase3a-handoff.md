---
status: active handoff
authority: next-session recovery entry; subordinate to frozen protocol and current Git state
supersedes: none
last-verified: 2026-07-29
---

# 2026-07-29｜Phase 3A 代码位置、进展与下一步交接

## 当前代码位置

本轮实现最初在隔离 Git worktree 中完成，随后已快进合并到 OneDrive 主工作区：

- 主工作区：`E:\OneDrive\Claude Code\Agent ex`
- 主工作区分支：`main`
- Phase 3A worktree：`C:\Users\57220\.codex\visualizations\2026\07\14\019f5e98-1f87-7310-b4f2-8f0b85f37926\worktrees\Agent ex\codex\paper1-platform`
- 来源分支：`codex/paper1-platform`
- Phase 3A 实现提交：`7e5731b0263a08338c37fbf441b676fb76e1d005`
- Phase 3A 交接提交：`d03c6b2`

主目录现在已经包含 `platform/`。合并前主目录 README 删除“课程论文提交前”旧清单
的意图已保留；本地 `.codex/`、`.pytest-tmp/`、虚拟环境和缓存均不进入 Git。

恢复时优先从主目录执行：

```powershell
Set-Location 'E:\OneDrive\Claude Code\Agent ex'
git status --short --branch
git log -1 --oneline
```

预期看到 `main`、`platform/`，以及 `d03c6b2` 之后的整合提交。隔离 worktree
暂时保留用于追溯，但换机恢复应以 GitHub 上的 `main` 为准，不依赖其本机绝对路径。

## 当前已经完成

1. Paper 1 已收束为 `identity 2 × continuity 2 × exposure 3` 的12-cell设计，
   正式目标为 N=1000、T=50、首批10个 matched seeds，盲态规则最多扩至20个。
2. 历史 `pilot-1.0/2.0/3.0` 原地冻结，只作机制线索和回归证据。
3. 建立正式 `platform/` package、Python 3.12 开发环境与17项依赖锁。
4. 完成 draft/formal 协议 gate、schema 镜像、decision value hash 和
   human-summary 同步。
5. 完成 Agent/Opinion/Exposure/Event/Attempt、运行身份、FrozenSchedule、
   RunManifest、恢复游标、证据图和严格 JSON round-trip。
6. 修复旧 wheel 污染，root/platform 两入口均加载当前源码；wheel 隔离 smoke 通过。
7. 最终结果为 `353 passed`；Ruff、format、pip check、diff check 和三路独立终审通过。

这表示“正式实验平台的协议与证据地基完成”，不表示真实模型实验已经运行。

## 本轮主要修改的文件

### 核心代码

- `platform/src/agent_ex/domain.py`：领域记录、分层 ID、FrozenSchedule、
  RunManifest、恢复与证据图。
- `platform/src/agent_ex/protocol.py`：协议加载、schema/formal gate、decision
  value binding 和 Unicode placeholder 防绕过。
- `platform/src/agent_ex/validation.py`：decision records、research-QA owner、
  human protocol summary 的严格解析与同步。
- `platform/src/agent_ex/__init__.py`：公开 API 导出。

### 协议、环境与测试

- `platform/protocols/paper1.schema.json`
- `platform/src/agent_ex/schemas/paper1.schema.json`
- `platform/pyproject.toml`
- `platform/tests/test_domain.py`
- `platform/tests/test_protocol.py`
- `platform/tests/test_installation.py`
- `.gitignore`

### 研究和项目文档

- `docs/paper1-protocol.md`
- `docs/research-qa.md`
- `docs/decisions.md`
- `docs/reproducibility.md`
- `docs/superpowers/plans/2026-07-14-paper1-platform-implementation-plan.md`
- `task_plan.md`
- `progress.md`
- `logs/2026-07-16-phase3a-wip.md`
- `logs/2026-07-29-phase3a-complete.md`
- 本交接文件

## 正式继续实验前必须完成

### A. 先冻结 Phase 4 最小研究决策

优先处理 `docs/research-qa.md` 中与 Phase 4 直接相关的项目：

- population 来源、字段、平衡和 exact-N 算法；
- 初始立场与初始理由来源；
- 四个 persona 模板制品及 hash；
- WS 的 `k`、`p`、方向和连通规则；
- 全体或子集激活及每轮激活数；
- social exposure 数量、最大邻居数和 memory window。

这些选择必须经用户/方法会审写入 decision records，coder 不能填默认值。

### B. Phase 4 模块实现顺序

1. `population.py`：确定性 population、exact N、跨 cell 匹配。
2. `persona.py`：四组合模板引用、禁止差异检查和 hash。
3. `network.py`：固定 WS 图、图 hash、非法图 fail-fast。
4. `exposure.py`：self-history、WS neighbor、degree-matched shuffled exposure。
5. mock fixtures：N=20/100/1000 的确定性生成和不变量测试。
6. `prompt.py`、parser、mock adapter。
7. 同步 engine、event store、checkpoint 持久化和恢复执行。

### C. 真实模型与正式运行 gate

在真实 adapter 前完成 Qwen3-8B revision、tokenizer/chat template、vLLM
版本/image、generation 参数、request seed、timeout/retry 的 artifact 与 runtime
smoke。随后按 N=20→100→200/500→1000 分级验证吞吐、失败率、存储和成本。

所有 formal-required 决策、指标公式、排除政策、seed、归档 URI 和模型运行身份冻结
之前，不得启动 N=1000 正式矩阵。若全体 Agent 每轮生成一次，首10 seeds 的上限约
为 `1000 × 50 × 12 × 10 = 6,000,000` 次生成，必须先完成云端容量和成本评估。

## 下次会话的第一个可执行工作包

先做“Phase 4 决策冻结工作坊 + population/persona/network/exposure 的 TDD
实现”，继续使用 mock，不连接真实模型。完成后再进入 prompt、adapter 与 engine。
