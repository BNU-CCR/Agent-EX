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
│   │   ├── research_design.md
│   │   ├── todo.md          # 实验任务清单
│   │   └── review_issues.md # 方案审查问题
│   ├── meetings/            # 组会汇报
│   └── results/             # 实验结果（未来）
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

### 每日工作保存

对 Claude 说：**"保存今日工作"** 或 **"/save-today"**

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

| 日期 | 文件 |
|------|------|
| 2026-04-03 | [logs/2026-04-03.md](logs/2026-04-03.md) |

---

## 实验设计速查

| 参数 | 设定值 | 说明 |
|------|--------|------|
| 节点数 (N) | 200（正式）/ 20（Phase 0） | 导师建议：真实社会网络规模下限 |
| 拓扑结构 | BA 无标度网络 | m 值待 Phase 0 确定（候选 2/3） |
| 交互轮数 | 50 轮 | 视 Phase 0 收敛曲线可调整 |
| 组别对比 | Instruct vs abliterated | RLHF 安全对齐效应 |
