---
status: complete
date: 2026-08-01
branch: codex/paper1-phase4b
baseline: 49f8047
phase: Phase 4B-2 complete / independently reviewed
---

# Phase 4B-2 完成检查点

Phase 4B-2 已完成实现、独立规格/反模式审查、独立代码质量审查和收口验证。
本检查点只关闭 4B-2；Phase 4B-3 尚未开始，不表示任何 Phase 4B-3 研究制品、接口或
机器参数已经实现或冻结。

## 完成边界

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
- 移除旧同步 engine / schedule v1 / round cursor / 同步 `AgentState`
  兼容契约；这符合用户已批准的破坏性迁移边界，不提供旧接口兼容层。
- `event_ordinal` 从 0 连续到 `N×T-1`；attempt index 从 1 开始，二者不得混淆。

测试总数相对 4B-1 的 369 项下降，是因为删除了约 200 项已经失效的同步、
schedule v1、round cursor、同步 `AgentState` 与 disposition 兼容契约测试，
并以 ordinal 契约测试替换；不是功能性失败。

## 失败关闭补强与审查修订

- 在台式机以 Codex bundled Python 3.12.13 重建忽略的 `platform/.venv`，按
  `platform/requirements-dev.lock` 安装 17 项精确版本依赖。lock SHA-256 为
  `13878C75C775657BBFB0896AE858645C0FE37CC4C3717EDD5FBAD4833B6FD292`。
- 严格 RED→GREEN 补强领域边界：event attempt ID 必须由自身 event identity 派生；
  manifest 必须保留完整且非空的模型/环境复现身份；`schedule_count` 不得接受 JSON
  boolean；`event_ids` 必须为 JSON array；普通身份字符串不得只含空白。
- 第一项独立代码质量 P1 指出，RNG 只拒绝顶层 `attempt_index`，嵌套 object/array
  仍可改变同一 event 的 model seed。两个参数化案例先稳定 RED（`2 failed`，均为
  `DID NOT RAISE ValueError`），随后在严格 JSON transport 校验后递归拒绝任意层级
  的该键；定向 RNG 回归为 `7 passed`，domain 回归为 `43 passed`。
- 后续独立代码质量审查提出四项修订，并以 `7 failed`→`7 passed` 完成：
  `GenerationAttempt` 恢复 provider metadata/headers、HTTP status、usage、finish
  reason 及对应 hash；FAILED attempt 可保留已收到的真实 raw response 与元数据但
  禁止 parsed success；RNG/artifact typed 构造支持自身冻结值与
  `dataclasses.replace`，同时保持 `from_payload` 的严格 JSON 边界；artifact 工厂在
  派生 ID 前显式校验 provenance 类型并稳定抛出合同内 `TypeError`。
- 独立规格审查和反模式审查结果均为 `APPROVED`；独立代码质量复审结果为
  `APPROVED`。上述 P1 与四项质量修订均已关闭。

## 最终验证证据

- fresh 全套：`194 passed`，无 skip、无 xfail。
- 独立全量 coverage：`1245 statements / 187 missed / 85%`。此前实现代理的覆盖率
  运行使用了不同统计口径，不作为 Phase 4B-2 最终覆盖率；本文件及项目进度统一采用
  独立全量 `85%`。
- Ruff check、Ruff format check、`pip check`、`git diff --check`、schema 镜像、
  draft gate 与 formal fail-closed gate 均通过。
- 文档收口前验证快照的 Git diff SHA-256 为
  `481BFA0FB75EEFC9E438732B9CF3A93FC889BB19DFA061E9ACAD545DC215B081`。
  这是 **pre-documentation verification hash**：本文件、`task_plan.md` 与
  `progress.md` 更新后 diff 必然改变；它不是最终提交 hash，也不得冒充提交身份。

## Phase 4B-2 文件边界

- 生产实现：`platform/src/agent_ex/domain.py`、`platform/src/agent_ex/artifacts.py`、
  `platform/src/agent_ex/rng.py` 及经测试的公开导出。
- 回归证据：`platform/tests/test_domain.py`。
- 计划与收口记录：
  `docs/superpowers/plans/2026-07-29-paper1-phase4b-implementation-plan.md`、
  `task_plan.md`、`progress.md` 与本文件。

## 恢复与下一步

```powershell
cd 'E:\OneDrive\Claude Code\Agent ex\.worktrees\codex-paper1-phase4b'
git switch codex/paper1-phase4b
& '.\platform\.venv\Scripts\python.exe' -m pytest -q `
  --basetemp '.pytest-tmp\phase4b2-resume' platform\tests
```

下一工作包是 Phase 4B-3：topic、population、initialization 与 persona 的 mock 制品。
本完成点没有开始 4B-3，也没有新增研究参数、填补任何 `UNRESOLVED[...]` 或改变
formal fail-closed 边界。进入 4B-3 前应从实施计划第 7 节重新执行 RED→GREEN 与独立审查。
