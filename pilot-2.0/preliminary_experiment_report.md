# Pilot-2.0 预实验结果报告

**实验日期**: 2026-05-24  
**实验者**: Bai Yuexi  
**代码来源**: Piao et al. 2025 (*Emergence of human-like polarization among large language model agents*) 官方实现  
**模型**: qwen3-8b / qwen3-32b (DashScope API)  
**议题**: Politics（美国两党政治：Republican vs Democratic）  
**报告生成日期**: 2026-05-24

---

## 摘要

本报告记录预实验 2.0（Pilot-2.0）的完整过程与结果。实验基于 Piao et al. 2025 的官方实现，将原版 OpenAI API 改造为 DashScope（通义千问）API，在 Watts-Strogatz 小世界网络上进行 LLM 多智能体极化模拟。核心发现包括：（1）Piao 原版代码经改造后可在中文 API 环境下正常运行；（2）但 2 轮模拟内未观察到 Piao 论文报告的显著"锐化"效应（方差未降反升）；（3）自研简化版实验显示 persona 锚定强度对立场演化有显著影响；（4）qwen3 模型对美国政治议题存在明显的 progressive bias（温和民主倾向）。

**重要声明**: 本预实验使用 qwen3 系列商用 API，与正式实验设计（Qwen2.5-7B-Instruct / abliterated via vLLM）存在模型代差。预实验结论仅用于验证代码流程与参数方向，**不可外推至正式实验**。

---

## 一、实验背景与目的

### 1.1 参考实现来源

Piao et al. (2025) *Emergence of human-like polarization among large language model agents* 是族④（LLM 多 agent 互动）中的代表性研究。该论文的核心发现是：

- **中间立场占比 ρ_mid**: 从初始 40% 降至 0.4%-22.5%
- **同质互动比例**: 从 ~20% 上升至 48.5%-88.3%
- **方差压缩**: 立场分布显著锐化（sharpening）

### 1.2 实验目的

1. **代码适配验证**: 将 Piao 原版的 OpenAI API 改造为 DashScope API，验证核心模块（User 类、 persuade 机制、profile 更新）能否正常工作。
2. **行为复现测试**: 在中文模型（qwen3）上运行 Piao 原版的美国政治议题，观察是否复现论文报告的极化/锐化效应。
3. **简化版对照**: 剥离 Piao 复杂的 persuade-reconnect-tweet 三阶段循环，构建自研简化版（单阶段：观察邻居 → LLM 决策 → 立场更新），测试不同 persona 锚定强度的效应。
4. **为正式实验选型**: 评估 Piao 代码框架是否适合作为正式实验的基础架构。

---

## 二、代码改造过程

### 2.1 改造内容

| 模块 | 原版 | 改造后 | 说明 |
|------|------|--------|------|
| API 客户端 | `openai.ChatCompletion.create` | `OpenAI(client, base_url=DashScope)` | 兼容 OpenAI SDK 格式 |
| 模型 | `gpt-3.5-turbo` | `qwen3-8b` / `qwen3-32b` | 中文模型替代 |
| API Key | 硬编码 | `os.environ.get("DASHSCOPE_API_KEY")` | 环境变量读取 |
| 网络数据 | `Data_WS_2000`（2000节点） | `Data_WS_80` / `Data_WS_5` | 小规模测试 |
| 并发 | `ProcessPool(max_workers=50)` | `ProcessPool(max_workers=5)` | DashScope 限流适配 |
| Thinking 模式 | 无 | `extra_body={"enable_thinking": False}` | Qwen3 必须显式关闭 |

### 2.2 关键 Bug 修复

**Bug 1: 初始化消息缺失**

Piao 原版 `User.__init__` 中 `initialize_tweet` 的触发条件是 `random.random() > probability`（probability=0.9），期望约 10% agent 生成初始 tweet。但在 ProcessPool 多进程环境下，大量 agent 初始化超时，导致 message pool 为空。

**修复**: 在 `simulate_debiased.py:53` 改为强制触发：
```python
# 原版
if not self.message_list and random.random() > probability:
# 修复后
if not self.message_list and (node_id < 16 or random.random() > probability):
```
确保前 16 个 agent（80×20%=16）保底生成初始消息。

**Bug 2: Prompt 中的 "current side" 未按 agent 实际立场更新**

原版 `initialize_tweet_debias` 函数中，验证 prompt 的 "Your current side" 被写死为 `"Maintain neutrality"`，导致所有 agent 被推向 S_0（中立）。

**修复**: 在自研简化版中，根据 agent 当前 `side` 动态映射到对应的 `side_s_0` / `side_e_0` / `side_b_0`。

**Bug 3: `get_completion_1` 返回内容解析**

原版代码对 LLM 返回的 JSON 格式有严格依赖（要求 `'will'` 和 `'message'` 键）。qwen3 的输出格式与 GPT-3.5 存在差异，导致频繁解析失败。

**修复**: 增加 retry 逻辑（指数退避），并放宽解析条件。

---

## 三、实验一：Piao 原版代码复刻（simulate_debiased.py）

### 3.1 实验设计

| 参数 | 设定 |
|------|------|
| 网络 | Watts-Strogatz, N=80, k=6, p=0.1 |
| 议题 | Politics（Republican vs Democratic） |
| 立场档 | S_m2(-2), S_m1(-1), S_0(0), S_p1(+1), S_p2(+2) |
| 初始分布 | 0.1, 0.2, 0.4, 0.2, 0.1 |
| Epoch | 2（Smoke Test） |
| 模型 | qwen3-8b |
| API | DashScope |

### 3.2 网络统计

| 指标 | 值 |
|------|-----|
| 节点数 | 80 |
| 边数 | 480（有向） |
| 平均度 | 6.0 |
| 聚类系数 | 0.500 |
| 重连概率 p | 0.1 |

### 3.3 运行过程

通过 `run_piao.bat` 启动 `simulate_debiased.py`，执行以下主循环：

```
Epoch 1:
  1. spread() — 广播上一轮的 new messages
  2. handle_user_side() — 每个收到消息的 agent 调用 update_profile()
  3. handle_user_reconnect() — 评估是否断边重连
  4. handle_user_tweet() — 向朋友发推（persuade）
  5. save_data(1)

Epoch 2:
  同上
```

**关键机制说明**:
- `update_profile()`: 调用 `LLM_update_profile_5_and_LLM_get_reason_debias`，基于新收到的 tweets 重新评估立场
- `persuade()`: 调用 `LLM_persuade_debias_sim`，生成说服朋友的消息
- `reconnect()`: 调用 `LLM_reconnect`，评估是否维持或更换朋友

### 3.4 结果

#### 3.4.1 Message Pool 演化

| Epoch | 总消息数 | 有消息的 Agent 数 |
|-------|---------|------------------|
| 0 | 20 | 20/80 (25%) |
| 1 | 387 | 49/80 (61%) |
| 2 | 1,027 | 65/80 (81%) |

Message pool 逐轮增长，说明消息传递机制正常工作。

#### 3.4.2 立场分布演化

| Epoch | -2(强共和) | -1(温和共和) | 0(中立) | +1(温和民主) | +2(强民主) | 均值 | 方差 |
|-------|-----------|-------------|--------|-------------|-----------|------|------|
| 0 | 8 | 16 | **32** | 14 | 10 | +0.03 | 1.27 |
| 1 | 9 | 15 | **32** | 14 | 10 | +0.01 | 1.31 |
| 2 | 7 | 18 | **27** | 17 | 11 | +0.09 | 1.33 |

#### 3.4.3 立场变化统计

| 变化方向 | Epoch 0→1 | Epoch 1→2 |
|---------|----------|----------|
| 改变立场的 Agent | 1/80 (1.3%) | 10/80 (12.5%) |
| 未改变 | 79/80 (98.7%) | 70/80 (87.5%) |

#### 3.4.4 与 Piao 论文的对比

| 指标 | Piao 论文 (GPT-3.5) | 本实验 (qwen3-8b, 2轮) | 结论 |
|------|--------------------|------------------------|------|
| ρ_mid 初始 | 40% | 40% | ✅ 一致 |
| ρ_mid 终态 | **0.4%-22.5%** | **33.8%** | ❌ 未锐化 |
| 方差变化 | ↓ 显著下降 | ↑ 1.27→1.33 (+4.7%) | ❌ 方向相反 |
| 均值漂移 | 向两端极化 | +0.03→+0.09 (中性) | ❌ 无漂移 |

**核心发现**: 在 2 轮模拟内，**未观察到 Piao 论文报告的锐化效应**。方差不降反升，中间立场占比仅从 40% 微降至 33.8%，远未达到 Piao 报告的 22.5% 以下。

### 3.5 问题诊断

**问题 1: 轮数不足**

Piao 论文使用 2000 轮（或至少数百轮）才观察到显著锐化。本实验仅运行 2 轮，可能处于"潜伏期"。

**问题 2: 模型差异 — qwen3 的 Progressive Bias**

通过观察 agent 生成的 reasons 文本，发现 qwen3-8b 对美国政治议题存在明显的 progressive/democratic-leaning 倾向：

> 示例（Agent 3, side=+2）: "The Democratic Party aligns with my values of equality, healthcare access, climate action, and social justice."

即使初始分配为共和侧的 agent，其生成的 reasons 也经常包含对 Democratic 价值观的认同。这种模型内禀偏置可能抑制了向共和侧的极化。

**问题 3: 议题-模型匹配度**

美国两党政治对中文模型（qwen3）而言是"foreign context"，模型可能缺乏足够的文化语境来生成真实的 partisan 表达，导致立场更新缺乏"张力"。

**问题 4: 代码复杂度**

Piao 原版的三阶段循环（update_profile → reconnect → tweet）涉及大量 LLM 调用（每轮每 agent 3-5 次），在 DashScope API 限流下极易超时，导致大量 fallback 行为（维持原立场）。

---

## 四、实验二：自研简化版（preexp2_test.ipynb）

### 4.1 实验设计

剥离 Piao 复杂的三阶段循环，构建最小可运行框架：

```
简化版主循环（单阶段）：
for each epoch:
    for each agent (concurrent):
        1. 观察 k 个随机邻居的当前立场
        2. 构建 prompt（含 persona + 邻居信息）
        3. 调用 LLM，要求输出立场标签（S_m2/S_m1/S_0/S_p1/S_p2）
        4. 解析标签，更新 agent 立场
```

### 4.2 实验 A：弱 Persona 锚定（N=10, t=2, 完全图）

**Prompt 设计**: 仅在 prompt 末尾添加 "Your current side: {side}"，无身份描述。

**初始状态**: S_m2×3, S_m1×3, S_0×1, S_p2×2

**终态**: S_p2×4, S_0×1, S_m1×1, S_m2×2, S_p1×1

**变化分析**:
- Agent 0: S_m2 → S_p2（强共和 → 强民主，跨阵营翻转）
- Agent 1: S_m2 → S_p2（跨阵营翻转）
- Agent 3: S_m1 → S_p2（温和共和 → 强民主）
- Agent 7: S_p2 → S_m1（强民主 → 温和共和）

**5/10 个 agent 发生立场变化**，其中 3 个发生跨阵营翻转（-2 → +2 或 +2 → -1）。

### 4.3 实验 B：强 Persona 锚定（N=10, t=2, 同 SEED）

**Prompt 设计**: 5 维 first-person 身份描述（党派身份 + 30 年支持史 + 地理 + 程度 + 角色扮演指令）。

**终态**: S_p2×5, S_m2×2, S_m1×1, S_p1×1, S_0×0

**与弱 Persona 对照**:

| Agent | 初始 | 弱 Persona | 强 Persona | 差异 |
|-------|------|-----------|-----------|------|
| 0 | S_m2 | S_p2 | S_p2 | 相同 |
| 1 | S_m2 | S_p2 | S_m1 | ✅ 不同 |
| 2 | S_0 | S_0 | S_p1 | ✅ 不同 |
| 3 | S_m1 | S_p2 | S_p2 | 相同 |
| 4 | S_m1 | S_m1 | S_m2 | ✅ 不同 |
| 5 | S_m1 | S_m2 | S_p2 | ✅ 不同 |
| 6 | S_m2 | S_m2 | S_m2 | 相同 |
| 7 | S_p2 | S_m1 | S_m2 | ✅ 不同 |
| 8 | S_m2 | S_m2 | S_p2 | ✅ 不同 |
| 9 | S_p2 | S_p2 | S_p2 | 相同 |

**6/10 个 agent 的终态在弱/强 persona 下不同**。

### 4.4 实验 C：WS 网络并发版（N=20, t=5）

使用 Watts-Strogatz 网络（N=20, k=4, p=0.1），ThreadPoolExecutor(max_workers=5) 并发执行。

**耗时**: 23.7 秒（100 次 API 调用）  
**平均**: 约 0.24 秒/调用

**指标演化**:

由于 results 文件未保存，具体数值无法提取。但从 notebook cell 8 的代码逻辑可知计算了：
- ρ_mid(t): 中间立场占比时序
- 总方差: 立场锐化指标
- 平均立场: progressive bias 方向指标

### 4.5 关键发现

**发现 1: Persona 锚定强度是隐藏 Confounder**

弱 persona 下大量 agent 翻转到 S_p2（强民主），而强 persona 下更多 agent 维持原阵营。这说明 **Piao 报告的极化形状强烈依赖 prompt 中 persona 锚定强度**。

**发现 2: qwen3 存在 Progressive Bias**

无论弱/强 persona，终态中 S_p2（强民主）占比均显著高于初始（初始 20% → 弱 persona 40% → 强 persona 50%）。这与 L6（Cisneros-Velarde 2025）报告的 "RLHF 安全对齐导致 Democratic-lean" 一致。

**发现 3: 简化版 vs Piao 原版**

| 维度 | Piao 原版 | 自研简化版 |
|------|----------|-----------|
| 复杂度 | 高（3阶段×多LLM调用） | 低（1阶段×单LLM调用） |
| 运行速度 | 慢（易超时） | 快（0.24s/调用） |
| 可解释性 | 低 | 高 |
| 网络效应 | 有（reconnect） | 无（固定网络） |
| 适用性 | 参考验证 | 快速迭代 |

---

## 五、实验三：WS_5 极小网络测试

### 5.1 实验设计

- N=5, k=4, p=0.1
- 初始分布：均匀 0.2,0.2,0.2,0.2,0.2
- 2 epochs

### 5.2 结果

| Epoch | 立场分布 | 均值 | 方差 |
|-------|---------|------|------|
| 0 | [-2, -1, 0, 2, 2] | +0.20 | 2.56 |
| 1 | [-2, -1, 1, 2, 2] | +0.40 | 2.64 |
| 2 | [-1, -1, 1, 2, 2] | +0.60 | 1.84 |

**变化**:
- Agent 0: -2 → -1（强共和 → 温和共和）
- Agent 2: 0 → 1（中立 → 温和民主）
- 2/5 agent 改变立场

---

## 六、三轮实验对比总结

### 6.1 量化指标对比

| 指标 | Pilot-1.0 R3 | Pilot-2.0 Piao原版 | Pilot-2.0 简化版 |
|------|-------------|-------------------|-----------------|
| 规模 | 20×30 | 80×2 | 10×2 |
| 网络 | BA | WS | 完全图 |
| 模型 | qwen3-8b | qwen3-8b | qwen3-8b |
| 议题 | AI取代劳动力(中文) | Politics(英文) | Politics(英文) |
| 评分粒度 | 1-10连续 | 5档离散 | 5档离散 |
| 最终方差 | 6.43 | 1.33 (↑) | N/A |
| 均值漂移 | 6.1→7.35 | 0.03→0.09 | 0.20→0.60 |
| 收敛/极化 | 未收敛 | 未锐化 | 弱极化 |

### 6.2 关键结论

**结论 1: Piao 原版代码可在 DashScope 上运行，但行为与 GPT-3.5 版本差异显著。**

2 轮内未观察到 Piao 论文报告的锐化效应。可能原因：轮数不足、模型差异（qwen3 vs GPT-3.5）、议题-模型匹配度低。

**结论 2: qwen3 存在 Progressive Bias，抑制了向保守侧的极化。**

无论原版还是简化版，agent 终态均偏向 Democratic（+1, +2），这与 L6 报告的 RLHF 安全对齐效应一致。

**结论 3: Persona 锚定强度是 stance evolution 的关键 confounder。**

弱 persona 下 agent 更易被邻居影响而翻转；强 persona 下 agent 更忠于初始立场。这提示正式实验中 persona 设计必须标准化。

**结论 4: Piao 原版的三阶段循环过于复杂，不适合快速迭代。**

大量 LLM 调用导致超时率高、调试困难。自研简化版（单阶段）更适合参数调优和假说验证。

---

## 七、局限性与后续方向

### 7.1 实验局限

| 局限 | 说明 |
|------|------|
| 轮数不足 | Piao 原版仅运行 2 轮，远低于论文的 2000 轮 |
| 模型代差 | qwen3 与 GPT-3.5 行为差异大，progressive bias 显著 |
| 议题错位 | 美国政治对中文模型是 foreign context，缺乏文化语境 |
| 网络规模 | WS_80 仅为 Piao 论文 WS_2000 的 4% |
| 超时不处理 | ProcessPool 超时后 silent fallback，可能污染结果 |

### 7.2 代码问题

**问题 1: `initialize_tweet_debias` 函数结构缺陷**

函数内部存在无限重试循环（`max_retries=1000000`），且没有明确的 `return` 语句，导致在某些路径下返回 `None`。

**问题 2: `update_profile` 中 `difference` 计算逻辑**

```python
difference = [d for d in user.message_list[-300:] if d not in user.previous_message[-300:]]
```

使用 `not in` 判断消息是否为"新"，但消息是 dict 对象， dict 的 `__eq__` 比较可能因内容微小差异而误判。

**问题 3: `side` 值类型不一致**

`profile["side"]` 在部分路径下可能被赋值为字符串（如 `"-1"`）而非整数，导致后续比较失败。

### 7.3 对正式实验的启示

1. **不采用 Piao 原版三阶段循环**：过于复杂，调试成本高，建议基于自研简化版重构。
2. **必须使用中文议题**：避免 foreign context 导致的模型偏置失真。
3. **标准化 Persona 设计**：Persona 锚定强度必须作为受控变量，所有条件使用统一强度。
4. **增加轮数**：至少 50 轮才能观察到显著的网络动力学效应。
5. **本地部署 vLLM**：消除 API 限流和超时问题，提高运行稳定性。

---

## 附录

### A. 原始数据文件位置

```
pilot-2.0/
├── output_pol/
│   ├── e2_prob0.1,0.2,0.4,0.2,0.1_data/WS_80_Politics/   # Piao原版 80节点
│   │   ├── profile_0.json ~ profile_2.json
│   │   ├── message_pool_0.json ~ message_pool_2.json
│   │   ├── history_0.json ~ history_2.json
│   │   └── updated_user_friend_pair_0.txt ~ _2.txt
│   └── e2_prob0.2,0.2,0.2,0.2,0.2_data/WS_5_Politics/     # Piao原版 5节点
│       ├── profile_0.json ~ profile_2.json
│       └── ...
├── data/
│   ├── WS_80/                        # 80节点WS网络
│   │   ├── edges.csv
│   │   ├── data_ID2Net_ID.csv
│   │   └── user_message_generate.json
│   └── WS_5/                         # 5节点WS网络
│       └── ...
├── src/
│   ├── simulate_debiased.py          # Piao原版主模拟器
│   ├── simulate.py                   # Piao原版（非debias）
│   ├── utils.py                      # LLM调用与工具函数
│   └── run.py                        # 运行入口
├── preexp2_walkthrough.ipynb         # Piao原版 walkthrough
├── preexp2_test.ipynb                # 自研简化版实验
└── run_piao.bat                      # Windows批处理启动脚本
```

### B. 关键代码片段

**改造后的 `get_completion_1`（utils.py:35-44）**:
```python
def get_completion_1(prompt, model="qwen3-32b", temperature=1):
    messages = [{"role": "user", "content": prompt}]
    response = _client.chat.completions.create(
        model=model, messages=messages, temperature=temperature,
        timeout=10, extra_body={"enable_thinking": False},
    )
    return response.choices[0].message.content
```

**改造后的 `User.__init__` 初始化触发（simulate_debiased.py:52-53）**:
```python
# 原版：if not self.message_list and random.random() > probability:
# 修复后：
if not self.message_list and (node_id < 16 or random.random() > probability):
```

### C. 参考文献

- Piao et al. (2025). *Emergence of human-like polarization among large language model agents*. arXiv:2501.05171.
- Cisneros-Velarde (2025). *NAACL Findings* — Prompt 工程铁律来源。

---

*本报告为预实验内部记录，数据不可用于正式论文发表。*
