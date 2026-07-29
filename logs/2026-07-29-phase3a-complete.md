---
status: complete
authority: implementation checkpoint
supersedes: logs/2026-07-16-phase3a-wip.md
last-verified: 2026-07-29
---

# 2026-07-29｜Phase 3A 恢复与完成

## 结论

07-16 WIP 已恢复并完成。当前提交候选建立了 Paper 1 平台的协议/schema gate、领域记录、内容寻址运行身份、冻结 schedule、run manifest、证据图与严格持久化边界。旧 pilot 未修改，真实 model adapter、engine、population/persona/network 生成和正式实验均未越界实现。

本 checkpoint 不是 formal 运行许可。`docs/research-qa.md` 中的 formal-required 研究决策仍须由相应责任人冻结；`docs/decisions.md` 不含伪造审批记录。

## 关键修复

- 修复旧 wheel 污染：普通 import 与 editable install 均指向当前工作树源码；pytest 不再依赖 `PYTHONPATH=src` 掩盖安装问题。
- 协议 gate 严格校验 RFC3339 UTC、decision record 精确字段和值哈希、human summary 单区块同步，以及 Unicode 标点、格式字符和组合标记隐藏的占位符。
- `run_spec_hash → run_id → event_id → attempt_id` 分层绑定协议、环境、模型、请求参数和 `schedule_hash`。
- `FrozenSchedule`/`ScheduleSlot` 支持 N=1000、T=50 的轻量复用、版本化 canonical artifact 和严格 round-trip；manifest 持久化只保存 URI/hash/count，不重复嵌入 runtime schedule。
- complete/incomplete graph 精确绑定 schedule 坐标；已完成轮逐事件终态，恢复游标固定为下一轮 0-based next-slot index。
- 分析资格必须显式传入 policy；未在代码中硬编码尚未冻结的排除阈值。
- exposure、attempt、disposition provenance 与归档/checkpoint 具备结构完整性约束；同主体和具体允许状态仍保留给研究协议冻结。
- persisted payload 使用 exact keys 和严格 JSON 类型，不接受 bool/float/string 冒充整数或非 JSON 容器。

## 最终验证

- Root 入口：`353 passed`
- Platform 入口：`353 passed`
- 边界定向回归：此前 schedule、cursor、placeholder、provenance 和反序列化绕过均通过复审
- Ruff check：通过
- Ruff format check：通过
- `pip check`：通过
- `git diff --check`：通过（仅 Windows LF→CRLF 提示）
- schema 镜像：字节一致
- requirements lock：17/17 一致
- wheel 隔离安装与 formal smoke：通过
- 独立发布验证、边界审计、代码质量审查：PASS，无 blocker/major

## 下一步

进入实施计划 Phase 4：先以 TDD 实现 population、persona、network/exposure 的可复用模块和 mock fixtures；继续保持真实 adapter blocked，直到 provider/runtime artifact、credential、版本和请求签名 gate 完成。formal 仍须等待全部 formal-required 决策及其审批值哈希冻结。
