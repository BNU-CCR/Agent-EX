# 进度与持续接续

## 当前目标
以 LLM-based Social Simulation / Generative ABM 方法论和发表生态为主线，完成方法知识地图、核心文献库、学术发表地图，以及当前论文/后续方法论文的双轨投稿策略。完整目标见 [GOAL.md](GOAL.md)。

## 当前状态（2026-11-26，Asia/Shanghai）

| 工作 | 状态 |
|---|---|
| 第一轮文献工作 | 已交付可访问公开证据部分：57条记录、15张全文阅读卡、12本核心来源期刊、10本投稿候选；完整SSCI目录及WoS/CNKI逐刊数据库检索仍有缺口 |
| 研究主线调整 | 用户已批准：方法论与发表生态为第一优先级；传播应用与Agent-EX直接对照保留为后续层 |
| 第二轮任务书 | 已创建 `METHODS_FIRST_REORIENTATION.md` |
| 北极星目标 | 已创建 `GOAL.md` |
| 第二轮实质执行 | 待开始 |

## 已完成
- 第一轮四阶段可访问部分已提交并同步；详见 [第一轮任务计划](task_plan.md) 和 [覆盖与缺口](reports/coverage_and_gaps.md)。
- 用户批准方法优先的第二轮调整。
- 已写入第二轮执行任务书与长期目标。

## 进行中
- 第二轮批次 A：schema 扩展、现有57条方法重分类、README与项目定位调整。

## 阻塞与限制
- 第一轮完整SSCI Communication目录未取得。
- WoS/CNKI授权数据库逐刊检索未完成。
- 13条文献首次正式发表日期待核、38条候选全文筛选未完成。
- 第二轮方法种子全文与方法发表生态尚待逐项核实。

## 下一项具体任务
1. 阅读 `METHODS_FIRST_REORIENTATION.md`、现有 `data/literature_master.csv` 和 `data/README.md`。
2. 为现有57条增加方法导向字段，先完成字段字典和编码规则，再逐条编码；保留所有原 ID 与筛选状态。
3. 核验并完成首批方法核心文献全文卡，优先 MASS、Larooij & Törnberg、Haase & Pokutta、ODD-based replication study。
4. 创建 `method_venue_map.csv`，先核实 JASSS、Journal of Simulation、Simulation Modelling Practice and Theory、SSCR 等真实发表先例。
5. 每批完成后更新本文件并提交，记录最新 commit SHA。

## 接续规则
每次 Codex 新会话必须先读 GOAL、README、METHODS_FIRST_REORIENTATION 和本文件，从“下一项具体任务”继续。不得重建第一轮数据库，不得把计划当作已经完成的检索，也不得声称会话结束后仍在后台工作。
