# 实验项目管理仓库

**研究者**: Bai Yuexi  
**创建时间**: 2026-04-03  
**GitHub**: https://github.com/572200469/Agent-EX

---

## 项目概述

本仓库包含两个独立项目：

| 项目 | 状态 | 说明 |
|------|------|------|
| **实验项目** | 🟢 进行中 | LLM 社会模拟实验（意见动力学、极化与均质化） |
| 理论文章修订 | 🟡 已完成 | 已返给出版社终审 |

**论文核心 claim（最新版）**：
> 在以 LLM 作为硅基样本的范式下，RLHF 安全对齐对观点动力学的影响呈现 **"簇内均质化 + 簇间分极"的双层结构**，其内在机制为条件分布锐化所导致的持续角色漂移。

---

## 目录结构

```
Agent-EX/
├── experiment/              # 【主线】实验项目
│   ├── design/              # 实验设计文档
│   │   ├── research_design.md         # 技术方案（RQ、H1-H5、参数、指标）
│   │   ├── todo.md                    # 待办清单
│   │   ├── decisions_log.md           # 设计决策日志
│   │   ├── advisor_feedback.md        # 导师反馈与决策追踪
│   │   └── methodology_review_2026-05-23.md  # 方法论反思与范式调整（2026-05-23）
│   ├── src/                 # 核心代码模块
│   │   ├── agent.py              # Agent 类与 Prompt
│   │   ├── network.py            # BA 网络构建与采样
│   │   ├── llm_client.py         # LLM API 客户端
│   │   ├── simulator.py          # 模拟器主循环
│   │   ├── metrics.py            # 指标计算
│   │   └── config.py             # 配置加载
│   ├── config/              # 配置文件
│   │   ├── experiment.yaml       # 实验参数
│   │   └── models.example.yaml   # 模型配置示例
│   ├── experiments/         # 实验运行脚本
│   │   └── run_pilot.py          # 预实验入口
│   ├── analysis/            # 分析脚本
│   │   └── plot_scores.py        # 结果可视化
│   ├── meetings/            # 组会汇报材料
│   ├── results/             # 实验结果（gitignore）
│   ├── run_pilot.ipynb      # Jupyter Notebook 交互运行
│   ├── requirements.txt     # Python 依赖
│   └── pre_experiment_guide.md  # AutoDL 部署指南
│
├── paper-revision/          # 理论文章修订（已阶段性完成）
│   ├── paper.md             # 论文草稿
│   ├── memo.md              # 修订备忘录
│   ├── question list.md     # 问题清单
│   └── revision-reports/    # 修订反馈
│
├── logs/                    # 每日工作日志（跨项目）
├── references/              # 参考文献 PDF
└── README.md                # 项目说明
```

---

## 使用指南

### 运行预实验

**方式 1：Jupyter Notebook（推荐）**
```bash
cd experiment
jupyter notebook run_pilot.ipynb
```

**方式 2：命令行**
```bash
cd experiment
python experiments/run_pilot.py --n-agents 20 --n-rounds 30
```

### 每日工作保存

对 Claude 说：**"保存今日工作"**

自动执行：
1. 总结当日修改内容
2. 更新 `logs/YYYY-MM-DD.md` 日志
3. Git 提交并推送到 GitHub

### 版本管理常用命令

```bash
# 查看当前状态
git status

# 查看历史记录
git log --oneline

# 查看上次修改内容
git diff HEAD~1

# 回到历史版本
git checkout <commit-id>
```

### 多设备同步

```bash
# 开始工作前（获取最新代码）
git pull

# 工作完成后（推送更新）
git add . && git commit -m "描述本次工作" && git push
```

---

## 设备配置

| 设备 | SSH 密钥 | 状态 |
|------|---------|------|
| 笔记本 | 已配置 | 使用中 |
| 台式机 | 待配置 | - |

---

## 日志索引

| 日期 | 文件 | 阶段 |
|------|------|------|
| 2026-03-10 ~ 03-24 | [2026-03-10_to_03-24.md](logs/2026-03-10_to_03-24.md) | 项目启动 |
| 2026-03-24 | [2026-03-24.md](logs/2026-03-24.md) | 方案审查 |
| 2026-03-25 ~ 03-31 | [2026-03-25_to_03-31.md](logs/2026-03-25_to_03-31.md) | 理论文章修订 |
| 2026-04-03 | [2026-04-03.md](logs/2026-04-03.md) | Git 配置 |
| 2026-05-22 | [2026-05-22.md](logs/2026-05-22.md) | 实验代码实现 + API 预实验（qwen3-8b） |
| 2026-05-23 | [methodology_review_2026-05-23.md](experiment/design/methodology_review_2026-05-23.md) | 方法论反思 + 范式调整 + H1-H5 假说 |

---

## 实验设计速查（2026-05-23 更新）

### 研究问题

| RQ | 内容 | 论证强度 |
|----|------|---------|
| RQ1 | LLM 多智能体网络能否复现观点均质化 | 基础事实承接（低） |
| RQ2 | RLHF 安全对齐对均质化进程的加速效应；角色漂移作为中介机制 | 核心 contribution（高） |

### 核心假说（H1-H5）

| 假说 | 机制 | 操作化 |
|------|------|--------|
| H1 锐化 | RLHF 单调降低条件分布 token-level 熵 | Instruct vs abliterated 输出 logits 熵差 |
| H2 锁死 | 条件锐化 → 跨时间步立场方差↓、persona 一致性↑ | 跨轮立场方差 + LLM-as-judge 角色一致性 |
| H3 中间空洞 | 条件锐化 × 网络聚类同质性 → 中间区域塌缩 | 评分分布 mode 计数 + 中间区间（4-6 分）密度时序 |
| H4 温度补偿 | T↑ 提升条件分布有效熵，部分抵消 H1 | T ∈ {0.3, 0.7, 1.0, 1.3} grid |
| H5 议题敏感性 | RLHF 对敏感议题压制更强 | 三档议题 × 议题语法位置控制 |

### 实验参数

| 参数 | 设定值 | 说明 |
|------|--------|------|
| 节点数 (N) | 200（正式）/ 20（Phase 0） | 导师建议：真实社会网络规模下限 |
| 拓扑结构 | BA 无标度网络 | m ∈ {2, 3}（Phase 0 敏感性分析确定） |
| 交互轮数 | 50 轮 × 5 重复 | 同步更新机制 |
| 激活比例 | 5-10% | 按度数加权（更贴近真实社交媒体低活跃率） |
| 邻居采样 | 度数加权（α=0.5），上限10 | α ∈ {0, 0.5}（Phase 0 敏感性分析） |
| 记忆窗口 | k=3 | 每邻居保留最近3轮 |
| 温度 (T) | 0.7（主实验） | H4 操控变量：T ∈ {0.3, 0.7, 1.0, 1.3} |
| 组别对比 | Instruct vs abliterated | RLHF 安全对齐效应（精确孤立） |
| 对照组 | persona-free | 2×2 设计（有/无 persona × Instruct/abliterated） |
| 议题 | 三档敏感度 | 低/中/高 RLHF 敏感度（Phase 0 probe 后确定） |
| 预实验模型 | qwen3-8b（通义千问 API） | **结论不外推**，仅验证代码流程 |
| 正式实验模型 | Qwen2.5-7B-Instruct（vLLM） | AutoDL RTX 4090D；线 B 用 Llama-3.1-8B |
| 评分 | 连续 Likert 1-10 | 强制 `【评分：X】` 格式输出 |

### 因变量（DV）

- **方差时序**：每轮观点分布方差
- **均值时序**：每轮均值漂移
- **收敛半衰期**：方差下降至初始值 50% 所需轮数
- **BGE 嵌入相似度**：`BAAI/bge-large-zh-v1.5`，语义趋同验证
- **模块度 (Modularity)**：网络社群结构演化
- **角色一致性得分**：cosine(embed(第 t 轮输出), embed(初始角色描述))
- **Self-BLEU**：文本多样性

### 统计方法

- LMM 主分析：`方差 ~ 轮次 × 组别 + (1+轮次|run_id)`
- H1-H5 联合检验
- 角色一致性中介分析

---

## 实验 Pipeline（7 步）

```
Step 1: 三档议题 probe（L6 铁律: 议题语法位置控制）
Step 2: 人口学画像采样（CNNIC 分布）
Step 3: 初始观点分布拟合（CGSS/CFPS）
Step 4: 零交互基线诊断（边际侧坍缩量化 + H1 直接检验）
Step 5: Phase 0 敏感性矩阵（m × α × T × Persona × Model 五维）
Step 6: 正式实验（200 × 50 × 5 × 2 模型 × 3 议题）
Step 7: LMM + H1-H5 联合检验 + 中介分析
```

---

## 预实验说明（2026-05-22，qwen3-8b）

⚠️ **重要**：5-22 预实验仅用于验证代码流程，**结论不可外推到正式实验**。原因：
1. 模型不一致（qwen3-8b vs Qwen2.5-7B-Instruct）
2. 抗均质化 trick（固执度 + temperature=0.6 + 强化角色 prompt）与 DV 互相干扰
3. 未做零交互基线，无法分离 LLM 内禀坍缩与网络动力学贡献

### 5-22 预实验原始发现（仅作参考）

1. **观点均质化现象存在**：LLM 介入下观点会互相影响
2. **但不会完全收敛**：在角色约束下，极端观点（1分/10分）可短期保持
3. **角色身份保持**：不同角色的 Agent 保持不同的表达风格
4. **均值缓慢偏移**：整体从 6.1 上升到 7.35

---

## 双线研究策略

| 线 | 议题语言 | 模型 | 发表语言 |
|----|---------|------|---------|
| 线 A | 中文 | Qwen2.5-7B-Instruct vs abliterated | 中文 |
| 线 B | 外文 | Llama-3.1-8B-Instruct vs abliterated | 英文 |

详见 `experiment/design/methodology_review_2026-05-23.md` 第五节。

---

## 关键文献

| 编号 | 文献 | 在本研究中的角色 |
|------|------|----------------|
| L1 | Piao et al. 2025 arXiv:2501.05171 | 族④ 主要先验；网络构建 / W-S vs BA 比较 |
| L2 | Wang et al. 2025 *COLING* "Decoding Echo Chambers" | 族④ 次要先验；统一假说骨架来源 |
| L6 | Cisneros-Velarde 2025 *NAACL Findings* | 安全对齐机制最直接学理对接；prompt 工程铁律来源 |
| L14 | Bisbee et al. 2024 *Political Analysis* 32(4) | 族② 主要先验；H1 SD 压缩量化基准（51%） |
| L30 | Shumailov et al. 2024 *Nature* | 族① 模型坍缩理论基础 |
| L5 | Xie et al. 2026 *PNAS* | 边际侧统计真实性基准 |

完整文献追踪数据库见 Notion 项目页面。

---

## 开放问题（待决策）

1. 三档议题最终选哪三个？
2. 真实立场分布映射：二元/三元如何映射到 1-10 分？
3. CNNIC 画像粒度若不足六维，是否退到三维（年龄×性别×学历）？
4. abliterated 版本：HuggingFace 现成 vs 自行 FailSpy 生成？
5. Temperature grid 扫描规模（72 次 Phase 0 跑，是否削减）？
6. 议题语法位置控制：Phase 0 一并扫，还是只在正式实验做稳健性？
7. Shumailov "保留 X% 初始立场记忆" 是否作为额外实验组？
8. persona-free 对照组规模：N=200 全量 vs N=50 缩减？
9. 是否补充连续 0-100 滑块评分作为子对照？

---

*README 最后更新：2026-05-23（方法论反思与范式调整后）*
