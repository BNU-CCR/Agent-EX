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

截至2026-11-26，保留首轮57条及15卡，新增25项工作、补读4条原记录，现82条、40张全文卡；29项正式纳入、45候选、6前沿、2排除。全文卡数含前沿、日期与正式版本未决项，不能等同正式纳入数。

- [方法字段与编码规则](protocol/method_coding_rules.md)、[57条重分类快照](reports/method_reclassification.md)：批次A历史结果，后续变化由主表和变更账维护。
- [方法种子精读](reports/method_seed_reading.md)、[跨学科检索](reports/method_crossdisciplinary_search.md)：版本、日期与实际阅读状态分列。
- [综述范围与验证比例比较](reports/review_scope_comparison.md)：Gao与R015语料、评价口径分开。
- [验证证据矩阵](reports/method_validation_matrix.md)：25个证据单元，回答、轨迹、经验效度分列。
- [方法发展地图](reports/method_landscape.md)、[Agent-EX方法定位](reports/agent_ex_method_positioning.md)。
- [发表生态](reports/method_venue_landscape.md)、[双轨投稿策略](reports/two_track_submission_strategy.md)：27载体（18刊/8会议入口/1仓库），定向样本，未声称完整数据库覆盖。
- [第二轮工作簿](exports/literature_and_journals_methods.xlsx)、[方法书目](exports/references_methods.bib)：8张工作表，书目仅26项正式纳入；前沿/候选见主表。
- [保留与门控核验](reports/methods_validation.json)：57旧ID、18份首轮文件hash、231原日志前缀保留，旧字段25项实质变化均记账；原导出不覆盖。

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

批次J补充：新增M017–M021、2张正式来源方法阅读卡和4个验证单元；完整覆盖状态见[载体覆盖审计](reports/venue_coverage_audit.md)。78条/35卡/25单元/23载体均为当前累计量。M020首次在线日及M021正式全文仍待核；不能把新增载体当完整覆盖。

批次K：补M021作者v2方法/经验评价精读及M020固定代码快照的七文件静态核查；累计78条/35卡/25验证单元。正式纳入仍27项，作者稿不升级为正式版全文。详见[校准与制品核查](reports/calibration_and_artifact_audit.md)。

批次L当前累计80条/37卡/28验证单元/24载体；正式纳入28、候选44、前沿6、排除2。新增CMASE作者v3与JEIC经验异质性方法精读；TSC接收仅作者声明，正式出版仍待核。见[共同体边界补查](reports/community_boundary_updates.md)；历史批次数字仅作快照。

批次M补正式版本与获取核查，未强升任何全文/日期状态；当前80条/37卡。见[版本获取审计](reports/version_access_audit.md)，下一批先读2024 SIGDIAL正式组件验证论文。

批次N当前累计81条/38卡/32验证单元/25载体；28正式纳入、45候选、6前沿、2排除。M024为正式来源全文已读、精确日期待核。见[组件验证分层](reports/component_validation_layers.md)。历史数字保留为各批快照，接续以progress当前统计为准。

批次O当前82条/39卡/35验证单元/27载体，29正式纳入；R017已补正式全文，M025只读摘要。17刊条件投稿表不含范围待核的SOCNET。见[社会方法共同体补查](reports/social_methods_community.md)。

批次P补M025方法全文，当前82条/40卡/38验证单元/27载体；29正式纳入不变。见[拟合与机制识别](reports/network_fit_identification.md)；日期/独立验证缺口仍保留。
