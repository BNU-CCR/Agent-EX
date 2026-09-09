---
status: Phase 0A-0 complete / independently reviewed
authority: verified engineering handoff; not a formal protocol or parameter decision
branch: codex/paper1-phase0
verified-through: 6af2ff1
last-verified: 2026-09-09
---

# Paper 1 Phase 0A-0离线 probe 交接

## 完成边界

本 checkpoint 完成批准规格中的 Phase 0A-0：离线 specification/case/attempt/score/
semantic-review/gate/report/freeze-proposal/bundle 合同、确定性 scripted dry run和恢复验证。
5/6/7/8/9各阶段均已有提交与复核证据。它没有运行真实模型或网络调用，没有批准或冻结
任何研究参数，也不代表 Phase 0A、Phase 0B、formal readiness或正式实验完成。

规格与实现范围：

- 批准规格：`28eafee`；实施计划：`7561cc2`；
- Tasks 0--8：`ada2f1c`至`4fbd193`；
- Task 9终审修复：`1ef0946`（runtime policy与异常恢复）、`9e998c1`（语义门与proposal
  防火墙）、`6af2ff1`（严格review policy JSON loader）；
- 本日志记录的待提交文档 checkpoint 在上述实现提交之后。

## 环境身份

- OS：Windows台式机本地隔离worktree；
- Python：`3.12.14`；
- dev lock：`platform/requirements-dev.lock`；
- dev lock SHA-256：
  `eedb8d1b236ff6a5f88e2d6eb07219d2a452c421f7a31181ee9faa297a092017`；
- 18/18 lock依赖与环境精确一致，`pip check`为`No broken requirements found`。

## 新鲜发布验证

- full：`1463 passed, 2 skipped, 1 deselected in 4601.94s (1:16:41)`；
- coverage：`1463 passed, 2 skipped, 1 deselected in 11635.94s (3:13:55)`；
- production coverage：`14,600 statements / 2,102 missed / 86%`；
- 协议/安装/离线集成专项：`163 passed in 1606.39s (0:26:46)`；
- 最终验证员独立专项复跑：`163 passed in 1630.74s`；
- `ruff check`、`ruff format --check`、`pip check`与`git diff --check`全部通过。

两个skip均为平台条件：当前Windows环境无创建symlink权限，以及仅POSIX执行的no-follow
identity smoke。唯一deselected是pytest默认明确排除的50,000-event `release_scale`测试；
该规模门已在Phase 4B按批准流程单独运行，不在普通full/coverage重复消耗资源。

## 离线制品与哈希

四replicates的all-pass synthetic fixture产生：

- 816个逻辑cases：topic quality 144、identity 96、continuity 576；
- 816 attempts；
- 816 request + 816 response + 816 parse = 2,448条证据记录；
- report status：`proposal_only`。

精确SHA-256/canonical hashes：

- fixture file：`2e9f360d5d3d2061a954d55a96e40250769672494d9fc203b65232a73192d0be`；
- specification：`88d87134e09797ebe7a9e03b6672686ffccdf5d369cd2bd2f2ecf413337e9afd`；
- case inventory：`c2e1909bc4d44dbabc7a4523108d71a49bef1b694bc322edcb3ef5c6a8fd45cf`；
- report projection：`54a263f0d364ba25d6d5d1443a9d38def11187b317aa5a421f813253524a56d2`；
- full run evidence：`9d79a2142d4cdb6479c30150c70a8fbd47dd4bca1eb14efef36efe56af0db97a`。

## 权限与制品卫生

- calibration包和锁文件无`requests/httpx/aiohttp/urllib3/openai/anthropic/
  huggingface_hub/vllm`网络客户端依赖或导入；
- offline facade只接受内部scripted adapter，不构造正式experiment engine对象；
- 未发现credential赋值、`formal_parameter_authority: true`或真实模型入口；
- `platform/configs/paper1/phase0a-probe.draft.yaml`保留50处、10类
  `UNRESOLVED[...]`，三个候选各有严格7个1--7标签；runnable loader继续fail closed；
- `docs/decisions.md`仍为`records: []`；
- Git跟踪的platform路径中无SQLite/database/checkpoint/raw/coverage/cache结果制品，
  无大于1 MiB的文件；原始大规模结果未进入Git。

## 独立复核

- specification rereview：`APPROVED`，P0/P1/P2/P3均为0；
- code-quality rereview：`APPROVED`，P0/P1/P2/P3均为0；
- final-verification review：`APPROVED`，P0/P1/P2/P3均为0。

终审曾发现并关闭：语义维度未完整进入gate、runtime等待/timeout未实际施行、
post-adapter异常无恢复snapshot、草案标签多一项、无门授权decision可进入proposal，以及
review policy嵌套非数组可被tuple化接受。每项均有RED/GREEN、focused回归和受影响复审。

## Phase 0A-1启动阻断项

进入云端真实小样本probe前，必须由相应owner明确批准并版本化：

1. 三个议题的题干、事实卡、量表锚点与persona文本候选；
2. 真实probe runtime policy，包括timeout、错误分类、attempt预算、Retry-After与backoff；
3. semantic-review policy，包括抽样、盲态allowlist、coder/judge、标签、聚合与一致性门；
4. Qwen revision、tokenizer/chat template、vLLM/Linux/CUDA候选栈和generation manifest；
5. 云端凭据的安全注入方式；
6. 原始响应、review和bundle的外部受控archive location。

上述阻断项未关闭前，不上传或运行真实probe，不写decision records，不生成formal config，
更不启动N=1000/T=50正式主矩阵。
