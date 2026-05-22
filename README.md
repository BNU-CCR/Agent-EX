# 实验项目管理仓库

**研究者**: Bai Yuexi  
**创建时间**: 2026-04-03  
**GitHub**: https://github.com/572200469/Agent-EX

---

## 项目概述

本仓库包含两个独立项目：

| 项目 | 状态 | 说明 |
|------|------|------|
| **实验项目** | 🟢 进行中 | LLM 社会模拟实验（意见动力学、极化现象） |
| 理论文章修订 | 🟡 已完成 | 已返给出版社终审 |

---

## 目录结构

```
Agent-EX/
├── experiment/              # 【主线】实验项目
│   ├── design/              # 实验设计文档
│   │   ├── research_design.md    # 技术方案（RQ、参数、指标）
│   │   ├── todo.md               # 待办清单
│   │   ├── decisions_log.md      # 设计决策日志
│   │   └── advisor_feedback.md   # 导师反馈与决策追踪
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
| 2026-05-22 | [2026-05-22.md](logs/2026-05-22.md) | 实验代码实现 + API 预实验 |

---

## 实验设计速查

| 参数 | 设定值 | 说明 |
|------|--------|------|
| 节点数 (N) | 200（正式）/ 20（预实验） | 导师建议：真实社会网络规模下限 |
| 拓扑结构 | BA 无标度网络 | m=2（预实验已验证） |
| 交互轮数 | 50 轮（正式）/ 30 轮（预实验） | 预实验显示30轮已可见趋势 |
| 组别对比 | Instruct vs abliterated | RLHF 安全对齐效应 |
| 预实验模型 | qwen3-8b（通义千问 API） | 本地快速迭代 |
| 正式实验模型 | Qwen2.5-7B-Instruct（vLLM） | AutoDL RTX 4090D |
| 激活比例 | 40%（8/20） | 每轮约20%节点激活 |
| 邻居采样 | 度数加权（α=0.5），上限10 | 模拟有限注意力 |
| 记忆窗口 | k=3 | 每邻居保留最近3轮 |
| 温度 | 0.6 | 预实验调优后参数 |

## 预实验核心发现

1. **观点均质化现象存在**：LLM 介入下观点会互相影响
2. **但不会完全收敛**：在真实角色约束下，极端观点（1分/10分）可长期保持
3. **角色身份保持**：不同角色的 Agent 保持不同的表达风格，不再是"复读机"
4. **均值缓慢偏移**：整体从 6.1 上升到 7.35，呈温和"支持 AI"偏向
