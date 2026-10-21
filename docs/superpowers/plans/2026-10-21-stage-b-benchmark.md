# Stage-B Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 接入已确认同30case/240项的独立Stage-B离线/SQLite/CLI流程，保留A hash，不授权云端。
**Architecture:** 显式stable_group inventory与stage-b/preflight-b modes；复用SQLite/HTTP/分析原语，
以冻结framing和完整A store冷重放作为B门。无新数据库表，不复制全套运行器。
**Tech Stack:** Python3.12、pytest、SQLite、现有vLLM HTTP adapter、Ruff。

规格：../specs/2026-10-21-stage-b-benchmark-design.md（独立规格审查Approved）。
范围来自用户本轮明确确认；在当前专用worktree inline执行，其他未提交文件不stage。

## Task 1: 独立inventory、固定framing与A证据门

Files: platform/src/agent_ex/identity_network/benchmark_trials.py、benchmark_transport.py、
新增benchmark_stage_b.py；新增platform/tests/test_identity_network_benchmark_stage_b.py。

- [ ] RED：新增下列行为测试，运行明确失败后才实现。
  ```python
  a = build_benchmark_trial_inventory(benchmark, expected_hash=BENCHMARK_HASH)
  b = build_benchmark_trial_inventory(benchmark, expected_hash=BENCHMARK_HASH, stage="stable_group")
  assert a.output_hash == "6aba583ad74921a4a3d0e9822b985d6385176fd04e31e1db7eea901473336e6f"
  assert {x["trial_id"] for x in a.payload["trials"]}.isdisjoint(x["trial_id"] for x in b.payload["trials"])
  assert [x["sampling_seed"] for x in a.payload["trials"]] == [x["sampling_seed"] for x in b.payload["trials"]]
  ```
- [ ] GREEN：inventory新增显式stage，默认pure_label原payload不改；replay从输入stage冷重建。
  B transport只允许固定framing及有效A证明，stage/mode加入event/trial身份；不改A默认路径。
- [ ] Tests：B各四配对只改group/frame/member prefix；移除这些字段后正文完全等于A；
  same seeds、独立预检、每request三attempt精确wire不变；错误framing/不完整或通过A拒绝。
- [ ] Run：Python3.12 -m pytest platform/tests/test_identity_network_benchmark_stage_b.py
  platform/tests/test_identity_network_benchmark_transport.py platform/tests/test_identity_network_benchmark_trials.py。

## Task 2: bound packet、A冷核验、B SQLite和分析

Files: benchmark_run.py、benchmark_store.py、test_identity_network_benchmark_stage_b.py。

- [ ] RED：B包缺A证明失败；fake HTTP完整A→B预检→B240；A receipt或A preflight不能借用。
  在网络调用前篡改A root/report拒绝；B store重开保持B身份，未决intent不重发。
- [ ] GREEN：build_bound_packet接受stage_a_report并将其绑定于B包；_validate_packet冷重建，
  run/resume/verify对stage_a_root调用verify_benchmark(A mode)并比对精确安全report。
  stage-b要求preflight-b且同source/runtime；store显式四mode及精确2/240。
  report根据packet.stage使用对应inventory，不合并A/B观察。
- [ ] Tests：合成A+真实adapter形状假HTTP，无真实模型；既有A专项全保持通过。
- [ ] Run：上项专项加test_identity_network_benchmark_run.py、store.py、retry.py、analysis.py。

## Task 3: CLI、证据说明与限定验收

Files: benchmark_cli.py、新增/扩展CLI测试、docs/decisions.md、docs/research-qa.md、progress.md。

- [ ] RED：CLI materialize/inspect/run/resume/verify/report对B要求--stage-a-root；错误A证据拒绝。
- [ ] GREEN：CLI在B离线物化时冷验A实际store并记录证明；run/verify传递stage_a_root。
  原A命令不需要额外参数，输出B仍dispatch_authorized=false且无自动Stage-C授权。
- [ ] Verify：上述命名专项、Ruff check/format --check、git diff --check。
  使用独立Temp pytest --basetemp/cache避免旧OneDrive锁；不重复全仓pytest。
- [ ] Commit：只stage此次明确源/测试/规格/计划/决策文件，不提交其他untracked测试或报告raw。
- [ ] Hand-off：报告精确新source与本地测试、剩余Linux/实际绑定/上传及运行审批；
  未获精确包批准不上传新源码，不发B请求，不重启当前健康服务。

Python工具复用既有3.12环境：
E:/OneDrive/Claude Code/Agent ex/.worktrees/codex-paper1-phase0/platform/.venv/Scripts/python.exe。
设置PYTHONPATH为本worktree/platform/src，确认不是导入legacy checkout。
