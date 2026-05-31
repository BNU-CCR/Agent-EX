# 实验项目管理仓库

**研究者**: Bai Yuexi  
**创建时间**: 2026-04-03  
**GitHub**: https://github.com/572200469/Agent-EX

---

## 项目概述

本仓库包含两个独立项目：

| 项目 | 状态 | 说明 |
|------|------|------|
| **实验项目** | 🟢 进行中 | LLM-agent 介入下的在线意见演化机制研究 |
| 理论文章修订 | 🟡 已完成 | 已返给出版社终审 |

**当前 Paper 1 定位**（2026-05-31 更新）：

> **基于探索性 LLM-ABM 实验的机制识别研究**
>
> 当 LLM-agent 作为新型社交机器人进入在线讨论网络时，意见演化是如何在模型默认生成倾向、persona 条件、网络互动和历史表达之间共同形成的？

**核心发现**（pilot-3.0 正式实验，四条件 × 五 seed）：
- **weak persona** 条件下，agent 更容易向高分端（10分）收敛，最终均值 9.23-10.00，方差降至 0.00-3.48，中间立场基本消失
- **lifelong strong persona** 条件下，agent 保留更多中间立场（29%-35%）和差异化理由，最终均值 7.28-7.92，方差维持在 2.68-4.10
- **BA / WS 网络结构**在 N=20 小规模实验中终点效应有限（network 主效应不显著）
- **"多极化不等于多样性"**：weak 条件下理由高度同质化（"AI将重塑劳动市场""技能转型不可避免"），而 lifelong strong 条件下保留更多基于个人经历的理由

---

## 目录结构

```
Agent-EX/
├── design/                    # 【共享】跨版本设计文档
│   ├── research_design.md         # 技术方案（历史版本，05-23 大设计）
│   ├── todo.md                    # 待办清单
│   ├── methodology_review_2026-05-23.md  # 方法论反思与范式调整（历史）
│   ├── decisions_log.md           # 设计决策日志
│   ├── advisor_feedback.md        # 导师反馈与决策追踪
│   └── meetings/                  # 组会汇报材料
│       ├── 2026-05-28_组会汇报.md   # 关键：研究收口决策
│       └── ...
│
├── pilot-1.0/                 # 【预实验1.0】自研 BA 网络框架（2026-05-22）
│   ├── src/                       # 核心代码
│   ├── config/                    # 配置文件
│   ├── experiments/               # 实验运行脚本
│   ├── analysis/                  # 分析脚本
│   ├── results/                   # 三轮预实验结果（gitignored）
│   ├── preliminary_experiment_report.md  # 预实验1.0结果报告
│   └── ...
│
├── pilot-2.0/                 # 【预实验2.0】Piao et al. 2025 参考实现（2026-05-24）
│   ├── src/                       # 改造后的 Piao 代码
│   │   ├── simulate_debiased.py   # 主模拟器（DashScope API 改造）
│   │   ├── utils.py               # LLM 调用工具函数
│   │   ├── simulate.py            # 原版模拟器
│   │   └── run.py                 # 运行入口
│   ├── data/                      # 网络数据
│   │   ├── WS_80/                 # 80节点 Watts-Strogatz
│   │   └── WS_5/                  # 5节点极小网络
│   ├── docs/
│   │   └── LLM4Polarization_experimental_setting.pdf
│   ├── output_pol/                # Piao原版实验输出（gitignored）
│   ├── preexp2_walkthrough.ipynb  # Piao原版 walkthrough
│   ├── preexp2_test.ipynb         # 自研简化版实验 notebook
│   ├── preliminary_experiment_report.md  # 预实验2.0结果报告
│   └── run_piao.bat               # Windows 启动脚本
│
├── pilot-3.0/                 # 【正式实验】AI劳动力议题探索性实验（2026-05-30）
│   ├── src/                       # 核心代码（基于 pilot-1.0 重构）
│   │   ├── agent.py               # Agent 类与 Prompt（weak / lifelong strong）
│   │   ├── network.py             # BA / WS 网络构建
│   │   ├── llm_client.py          # DashScope API 客户端
│   │   ├── simulator.py           # 同步更新模拟器
│   │   ├── metrics.py             # 指标计算
│   │   └── config.py              # 配置加载
│   ├── run.ipynb                  # 主实验 notebook（Cell 0-15）
│   └── results/                   # 实验结果（gitignored）
│       ├── current_experiment/    # 四条件 × 五 seed 正式数据
│       └── paper_outputs/         # 论文图表与统计表
│
├── logs/                        # 工作日志
│   ├── 2026-05-22.md              # 预实验1.0
│   ├── notion-2026-05-23.md       # 05-23 交接（RLHF/abliterated 大设计）
│   └── notion-2026-05-31.md       # 05-31 交接（当前最新状态）
├── references/                  # 参考文献（Notion 统一管理）
└── README.md                    # 本文件
```

---

## 版本演进

| 版本 | 时间 | 代码来源 | 议题 | 规模 | 状态 | 核心发现 |
|------|------|---------|------|------|------|---------|
| **预实验 1.0** | 2026-05-22 | 自研 | AI劳动力（中文） | 20×30 | ✅ 完成 | 弱约束下快速高分端收敛；固执度+角色强化可保留多样性 |
| **预实验 2.0** | 2026-05-24 | Piao et al. 2025 | Politics（英文） | 80×2 | ✅ 完成 | persona 锚定强度是隐藏 confound；qwen3 存在 progressive bias |
| **正式实验 (pilot-3.0)** | 2026-05-30 | 基于 pilot-1.0 重构 | AI劳动力（中文） | 20×30×4条件×5seed | ✅ 完成 | weak persona → 高分端饱和；lifelong strong → 保留中间立场与理由多样性 |

**关键转折**（2026-05-28 组会）：
- 05-23 的 RLHF / abliterated / H1-H5 大设计 **暂缓进入 Paper 1**，移至 **Paper 2 储备**
- Paper 1 收口为：**探索性 LLM-ABM 机制识别**——聚焦 weak vs lifelong strong persona 在 AI 劳动力议题上的效应

---

## 实验设计速查（pilot-3.0 正式实验）

### 核心问题

当 LLM-agent 作为新型社交机器人进入在线讨论网络后，意见演化是如何在模型默认生成倾向、persona 条件、网络互动和历史表达之间共同形成的？

### 议题

**AI 是否会取代人类劳动力**（中文）

### 模型

- `qwen3.5-plus`（DashScope / 阿里云百炼）
- temperature = 0.7, top_p = 0.9, max_tokens = 180

### 实验条件（2×2 设计）

| 条件 | Persona | Network | 预期 |
|------|---------|---------|------|
| C1_weak_BA | weak | BA | 向高分端收敛 |
| C2_lifelong_BA | lifelong strong | BA | 保留中间立场 |
| C3_weak_WS | weak | WS | 向高分端收敛 |
| C4_lifelong_WS | lifelong strong | WS | 保留中间立场 |

### 规模

- N = 20 agents
- T = 30 rounds
- 每组条件 5 个随机种子：42, 43, 44, 45, 46

### 关键指标

| 指标 | 说明 |
|------|------|
| 最终均值 | 立场评分均值（1-10 Likert） |
| 最终方差 | 立场分布方差 |
| 中间立场比例 | 评分 4-6 的 agent 占比 |
| 极端比例 | 评分 ≤2 或 ≥9 的 agent 占比 |
| 方差下降幅度 | 初始方差 - 最终方差 |
| 收敛轮次 | 方差降至初始 50% 以下所需轮次 |

### ANOVA 核心结果

| 因变量 | Persona p | Network p | 解读 |
|--------|----------:|----------:|------|
| 最终均值 | **.001** | .891 | persona 显著影响均值 |
| 中间立场比例 | **<.001** | .821 | persona 显著保留中间立场 |
| 极端比例 | **<.001** | .901 | persona 显著降低极端化 |
| 收敛轮次 | **<.001** | 1.000 | persona 显著延迟收敛 |
| 最终方差 | .339 | .548 | **不显著**（方差本身不敏感） |

---

## 使用指南

### 运行正式实验（pilot-3.0）

```bash
cd pilot-3.0
jupyter notebook run.ipynb
```

Notebook 结构：
- Cell 0-5: 环境配置、API key、模块导入、角色定义、网络构建
- Cell 6-10: 实验参数设置、零交互 baseline、主实验循环、按 RUN_MODE 启动
- Cell 11-15: 结果汇总、绘图、解析审计、文本样本、论文统计分析与图表导出

`RUN_MODE` 可选：`smoke` / `main_one_seed` / `main_five_seeds`

### 运行预实验 1.0（历史参考）

```bash
cd pilot-1.0
jupyter notebook run_pilot.ipynb
```

### 运行预实验 2.0（Piao 参考实现）

```bash
cd pilot-2.0
# 方式1：Jupyter Notebook
jupyter notebook preexp2_test.ipynb

# 方式2：批处理（Windows）
run_piao.bat
```

---

## 论文写作进展

**当前状态**：课程论文版本基本完成（2026-05-31）

**标题**：
> 大模型 Agent 介入下的在线意见演化机制研究——基于探索性 LLM-ABM 实验的机制识别

**已完成部分**：
- ✅ 摘要与关键词
- ✅ 一、引言
- ✅ 二、文献综述（在线意见演化 / LLM 分布压缩 / LLM-agent 网络极化）
- ✅ 三、理论框架与研究假设
- ✅ 四、研究设计
- ✅ 五、研究结果
- ✅ 六、结论与讨论（四层贡献压实）
- ✅ 参考文献（APA 格式）
- ✅ 图 1-7（流程图 / 机制图 / 时序图 / 终点指标图）
- ✅ 表 1-2（条件汇总表 / ANOVA 结果表）

**理论贡献（四层）**：
1. **整合贡献**：把 LLM 分布压缩与网络极化文献统一到"条件化生成 + 网络互动 + 历史记忆"框架
2. **机制贡献**：LLM-agent 舆论演化不是简单社会影响，而是条件结构共同决定的生成过程
3. **概念贡献**：区分"立场多峰/极端化"与"理由多样性"——多极化不等于多样性
4. **社交机器人贡献**：LLM-agent 是参与生产意见本身的新型社交机器人

---

## 下一步路线图

### 立即：课程论文提交前
- [ ] 全文参数一致性检查（qwen3.5-plus / N=20 / T=30 / 5 seeds / ws_p=0.1）
- [ ] 方法部分未计算指标的承诺清理（group within-between ratio / embedding / Self-BLEU）
- [ ] 术语"极化"改为"高分端集中 / 端点饱和"
- [ ] 图号、表号、APA 参考文献核对

### 课程论文后：正式 Paper 1
- [ ] 扩大 N 至 200-1000，T 至 50，10+ seeds
- [ ] 补文本指标（embedding 距离 / Self-BLEU / 高频理由分布 / long-tail retention）
- [ ] 网络结构效应在更大规模下重新检验
- [ ] 外部效度讨论（真实社交媒体网络验证）

### Paper 2 储备（05-23 大设计）
- [ ] 回到 research_design.md (05-23 版)
- [ ] instruct vs abliterated
- [ ] 三档议题敏感度
- [ ] temperature grid
- [ ] persona-free / weak / medium / strong

---

## 日志索引

| 日期 | 文件 | 阶段 |
|------|------|------|
| 2026-03-10 ~ 03-24 | [2026-03-10_to_03-24.md](logs/2026-03-10_to_03-24.md) | 项目启动 |
| 2026-03-24 | [2026-03-24.md](logs/2026-03-24.md) | 方案审查 |
| 2026-03-25 ~ 03-31 | [2026-03-25_to_03-31.md](logs/2026-03-25_to_03-31.md) | 理论文章修订 |
| 2026-04-03 | [2026-04-03.md](logs/2026-04-03.md) | Git 配置 |
| 2026-05-22 | [2026-05-22.md](logs/2026-05-22.md) | 预实验1.0：代码实现 + 三轮 API 测试 |
| 2026-05-23 | [notion-2026-05-23.md](logs/notion-2026-05-23.md) | 方法论反思 + H1-H5 假说（大设计，历史） |
| 2026-05-24 | — | 项目结构重构：区分预实验1.0/2.0 |
| 2026-05-28 | [design/meetings/2026-05-28_组会汇报.md](design/meetings/2026-05-28_组会汇报.md) | 关键：研究收口决策 |
| 2026-05-30 | — | pilot-3.0 正式实验完成（四条件×五seed） |
| 2026-05-31 | [notion-2026-05-31.md](logs/notion-2026-05-31.md) | 当前最新状态交接 |

---

## 关键文献

| 编号 | 文献 | 在本研究中的角色 |
|------|------|----------------|
| L1 | Piao et al. 2025 arXiv:2501.05171 | 预实验 2.0 代码来源；persona 锁死效应 |
| L2 | Wang et al. 2025 *COLING* | Echo Chambers 解码；统一假说骨架来源 |
| L6 | Cisneros-Velarde 2025 *NAACL Findings* | RLHF progressive bias；prompt 工程铁律 |
| L14 | Bisbee et al. 2024 *Political Analysis* | LLM 调查仿真 SD 压缩 51% |
| L30 | Shumailov et al. 2024 *Nature* | 模型坍缩理论基础 |

---

*README 最后更新：2026-05-31（项目收口：探索性 LLM-ABM 机制识别）*
