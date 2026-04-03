# 实验项目管理仓库

**研究者**: Bai Yuexi  
**创建时间**: 2026-04-03  
**GitHub**: https://github.com/572200469/Agent-EX

---

## 目录结构

```
Agent-EX/
├── logs/              # 每日工作日志（自动保存）
├── docs/              # 研究文档
│   ├── research_design.md
│   ├── paper.md
│   ├── memo.md
│   └── reviews/       # 评审反馈
├── meetings/          # 组会材料
├── tasks/             # 任务管理
│   ├── todo.md
│   └── question list.md
├── references/        # 参考文献 PDF
└── article/           # 原有 article 结构
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
