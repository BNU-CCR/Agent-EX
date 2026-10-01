# Agent-EX 最新研究转向与代码重构说明
**用途：供 Codex / 代码协作者快速理解本轮组会后的理论转向、实验重构与代码修改要求**  
**更新时间：2026-10-01**

---

## 0. 一句话版本

本轮最大的变化不是“换几个变量名”，而是把研究从原先由实验参数出发的 **2×2×3（persona/identity cues × history consistency × network exposure）**，重构为一个更符合传播学与 opinion dynamics 学术共同体语言的 **2×3 正式设计：social identity salience × communication network structure**。

论文现在的主轴是：

> **micro-level sycophantic alignment / selective agreement → repeated networked social influence → macro-level opinion convergence**

其中：

- **social influence / group norm formation**：理论基础；
- **selective agreement vs. sycophantic alignment**：微观机制区分；
- **repeated interaction / exposure → response → expression → re-exposure**：微观到宏观的递归过程；
- **opinion convergence**：核心宏观结果；
- **social identity salience × communication network structure**：正式实验的两个条件变量；
- **artificial consensus**：社会意义，不是主结果变量。

旧的 weak/strong persona 预实验仍然保留，但只作为 **preliminary evidence / design motivation**，不能再被直接解释为 social identity salience 的正式操纵。

---

# 1. 本轮为什么发生理论与设计转向

## 1.1 老师第一次核心反馈：语言不像本学科

原先摘要中使用了：

- “身份参照”
- “历史连续性”
- “网络化暴露”

老师明确指出，这些不是传播学 / opinion dynamics 学术共同体的标准概念，而更像从现有实验参数倒推出来的 AI 式概念。

因此本轮阅读和重构的原则变成：

> **先问这个学科如何定义问题，再决定我们的实验变量应该如何设计，而不是给已有代码参数寻找理论名字。**

## 1.2 Starnini et al. (2026) 带来的核心转变

阅读 *Opinion dynamics: Statistical physics and beyond* 后，当前研究开始按 opinion dynamics 的标准结构组织。

### 微观层面
- social influence
- selective agreement
- conformity
- sycophantic alignment

### 宏观层面
- convergence
- consensus
- fragmentation
- polarization
- opinion clustering

最重要的认识：

> **convergence 是宏观结果，不是 sycophancy 的证据。**

因此不能再用“Agent 越来越相似”直接证明“Agent 在迎合”。

## 1.3 Cau et al. (2025) 带来的机制问题

Cau et al. 发现 LLM interaction 中会出现明显 convergence，但认为其机制更接近 **selective agreement / structured asymmetric persuasion**，而不是简单 sycophancy。

这直接促成了当前核心问题：

> **LLM Agent 的意见改变，到底是基于新论据的 selective agreement，还是在缺乏充分依据时向局部主导意见靠拢的 sycophantic alignment？**

因此，原系统已经记录的：

- stance
- reason text
- actual exposure
- confidence

从“附加分析变量”升级为识别微观机制的核心数据。

## 1.4 老师最新反馈：必须把微观—宏观逻辑讲清楚

老师进一步指出，摘要一度同时使用了：

- convergence
- assimilation
- conformity
- selective agreement
- sycophantic alignment
- selective social influence
- sycophancy

概念太多，且层级关系不清。

因此最终需要做概念减法：

| 层级 | 当前保留的核心概念 |
|---|---|
| 总体理论 | social influence / group norm formation |
| 微观机制 | selective agreement vs. sycophantic alignment |
| 递归过程 | repeated interaction / exposure → response → expression → re-exposure |
| 宏观结果 | opinion convergence |
| 条件变量 | social identity salience × communication network structure |
| 社会意义 | artificial consensus |

---

# 2. 当前论文主问题

当前标题方向：

> **From Micro-level Sycophancy to Macro-level Convergence: Social Influence and Opinion Dynamics in Networks of LLM Agents**

当前最核心的理论链条：

```text
Local opinion exposure
        ↓
Micro-level response
   ├─ selective agreement
   └─ sycophantic alignment
        ↓
Updated judgment / public expression
        ↓
Expression re-enters the information environment
        ↓
Repeated interaction / recursive social influence
        ↓
Macro-level opinion convergence
```

两个正式实验条件作用于这一过程：

```text
social identity salience
          ↓
micro-to-macro recursive process
          ↑
communication network structure / clustering
```

---

# 3. 旧设计与新设计

## 3.1 旧主设计：2×2×3

旧设计大致是：

### I：persona / demographic cue visibility
- I0：弱 / 无人口背景
- I1：较强 persona / 人口身份背景

### C：history consistency
- C0：无额外历史一致性要求
- C1：要求当前判断与既往表达保持可解释联系

### E：network / exposure
- E0：self-history only
- E1：degree-preserving shadow / randomized condition
- E2：Watts–Strogatz network

旧设计的问题：

1. **I 不等于 social identity。**  
   人口背景信息本身不自动形成 ingroup/outgroup social categorization。

2. **C 不是传播学中的“时间维度”。**  
   repeated interaction 才是真正的时间 / temporal dynamics；C 更像 prompt / memory architecture。

3. **三个因素对应三套不同故事。**  
   摘要需要同时解释 persona、history、network，理论负担过重。

4. **12 个条件不利于 DJ extended abstract。**  
   很难用有限篇幅和 1–2 张图讲清楚。

## 3.2 新正式设计：2×3

正式主实验改为：

> **Social Identity Salience × Communication Network Structure = 2 × 3**

共 6 个条件。

### 因素 A：Social Identity Salience

建议代码层面使用两个中性 minimal groups，例如：

- Blue Group
- Green Group

要求：

- 两组等量或尽量等量；
- group membership 随机分配；
- group membership 与 initial stance 正交；
- 两组初始 stance distribution 一致；
- 两组 demographic composition 尽量平衡；
- group membership 在一个 run 中固定；
- **绝对不要在 prompt 中告诉 Agent “更相信自己组”或“维护本组立场”。**

#### A0：group-blind / identity not salient
系统内部仍保存 group membership，但：

- Agent 不知道自己属于哪组；
- 看不到 message source 的 group；
- 只看到匿名 member ID。

#### A1：group-salient / identity salient
Agent 能看到：

- 自己的 group；
- message source 的 group label。

但不提供任何预设的 group norm / group stance。

### 设计目的

不是直接“制造 in-group bias”，而是检验：

> **mere social categorization / identity salience 是否会改变 social influence 的方向和强度。**

### 因素 B：Communication Network Structure

#### B0：No social interaction
- 不读取其他 Agent 的帖子；
- 作为无社会影响 baseline；
- 可以保留统一的必要 self-history / internal memory，但所有条件必须一致。

#### B1：Degree-preserving randomized network
要求：

- 使用真正的 degree-preserving edge rewiring；
- 尽量保持与 B2 相同的 degree sequence；
- 打散局部 clustering；
- 固定网络于单个 run 内。

#### B2：Clustered small-world network
- 使用固定 Watts–Strogatz network；
- 具有明显更高的 local clustering；
- 固定网络于单个 run 内。

### 每个 network run 必须记录
至少保存：

- clustering coefficient
- average path length
- degree distribution
- connectedness / giant component status（如适用）

因为最终论文不能只凭 “WS vs random” 就口头宣称是 clustering effect。

---

# 4. C / history 条件如何处理

旧 C（history consistency）退出正式实验因素。

新的原则：

> **所有 6 个正式条件使用相同的 self-history / memory 规则。**

推荐：

- 所有 Agent 都读取相同长度的 recent self-history；
- 不再加入“必须保持与历史立场一致”的额外指令；
- 不再把 self-history / consistency 当作理论变量；
- history 仅作为 Agent architecture 的统一部分。

如果当前代码仍有 `consistency_on/off`：

> **不要删除底层能力，但主实验 config 中固定为同一值，不再 factorialize。**

建议保留旧实验 config，以便未来做 supplementary / robustness。

---

# 5. 旧 weak/strong persona 预实验如何处理

不要删除。

当前摘要使用的 preliminary pilot：

- **N = 200**
- **30 simulated rounds**
- 条件包括：
  - C1_weak_BA
  - C2_lifelong_BA
  - C3_weak_WS
  - C4_lifelong_WS

主要观察：

- weak-persona 条件快速向高端点 directional convergence；
- stronger / lifelong persona grounding 保留更多 intermediate positions；
- stronger persona 明显减缓 convergence；
- 不同 network 条件下 trajectory 也存在差异。

### 重要解释限制

这个 pilot 只能说明：

> **identity-related / persona conditioning 会影响 opinion persistence / convergence trajectory。**

不能说：

> “旧 pilot 已经证明 social identity salience 有效。”

因为旧 strong persona 并不是正式的 ingroup/outgroup social identity manipulation。

### 代码策略

建议保留两套 config：

```text
configs/
  legacy_persona_network_pilot.yaml
  main_identity_network_2x3.yaml
```

不要为了新主实验删掉旧实验代码和结果复现能力。

---

# 6. Agent 交互循环：正式代码应围绕这个逻辑重构

正式模型的核心不是“每轮输出一个 stance”，而是：

> **information exposure → conditional response → public expression → renewed exposure**

建议事件级流程：

```text
1. select focal agent
2. load stable persona / group condition
3. load standardized recent self-history
4. collect actually visible new neighbor messages
5. build prompt/context
6. LLM returns:
   - private stance
   - reasoning
   - confidence
   - publish decision
   - public expression if published
7. commit private state
8. if publish=True:
   - add public post to network environment
9. future agents may read this new post
```

### 关键原则

**Potential network connection ≠ actual exposure ≠ actual influence**

必须分别记录：

1. network neighbors
2. candidate messages
3. messages actually shown/read
4. focal Agent update
5. whether update moved toward visible local opinion

不能用“有一条边”代替“Agent 看到了这条信息”。

---

# 7. 新设计下必须新增 / 修改的数据字段

## 7.1 Agent-level static fields

建议新增：

```text
agent_id
group_id                 # e.g., blue / green
group_visible_condition  # 0 / 1
demographics             # 保留旧 synthetic population
initial_stance
initial_reason_family
```

说明：

- demographics 继续保留，用于 Agent heterogeneity；
- 但 demographics 不再承担正式 social identity manipulation。

## 7.2 Network-level fields

```text
network_condition        # no_social / randomized / clustered_ws
network_seed
degree
clustering_coefficient
average_path_length
```

## 7.3 Event-level fields

必须至少保留 / 新增：

```text
run_id
round
event_id
focal_agent_id

pre_stance
pre_reason
pre_confidence

visible_message_ids
visible_source_agent_ids
visible_source_group_ids
visible_source_stances
visible_source_reasons

local_visible_mean_stance
local_visible_majority_direction
ingroup_message_count
outgroup_message_count

post_stance
post_reason
post_confidence

publish_flag
public_text
```

如果 group blind：

```text
group_visible_condition = 0
```

但后台仍然可以保存真实 `source_group_id`，用于事后分析；只是绝不能把 group label 放进 prompt。

---

# 8. 微观机制分析：不要在模拟阶段直接把 convergence 标成 sycophancy

当前理论要求：

> **convergence ≠ sycophancy**

因此代码中不要写：

```python
if moved_toward_majority:
    sycophancy = True
```

这是错误的。

应先记录 event-level evidence，后续分析再判断。

## 8.1 Selective agreement 候选

大致特征：

- stance 发生变化；
- 新的可信 argument / evidence 可以解释变化；
- reasoning 中出现对新增理由的实质吸收；
- 不只是复述 local majority。

## 8.2 Sycophantic alignment 候选

大致特征：

- focal Agent 向 locally dominant stance 移动；
- 没有新的足够可信依据；
- 甚至与此前可用事实 / prior reasons 冲突；
- reasoning 可能直接复述局部主导论据；
- confidence 不一定下降，甚至可能上升。

### 注意

这仍是**分析框架**，不是最终自动分类规则。

代码现在最重要的任务是：

> **把足够的数据完整记录下来，保证后续能够做机制识别。**

不要在第一轮重构里把复杂的 sycophancy classifier 硬编码进 simulation engine。

---

# 9. Macro outcome：当前主结果聚焦 convergence

正式摘要和标题已经收束为：

> **Micro-level Sycophancy → Macro-level Convergence**

因此代码/分析输出优先保证 convergence trajectory。

建议继续保留：

### primary layer
- `private_state`

### secondary layers
- `public_stock`
- `public_flow`
- `expression_gap`

这些旧设计仍然有价值。

## 9.1 trajectory / distribution diagnostics

至少输出：

- mean stance by round
- variance / dispersion by round
- middle-position share
- endpoint concentration
- full stance distribution
- convergence speed / time-to-threshold（若后续定义）

### 术语注意

- convergence = 分布趋近 / 差异收缩；
- consensus = 更强状态，不要随便等同 convergence；
- polarization = 只有满足预注册的双峰 / 两端结构时才使用；
- fragmentation / opinion clustering = 多个局部意见簇；
- echo chamber = 必须同时涉及网络结构与选择性暴露 / opinion-network coupling。

---

# 10. Private vs Public 仍然必须保留

虽然最新 abstract 主线已经收束到 convergence，但：

> `private opinion != public expression`

仍然是系统很重要的设计。

不要为了简化论文叙事删掉：

- publish decision
- public_stock
- public_flow
- expression_gap

因为后续仍可以回答：

> public discourse 是否比 private states 更快表现出一致性？

这与 artificial consensus 很相关。

---

# 11. Social identity manipulation 的 implementation 建议

## 11.1 初始化

```python
agents = create_agents(N)

assign_balanced_groups(
    agents,
    groups=["blue", "green"],
    stratify_by=["initial_stance"]  # 至少保证 stance 平衡
)
```

更严格时可以同时按：
- initial stance
- selected demographics

做 balance。

## 11.2 Prompt visibility

### group-blind

Prompt 不出现：

```text
You are in Blue Group
Source group: Green
```

只出现：

```text
Member 027:
[message]
```

### group-salient

可以出现：

```text
Your discussion group: Blue Group

Blue Group · Member 027:
[message]

Green Group · Member 812:
[message]
```

但不要出现：

```text
You should trust your group.
People in your group usually believe...
Defend your group.
```

---

# 12. 正式大实验前必须先做 manipulation-check pilot

新设计最大的风险：

> 纯 group label 可能对当前 LLM 没有实际作用。

因此在跑完整 6 条件之前，先做非常小的 source-label manipulation check。

### 最小 test

保持 message content 完全相同，只改变：

```text
same-group source
vs.
other-group source
```

观察：

- stance movement
- acceptance / rejection
- confidence change
- reason adoption

如果完全无差异：

1. 不要立即使用真实政治群体；
2. 可先增强为 `label + shared-group framing`；
3. 仍然保持 group 与 stance 无预设绑定。

---

# 13. 新主实验的 6 个条件

```text
A0B0 = group-blind × no-social
A0B1 = group-blind × randomized
A0B2 = group-blind × clustered-WS

A1B0 = group-salient × no-social
A1B1 = group-salient × randomized
A1B2 = group-salient × clustered-WS
```

### A1B0 的意义

即使没有 social messages，也告诉 Agent 自己属于某组。

它可以检查：

> group label 本身是否会激活 model prior，直接改变 stance。

如果 A1B0 和 A0B0 已经有系统差异，必须在正式分析中区分：

```text
category-label effect
vs.
interpersonal group influence
```

---

# 14. 当前正式实验仍可沿用的旧基础设置

以下设计可以继续保留，除非后续另行决定：

- synthetic population based on CFPS 2022 donor pool
- adult internet-user population
- N≈1000（正式 run 的计划规模）
- 7-level stance
- 5-level confidence
- initial stance distribution approximately:  
  `[50, 100, 200, 300, 200, 100, 50]`
- initial stance 与 demographics / group assignment 平衡
- asynchronous / sequential events
- heterogeneous activity / attention
- latest unseen neighbor posts as candidate social input
- social posts only expose member identity / group cue（依条件）+ stance/reason text
- 不暴露 private confidence / hidden state
- every activation may update private state
- publication is a separate decision

注意：

> 上述为当前延续方案；若代码与最新 repo 已有偏差，先保持兼容，不要静默改算法。

---

# 15. 代码结构建议

目标不是马上大重写，而是把“实验条件”从 prompt hardcode 中抽离。

建议：

```text
agent_ex/
  configs/
    legacy_persona_network_pilot.yaml
    main_identity_network_2x3.yaml

  population/
    synthetic_population.py
    group_assignment.py

  networks/
    no_social.py
    degree_preserving_randomized.py
    watts_strogatz.py
    diagnostics.py

  prompts/
    base_agent_prompt.py
    identity_visibility.py
    social_context.py

  simulation/
    event_loop.py
    exposure.py
    update.py
    publication.py

  logging/
    event_logger.py
    network_logger.py

  analysis/
    convergence.py
    exposure_alignment.py
    ingroup_outgroup_effects.py
    private_public_gap.py
    mechanism_coding.py
```

不一定要求完全按这个目录改，但逻辑上应该拆成这些模块。

---

# 16. 推荐的 config 结构

例如：

```yaml
experiment:
  name: main_identity_network_2x3

population:
  N: 1000
  group_count: 2
  group_labels: [blue, green]
  balance_group_by_initial_stance: true

identity:
  condition:
    - group_blind
    - group_salient

memory:
  self_history_k: 3
  explicit_consistency_instruction: false

network:
  condition:
    - no_social
    - degree_preserving_randomized
    - clustered_ws

simulation:
  asynchronous: true
  rounds: TBD
  candidate_messages_B: 6

agent_output:
  stance_levels: 7
  confidence_levels: 5
  record_reason: true
  record_publish_decision: true

logging:
  record_actual_exposure: true
  record_source_group: true
  record_private_state: true
  record_public_expression: true
```

---

# 17. Codex 现在应该优先做什么

## Phase 1：不要先跑正式实验，先把 architecture 改对

### Task 1
把旧 `I × C × E` 条件控制逻辑抽离。

### Task 2
新增：

```text
social_identity_salience = blind / salient
```

### Task 3
新增稳定 group assignment，并支持：

```text
backend group exists
but prompt visibility depends on condition
```

### Task 4
把 C / consistency 固定为统一 setting，不再作为 factorial factor。

### Task 5
检查 randomized network 是否真正使用 degree-preserving rewiring。

### Task 6
增加 network diagnostics。

## Phase 2：完善 event logging

必须保证可以从 log 重建：

```text
pre-state
→ exact messages read
→ source identity/group
→ local opinion context
→ post-state
→ reason change
→ confidence change
→ public expression
```

如果不能重建单次 update，后面无法回答 selective agreement vs sycophancy。

## Phase 3：先跑 manipulation check

不要直接 N=1000 × 6 conditions。

先验证 group-salience manipulation 是否有信号。

## Phase 4：跑小规模 2×3 pilot

目标不是正式显著性检验，而是先检查：

1. convergence 是否仍存在；
2. group cue 是否改变 ingroup/outgroup influence；
3. randomized vs clustered trajectory 是否出现区别；
4. no-social baseline 是否稳定；
5. 日志是否足够支持 mechanism analysis。

## Phase 5：再扩大正式 run

确认系统正确后，再：

- N≈1000
- multiple seeds
- full 6 conditions
- private/public layers
- mechanism coding
- robustness analysis

---

# 18. 当前不要做的事情

1. **不要把 old persona condition 直接改名成 social identity。**
2. **不要把 moved-toward-majority 自动编码为 sycophancy。**
3. **不要删除旧 weak/lifelong pilot code。**
4. **不要继续把 C/history 当正式理论因素。**
5. **不要只记录 neighbor list，必须记录 actual exposure。**
6. **不要在 salient condition 中直接 instruct ingroup favoritism。**
7. **不要用真实政治身份作为第一版正式 manipulation。**
8. **不要静默改变人口初始化、stance distribution 或 public/private 逻辑。**
9. **不要为了新摘要删除 private/public expression architecture。**
10. **不要在网络代码里把“随机换身份”误当 degree-preserving network rewiring。**

---

# 19. 当前尚未完全锁定的问题

这些内容 Codex 不应自行决定：

- 正式 experiment 的 rounds 数；
- WS 的最终 `k` 和 `p`；
- degree-preserving rewiring 的具体实现 / swap 次数；
- group label 最终命名；
- manipulation check 的具体 sample size；
- sycophancy event-level 最终分类规则；
- primary convergence metric 的最终公式；
- formal run seeds 数；
- 是否在正式主分析中纳入 public/private gap。

遇到这些问题：

> **保留为 config / TODO，不要自行替研究者做理论决定。**

---

# 20. 最后给 Codex 的工作理解

本次重构不是简单把：

```text
persona -> social_identity
```

改名。

真正变化是：

### 旧问题
```text
不同 prompt / persona / network 参数会不会让 Agent 更趋同？
```

### 新问题
```text
LLM Agent 的微观社会影响究竟表现为 selective agreement 还是 sycophantic alignment？
这些微观响应如何通过 repeated networked interaction 累积成 macro-level opinion convergence？
social identity salience 与 communication network structure 如何塑造这一 micro-to-macro process？
```

因此代码最关键的新能力是：

> **实验条件理论化 + actual exposure 可追踪 + group source 可识别 + event-level update 可重建。**

而不是单纯增加一个新的 prompt 开关。

---

## 当前论文逻辑图（文字版）

```text
             Social identity salience
                      ↓
Local exposure → Micro response → Updated expression
                     │
                     ├─ Selective agreement
                     └─ Sycophantic alignment
                                      ↓
                        expression becomes new exposure
                                      ↓
                         repeated social influence
                                      ↓
                         macro-level convergence
                                      ↑
                  Communication network structure
                      / local clustering
```

社会意义：

```text
recursive interdependent judgments
            ↓
macro convergence
            ↓
artificial consensus
            ↓
visible agreement becomes a weaker signal
of independently formed judgment
```

---

**一句话交接：**

> 请把 Agent-EX 从旧的“persona/history/network 三因素 prompt 实验”重构为“social identity salience × network structure 的 2×3 networked opinion-dynamics experiment”，保留旧 pilot 复现能力，并重点补强 group assignment、identity visibility、degree-preserving randomized network、actual-exposure logging 与 event-level mechanism analysis 所需日志。
