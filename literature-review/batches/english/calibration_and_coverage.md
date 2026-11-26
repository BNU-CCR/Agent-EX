# 英文传播试检索与扩展校准

检索截止：2026-11-26（Asia/Shanghai）。独立研究数由正式主表合并后计算，本批次不声称全领域召回。

## 已完成

- 8刊试检索：Communication Methods and Measures、Computational Communication Research、Journal of Communication、New Media & Society、Social Media + Society、Digital Journalism、Human Communication Research、Communication Research。
- 校准后向Political Communication、JCMC、Communication Theory、Information, Communication & Society扩展；另随问题加入Social Science Computer Review和AI and Ethics。
- 先以agent-based/model/simulation发现，再加入social simulation/generative agents/multi-agent。共32个已执行公开查询（E01目录核查；其余逐刊/补充查询）；16个定向正式文献核查记录另列EV01–EV16。查询返回的稳定命中总数不可得，故空白，不能用空白当零。
- 17条发表记录：3条关键全文章节核查、12条已读摘要候选、1条date_pending候选、1条时间排除。最终主表仍须统一核对状态；17条不是17篇已确认核心纳入。
- 主表片段见results.json；EN01、EN08、EN11为11项结构的全文关键章节卡。

## 校准发现

1. **术语漏检**：只搜agent-based会遗漏LLM generative/multi-agent；CCR 2026特刊目录补查找出两篇与网络互动直接相关正式论文（EN03、EN04）。它们不是任务书指定种子，说明主题检索与期刊目录补查互补。
2. **时间漏判**：HCR 2024卷期EN08首发2023-08-07；SSCR 2026卷期EN13首发2025-10-17。CCR两平台日期不同，优先保存明确的文章Published/Published online字段及差异备注。EN05已由OJS2026-08-11改用较早AUP明确Published online2026-07-13。
3. **方法误收**：agent-based testing通常是平台审计（EN10、EN15），不是互动仿真；multi-agent也会命中新闻编辑任务、无线网络和实证议程网络。不能按词命中直接纳入核心。
4. **日期误收**：搜索引擎即使用before/after仍返回2014/2019/2021文献、被引记录；2021 CMM特刊保留为时间排除，不继续精读经典。
5. **非支持性结果**：EN13摘要显示，反作用规则下开放接触未必降低情感极化。它对既有趋同叙述构成必要边界，而不是要证明Agent-EX错误；模型/指标差异须全文比较。

## 覆盖边界与目录障碍

Clarivate MJL首页仅静态应用壳，未获取带Communication类别与SSCI过滤条件的全部正式目录。官方帮助明确详情/下载需注册，完整列表下载还有订阅限制：[MJL说明](https://supportcenter.clarivate.com/s/article/Web-of-Science-Master-Journal-List?language=en_US)。当前14刊仅为工作草案，不知道正式Communication–SSCI全集分母；当前索引均标current_index_pending，不用JIF反推SSCI，也不把第三方旧表当2026官方目录。

所有逐刊状态为**仅公开补查**，未宣称WoS规定检索完成，也不宣称零命中。CCR已检查2022(2)、2023(1)、2024(1)、2026(2)目录与相关命中记录，其他期号和全年在线内容仍有缺口。8刊只完成若干代表性公开查询，不能称期刊2022–2026全覆盖。

全文障碍：AUP摘要页面的Full-Text点击仍只显示加载占位，OJS PDF链接跳转回DOI；EN03/EN04不能当已全文阅读。EN01经合法机构库取得正式PDF；EN08经VU机构库正式PDF；EN11出版社HTML全文可读。HCR文章HTML重定向到不支持的最小化页面，以机构库正式稿替代。

## 下一批可执行动作

取得MJL Communication–SSCI目录导出（刊名、ISSN/eISSN、索引、类别、导出日期），建立真实全集；对每刊在WoS执行2022起题名/摘要/关键词检索并导出全部题录与精确查询命中数。仍可独立继续CCR其余期号/目录、EN03/04出版社可读全文与相近研究追踪；无需等目录才开展跨学科或综合。
