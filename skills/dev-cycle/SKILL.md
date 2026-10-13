---
name: dev-cycle
description: "Run a code change through the development cycle that ends in a PR: implement, verify only what the change affects, review with /code-review, fix, and repeat until the review asks for no change or only doc changes; then run the full suites and the full e2e once before the PR. Project-specific commands come from profiles/<repo>.md; a step the project has no way to run is skipped and reported. Use when implementing a planned change in a repository, when the user asks to verify, review or 'run the cycle' on a change ('개발 사이클', '리뷰 반복', 'PR 전 검증'), or before opening a PR."
user-invocable: true
---

# Development cycle

One loop for every code change that will become a PR:

```
implement ─► verify what it affects ─► /code-review ─► report, wait for decisions
    ▲                                                        │
    └──────────── fix the chosen findings ◄──────────────────┘
ends when a review round asks for no change, or only doc changes
then, once, before the PR: full suites + full e2e on the final HEAD
```

Running everything on every round is wasted time: a full Rust test suite or a
release e2e build takes tens of minutes, and a fix to one module cannot break
another module's tests. The full run happens once, on the commit that will be
reviewed.

This document is Claude-facing and stays in English. Reports to the user are in
the user's language.

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
any e2e skill named for the project. Note what you used; step 6 turns it into a
profile.

## 1. Before the first edit

- Agree on the plan first; this skill does not replace planning.
- If the profile asks for a baseline (a regression comparison, recorded test
  outcomes), take it NOW, on the commit the change starts from. A baseline
  taken after editing compares the change with itself.
- Never use a bare `git stash` (the stash is shared across worktrees). Set
  work aside with a temporary commit.

## 2. Verify what the change affects

Work out the affected set from the changed paths
(`git diff --name-only <base>...HEAD` plus the working tree) and the profile's
path table. Run, in order:

1. formatter and linter in the profile's configurations;
2. the project's audit / policy scripts, if any;
3. the tests for the touched modules and their direct consumers;
4. extra regression checks the profile ties to these paths;
5. the e2e cases for the behaviour the change touches (one suite, not all).

A step the project cannot run (no e2e, no linter) is skipped, and the report
says so in one line: what was skipped, and what it would have covered. Never
skip silently. Do not build a new e2e harness on the fly; propose one instead.

A failing check stops the cycle. Find the cause before going on; a test
expectation is changed only when the change intends it, and the report names
each one.

## 3. Review

Run `/code-review` (high effort) in a subagent, read-only, over the change
(`<base>..HEAD`). From the second round on, the prompt carries the earlier
rounds' findings with their decisions, and the decisions already made, marked
"do not re-argue".

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

- Fix the chosen findings. Fold each fix into the commit it belongs to
  (`git commit --fixup` + autosquash), unless the user wants a separate commit.
- Back to step 2 with the affected set of the FIX, not of the whole change.
- Back to step 3. A round whose fixes touched code is always followed by
  another review round, even if every finding was minor: a fix can bring its
  own defect.
- The cycle ends after a round whose fixes were doc-only, or that had nothing
  to fix.

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

## Baselines to take before editing
## Pre-PR checklist
## Pitfalls (things that cost time before)
```

Scripts a profile needs live beside it in `profiles/<repo>/scripts/`. They are
personal tooling: they are never added to the project repository, and the
shared copy of this skill leaves them out.
