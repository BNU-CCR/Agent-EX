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

**当前 Paper 1 定位**（2026-07-14 聚焦规格）：

> 模拟 LLM-agent 进入固定在线讨论网络后，在身份信息、身份连续性和社会暴露的正交操纵下，识别多轮意见演化中的组内均质化与组间分化机制。

正式设计为 `identity 2 × continuity 2 × social exposure 3 = 12 cells`，N=1000、T=50，首批10个 matched seeds，并按一次预注册的盲态 nuisance-variance 重估最多扩至20个。唯一 primary estimand 是 continuity 对 `WS - shuffled` 的 matched-seed DiD 调节；完整定义见 [07-14 Paper 1 聚焦研究设计](docs/superpowers/specs/2026-07-14-paper1-focused-research-design.md)。

2026-05 的 weak/lifelong × BA/WS 结果是 N=20 的历史 pilot 证据，只用于提出问题、迁移回归和识别旧实现风险，不是当前 Paper 1 的正式设计或已验证结论。

**当前工作入口**：先读 [AGENTS.md](AGENTS.md) 与 [项目总览](docs/project-overview.md)；Paper 1 人类可读协议见 [paper1-protocol.md](docs/paper1-protocol.md)，未决项见 [research-qa.md](docs/research-qa.md)，已确认选择见 [decisions.md](docs/decisions.md)。

**当前代码位置**：正式平台 Phase 3A 已合入本地 `main`，代码位于 `platform/`；实现提交为 `7e5731b`，交接文档提交为 `d03c6b2`。恢复开发前先阅读 [Phase 3A 交接日志](logs/2026-07-29-phase3a-handoff.md)。

---

## 目录结构

```
Agent-EX/
├── platform/                  # 【正式平台】Paper 1 与后续研究唯一活跃代码
│   ├── src/agent_ex/              # 协议、领域记录、运行身份与证据契约
│   ├── protocols/                 # Paper 1 schema 镜像
│   ├── configs/paper1/            # draft 机器协议；formal 尚未解锁
│   └── tests/                     # 单元、边界、安装与 wheel smoke
│
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
├── pilot-3.0/                 # 【历史 pilot】AI劳动力议题探索性实验（2026-05-30）
│   ├── src/                       # 核心代码（基于 pilot-1.0 重构）
│   │   ├── agent.py               # Agent 类与 Prompt（weak / lifelong strong）
│   │   ├── network.py             # BA / WS 网络构建
│   │   ├── llm_client.py          # DashScope API 客户端
│   │   ├── simulator.py           # 事件过程模拟器（模块8规格修订后实现）
│   │   ├── metrics.py             # 指标计算
│   │   └── config.py              # 配置加载
│   ├── run.ipynb                  # 历史 pilot notebook（Cell 0-15）
│   └── results/                   # 实验结果（gitignored）
│       ├── current_experiment/    # 四条件 × 五 seed 历史 pilot 数据
│       └── paper_outputs/         # 历史论文图表与统计表
│
├── logs/                        # 工作日志
│   ├── 2026-05-22.md              # 预实验1.0
│   ├── notion-2026-05-23.md       # 05-23 交接（RLHF/abliterated 大设计）
│   └── notion-2026-05-31.md       # 05-31 历史状态快照（已被当前主线取代）
├── references/                  # 参考文献（Notion 统一管理）
└── README.md                    # 本文件
```

---

## 版本演进

| 版本 | 时间 | 代码来源 | 议题 | 规模 | 状态 | 核心发现 |
|------|------|---------|------|------|------|---------|
| **预实验 1.0** | 2026-05-22 | 自研 | AI劳动力（中文） | 20×30 | ✅ 完成 | 弱约束下快速高分端收敛；固执度+角色强化可保留多样性 |
| **预实验 2.0** | 2026-05-24 | Piao et al. 2025 | Politics（英文） | 80×2 | ✅ 完成 | persona 锚定强度是隐藏 confound；qwen3 存在 progressive bias |
| **历史 pilot (pilot-3.0)** | 2026-05-30 | 基于 pilot-1.0 重构 | AI劳动力（中文） | 20×30×4条件×5seed | ✅ 完成 | weak persona → 高分端饱和；lifelong strong → 保留中间立场与理由多样性 |

**关键转折**：
- 2026-05 的 weak/lifelong × BA/WS 设计保留为历史 pilot，不再提供正式执行参数。
- 2026-07-14 起，Paper 1 以已批准的 12-cell 聚焦规格为设计权威；RLHF / abliterated、动态重连和多模型全因子移至后续研究。

---

## 当前 Paper 1 实验设计速查

### 核心问题

Agent 进入在线舆论网络并多轮互动后，身份信息和跨轮连续性是否改变网络拓扑对组内均质化与组间分化的作用？

### 实验条件（2×2×3）

| 因素 | 水平 |
|------|------|
| identity | 无身份信息 / 有身份信息 |
| continuity | 无跨轮一致性要求 / 有跨轮一致性要求 |
| social exposure | self-history only / degree-matched shuffled social / 固定 WS 邻居 |

### 规模

- N = 1000 agents
- T = 50 rounds
- 12 cells 共享 matched seeds；首批10个，盲态规则最多扩至20个
- N=200/500 只用于有限规模 gate，不进入正式主结论

### 主结果与模型路线

- 唯一 primary outcome：`Δlog((B+ε)/(W+ε))`，同时报告组间分量 B 与组内分量 W。
- 主模型：Qwen3-8B BF16、non-thinking、自部署 vLLM；精确 revision 与运行环境须经 Phase 0B smoke 后冻结。
- API：仅运行预注册固定 snapshot 的审批子集；核心8 cells 只是推荐候选，不是已冻结常量，也不解释为“API 部署效应”。

---

## 使用指南

### 复现历史 pilot（pilot-3.0）

以下入口仅用于历史 pilot 复现与迁移回归验收，不得作为正式 Paper 1 运行入口；正式运行必须使用冻结协议下的 `platform/`。

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

### 课程论文后：正式 Paper 1
- [ ] 完成 Phase 0B 模型、API 与运行时 smoke，冻结仍未决的精确版本和生成参数
- [x] 完成 `platform/` Phase 3A 协议、领域记录、运行身份、FrozenSchedule、manifest 与证据图基础
- [ ] 实现 population、persona、network/exposure、prompt、mock adapter 与事件过程 engine
- [ ] 依次通过 mock、真实模型校准和 N=200/500/1000 有限规模 gate
- [ ] 运行 N=1000、T=50、12 cells、10→20 matched-seed 正式矩阵
- [ ] 冻结分析数据后执行预注册主分析与 API 外部稳健性子集

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
| 2026-05-30 | — | pilot-3.0 历史 pilot 完成（四条件×五seed） |
| 2026-05-31 | [notion-2026-05-31.md](logs/notion-2026-05-31.md) | 历史 pilot 状态交接 |
| 2026-07-14 | [2026-07-14.md](logs/2026-07-14.md) | Paper 1 聚焦规格与正式规模基线 |
| 2026-07-16 | [2026-07-16-phase3a-wip.md](logs/2026-07-16-phase3a-wip.md) | Phase 3A 中断 checkpoint（已被07-29取代） |
| 2026-07-29 | [2026-07-29-phase3a-complete.md](logs/2026-07-29-phase3a-complete.md) | Phase 3A 实现与验证完成 |
| 2026-07-29 | [2026-07-29-phase3a-handoff.md](logs/2026-07-29-phase3a-handoff.md) | 代码位置、文件清单与下一步恢复入口 |

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

*README 最后核对：2026-07-29（Paper 1 以冻结机器协议为最终执行权威；冻结前以 2026-07-14 聚焦规格为研究边界）*
