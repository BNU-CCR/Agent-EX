# Agent-EX 文献梳理与投稿期刊定位

本目录持续建设 Agent-EX 的社会模拟与 LLM-based Agent-Based Modeling 文献库，并服务当前论文投稿与后续方法研究布局。

## 当前研究主线

**最高优先级：LLM 社会模拟方法论与发表生态。**

重点研究 LLM-based Social Simulation / Generative ABM 的方法范式、智能体架构、环境与互动协议、校准验证、外部效度、实验报告和可复现性；同时梳理这些研究主要发表的学科、期刊和会议。

传播学中的意见动力学、网络互动、信息接触和私人/公开表达仍然保留，但作为社会模拟方法的应用场景与 Agent-EX 直接对照，不再支配总检索方向。

## 时间范围

- 2022 年 1 月 1 日至每次实际检索截止日。
- 2022 年以前文献不纳入本轮独立检索、核心统计或精读卡。
- 期刊、会议、预印本与正式发表版本分别记录。

## 执行入口

1. [GOAL.md](GOAL.md)：持续推进的北极星目标、完成定义与接续规则。
2. [METHODS_FIRST_REORIENTATION.md](METHODS_FIRST_REORIENTATION.md)：用户批准的第二轮方法导向任务书。
3. [CODEX_TASK_2022_ONWARD.md](CODEX_TASK_2022_ONWARD.md)：第一轮原始任务书，继续作为时间、证据和数据管理规则的基础。
4. [第一轮研究综合](reports/research_synthesis.md)：已有传播应用和直接对照成果。
5. [第一轮投稿建议](reports/submission_recommendations.md)：已有期刊判断，待第二轮双轨重评。
6. [覆盖与缺口](reports/coverage_and_gaps.md)：第一轮检索未完成事项。
7. [进度](progress.md)：每次工作恢复和持续推进的唯一状态入口。

## 两条投稿路线

- **当前论文**：以社会模拟方法为基础，研究 LLM 智能体群体中的意见演化与社会互动过程。
- **后续方法论文**：研究 LLM-driven ABM 如何成为可控、可验证、可复现的社会科学研究方法。

两条路线分别评估，不把当前应用论文包装成已经成熟的方法规范。

## 第二轮方法研究成果

- [方法字段与编码规则](protocol/method_coding_rules.md)：schema v2，仅追加方法字段，首轮语义不变。
- [57条方法重分类](reports/method_reclassification.md)：方法核心16、方法验证10、应用5、直接对照15、外围11；全文确认方法核心4、方法验证3，其他候选与日期门分别统计。
- [第二轮工作簿](exports/literature_and_journals_methods.xlsx)、[方法书目](exports/references_methods.bib)：与首轮导出分开维护。
- 批次A已核对所有旧字段、ID、DOI、状态及15张卡/原导出哈希未改变，基线见data/round1_preservation_manifest.json；现直接开展批次B方法全文。

## 第一轮工作状态与保留

第一轮已建立 57 条文献工作库、15 张全文阅读卡、12 本核心来源期刊、10 本投稿候选期刊，并完成 Excel/BibTeX 和交叉核查。完整 SSCI 目录及 WoS/CNKI 逐刊数据库检索仍有缺口，详见覆盖报告。第一轮成果保留，不因第二轮重分类而删除或重编号。

## 后续维护

- 统一维护稳定 record_id/work_id/venue_id。
- 新增字段先更新 schema 说明，再迁移数据。
- 每批更新 progress.md，留下具体下一任务和 commit SHA。
- 真实来源、全文状态、日期与索引核验分开记录。
- 不将 Codex 会话结束后的工作描述为后台自动运行；每次新会话从 GOAL 与 progress 恢复。

仓库：`BNU-CCR/Agent-EX`
分支：`codex/social-identity-network-2x3`
目录：`literature-review/`
