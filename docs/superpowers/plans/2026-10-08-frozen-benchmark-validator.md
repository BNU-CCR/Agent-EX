# Frozen benchmark validator implementation plan

执行方式：当前隔离worktree内按TDD逐项执行；不启动云端、不修改legacy、不使用旧未提交loop文件。

**Goal:** Validate the approved thirty-case content snapshot before later trial materialization.
**Architecture:** A pure function binds exact canonical payload hash plus strict structure; no dispatch, seed generation or HTTP. User-approved research content is stored separately from runtime approval.
**Tech Stack:** Python 3.12, existing canonical_payload_hash, pytest.

## Task 1：冻结材料

- [x] 保存benchmark.json：v3仅修改AD-028，其余29条保留，明确004/023共享family。
- [x] 保存stage-b-framing.json与analysis-policy.json；研究冻结不授予dispatch。
- [x] 计算canonical SHA-256及文件SHA-256，保存精确字节说明与决策。

## Task 2：纯校验器

Files: create `platform/src/agent_ex/identity_network/benchmark.py` and
`platform/tests/test_identity_network_benchmark.py`.

- [x] RED：真实冻结JSON验收；对正文漂移、重哈希后count/stance/ID/review/history/flags/
  reason/shared-family结构漂移分别拒绝；不调用HTTP。
- [x] 运行命令：既有.test-venv python，PYTHONPATH=platform/src，pytest仅指定本测试文件，-q，basetemp/cache_dir均指向新临时目录（仓库strict-config不兼容禁用cacheprovider）。
- [x] GREEN：`validate_frozen_benchmark(payload, expected_hash=...)`先用canonical_payload_hash绑定外部预期hash，
  再检查精确键集、严格整数、六层ID/内容ID映射、30唯一完整case、focal4/source距离、
  approved状态、共享family标记、两句公开表达及理由一致、固定persona/context/history/confidence。
  返回不可变safe摘要，仅count/hash/status，不输出刺激或模型响应。
- [x] 检查Ruff lint/format与git diff check；不跑全仓pytest。

此slice不声称完整JSON Schema、trial materializer、retry store或CLI已完成。
下一slice需修订旧单attempt/stop-invalid合同，再实现同identity最多三attempt及崩溃恢复；
含糊INTENT不得盲目重发。Stage-B需要完整有效Stage-A与冻结条件且后续显式dispatch授权。
