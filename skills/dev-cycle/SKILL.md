---
name: dev-cycle
description: "Run a code change through the development cycle that ends in a PR: the first plan reviewed once by a read-only subagent before user feedback; for each planned commit, tests for new behaviour written first from the spec by a separate agent, implement, verify only what the change affects; once every commit exists, review the whole range with /code-review, fix, and repeat until the review asks for no change or only doc changes; slow checks at the end of the phase, then the full suites and the full e2e once before the PR. Project-specific commands come from profiles/<repo>.md; a step the project has no way to run is skipped and reported. Use when implementing a planned change in a repository, when the user asks to verify, review or 'run the cycle' on a change ('개발 사이클', '리뷰 반복', 'PR 전 검증'), or before opening a PR."
user-invocable: true
---

# Development cycle

One loop for every code change that will become a PR:

```
plan ─► plan review (read-only subagent, once) ─► user feedback ─► agreed plan

for each planned commit:
  spec ─► tests from the spec (separate agent) ─► implement ─► verify what it affects ─► commit

once every planned commit exists:
  /code-review over the whole range ─► report, wait for decisions
        ▲                                         │
        └── verify the fix ◄── fix the chosen findings (amend into their commits)
  ends when a review round asks for no change, only doc changes, or only
  spec-derived test rows that pass

end of the phase: the slow checks the profile defers to it
then, once, before the PR: full suites + full e2e on the final HEAD
```

Running everything on every verification is wasted time: a full test suite or a
release e2e build takes tens of minutes, and a fix to one module cannot break
another module's tests. The full run happens once, on the commit that will be
reviewed.

This document is Claude-facing and stays in English. Reports to the user are in
the user's language.

## Roles and prompts

The one running this skill is the **orchestrator**: it implements, and it
writes the prompt for every helper agent from the plan. There are no fixed
agent definitions; each prompt has two parts.

| Role | Always in the prompt | Chosen from the plan for this call |
| --- | --- | --- |
| Plan reviewer (step 1) | Read-only; the plan and the repository, never a draft implementation; report only, change nothing | The plan, the user's request and decisions so far, the profile's path table |
| Test agent (step 1a) | Spec only, never the implementation; edit test files only, or return values as a list when tests live inside implementation files; a spec that contradicts itself, or an example that fails its own rule, is reported, not fixed | The spec for this commit's scope (the design doc's sections, shapes, rules, labels, layers), the user's decisions that override the doc, where the tests go |
| Reviewer (step 3) | Read-only; the required method (step 3) and the method on the first line; earlier rounds' decisions are not re-argued | The range, what changed this round, earlier findings and their decisions, the user's decisions, what was already verified |

- Never pass the test agent the implementation, nor test cases the
  orchestrator picked itself: both bring the implementer's view back in.
- Never write a "do it yourself if the skill is missing" fallback into a
  reviewer prompt (step 3).
- When reporting a helper's result, say in a line or two what it was given.
  Show the full prompt only when the user asks.

## When each check runs

Every check belongs to one of three moments. The profile assigns its checks
to them; without a profile, put fast checks (formatter, linter, the touched
modules' tests) in the first and anything that takes tens of minutes in the
second.

| moment | what runs |
| --- | --- |
| every verification: after implementing a commit, after each review fix | the fast checks of step 2, for the affected set |
| end of the phase: the review loop has ended and the commits are settled | the slow checks the profile defers here (regression comparisons, e2e suites, performance measurements) |
| before the PR: once, on the final HEAD | step 6 |

A phase is one unit of work that ends in settled commits: the commits of one
plan, or one milestone of a longer plan. A failure found at the end of the
phase is fixed and re-checked there (only the affected part), then goes
through the review loop like any other fix. The review loop never waits for
the slow checks.

A check the profile assigns no moment runs only when it is called for: the
plan names it for the commits that need it, or the user asks. The plan
reviewer (step 1) checks that the plan names such a check where the change
needs it.

"Round" in this document means one pass of the review loop (step 3 to
step 5), never a verification.

A check that compares before and after (a regression comparison, a test
outcome comparison, a performance measurement) compares the base with HEAD
once. When every difference is one the plan explains, it is done. Only an
unexplained difference is narrowed down commit by commit, to find the
commit that made it.

## When the review runs

The review covers the whole change, not each commit on its own. A change
planned as several commits goes through steps 1a and 2 commit by commit, and
each commit is made as soon as its checks pass. Step 3 starts once every
planned commit exists and reviews `<base>..HEAD` in one pass. Fixes go into
the commit they belong to (step 5), and every later round reviews the whole
range again. A change of one commit is the same loop with a range of one.

Reviewing after each commit is not wrong, just slower: a later commit often
changes what an earlier finding was about. Do it only when the user asks.

## 0. Find the project profile

```bash
repo=$(basename -s .git "$(git remote get-url origin 2>/dev/null)")
```

Read `profiles/$repo.md` in this skill's directory. Keyed by the remote's
repository name, not the directory, so every worktree of one repository shares
one profile. A profile says, per step, which commands to run and which changed
paths call for which tests, extra regression checks and e2e suites.

No profile → discover from the repository: its `AGENTS.md` / `CLAUDE.md`, CI
workflow files, `Cargo.toml` / `package.json` / `Makefile` test targets, and
any e2e skill named for the project. Note what you used; step 7 turns it into a
profile.

## 1. Before the first edit

- Agree on the plan first; this skill does not replace planning.
- Have the first complete plan reviewed once, by a read-only subagent, before
  showing it to the user for feedback. The reviewer checks:
  - facts: every file, function, line, call site and config value the plan
    names exists and says what the plan claims;
  - the spec: each commit's spec is concrete enough for the test agent to
    fix expected values, and does not contradict itself;
  - the commits: order and dependencies, and the allowed regression
    differences of each;
  - verification: each commit's changed paths get the checks the profile
    ties to them;
  - the repository's own rules (`AGENTS.md`, `CLAUDE.md`) and risks the plan
    misses.

  Check every finding against the code, as in step 3, then show the plan with
  the findings: fold in the ones that hold, and list the ones left out with
  the reason. A plan revised from the user's feedback is not reviewed again.
- If the profile asks for a baseline (a regression comparison, recorded test
  outcomes), take it NOW, on the commit the change starts from. A baseline
  taken after editing compares the change with itself.
- Never use a bare `git stash` (the stash is shared across worktrees). Set
  work aside with a temporary commit.

## 1a. Tests first, from the spec, by a separate agent

A test written by whoever writes the code tends to follow the code rather
than the intent. So the expected values of NEW behaviour are fixed first,
by another agent that sees only the spec.

- **Spec** means what the change is meant to do, written down: the plan, a
  design document, an issue, or for a bug fix the reproducing input and the
  correct result.
- Give the test agent the spec and the project's test conventions (the
  profile says where tests live). Never the implementation, nor a draft of
  it.
- What it writes, by where the tests live (the profile says which applies):
  - tests in their own files (integration tests; unit tests in languages
    that keep them apart, e.g. `*.test.ts`, `test_*.py`, `*_test.go`): it
    writes them directly, touching test files only;
  - tests inside implementation files (e.g. Rust `#[cfg(test)]` modules):
    it does not open the file; it returns the expected values as a list
    (input, expected result, the spec text it comes from), and the
    implementer inserts them unchanged.
- New tests failing at this point is expected.
- Who runs it: Claude runs it as a subagent; other agents use a separate
  session; or the user writes the tests.
- Not this agent's job: tests that check the implementation's own design
  (helpers, offsets, internal structure) and structural edits that follow
  the code (counts, sample lists, keeping existing rows). The implementer
  writes those.
- Do not run the test agent and the implementation at the same time in one
  worktree.
- Skip this step, and say so in the report, when there is no spec to derive
  expectations from (a refactor or a performance change: there "behaviour
  unchanged" is shown by the existing tests and the regression checks) or
  the change is trivial (a typo, one config value).

Then implement until those tests pass. When a test and the implementation
disagree, change neither on your own: report the test, the spec text it came
from, and what the code does, and let the user decide. Bending a test to the
code is the bias this step exists to remove.

## 2. Verify what the change affects

Work out the affected set from the changed paths
(`git diff --name-only <base>...HEAD` plus the working tree) and the profile's
path table. Run, in order, the checks that belong to this moment (see "When
each check runs"); a check the profile defers to the end of the phase or to
the PR is not run here:

1. formatter and linter in the profile's configurations;
2. the project's audit / policy scripts, if any;
3. the tests for the touched modules and their direct consumers;
4. extra regression checks the profile ties to these paths;
5. the e2e cases for the behaviour the change touches (one suite, not all).

A step the project cannot run (no e2e, no linter) is skipped, and the report
says so in one line: what was skipped, and what it would have covered. Never
skip silently. Do not build a new e2e harness on the fly; propose one instead.

A profile tool that does not fit the branch under test (it calls an API the
branch or the base lacks, or expects a file layout the tree does not have)
is adapted in a scratch copy for this change, never in the profile and
never in the repository. The verification note says what was adapted and
why.

When the cycle ends, judge each adaptation: would the profile's tool be
better off working this way on every branch (a layout or API difference
that will recur, not a one-off workaround)? If so, propose folding it into
the profile's tool so that one tool serves both, together with the profile
text that describes the tool. Once the user agrees, change the tool, update
the profile, and sync the shared copy (step 7). A one-off adaptation stays
in scratch and is not carried forward.

A failing check stops the cycle until its cause is found and fixed; that is
the orchestrator's work, not a wait for the user. A test expectation is
changed only when the change intends it, and the report names each one.

Report each verification as a progress note and keep going: once a commit's
checks pass, move on to the next planned commit, and after the last one, to
the review (step 3). The note carries:

- the result lines as the tools printed them (e.g. `test result: ok. 364
  passed; 0 failed`) and the name of every failing test;
- every edit to a spec-derived test since the test agent wrote it, as a diff
  with its reason, or "no test edits".

Before the review, stop and wait for the user only when a spec-derived test
and the implementation disagree (step 1a), or a regression comparison shows
a difference the plan does not allow.

## 3. Review

Run the review in a subagent, read-only, over the change (`<base>..HEAD`):

- **Claude (Claude Code):** the subagent MUST run the `code-review` skill at
  high effort. No substitute review: if the skill cannot be run, the subagent
  stops and reports that, and the round is repeated once it can. A fixup that
  looks small is not a reason to skip the skill. Do not write an "if the skill
  is unavailable, review it yourself" fallback into the prompt; a subagent
  reads it as permission.
- **Other agents** (no `code-review` skill): review the range by hand for
  correctness, edge cases, regressions, consistency between code, config,
  tests and docs, and the repository's own rules.

Either way, the report's first line states the method actually used
("code-review skill, high" / "manual review"). A report without that line,
or with a different method than required, is rerun, not used.

From the second round on, the prompt carries the earlier rounds' findings
with their decisions, and the decisions already made, marked "do not
re-argue".

A fix that changes behaviour gets its expected values the step-1a way when
the spec covers the case: from the test agent, not from the implementer.

Then check every finding against the code before reporting it:

- "X derives from Y" → follow the binding to its source.
- "call sites are A, B, C" → search the name across the workspace and count.
- a race or ordering claim → write the sequence down statement by statement and
  decide from it, not from how likely it sounds.
- the reviewer's tone ("blocking", "likely bug") is not evidence; only what the
  code does is.

## 4. Report, then wait

```
결론: 고칠 결함 <n>건 / 사실이지만 동작 영향 없음 <n>건 / 해당 없음·이미 처리됨 <n>건

| # | 지적 | 판정 | 확인 결과 (한 줄) | 수정안 |
| --- | --- | --- | --- | --- |
```

Every finding gets a row. The three labels, always written out (never as bare
letters):

- **고칠 결함** — a runtime defect reproducible from the code, or a guard that
  is silently skipped.
- **사실이지만 동작 영향 없음** — true, with no behavioural effect: doc wording,
  a log level, test consistency, a check on a path no caller reaches.
- **해당 없음·이미 처리됨** — the premise is wrong, the code already handles
  it, it is outside the change, or an earlier round answered it.

Give a fix sketch (file, line, the change) for each finding that has one, then
STOP. The user picks what is fixed, from any of the three groups. Do not edit
before that.

## 5. Fix, re-verify, re-review

- Fix the chosen findings and amend each fix into the commit it belongs to
  right away (`git commit --amend` when it is HEAD, otherwise
  `git commit --fixup=<commit>` immediately followed by
  `git rebase -i --autosquash`). Do not leave `fixup!` commits standing
  between rounds. A new commit only when no existing commit is the fix's
  home (e.g. a change to a file the series never touched for that purpose).
- Rewriting history while a background check has the tree checked out (a
  regression dump at a base revision) breaks that check: wait for it first.
- Keep the pre-amend SHA for the next verification: it is the base of the
  fix's regression comparison, when the profile has one.
- When a finding is about a test:
  - a spec-derived expectation is wrong, or a case the spec covers has no
    test → the test agent fixes it (step 1a), given the finding and the
    spec text; if the spec itself is unclear or wrong, the user decides
    the spec first;
  - a test of the implementation's own design, or a structural problem
    (naming, duplication, comments, counts) → the implementer fixes it;
  - a corrected or added test that now fails means the implementation is
    wrong: fix the code, then verify and review as for any code fix.
- Back to step 2 with the affected set of the FIX, not of the whole change.
- Back to step 3. A round whose fixes touched code is always followed by
  another review round, even if every finding was minor: a fix can bring its
  own defect.
- The cycle ends after a round whose fixes were doc-only, had nothing to
  fix, or only changed spec-derived test rows or expected values written by
  the test agent, all passing. A round that changed test logic (helpers,
  how results are compared, test structure) or the implementation is
  followed by another review round.

## 6. Before the PR (once)

On the final HEAD:

- the full test suites from the profile, compared with the baseline if one was
  taken (per-test outcomes: newly failing, disappeared, added);
- the full e2e from the profile;
- the profile's pre-PR checklist.

Report the result. Pushing, opening the PR, and commenting are separate
instructions; wait for each.

After a history rewrite (squash, rebase, reword), verify the final HEAD only,
not each commit. A rewrite that leaves the tree identical
(`git diff --quiet <old> <new>`) needs no re-run.

## 7. Grow the profile

When the cycle ran without a profile, or found a profile wrong or incomplete,
show a profile draft (or a diff of the profile) built from the commands that
were actually used, and save it to `profiles/<repo>.md` only after approval.

A profile holds:

```markdown
# <repo>

## Commands
- formatter / linter (every configuration that CI runs)
- audits
- full test suites (pre-PR), and how long they take
- e2e: the skill or script, how to pick one suite

## Path → affected checks
| changed path | tests | extra checks | e2e suite |

## When each check runs
| when | checks |   (every verification / end of the phase / before the PR)

## Tests: where they live, who writes them
- where new behaviour's tests go (files, tables), and whether unit tests sit
  inside implementation files (then the test agent returns values only)

## Baselines to take before editing
## Pre-PR checklist
## Pitfalls (things that cost time before)
```

Scripts a profile needs live beside it in `profiles/<repo>/scripts/`. They are
personal tooling: they are never added to the project repository, and the
shared copy of this skill leaves them out.
