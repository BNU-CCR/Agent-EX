---
status: complete / independently reviewed
date: 2026-08-01
branch: codex/paper1-phase4b
baseline: 09768d3
phase: Phase 4B-3 completion checkpoint
---

# Phase 4B-3 实现检查点

本检查点记录topic、population、initialization与persona的mock-only实现及最终收口。
独立规格审查、反模式审查与代码质量复审均已`APPROVED`，Phase 4B-3状态为
`complete / independently reviewed`。Phase 4B-4尚未开始。

## 已实现边界

- `TopicPackage`严格字段、schema/package版本、七档标签、固定输出合同、不可变
  round-trip与canonical hash。
- TRS按连续权重的整数部分复制并按小数余量无放回补足，输出恰好N；非法权重、未缩放
  权重、结构零、缺失、不可实现约束与超容差全部fail closed。
- `build_population_artifact`为每matched seed构造独立人口，同seed不包含cell identity，
  因而可由12 cells逐Agent复用；制品报告克隆、缺失、结构零、TRS source counts、
  residual draw count、显式mock tolerance、边际与联合误差。约束与tolerance共同进入
  可审计input hash，不同tolerance gate不能生成同一envelope identity。
- 初始化使用批准的N=1000七档人数`[50,100,200,300,200,100,50]`；N=20和N=100仅按
  显式mock最大余数规则产生`[1,2,4,6,4,2,1]`与
  `[5,10,20,30,20,10,5]`，不得解释为正式参数。
- 人口字段与初始立场采用joint-stratum约束整数分配；round 0同时生成私人初始状态、
  私人理由和一条公开初始帖。理由仅从版本化mock离线库分配，不调用模型。
- Persona由共同骨架机械插入identity和continuity块；absent条件为空串，present块必须
  非空，自动diff只允许两个因素块变化。平台独立固定§4.2六类最小身份字段allowlist，
  拒绝analysis-only、敏感或方向字段；平台锁死措辞规则不可被模板空denylist清除，模板
  仍可附加更严格禁词。
- population、initial stance和initial reason分别登记独立RNG namespace；确定性Persona
  不伪造RNG。所有构建输出及所有fixture均使用`ArtifactEnvelope`。

## TDD证据

- Topic RED：`ModuleNotFoundError: agent_ex.topic`；GREEN：`7 passed`。
- Population RED：`ModuleNotFoundError: agent_ex.population`；GREEN：`14 passed`。
- Initialization RED：`ModuleNotFoundError: agent_ex.initialization`；GREEN：`10 passed`。
- Persona RED：`ModuleNotFoundError: agent_ex.persona`；GREEN：`6 passed`。
- 公开API/fixture整合RED：缺公开导出及fixture；编码漂移进一步被output hash mismatch
  拒绝。修复后4B-3定向整合：`42 passed`。
- 首次fresh全套：`235 passed, 1 failed`，唯一失败是旧公开API集合断言；更新断言后的
  定向API回归为`2 passed`。修订后的fresh全套为`236 passed in 13.77s`，无skip、
  无xfail；coverage套件同为`236 passed`，`1723 statements / 250 missed / 85%`。
- 审查修订Population RED为`3 failed`：缺失TRS审计字段、round-trip无审计字段、不同
  tolerance得到相同hash；最小GREEN后population/initialization/fixture为`30 passed`。
- 审查修订Persona/空块RED为`7 failed`：三类越权身份字段、空denylist绕过平台禁语、
  两类空present模板块与diff接受空present集合；最小GREEN后Persona/fixture为
  `17 passed`，补齐identity/continuity双因素diff后Persona为`14 passed`。
- Persona policy复审RED为`9 failed, 15 passed`：空模板denylist仍可绕过抗从众、固定
  原有价值方向、最大一步变化，且四模板差异校验未执行平台禁语检查。最小GREEN把四类
  canonical逐字短语提升为平台不可清空常量，并由render/validate共用；Persona定向为
  `24 passed`。正常的“保持或改变都可以、不要忽略有说服力的信息”continuity模板仍通过。
- 最终规格复审补充RED为`8 failed, 24 passed`：`docs/decisions.md:306-307`中的“坚持、
  捍卫、忠于、除非证据确凿”分别可从identity/continuity块绕过render与直接validate。
  最小GREEN只将这四个确切短语加入同一平台tuple，不增加同义词或开放语义分类；
  Persona定向为`32 passed`，正常canonical continuity仍通过。

## 审查修订后验证

- fresh全套：`246 passed in 11.92s`，无skip、无xfail。
- fresh coverage：`246 passed in 25.64s`，`1735 statements / 251 missed / 86%`；
  persona `81%`、population `91%`。
- Phase 4B-3五模块及fixture交叉回归的前一轮记录更正为`52 passed`；Persona policy
  修订后的同范围交叉回归为`62 passed`。
- platform范围Ruff check通过；Ruff format check为`19 files already formatted`；
  `pip check`为`No broken requirements found.`。
- `git diff --check`退出0，仅报告Windows工作树未来LF/CRLF转换提示；schema镜像、draft
  unresolved登记和formal fail-closed三个定向gate为`3 passed`。
- Persona policy格式化后最终定向为`24 passed`，五模块/fixture交叉回归为`62 passed`；
  fresh全套为`256 passed in 13.30s`，无skip/xfail。fresh coverage同为`256 passed in
  22.18s`，`1742 statements / 252 missed / 86%`，persona为`82%`。Ruff check通过，
  format check为`19 files already formatted`，pip check无破损依赖，diff check退出0，
  schema镜像/draft unresolved/formal fail-closed三门禁为`3 passed`。
- 四个补充canonical禁语加入后，Persona定向为`32 passed`，五模块/fixture为
  `70 passed`；fresh全套为`264 passed in 11.64s`，fresh coverage同为`264 passed in
  21.41s`，`1742 statements / 252 missed / 86%`，persona为`82%`。Ruff check通过，
  format check为`19 files already formatted`，pip check无破损依赖，diff check退出0，
  schema镜像/draft unresolved/formal fail-closed三门禁为`3 passed`。
- 上述证据是独立复审关闭前的阶段性验证；当时状态仍为
  `in_progress / review fixes pending re-review`，未提交且未进入Phase 4B-4。

## 首轮实现代理验证（历史阶段）

- fresh全套：`236 passed in 13.77s`。
- fresh coverage：`236 passed in 23.09s`，总覆盖率`85%`；4B-3新模块分别为
  initialization `87%`、persona `80%`、population `91%`、topic `86%`。
- Ruff check通过；Ruff format check为`19 files already formatted`。
- `pip check`为`No broken requirements found.`；`git diff --check`退出0，仅报告
  Windows工作树未来LF/CRLF转换提示，无空白错误。
- schema镜像、draft unresolved登记和formal fail-closed三个定向gate为`3 passed`。
- 这些是首轮实现代理的历史验证证据，不替代后续已经完成的独立规格、反模式和
  代码质量审查，也不作为Phase 4B-3最终验证数字。

## 研究与范围边界

- 未下载、读取或伪造CFPS/NBS/CNNIC正式数据。
- fixture原文、标签、人口组合、容差与理由均显式`mock_only`和`not_frozen`；不得升级为
  formal默认值。
- 最终topic原文/hash、人口crosswalk/容差、理由库、Persona逐字模板与操纵阈值仍按
  `docs/research-qa.md`保持未冻结；本轮没有填补任何`UNRESOLVED[...]`。
- 未调用模型，未实现network/node mapping，未进入Phase 4B-4。

## 文件边界

- 实现：`platform/src/agent_ex/topic.py`、`population.py`、`initialization.py`、
  `persona.py`及`platform/src/agent_ex/__init__.py`公开导出。
- 测试：对应四个`test_*.py`、`test_paper1_mock_fixtures.py`以及公开API集合迁移。
- 制品：`platform/tests/fixtures/paper1/mock_*.artifact.json`五个fixture envelopes。
- 状态：`task_plan.md`、`progress.md`与本检查点。

## 下一步

Phase 4B-3已经收口。下一工作包是Phase 4B-4的前置工程gate；本检查点未开始网络、
shadow graph或node mapping实现，也未授权跳过Phase 4B-4前置冻结步骤。

## 2026-08-01代码质量审查修订（历史阶段）

The five code-quality findings were implemented with fresh RED-to-GREEN evidence. At
that intermediate checkpoint, Phase 4B-3 remained
`in_progress / review fixes pending re-review`:

- Round-0 reasons are deterministically shuffled within stance and assigned without
  replacement. A run cannot reuse a reason ID or text, and an undersized stance pool
  fails closed. The explicit mock library now contains 1,000 persisted entries with
  capacities `50/100/200/300/200/100/50`; no runtime reason generation or duplicate
  fallback was introduced. The `initial_reason` RNG namespace and matched-seed binding
  remain unchanged.
- Persona diff validation now rejects unknown payload fields (including covert
  `condition_specific_hidden` data), validates the exact condition object, and compares
  every non-derived envelope field plus every payload invariant outside the approved
  condition/block/rendered-text differences. Identity templates are parsed with
  `string.Formatter` and must use each of the six frozen mock identity fields exactly
  once, with no unknown field or format modifier.
- Population donors must be non-empty and field-schema-isomorphic. Missing and extra
  field diagnostics identify the donor and exact fields; missing-value failures report
  the actual count and locations rather than a fixed value.
- Population diagnostics now preserve target, weighted-donor, and integerized marginal
  and joint counts, plus calibration and TRS errors. They reuse the supplied constraints
  and tolerance and are included in the immutable payload/hash/round trip. The TRS draw
  algorithm itself was not changed.

Fresh verification after these fixes: targeted quality suite `72 passed`; full suite
`274 passed`; coverage suite `274 passed`, `1817 statements / 257 missed / 86%`;
platform Ruff check and format check passed (`19 files already formatted`); `pip check`
reported no broken requirements; `git diff --check` exited zero with only existing
Windows LF/CRLF notices; schema mirror, draft unresolved, and formal fail-closed gates
were `3 passed`. This was the pre-re-review implementation checkpoint.

## 最终审查与关闭证据

- 独立规格审查与反模式审查均为`APPROVED`；独立代码质量复审为`APPROVED`。上述人口
  审计、Persona边界、理由分配与供体诊断问题均已关闭，无开放审查项。
- 质量定向回归为`72 passed`。最终fresh全套为`274 passed`，无skip、无xfail；fresh
  coverage同为`274 passed`，`1817 statements / 257 missed / 86%`。
- 版本化mock理由库包含1,000条唯一理由；分层无放回分配、容量不足fail closed及
  跨round-0输出不重复均有回归覆盖。该数量与内容只属于`mock_only / not_frozen`
  fixture，不是formal理由库参数或制品冻结。
- platform范围Ruff check、Ruff format check、`pip check`与`git diff --check`均通过；
  schema镜像、draft unresolved、formal fail-closed和generated human-summary同步gate均通过。
- 文档收口前验证快照的Git diff SHA-256为
  `57de0f024bbf41ba8b46335d593f90a5617578536824ba12450cee999db4fa5d`。这是
  pre-documentation verification hash；文档修改后会变化，不是提交hash。
- Phase 4B-3正式关闭为`complete / independently reviewed`。本轮未修改任何
  `UNRESOLVED[...]`，未将fixture值升级为formal值，未调用真实模型，未开始Phase 4B-4。
