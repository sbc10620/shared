---
name: dev-cycle
description: "Run a code change through the development cycle that ends in a PR: the first plan reviewed once by a read-only subagent before user feedback; for each planned commit, tests for new behaviour written first from the spec by a separate agent, implement, verify only what the change affects; once every commit exists, review the whole range (the agent's own built-in code review skill if it has one, otherwise the dev-cycle-code-review skill; high effort for the first round, medium after that), fix, and repeat until a round's fixes touch only docs and tests or there is nothing to fix; then, once before the PR, the slow checks, the full suites and the full e2e. Project-specific commands come from profiles/<repo>.md; a step the project has no way to run is skipped and reported. Use when implementing a planned change in a repository, when the user asks to verify, review or 'run the cycle' on a change ('개발 사이클', '리뷰 반복', 'PR 전 검증'), or before opening a PR."
user-invocable: true
---

# Development cycle

One loop for every code change that will become a PR:

```
plan ─► plan review (read-only subagent, once) ─► user feedback ─► agreed plan

for each planned commit:
  spec ─► tests from the spec (separate agent) ─► implement ─► verify what this change affects ─► commit

once every planned commit exists:
  review the whole range in a read-only subagent ─► report, wait for decisions
  (built-in review skill, else dev-cycle-code-review: high in round 1, medium from round 2)
        ▲                                         │
        └── verify what the fix affects ◄── fix the chosen findings (amend into their commits)
  ends after a round whose fixes touch only docs and tests, or that has nothing to fix

once, before the PR: slow checks + full suites + full e2e on the final HEAD
```

Running everything on every verification is wasted time: a cold full test
suite or a release e2e build is the costliest work in the cycle, and a fix
to one module cannot break another module's tests. The full run happens
once, on the commit that will be reviewed.

This document is Claude-facing and stays in English; reports to the user
are in the user's language. Two files beside it are read when a step says
so: `references/design-principles.md` and `references/profile-guide.md`.

## Roles

The one running this skill is the **orchestrator**: it implements, runs the
checks, and writes every helper's prompt from the plan. There are no fixed
agent definitions.

| Role | Step | Given | Never given / never does |
| --- | --- | --- | --- |
| Orchestrator (the implementer) | every step not run by a helper below | Everything; implements and fixes to the design principles | — |
| Plan reviewer | 2 | The plan, the repository, the user's decisions, the profile's path table, the design principles | A draft implementation; edits |
| Test agent | 3 | The spec for this commit, the user's decisions that override it, the test conventions | The implementation; test cases the orchestrator picked |
| Reviewer | 6 | The range, this round's changes, earlier findings and decisions ("do not re-argue"), what was verified, the design principles | Edits |

- The orchestrator picks the review method from its skill list (step 6:
  its own built-in code review skill first, otherwise
  `dev-cycle-code-review`) and names it in the reviewer prompt. A manual
  review in place of an available skill is allowed only when every
  available skill fails to run (step 6).
- When reporting a helper's result, say in a line or two what it was given.
  Show the full prompt only when the user asks.

## When each check runs

Every check belongs to one of three moments; the profile assigns them (see
`references/profile-guide.md` when there is no profile).

| moment | what runs |
| --- | --- |
| before editing (step 2): on the commit the change starts from | the baselines and kept base binaries the profile or the plan asks for |
| every verification: after implementing a commit (step 4), after each review fix (step 8) | the fast checks of step 5, for the affected set |
| before the PR (step 9): once the review loop has ended, on the final HEAD | the slow checks the profile defers here (regression comparisons, performance measurements), the full test suites (compared with the baseline), the full e2e, the pre-PR checklist |

A check the profile assigns no moment runs only when the plan names it or
the user asks. A check that compares before and after compares the base
with HEAD once; only a difference the plan does not explain is narrowed
down commit by commit. At one moment, run the checks that share a build
back to back, narrower before wider (the profile lists the groups).

A large plan can be split into milestones: intermediate points, each ending
in settled commits. The review loop runs once per milestone, over the
range from the plan's start commit to HEAD; each milestone's loop starts at
round 1 (high), with the earlier milestones' decisions marked "do not
re-argue". Step 9 runs
per milestone when each milestone gets its own PR, and once at the end when
the milestones go into one PR; in the latter case the slow checks may also
be run at the end of a milestone, to find a problem earlier. "The phase" in
this document is the one plan, or the one milestone, being worked on. The
review loop never waits for the slow checks.

"Round" means one pass of the review loop (steps 6 to 8), never a
verification.

## 1. Find the project profile

```bash
repo=$(basename -s .git "$(git remote get-url origin 2>/dev/null)")
```

Read `profiles/$repo.md` in this skill's directory. The file always lives
there, never in the repository: the repository only supplies the name, its
`origin` remote's repository name, so every worktree of one repository
shares one profile. No profile → follow "Without a profile" in
`references/profile-guide.md`.

## 2. Before the first edit

- Agree on the plan first; this skill does not replace planning.
- The plan names the worktree the change is made in, and its branch. By
  default it is a new worktree at `<main checkout>/.worktrees/<repo>-<topic>`
  (`<main checkout>` is
  `$(cd "$(git rev-parse --git-common-dir)/.." && pwd -P)`, the same from
  any directory of any worktree, so a cycle started inside another worktree
  still nests under the main checkout; `<repo>` as in step 1, `<topic>` a
  few words in kebab case).
  The user may name another place, or the current worktree, instead.
  Create it once the plan is agreed and before the baselines below, which
  build that tree. If `git check-ignore -q .worktrees/x` fails in the main
  checkout, add `.worktrees/` to its `.git/info/exclude` (local; never the
  repository's `.gitignore`).
- Have the first complete plan reviewed once, by a read-only subagent,
  before showing it to the user. The reviewer checks:
  - facts: every file, function, line, call site and config value the plan
    names exists and says what the plan claims;
  - the spec: each commit's spec is concrete enough for the test agent to
    fix expected values, and does not contradict itself;
  - the commits: order, dependencies, and the regression differences each
    may cause;
  - verification: each commit's changed paths get the checks the profile
    ties to them, and a check the profile assigns no moment is named where
    the change needs it;
  - the repository's own rules (`AGENTS.md`, `CLAUDE.md`) and risks the
    plan misses;
  - the design, against `references/design-principles.md` (a new global
    table, a flag where a function would do, an invariant left to a
    convention). Cheapest to change here, before any code exists.

  Check every finding against the code, as in step 6, then show the plan
  with the findings: fold in the ones that hold, list the others with the
  reason. A plan revised from the user's feedback is not reviewed again.
- Take the baselines the profile or the plan asks for NOW, on the commit the
  change starts from (regression comparisons, recorded test outcomes, base
  binaries kept outside the target directory), and let every baseline build
  and run finish before the first edit: each compiles the tree on disk. A
  baseline taken after editing compares the change with itself.
- Never use a bare `git stash` (the stash is shared across worktrees). Set
  work aside with a temporary commit.

## 3. Tests first, from the spec, by a separate agent

A test written by whoever writes the code tends to follow the code rather
than the intent. So the expected values of NEW behaviour are fixed first,
by another agent that sees only the spec.

- **Spec**: what the change is meant to do, written down: the plan, a
  design document, an issue, or for a bug fix the reproducing input and the
  correct result.
- Give the test agent the spec and the project's test conventions (the
  profile says where tests live), never the implementation or a draft of it.
- Tests in their own files (integration tests; unit tests in languages that
  keep them apart, e.g. `*.test.ts`, `test_*.py`, `*_test.go`): the agent
  writes them, touching test files only. Tests inside implementation files
  (e.g. Rust `#[cfg(test)]` modules): it does not open the file; it returns
  the expected values as a list (input, expected result, the spec text it
  comes from), and the implementer inserts them unchanged.
- New tests failing at this point is expected.
- Claude runs the agent as a subagent; other agents use a separate session,
  or the user writes the tests. Never run it and the implementation at the
  same time in one worktree.
- Not this agent's job: tests of the implementation's own design (helpers,
  offsets, internal structure) and structural edits that follow the code
  (counts, sample lists). The implementer writes those.
- Skip this step, and say so, when there is no spec to derive expectations
  from (a refactor or a performance change: "behaviour unchanged" is shown
  by the existing tests and the regression checks) or the change is trivial
  (a typo, one config value).

## 4. Implement

Implement until the step-3 tests pass. When a test and the implementation
disagree, change neither on your own: report the test, the spec text it
came from, and what the code does, and let the user decide. Bending a test
to the code is the bias step 3 exists to remove.

Before committing, read `references/design-principles.md` and check the
structure the commit adds or extends against it, as the reviewers will.
Fix what you find now; a structural problem the review finds costs a round.

## 5. Verify what each change affects, before every commit and after every fix

Work out the affected set from the changed paths
(`git diff --name-only <base>...HEAD` plus the working tree) and the
profile's path table. Run, in order, what belongs to this moment (checks
deferred to the PR are not run here):

1. formatter and linter in the profile's configurations;
2. the project's audit / policy scripts, if any;
3. the tests for the touched modules and their direct consumers;
4. extra regression checks the profile ties to these paths;
5. the e2e cases for the behaviour the change touches (one suite, not all).

- A step the project cannot run (no e2e, no linter) is skipped, and the
  report says so in one line: what was skipped, and what it would have
  covered. Never skip silently. Do not build a new e2e harness on the fly;
  propose one instead.
- A profile tool that does not fit the branch under test is adapted in a
  scratch copy, never in the profile or the repository; the note says what
  was adapted and why (`references/profile-guide.md` says what happens to
  it when the cycle ends).
- A failing check stops the cycle until its cause is found and fixed; that
  is the orchestrator's work, not a wait for the user. A test expectation
  is changed only when the change intends it, and the report names each one.

Report each verification as a progress note and keep going: to the next
planned commit, and after the last one, to the review (step 6). The note
carries the result lines as the tools printed them (e.g. `test result: ok.
364 passed; 0 failed`), the name of every failing test, and every edit to a
spec-derived test since the test agent wrote it (a diff with its reason, or
"no test edits").

Before the review, stop and wait for the user only when a spec-derived test
and the implementation disagree (step 4), or a regression comparison shows
a difference the plan does not allow.

## 6. Review

The review covers the whole change (`<base>..HEAD`), never each commit on
its own, unless the user asks: a later commit often changes what an earlier
finding was about. Run it in a read-only subagent.

- **Which skill** (decide by your skill list, not by which model or agent
  you are):
  1. your own built-in code review skill, if you have one;
  2. otherwise the `dev-cycle-code-review` skill (installed beside this
     one), which any agent can run.
- The subagent MUST run the chosen skill, at **high** effort in the first
  round and **medium** from the second round on, including a round reopened
  by a fix from step 9. Every round covers the whole range; from the second,
  the prompt points it at what changed this round. (High runs several
  finder angles for recall; medium makes one careful correctness pass and
  reports only what it believes is real.) Pass the focus in the skill's
  arguments, in one call: `<level> <base>..HEAD — Report findings only, no
  edits.` then one line per item of `references/design-principles.md` (the
  principle and its "Look for" cell), the earlier rounds' findings and
  decisions, and the user's guiding rules; the skill does not know the list
  otherwise. A fixup that looks small is no reason to skip the skill.
- **If the chosen skill fails to run:** a built-in skill falls back to
  `dev-cycle-code-review` in the same subagent, which then puts one line
  before that skill's report: `built-in review skill failed: <reason>`
  (the method line that follows counts as the required method, with its
  reason given). If that fails too (or is not
  installed), the subagent reviews the range by hand in the same pass —
  correctness, edge cases, regressions, consistency between code, config,
  tests and docs, the repository's own rules, and the design principles —
  and says so on its first line ("manual review — <skill> failed:
  <reason>"); the orchestrator passes that on in its report.

Design principles are never checked by a separate agent or a second review
(that doubles the tokens for one range). The report's first line states the
method actually used (the skill's name and level, e.g.
"dev-cycle-code-review, high", or "manual review — …"); a report without
it, or with another method than required and no reason given, is rerun,
not used.

From the second round on, the prompt carries the earlier rounds' findings
with their decisions, and the decisions already made, marked "do not
re-argue". The orchestrator writes them in this block, after the design
principles, one line per finding of every earlier round:

```
Earlier rounds (do not re-argue):
- R<round>#<n> <path>:<line> — <the finding, one line> — <decision>
User decisions (do not re-argue):
- <a decision the user made, one line>
Changed this round: <commits or files>
```

- `<decision>` is one of: `fixed in <commit>` (the reviewer may check that
  the fix holds, not raise the finding again), `not fixed: <reason>` (the
  user chose not to fix it), `not applicable: <reason>` (the finding did not
  hold against the code).
- "User decisions" are choices that are not tied to one finding: a design
  principle the user decided against, a scope limit, a rule from an earlier
  milestone.
- Keep every line to one line; the block is the reviewer's whole memory of
  earlier rounds.

A fix that changes behaviour the spec covers gets its expected values from
the test agent (step 3), not from the implementer.

Then check every finding against the code before reporting it:

- "X derives from Y" → follow the binding to its source.
- "call sites are A, B, C" → search the name across the workspace and count.
- a race or ordering claim → write the sequence down statement by statement
  and decide from it, not from how likely it sounds.
- the reviewer's tone ("blocking", "likely bug") is not evidence; only what
  the code does is.

## 7. Report, then wait

```
방법: <the reviewer's first line, e.g. dev-cycle-code-review, medium>
결론: 고칠 결함 <n>건 / 사실이지만 동작 영향 없음 <n>건 / 해당 없음·이미 처리됨 <n>건

| # | 지적 | 판정 | 확인 결과 (한 줄) | 수정안 |
| --- | --- | --- | --- | --- |
```

Every finding gets a row. The three labels, always written out (never as
bare letters):

- **고칠 결함** — a runtime defect reproducible from the code, or a guard
  that is silently skipped.
- **사실이지만 동작 영향 없음** — true, with no behavioural effect: doc
  wording, a log level, test consistency, a check on a path no caller
  reaches.
- **해당 없음·이미 처리됨** — the premise is wrong, the code already
  handles it, it is outside the change, or an earlier round answered it.

A design finding follows "Reporting a design finding" in
`references/design-principles.md`. Give a fix sketch (file, line, the
change) for each finding that has one, then STOP. The user picks what is
fixed, from any of the three groups. Do not edit before that.

## 8. Fix, re-verify, re-review

- Fix the chosen findings and amend each fix into the commit it belongs to
  right away (`git commit --amend` when it is HEAD, otherwise
  `git commit --fixup=<commit>` immediately followed by
  `git rebase --autosquash <commit>^`, which needs no `-i` from Git 2.44 on;
  with an older Git use `GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash
  <commit>^`, which opens no editor either). Do not leave `fixup!` commits standing
  between rounds. A new commit only when no existing commit is the fix's
  home.
- Before amending, check the structure the fix adds or extends against
  `references/design-principles.md`, as in step 4.
- When a fix changes behaviour (what a function returns or refuses, an
  order, a message, a default), search the whole repository for what still
  states the old behaviour: comments and doc comments, docs, error and log
  messages, test names and expectations. Fix them in the same amend.
- Do not rewrite history while a background check has the tree checked out
  (a regression dump at a base revision); wait for it first. Keep the
  pre-amend SHA while an unexplained difference is being narrowed down
  commit by commit.
- A finding about a test: a wrong spec-derived expectation, or a case the
  spec covers with no test → the test agent fixes it (step 3), given the
  finding and the spec text (an unclear spec is the user's to settle
  first); a test of the implementation's own design, or a structural
  problem (naming, duplication, comments, counts) → the implementer fixes
  it; a corrected or added test that now fails means the implementation is
  wrong.
- Back to step 5 with the affected set of the FIX, then to step 6 unless
  the round ends the loop (next item).
- The cycle ends after a round that had nothing to fix, or whose fixes
  touched only docs and tests (doc comments included), with every test
  passing. "Tests" means code built or run only for tests: test files and
  directories, and test-only blocks inside production files (e.g. Rust
  `#[cfg(test)]` modules, for which the test agent still returns values
  only, step 3). Code in the normal build is "the implementation", even when
  only tests call it. A round whose fixes touched the implementation is
  always followed by another review round, even if every finding was minor:
  a fix can bring its own defect.

## 9. Before the PR (once)

Once the review loop has ended and the commits are settled, on the final
HEAD:

- the slow checks the profile defers to this moment (regression
  comparisons, performance measurements), for what the phase changed;
- the full test suites from the profile, compared with the baseline if one
  was taken (per-test outcomes: newly failing, disappeared, added);
- the full e2e from the profile;
- the profile's pre-PR checklist.

- A test that passed on the base and now fails is a failure: find the cause
  and fix it (a failure that also happens on the base, or a flaky test that
  passes on a rerun, is reported, not fixed).
- A difference the plan does not allow (a regression comparison, a test
  that disappeared or appeared) stops the cycle: report it and let the user
  decide whether it is a defect to fix or a behaviour to allow. A
  performance or memory measurement follows its profile: where the profile
  says it does not stop the cycle, finish the other checks and report it
  next to the base, but do not move on to the PR until the user has
  decided. An allowed difference is written into the plan's allowed
  differences, so it is not raised again.
- A failure, or a difference the user calls a defect, is fixed and
  re-checked here (only the affected part), goes through the review loop
  (steps 6 to 8), and then this whole step runs again on the new HEAD.
  "Once" in the title means once when nothing needs fixing.

Report the result. Pushing, opening the PR, and commenting are separate
instructions; wait for each.

After a history rewrite (squash, rebase, reword), verify the final HEAD
only, not each commit. A rewrite that leaves the tree identical
(`git diff --quiet <old> <new>`) needs no re-run; otherwise rerun, on the
final HEAD, the checks that the changed files call for
(`git diff --name-only <old> <new>` through the profile's path table, at
the moment the cycle is in).

## 10. Grow the profile

When the cycle ran without a profile, found a profile wrong or incomplete,
or adapted one of its tools, follow "Changing a profile" in
`references/profile-guide.md`: show a draft or a diff, and save it only
after approval.
