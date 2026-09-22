# Summer Review, README, and Branch Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a current project README and a web-safe summer progress review, then fast-forward the complete committed Phase 0 history into `main` without touching unfinished Phase 0B work.

**Architecture:** Documentation is built from the repository specification chain, Git history, committed evidence, and the verified Phase 0A-1 terminal hashes. The integration pins exact pre-merge and source OIDs, commits only an explicit four-path allowlist, checks the target worktree for tracked changes and path collisions, and uses a non-force fast-forward push. Redundant remote branch deletion is a separate post-push step; the active Phase 0 branch/worktree remains until its uncommitted implementation is independently resolved.

**Tech Stack:** Markdown, Git, PowerShell, ripgrep, repository-local specifications and evidence logs.

---

## File Map

- Modify: `README.md` — concise current operational landing page.
- Create: `docs/2026-09-22-summer-progress-review.md` — group-meeting summary, technical history, and web-safe GPT handoff.
- Preserve: `docs/superpowers/specs/2026-09-22-summer-review-readme-and-branch-integration-design.md` — approved design and safety boundary.
- Create: `docs/superpowers/plans/2026-09-22-summer-review-readme-and-branch-integration.md` — this execution plan.
- Read only: `AGENTS.md`, `logs/2026-07-29-phase3a-handoff.md`, `docs/project-overview.md`, `task_plan.md`, `progress.md`, `findings.md`, `docs/decisions.md`, `docs/research-qa.md`, and approved specifications/plans under `docs/superpowers/`.
- Never stage: `platform/`, `.pytest-tmp-*`, `.test-venv/`, `*.bundle`, or any path outside the four-file allowlist.

### Task 1: Freeze the documentation evidence set

**Files:**
- Read: `AGENTS.md`
- Read: `logs/2026-07-29-phase3a-handoff.md`
- Read: `docs/project-overview.md`
- Read: `task_plan.md`
- Read: `progress.md`
- Read: `findings.md`
- Read: `docs/decisions.md`
- Read: `docs/research-qa.md`
- Read: `docs/superpowers/specs/2026-09-22-summer-review-readme-and-branch-integration-design.md`

- [ ] **Step 1: Capture the repository and worktree state without modifying it**

Run:

```powershell
git status --porcelain=v1 --untracked-files=all
git worktree list --porcelain
git branch -vv
```

Expected: the Phase 0 worktree may remain dirty only because of pre-existing implementation/test/temp paths; no documentation path except the approved plan is unexpectedly modified.

- [ ] **Step 2: Capture exact branch relationships and summer history**

Run:

```powershell
git rev-parse main
git rev-parse codex/paper1-phase0
git merge-base --is-ancestor main codex/paper1-phase0
git rev-list --count main..codex/paper1-phase0
git log --since=2026-06-01 --date=short --format='%H`t%ad`t%s' codex/paper1-phase0
```

Expected: the ancestor command exits 0; the commit count is recomputed rather than copied from the design document.

- [ ] **Step 3: Build a fact ledger for the two documents**

Record only facts supported by the read-only sources:

```text
Research matrix: identity 2 × continuity 2 × exposure 3 = 12 cells
Formal scale: N=1000, T=50, first 10 matched seeds
Model route: self-hosted Qwen3-8B BF16, non-thinking, vLLM; exact revision freezes in Phase 0B
Phase 0A-1 terminal replay: 797 states, 797 coded, 0 unresolved intent
Terminal projection record hash: b09e0a242018c1bc48c00fb0af0f87740e8c420080e73e0411de095db761873d
Last pre-terminal projection SHA-256: 6c65dbc6b7d27f709821b8da1751b5eca7b18b6e377efa7b66fde7cae898fd0e
Current boundary: Phase 0B real N=20 dynamics is not yet a completed formal experiment
```

Expected: no claim treats diagnostic/preliminary artifacts as frozen main-experiment results.

### Task 2: Rewrite the project README

**Files:**
- Modify: `README.md`
- Read: the evidence set from Task 1

- [ ] **Step 1: Replace the historical-first README with the approved current structure**

Write these sections in this order:

```markdown
# Agent-EX

## 项目定位
## 当前状态（2026-09-22）
## Paper 1 研究设计
## 已完成的平台能力
## 证据链与研究边界
## 仓库导航
## 五分钟接续顺序
## 本地开发与云端运行
## 当前阻塞与未来七天
## 历史 pilot 与暑期复盘
```

The status section must distinguish `已完成并核验`, `已实现但待复核/提交`, and `尚未完成`. The research-design section must state the 12-cell matrix and formal scale exactly. The cloud section must describe the workflow without hosts, ports, credentials, key filenames, or raw-result locations.

- [ ] **Step 2: Link authoritative documents instead of duplicating them**

Include repository-relative links to:

```text
AGENTS.md
logs/2026-07-29-phase3a-handoff.md
docs/project-overview.md
docs/superpowers/specs/2026-07-29-paper1-phase4a-completion-design.md
docs/superpowers/specs/2026-07-14-paper1-focused-research-design.md
docs/paper1-protocol.md
docs/research-qa.md
docs/decisions.md
docs/archive-index.md
docs/2026-09-22-summer-progress-review.md
```

Expected: the README remains an entry point; it does not become a second specification.

- [ ] **Step 3: Remove misleading current-use commands**

Delete or archive homepage instructions that present historical pilot notebooks/batch files as the current Paper 1 execution path. Preserve their existence through `docs/archive-index.md` and the history section.

- [ ] **Step 4: Check the README’s internal structure**

Run:

```powershell
rg '^#{1,3} ' README.md
rg -n 'UNRESOLVED|preliminary|diagnostic|正式主实验|797|2 × 2 × 3|N=1000|T=50' README.md
```

Expected: all approved sections exist; wording clearly says that the formal main experiment has not yet run.

### Task 3: Write the summer progress review

**Files:**
- Create: `docs/2026-09-22-summer-progress-review.md`
- Read: the evidence set and fact ledger from Task 1

- [ ] **Step 1: Write the one-page group-meeting layer**

Use this exact section structure:

```markdown
# 2026 暑期 Agent-EX 项目进展复盘

## 一、组会一页摘要
### 暑期目标
### 已完成的核心工作
### 可汇报的真实量化里程碑
### 当前边界与问题
### 未来七天计划
```

The summary must say: the summer produced a research specification, an auditable event platform, cloud deployment, and a verified 797-item calibration evidence chain; it did not yet produce formal N=1000 experimental findings.

- [ ] **Step 2: Write the chronological technical layer**

Use these subsections and bind each claim to commits/specs/logs:

```markdown
## 二、完整技术进展
### 7 月：研究问题收敛与规范链建立
### 7 月下旬：Phase 3A、4A 与 4B
### 8 月：事件级实验平台建设
### 8 月下旬至 9 月：持久化、恢复与证据链
### 9 月：Phase 0A-0、Phase 0A-1 与云端部署
### 797 条盲判的完成与终态核验
### 当前 Phase 0B 的真实完成边界
```

Explicitly distinguish the earlier committed 609/797 snapshot from the later verified 797/797 terminal replay. Do not infer semantic research results from completion counts or hashes.

- [ ] **Step 3: Document lessons and the remaining critical path**

Add:

```markdown
## 三、关键问题与工程教训
## 四、从现在到正式实验的关键路径
## 五、周四组会建议讲法
```

Cover AutoDL resource changes, network/model-download constraints, quota interruptions, overly slow evidence writes, the discovery that a prior single-agent/self-history runner was not real N=20 dynamics, and the need to separate preliminary reporting from formal evidence completion.

- [ ] **Step 4: Add the web-safe GPT handoff**

Add:

```markdown
## 六、Web-safe GPT 接续附录
### 当前 Git 状态
### 权威阅读顺序
### 不得违反的研究红线
### 下一步最小工作包
### 禁止重复或误做的工作
```

Use repository-relative paths, commit IDs, the two approved hashes, and non-sensitive status only. Exclude usernames, absolute local paths, SSH hosts/ports, key filenames, credentials, directly actionable cloud commands, raw-response locations, and raw content.

- [ ] **Step 5: Check headings and mandatory statements**

Run:

```powershell
rg '^#{1,3} ' docs/2026-09-22-summer-progress-review.md
rg -n '797|609/797|b09e0a242018c1bc48c00fb0af0f87740e8c420080e73e0411de095db761873d|6c65dbc6b7d27f709821b8da1751b5eca7b18b6e377efa7b66fde7cae898fd0e|preliminary|diagnostic|not_frozen|正式主实验' docs/2026-09-22-summer-progress-review.md
```

Expected: the three audiences—group meeting, technical audit, and next GPT—can each find a self-contained section.

### Task 4: Verify and commit only the documentation allowlist

**Files:**
- Modify: `README.md`
- Create: `docs/2026-09-22-summer-progress-review.md`
- Preserve: `docs/superpowers/specs/2026-09-22-summer-review-readme-and-branch-integration-design.md`
- Create: `docs/superpowers/plans/2026-09-22-summer-review-readme-and-branch-integration.md`

- [ ] **Step 1: Validate Markdown links**

For every relative Markdown link in the two deliverables, resolve the target against the containing file and confirm it exists. Expected: zero broken repository-local links.

- [ ] **Step 2: Run the privacy and credential scan**

Run:

```powershell
rg -n -i 'connect\.|seetacloud|IdentityFile|known[_-]?hosts|BEGIN .*PRIVATE KEY|ssh-ed25519|password|密码|C:\\Users|E:\\' README.md docs/2026-09-22-summer-progress-review.md
```

Expected: no matches. Generic discussion of cloud deployment is allowed, but operational endpoints and private locations are not.

- [ ] **Step 3: Check whitespace and changed paths**

Run:

```powershell
git diff --check -- README.md docs/2026-09-22-summer-progress-review.md docs/superpowers/specs/2026-09-22-summer-review-readme-and-branch-integration-design.md docs/superpowers/plans/2026-09-22-summer-review-readme-and-branch-integration.md
git status --short
```

Expected: documentation paths are the only new changes created by this task; pre-existing implementation/temp paths remain untouched.

- [ ] **Step 4: Stage the exact allowlist and inspect it**

Run:

```powershell
git add -- README.md docs/2026-09-22-summer-progress-review.md docs/superpowers/plans/2026-09-22-summer-review-readme-and-branch-integration.md
git diff --cached --name-only
git diff --cached --check
```

Expected staged paths exactly:

```text
README.md
docs/2026-09-22-summer-progress-review.md
docs/superpowers/plans/2026-09-22-summer-review-readme-and-branch-integration.md
```

- [ ] **Step 5: Commit the documentation snapshot**

Run:

```powershell
git commit -m "docs: publish summer progress review"
```

Expected: one documentation-only commit; existing Phase 0B modifications and untracked files remain unchanged.

### Task 5: Pin and fast-forward `main`

**Files:**
- No content edits
- Operate in the existing `main` worktree only after all preconditions pass

- [ ] **Step 1: Pin exact local and remote identities**

In the Phase 0 worktree, run:

```powershell
$PRE_MERGE_MAIN = git rev-parse main
$SOURCE_TIP = git rev-parse codex/paper1-phase0
$REMOTE_MAIN = (git ls-remote --heads origin main).Split("`t")[0]
if ($PRE_MERGE_MAIN -ne $REMOTE_MAIN) { throw 'main moved; stop for re-review' }
git merge-base --is-ancestor $PRE_MERGE_MAIN $SOURCE_TIP
if ($LASTEXITCODE -ne 0) { throw 'source is not a fast-forward of main' }
if ((git rev-parse codex/paper1-phase0) -ne $SOURCE_TIP) { throw 'source tip changed' }
```

Expected: all checks pass. `git ls-remote` is used because the unrelated damaged internal Codex checkpoint ref must not be repaired as part of this task.

- [ ] **Step 2: Verify the target main worktree is safe**

In the main worktree, run:

```powershell
if (git status --porcelain --untracked-files=no) { throw 'main has tracked changes' }
git status --porcelain=v1 --untracked-files=all
git ls-files --others --ignored --exclude-standard
git diff --name-only "$PRE_MERGE_MAIN..$SOURCE_TIP"
```

Compare normalized, case-insensitive paths. Stop on exact-path, parent-directory, child-directory, or case-folding collision. Do not delete or move untracked files to make the check pass.

- [ ] **Step 3: Perform the fast-forward**

Run in the main worktree:

```powershell
git merge --ff-only $SOURCE_TIP
if ((git rev-parse main) -ne $SOURCE_TIP) { throw 'main did not reach source tip' }
git merge-base --is-ancestor $PRE_MERGE_MAIN main
if ($LASTEXITCODE -ne 0) { throw 'pre-merge main is not preserved' }
```

Expected: no merge commit is created and the complete individual history is retained.

- [ ] **Step 4: Verify the integrated range**

Run:

```powershell
git rev-list --count "$PRE_MERGE_MAIN..main"
git log --oneline "$PRE_MERGE_MAIN..main"
git diff --check "$PRE_MERGE_MAIN..main"
Test-Path README.md
Test-Path docs/2026-09-22-summer-progress-review.md
```

Expected: the range count and log match the pinned Phase 0 range; both deliverables exist.

- [ ] **Step 5: Push without force and verify remote equality**

Immediately before pushing, re-read remote main and stop if it differs from `$PRE_MERGE_MAIN`. Then run:

```powershell
git push origin main
$REMOTE_MAIN_AFTER = (git ls-remote --heads origin main).Split("`t")[0]
if ($REMOTE_MAIN_AFTER -ne $SOURCE_TIP) { throw 'remote main verification failed' }
```

Expected: `origin/main` equals the pinned source tip; no force option is used.

### Task 6: Remove only the proven-redundant remote branch

**Files:**
- No content edits

- [ ] **Step 1: Prove `codex/paper1-phase4b` is contained in remote main**

Run:

```powershell
$REMOTE_MAIN = (git ls-remote --heads origin main).Split("`t")[0]
$PHASE4B_TIP = (git ls-remote --heads origin codex/paper1-phase4b).Split("`t")[0]
git merge-base --is-ancestor $PHASE4B_TIP $REMOTE_MAIN
if ($LASTEXITCODE -ne 0) { throw 'phase4b is not contained in remote main' }
git worktree list --porcelain
```

Expected: the remote branch tip is an ancestor of verified remote main. Local worktree/ref existence is recorded but not deleted here.

- [ ] **Step 2: Delete only the redundant remote Phase 4B ref**

Run:

```powershell
git push origin --delete codex/paper1-phase4b
git ls-remote --heads origin codex/paper1-phase4b
```

Expected: the final command prints nothing.

- [ ] **Step 3: Preserve Phase 0 and report the temporary two-branch state**

Do not delete local or remote `codex/paper1-phase0`, its active worktree, any unfinished implementation, or any internal checkpoint ref. Report that GitHub temporarily retains `main` plus `codex/paper1-phase0` until Phase 0B work is independently committed or otherwise resolved.

### Task 7: Final acceptance report

**Files:**
- No content edits

- [ ] **Step 1: Re-run the acceptance checks**

Run:

```powershell
git ls-remote --heads origin main codex/paper1-phase0 codex/paper1-phase4b
git log -5 --date=short --format='%h %ad %s' main
git status --short
```

Expected: remote main is the pinned source tip; remote Phase 4B is absent; Phase 0 remains; pre-existing unfinished files are still present and unmodified.

- [ ] **Step 2: Report exact outcomes and remaining boundary**

Report the README and summer-review links, `SOURCE_TIP`, integrated commit count, remote branch state, preserved uncommitted Phase 0B paths, and the fact that formal N=1000 experiments still have not run.
