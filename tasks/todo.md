# 研究推进待办清单

> 创建时间：2026-03-24
> 最后更新：2026-03-31
> 关联文档：research_design.md · 组会汇报/实验进展报告_20260331.md

---

## 📚 Phase -1：文献查阅与方案制订（已完成）

> 状态：✅ 已完成
> 交付物：research_design.md v1.0、实验进展报告

**已完成工作**：
- [x] 理论文章修订（术语清理、概念聚焦、实践场域补充）
- [x] 研究设计文档更新（RQ、指标、参数、实验分组）
- [x] 关键设计决策确定（8 项决策，见实验进展报告 2.2.3）
- [x] 待办清单细化（6 Phases，敏感性分析矩阵）

---

## 🔍 Phase 0 前置准备（优先级：高）

> 目标：完成文献查阅与参数锁定，为 Phase 1 环境验证做准备

- [ ] **查阅文献①：话题选定**

  查阅意见动力学 & LLM 社会模拟文献（2023-2026），参考已有极化研究使用的标准话题
  - [ ] 确定主实验话题（1 个，候选：AI 取代劳动力 / 生育政策 / 性别平等）
  - [ ] 确定 Phase 0 备选话题（1 个）
  - [ ] 写入 `config/experiment.yaml`
  - **截止日期**：2026-04-05

- [ ] **查阅文献②：temperature 设置**

  查阅 LLM 社会模拟 / agent-based modeling 文献，确认 temperature 主流先例
  - [ ] 若有明确先例 → 直接引用固定，无需测试
  - [ ] 若文献不一致 → 列入 Phase 0 补测（0.3 / 0.7 / 1.0）
  - **截止日期**：2026-04-05

- [ ] **查阅文献③：BA 网络参数设定**

  查阅社交网络模拟 / 意见动力学文献，确认 BA 网络参数（m 值）的合理范围
  - [ ] 查找使用 BA 网络的 LLM 社会模拟论文（2023-2026）
  - [ ] 确认 m 值设定先例（m=2 或 m=3 或其他）
  - [ ] 若文献不一致 → 通过 Phase 0 敏感性分析确定（m=2 vs m=3）
  - **截止日期**：2026-04-05
  - **背景疑问**：
    - BA 网络生长机制：新节点依次加入，每个新节点连接 m 条边到已有节点（优先连接度数高的节点）
    - 最终结果：早期节点可能成为 hub（50+ 邻居），晚期节点至少 m 个邻居
    - 因此仍需邻居采样：hub 节点邻居过多，无法全部读取

- [ ] **确认 abliterated 模型**

  在 HuggingFace 搜索 `Qwen2.5-7B-Instruct-abliterated`
  - [ ] 若有现成版本 → 记录模型卡链接，备用
  - [ ] 若无 → 计划在 Phase 1 云端自行生成（FailSpy/abliterator）
  - **截止日期**：2026-04-05

---

## 🖥️ Phase 1：环境验证（优先级：高）

> 目标：AutoDL 环境跑通，两个模型均可正常推理

- [ ] 注册 AutoDL 账号，充值 ¥50
- [ ] 租用 RTX 4090（1 小时），安装 vLLM，加载 `Qwen2.5-7B-Instruct`
- [ ] 发送单条结构化 Prompt，验证 `【评分：X】` 格式正确解析
- [ ] 获取 abliterated 模型（HuggingFace 下载 或 运行 FailSpy/abliterator 自行生成）
- [ ] 验证 abliterated 模型能正常输出实质性极端观点（单条对比测试）
- [ ] **备选**：确认实验室服务器是否可用（组会讨论）

**vLLM 启动命令参考**：
```bash
# 网络 A：Instruct 模型
python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-7B-Instruct \
    --port 8000 \
    --max-num-seqs 20 \
    --gpu-memory-utilization 0.90

# 网络 B：abliterated 模型（分时运行）
python -m vllm.entrypoints.openai.api_server \
    --model /path/to/Qwen2.5-7B-Instruct-abliterated \
    --port 8000 \
    --max-num-seqs 20 \
    --gpu-memory-utilization 0.90
```

---

## 💻 Phase 2：MVP 开发

> 目标：5 agents × 5 轮跑通，数据流完整，指标可计算

- [ ] `src/network.py`
  - BA 网络构建，支持参数化 N、m
  - 输出平均度、最大度等网络统计量

- [ ] `src/agent.py`
  - Agent 类：角色设定、历史记录（滑窗 k=3）
  - 度数加权邻居采样（参数化 α）

- [ ] `src/llm_client.py`
  - vLLM 异步调用封装
  - `【评分：X】` 正则提取
  - 解析失败异常记录

- [ ] `src/simulator.py`
  - 同步更新主循环
  - 快照读取 → 并发生成（Semaphore） → 统一写入 → 下一轮

- [ ] `src/metrics.py`
  - [ ] 方差 / 均值时序（每轮）
  - [ ] BGE 嵌入相似度（`BAAI/bge-large-zh-v1.5`）
  - [ ] 角色一致性得分（cosine similarity vs 初始角色描述）
  - [ ] Self-BLEU（文本多样性补充）
  - [ ] 收敛半衰期（方差降至初始 50% 所需轮数）

- [ ] **最小验证**：5 agents × 5 轮，确认完整数据流与指标输出

**项目文件结构**：
```
experiment/
├── config/experiment.yaml      # 实验参数配置
├── src/                        # 核心代码模块
├── experiments/                # 实验执行脚本
├── results/                    # 实验结果
└── analysis/                   # 分析脚本
```

---

## 🔬 Phase 0：小规模试点（20 agents × 50 轮）

> 目标：验证均质化现象，确定正式实验参数（m、α、轮数、temperature）

**敏感性分析矩阵**（两组模型各跑 4 种组合，共 8 次）：

| 组合 | m 值 | α值 | Instruct 状态 | abliterated 状态 |
|------|-----|-----|---------------|------------------|
| 1 | 2 | 0 | ⬜ 待跑 | ⬜ 待跑 |
| 2 | 2 | 0.5 | ⬜ 待跑 | ⬜ 待跑 |
| 3 | 3 | 0 | ⬜ 待跑 | ⬜ 待跑 |
| 4 | 3 | 0.5 | ⬜ 待跑 | ⬜ 待跑 |

- [ ] 跑完全部 8 次，绘制方差收敛曲线
- [ ] **决策：确定正式实验 m 值**（写入 experiment.yaml）
- [ ] **决策：确定正式实验 α 值**（写入 experiment.yaml）
- [ ] **决策：确定正式实验轮数**（50 轮足够 or 需延长）
- [ ] 若文献未锁定 temperature：补测 0.3 / 0.7 / 1.0，确定后写入 experiment.yaml

**决策规则**：
- 若各参数趋势一致（仅速度差异）→ 选收敛最清晰的组合用于正式实验
- 若某参数产生定性差异 → 正式实验需将该参数作为调节变量分析

---

## ⚙️ Phase 3：并发优化与正式实验

> 目标：200 agents × 50 轮 × 5 重复，两组实验数据全部收集

- [ ] Semaphore 从 10 开始逐步提升（目标 15-20），找到 RTX 4090 稳定上限
- [ ] 所有参数写入 `config/experiment.yaml`（N、m、α、k、temperature、轮数、话题）

**网络 A（Instruct）× 5 次重复**，结果保存至 `results/raw/network_A/`：
- [ ] Run 1
- [ ] Run 2
- [ ] Run 3
- [ ] Run 4
- [ ] Run 5

**网络 B（abliterated）× 5 次重复**，结果保存至 `results/raw/network_B/`：
- [ ] Run 1
- [ ] Run 2
- [ ] Run 3
- [ ] Run 4
- [ ] Run 5

**并发控制参考**：
```python
semaphore = asyncio.Semaphore(10)  # 从 10 开始，逐步测试至 15-20

async def bounded_task(agent_id, task):
    async with semaphore:
        result = await task
        return agent_id, result
```

---

## 📊 Phase 4：分析与写作准备

> 目标：产出可直接用于论文的图表与统计结果

**统计检验**：
- [ ] LMM 主检验：`方差 ~ 轮次 × 组别 + (1+轮次|run_id)`
- [ ] t 检验：收敛半衰期描述统计（均值 ± SD，两组对比）
- [ ] Spearman 检验：自报评分 vs BGE 嵌入位置相关性（ρ > 0.6 视为有效）

**主要图表**：
- [ ] 图 1（主图）：两组方差轨迹 + 95% 置信带（时序曲线）
- [ ] 图 2（机制图）：两组角色一致性得分随轮次变化
- [ ] 图 3（拓扑图）：模块度演化 + 社群数量变化
- [ ] 图 4（验证图）：BGE 嵌入相似度时序（与方差趋势对照）

**写作联动**：
- [ ] 论文方法论部分：写入同步更新、有限注意力采样的规范表述
- [ ] 论文局限性部分：异步更新、零模型基线两条局限性写入
- [ ] 论文结果部分：LMM 统计结果 + 图表解读

**预期里程碑**：
- 04-07：Phase 1 环境验证完成
- 04-14：Phase 2 MVP 开发完成
- 04-20：Phase 0 敏感性分析完成
- 04-30：Phase 3 正式实验数据采集完成
- 05-15：Phase 4 分析与图表产出完成

---

## ⏸️ Paper 2（暂缓，不在当前推进范围内）

> 网络 C：人类代理负熵干预

- [ ] 人类语料收集（1000 条，2022 年前，高极化）
- [ ] FAISS 向量索引构建
- [ ] RAG 检索模块实现（`src/human_proxy.py`）
- [ ] 网络 C（90% Instruct + 10% Human Proxy）实验设计与执行

---

## 📋 实验设计核心参数速查

| 参数 | 设定值 | 说明 |
|------|--------|------|
| 节点数 (N) | 200（正式）/ 20（Phase 0） | 导师建议：真实社会网络规模下限 |
| 拓扑结构 | BA 无标度网络 | m 值待 Phase 0 确定（候选 2/3） |
| 激活比例 | 40 节点/轮（20%） | 随机激活 |
| 交互轮数 | 50 轮 | 视 Phase 0 收敛曲线可调整 |
| Temperature | 0.7（暂定） | 待文献确认后固定 |
| 记忆窗口 | k=3 | 每邻居保留最近 3 轮发言 |
| 邻居采样 | 度数平方根加权（α=0.5），上限 10 | α值待 Phase 0 确定（候选 0/0.5） |
| 更新机制 | 同步更新 | 与 DeGroot/HK 经典模型对标 |

---

## 📝 实验分组速查

| 组别 | 模型构成 | 机制 | 用途 |
|------|---------|------|------|
| 网络 A（控制组） | 100% Qwen2.5-7B-Instruct | 测试 RLHF 对齐效应 | Paper 1 |
| 网络 B（对照组） | 100% abliterated | 安全向量切除对照 | Paper 1 |
| 网络 C（实验组） | 90% Instruct + 10% Human Proxy | 人类负熵干预 | Paper 2（暂缓） |

---

*此文档为 living document，每个阶段完成后持续更新状态。*
