---
status: checkpoint
date: 2026-07-29
branch: codex/paper1-phase4b
baseline: 49f8047
phase: Phase 4B-2 in_progress / unreviewed
---

# Phase 4B-2 阶段检查点

本检查点只用于在用户额度不足时安全保存当前工作，**不表示 Phase 4B-2 已完成**。
4B-2 尚未通过独立规格审查和代码质量审查，不得据此进入 4B-3。

## 已实现边界

- 将事件身份迁移为由 `event_ordinal` 唯一标识，支持同一 Agent 在同一 sweep
  内被重复激活。
- 将冻结 schedule 迁移为 v2 槽位结构，显式记录 sweep、draw、Agent、
  publish flag 与算法版本。
- 将领域证据链迁移到 ordinal 语义；恢复游标使用
  `next_event_ordinal` 与当前 `event_id`。
- Exposure 基础允许空社会 feed、同发送者多条公开帖子，并只要求来源事件
  ordinal 更早。
- 新增版本化 `ArtifactEnvelope`、`RNGProvenance` 与确定性 seed 派生；
  event 级 RNG 必须绑定 `event_ordinal`，重试不得用 `attempt_index`
  推进 model seed。
- 已移除旧同步 engine / schedule v1 / round cursor / 同步 `AgentState`
  兼容契约；这符合用户已批准的破坏性迁移边界，不提供旧接口兼容层。

实现者最近一次报告为 `177 passed`、总覆盖率 `84%`。测试总数相对 4B-1
的 369 项下降，是因为删除了约 200 项已经失效的同步、schedule v1、
round cursor、同步 `AgentState` 与 disposition 兼容契约测试，并以 ordinal
契约测试替换；该数字将在本检查点提交前重新独立验证。

## 当前改动文件

- `platform/src/agent_ex/__init__.py`
- `platform/src/agent_ex/domain.py`
- `platform/src/agent_ex/artifacts.py`
- `platform/src/agent_ex/rng.py`
- `platform/tests/test_domain.py`
- `task_plan.md`
- `progress.md`
- `logs/2026-07-29-phase4b2-checkpoint.md`

## 未完成风险

- domain 异常分支和其他 fail-closed 边界仍需补强覆盖。
- 尚未进行 Phase 4B-2 独立规格审查。
- 尚未进行 Phase 4B-2 独立代码质量审查。
- 审查意见关闭并重新完成全套验证后，才能提交正式 4B-2 完成点并继续 4B-3。

## 恢复方式

```powershell
cd 'E:\OneDrive\Claude Code\Agent ex\.worktrees\codex-paper1-phase4b'
git switch codex/paper1-phase4b
git pull --ff-only origin codex/paper1-phase4b
& '.\platform\.venv\Scripts\python.exe' -m pytest -q `
  --basetemp '.pytest-tmp\phase4b2-resume' platform\tests
```

恢复后先阅读本文件、`task_plan.md`、`progress.md` 与
`docs/superpowers/plans/2026-07-29-paper1-phase4b-implementation-plan.md`。
下一步不是进入 4B-3，而是继续 4B-2：补足 fail-closed / 异常覆盖，
再分别完成独立规格审查和代码质量审查。
