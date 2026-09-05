---
status: approved design; pending independent review and written-spec review
authority: Phase 0A no-network topic/persona probe design; subordinate to frozen machine protocol, schema, and 2026-07-29 Phase 4A completion design
approved-by: user
approved-date: 2026-09-05
supersedes: none
---

# Paper 1 Phase 0A 无网络议题与 Persona 探针设计

## 1. 目的与完成边界

本阶段建立正式实验前的最小真实模型校准闭环，回答两个问题：

1. 三个候选议题能否在目标 Qwen 系统上稳定测量各自的单一构念；
2. identity 与 continuity 两个 Persona 因素能否保持正交、产生可解释操纵，且不造成
   身份泄漏、刻板化或立场锁死。

本阶段只运行相互独立、无社会网络、无跨样本状态传播的 probe。它不运行 12-cell
网络矩阵，不校准 B/K、注意或表达分布，不估计 Paper 1 处理效应，不选择 primary
outcome，也不授权正式实验。

通过本阶段意味着可以提出 `P1_TOPIC_PRIMARY`、`P1_STANCE_SCALE`、
`P1_PERSONA_TEMPLATES`、`P1_CONTINUITY_MC_SCORING`、
`P1_CONTINUITY_LOCK_THRESHOLD`、`P1_REFUSAL_THRESHOLD`、
`P1_PARSE_FAILURE_THRESHOLD`、`P1_TEMPERATURE` 和 `P1_TOP_P` 的机器冻结建议。
只有经过规定的人类/方法/运行时审批并写入正式 decision records 后，这些值才获得
formal authority。

## 2. 不变约束

- 候选议题固定为延迟退休、依法标识的转基因大豆油销售、未来十年生成式 AI 在中国的
  净就业岗位判断。
- 多个议题通过全部硬门时，主议题按
  `延迟退休 > 转基因大豆油 > AI净就业`选择；下一顺位通过者才可成为缩减稳健性候选。
- 首选量表为 1--7 全标签有序量表，真实中点为 4；0--10 只作预先声明的挑战者。
- confidence 是独立的 1--5 审计字段，不进入意见更新或 primary outcome。
- Persona 由一份共同骨架机械插入 identity 与 continuity 块；absent 条件必须真省略。
- continuity 只增加历史解释连贯要求，同时对保持和改变提供对称许可。
- 不得使用抗从众、最大变化步长、方向性价值、坚持/捍卫或“永不改变”等锁定语句。
- formal config 在 decision records 和全部绑定 hash 完成前继续 fail closed。

## 3. 方案选择

采用“平台内契约优先”的 probe 子系统，而不是 Notebook 主循环或一次性脚本：

- 复用 `TopicPackage`、Persona 渲染、prompt/parser、`ArtifactEnvelope` 和规范化 hash；
- 为 calibration 单独建立 case、attempt、score、report 和 freeze-proposal 合同；
- 不把真实模型能力塞进当前 `mock_only` adapter，也不复用正式网络事件身份伪装 probe；
- 真实 provider adapter 只依赖一个窄的 probe request/response 接口，Phase 0B 再决定它
  是否可安全复用于正式 event pipeline。

拒绝的替代方案：

- Notebook/独立脚本直接调用模型：启动快，但难以证明题干、参数、顺序、重试和原始
  响应是否精确绑定；
- 现在建立覆盖 Phase 0A/0B、人口、网络和正式运行的通用校准框架：复用潜力较高，
  但会扩大本阶段范围并延迟第一批真实 probe。

## 4. 架构与组件

### 4.1 Probe specification

版本化 specification 必须列出：

- 三个 topic candidate 及每个候选的一份拟冻结题干、两个同方向等义改写；
- 1--7 主量表与 0--10 挑战量表；
- 输出字段顺序挑战；
- Persona 共同骨架、identity block、至少两组等义 continuity block 及因素块顺序挑战；
- 平衡的最小身份壳，不引用正式人口分布，也不声称代表目标总体；
- continuity 情境库、候选 generation settings、重复数和抽样 seed；
- 允许读取的指标、硬门、人工审计抽样规则及禁止输出字段；
- 每个仍未冻结值对应的稳定 `P1_*` ID。

所有机器可见文本、字段顺序、生成参数、模型/运行时身份和 scenario assignment 都须
进入 canonical payload 和 SHA-256。修改任一可见字符或执行值必须产生新版本。

### 4.2 Probe case builder

case builder 确定性展开 specification，生成三类不相互污染的 case：

1. **Topic quality cases**：不提供身份或社会信息，比较题干等义、量表及字段顺序；
2. **Identity cases**：在共同题干和状态下只切换最小身份卡，检查 uptake、泄漏、
   刻板化和构念漂移；
3. **Continuity cases**：在共同历史下只切换 continuity 块，并平衡三种情境：
   合理保持、充分且非欺骗性的反向信息、信息不足/模糊。

每个 case 拥有稳定 `probe_case_id`，由 specification hash、topic、case family、
factor condition、scenario、variant、scale、field order、replicate 和 model-sampling
seed scope 派生。执行顺序不得改变 case identity。

### 4.3 Probe runner 与 adapter 边界

runner 逐 case 构造不可变请求并调用 provider-neutral probe adapter。它必须保存：

- 完整渲染消息及 hash；
- generation settings、模型 revision、tokenizer/chat-template、运行时和 adapter 身份；
- provider request ID、开始/结束时间、终止原因、token 计数和错误分类；
- 原始响应字节/文本及 hash；
- 解析结果、失败原因和 attempt 链。

同一 case 的首次格式失败最多允许一次**仅格式修复重试**。重试保留相同语义内容、
case identity 和预定模型 seed，只能追加统一格式提醒；第二个 attempt 必须具有独立
request/response identity。超时、OOM、provider 错误和实质拒答不是格式重试，不能用
改写问题静默替代。

Phase 0A case 彼此独立，因此可在运行层并发；单 case 的 attempt 链严格串行。并发只
影响调度，不得改变 case、sampling seed、输出顺序或报告 hash。

### 4.4 Deterministic scorer

确定性 scorer 只计算可机械复核的质量指标：

- 首次与一次格式重试后的有效解析率；
- 实质拒答率和运行时失败率，分别报告；
- 使用类别数、单一点/端点占比和完整分布；
- 等义题干与字段顺序挑战的标准化差异及分布差异；
- stance、confidence 和 public_reason 的字段合同；
- 明确的理由--立场直接矛盾规则；
- 禁止文本、身份扩写和未提供敏感属性的命中；
- prompt、response、parse 和 model/runtime provenance 完整性。

操作性门槛继承 `D-2026-07-29-02`：至多一次格式重试后解析率至少 99%，实质拒答率
不高于 1%，至少使用 7 点中的 4 类，单一端点不超过 80%，等义版本标准化差异
`|d| <= 0.20`且同时检查完整分布，理由--立场直接矛盾不高于 5%。这些值是候选比较前
统一使用的项目操作规则，不自动成为 formal canonical values；若 dry run 暴露规则缺陷，
必须在比较任何候选前统一修订、版本化并留痕。

### 4.5 Judge 与人工盲审接口

需要语义判断的项目不交给 deterministic scorer 猜测。系统导出不含候选排名和
动力学结果的盲审包，供独立 judge 和分层人工编码使用：

- 理由是否实际回答单一构念；
- 理由与立场是否一致；
- identity 是否被合理使用、被忽略、被扩写或刻板化；
- continuation 是否与历史解释连贯；
- 在充分反向信息下是否能够可解释改变；
- 在信息不足情境下是否发生无依据的大幅改变；
- 是否存在安全模板化、议题无关或隐藏第二构念。

judge 的模型、revision、prompt、顺序和原始输出必须单独冻结和留痕。人工编码表保存
匿名 item ID、量表、编码者、时间和 adjudication；精确抽样、量表、一致性门和锁死
上限在运行真实 probe 前写入 specification，仍由相应 `P1_*` 决策 ID 管理。

### 4.6 Report 与 freeze proposal

报告分成四层，不允许越权：

1. **Completeness**：预期 case、attempt、response、parse 和审计记录是否齐全；
2. **Quality gates**：逐候选、逐挑战报告允许指标和 pass/fail；
3. **Precommitted selection**：只对全部硬门均通过的议题应用既定优先级；
4. **Freeze proposal**：列出建议值、制品 ID/hash、证据定位和仍未决项。

freeze proposal 不是 decision record。程序不得自动修改 `docs/decisions.md`、正式协议、
schema 或 formal config，也不得把 probe 成功标记成正式审批。

## 5. 数据流与存储

数据流为：

`probe specification -> immutable cases -> rendered requests -> raw attempts -> parse evidence
-> deterministic metrics -> blinded semantic review -> gate report -> freeze proposal`

每一层只引用上游稳定 ID/hash，不复制无绑定的自由文本。输出目录按 probe run 隔离，
至少包含 manifest、specification/case inventory、requests、raw responses、parse evidence、
machine metrics、blind-review export/import、gate report 和 freeze proposal。

原始响应和可能较大的运行产物不进入 Git。Git 只提交 schema、代码、测试、脱敏小型
fixture、manifest/hash 和外部归档定位。任何缺失、重复、hash 漂移或 review item
无法回绑原始 case 时，报告必须 fail closed。

## 6. 禁止读取与选择防火墙

Phase 0A 的实现和标准报告不得计算、展示或导出：

- 网络极化、均质化、方向漂移、双层结构或收敛形态；
- `WS - shadow`、continuity DiD、任一 primary/secondary cell contrast；
- CI、p 值、显著性或按议题排列的“效果强弱”；
- 哪个议题、模板、量表或 generation setting 产生更有趣的论文故事。

Topic 的分布检查只用于识别拒答、量表退化和题干不稳定，不得解释为目标总体民意。
Persona 的 stance 变化只在预构造 manipulation scenarios 内用于判断合理保持/可改变/
无依据改变，不得当作网络处理效应。

## 7. 错误处理与停止规则

- specification 含未知 placeholder、未登记决策 ID 或未绑定文本/hash：构建前失败；
- case inventory 不完整、重复或顺序依赖：执行前失败；
- 模型/runtime/tokenizer/chat template 与运行 manifest 不一致：立即停止该 run；
- 响应失败：保留证据，按预先分类处理；除一次格式重试外不得现场改 prompt；
- 原始响应、parse evidence 或审计导入 hash 不一致：报告失败，不重新解释数据；
- 任一候选硬门失败：该候选不得进入选择集合；
- 三个议题均失败：停止并重开题干/量表设计，不按相对最好者强行选主议题；
- Persona 操纵无效或锁死：修改候选模板、产生新版本并重跑全部受影响 cases；
- probe 期间更换模型 revision、chat template 或 generation strategy：新建 probe run，
  不与旧 run 拼接为同一比较。

## 8. 测试策略

实现采用测试先行，至少覆盖：

- case 笛卡尔展开、稳定 ID、顺序不敏感和重复拒绝；
- topic/persona 只有批准字段发生差异；
- 1--7 与 0--10、题干等义、字段顺序和 continuity 情境配对完整；
- 原始请求/响应、模型身份、sampling seed、attempt 和 hash 的严格 round-trip；
- 首次成功、一次格式修复成功、二次格式失败、拒答、timeout 和 provider error；
- 缺字段、重复键、NaN、越界、额外 prose、理由矛盾和身份泄漏 fixture；
- 所有硬门的边界值，尤其 99%、1%、4 类、80%、`|d|=.20`和5%；
- judge/人工审计导入的盲态、完整性、编码者一致性与 hash 回绑；
- 三议题全过、部分通过和全部失败时的确定性选择；
- freeze proposal 无权修改 decision records 或 formal config；
- 报告 schema 明确拒绝 forbidden outcome/contrast 字段；
- Windows 本地 mock/dry run 与云端 Linux 真实 adapter 使用同一 case/report 合同。

真实模型调用前必须先用确定性 scripted responses 完成完整 dry run。真实 probe 后只重跑
与 provider/runtime 有关的集成门，不用真实响应替代单元测试 fixture。

## 9. 分阶段实施与验收

### Phase 0A-0：离线 probe 骨架

- 完成 specification/case/attempt/score/report/freeze-proposal 合同；
- 编写三议题和 Persona 候选草案，但保持 `not_frozen`；
- 完成确定性 dry run、盲审导出导入和选择防火墙；
- 不联网、不调用真实模型。

### Phase 0A-1：云端真实小样本 probe

- 在锁定的 Linux/CUDA/vLLM/Qwen candidate 栈重跑环境与 adapter smoke；
- 固定该次 probe 的候选模型/runtime/chat-template/generation manifest；
- 执行预登记 cases，完成机器评分、独立 judge 和人工盲审；
- 生成唯一、可审计的 gate report 与 freeze proposal。

### Phase 0A-2：审批与机器冻结

- 用户、方法和运行时 owner 审阅 freeze proposal；
- 为获批字段计算 schema JSON-pointer canonical payload hashes；
- 写入 `docs/decisions.md` 正式 fenced YAML records，同步人类协议和机器协议；
- 验证 formal gate 只关闭已获批准字段，其他 Phase 0B/统计项继续 unresolved。

本设计验收条件是：Phase 0A-0 可在无网络 mock 环境完整复现；真实 run 的每个允许指标
可由原始 evidence 重算；禁止结果不会出现在标准报告；全部选择由硬门和既定优先级唯一
决定；任何 freeze 都必须经过独立审批而非代码自动晋升。

## 10. 后续边界

Phase 0A 完成后才进入 Phase 0B：真实 N=20/50/100 动力学校准、B/K、注意/表达过程、
模型 revision/runtime 镜像、吞吐/显存/恢复和统计 endpoint 冻结。Phase 0B 通过仍不等于
正式 N=1000 主矩阵获准；formal protocol、分析、seed、成本与归档 gates 必须全部关闭。
