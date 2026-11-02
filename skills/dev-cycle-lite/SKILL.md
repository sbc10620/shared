---
name: dev-cycle-lite
description: "Token-light variant of the dev-cycle skill, same flow and profiles: the implementer writes the spec-derived tests before the code, verification runs only what the change affects with tool output cut to result lines, one dev-cycle-code-review round at medium over the whole range, then a second round over the fix diff only when a fix touched the implementation, a third only if the user asks, and the same pre-PR checks. Use ONLY when the user or an instruction file (CLAUDE.md, AGENTS.md) names dev-cycle-lite or asks for the lite cycle ('dev-cycle-lite', 'lite 로', '경량 사이클'). Otherwise use dev-cycle."
user-invocable: true
---

# Development cycle, lite

The dev-cycle flow with fewer agents and fewer tokens. This file is
self-contained: do NOT read `../dev-cycle/SKILL.md`. It shares three files
with dev-cycle, read only where a step says so:
`../dev-cycle/profiles/<repo>.md`, `../dev-cycle/references/design-principles.md`,
and the "Without a profile" section of `../dev-cycle/references/profile-guide.md`.
The profile's own tools live in `../dev-cycle/profiles/<repo>/scripts/`;
any other `scripts/…` path a profile names is the repository's.

Never switch to dev-cycle on your own; if the plan
is big enough to need milestones, tell the user and switch only on their
word. Reports to the user are in the user's language. Push, PR and comments
each wait for their own instruction.

## 1. Profile

```bash
repo=$(basename -s .git "$(git remote get-url origin 2>/dev/null)")
p=SKILL_DIR/../dev-cycle/profiles/$repo.md
preamble() { awk '/^## /{exit} 1' "$1"; }
section()  { awk -v h="## $2" 'index($0,"## ")==1{p=(index($0,h)==1)} p' "$1"; }
preamble "$p"; section "$p" Commands; section "$p" "Path → affected checks"   # …
```

Replace `SKILL_DIR` with this skill's absolute directory. Shell functions
and variables do not survive between tool calls: define them in the same
command that calls them. Read sections, not the whole file; read the whole
profile only if `section` prints nothing in a command that defined it (a
section was renamed).

| when | sections |
| --- | --- |
| at the start | `preamble`, Commands, Path → affected checks, Check cost, When each check runs, Tests, Pitfalls |
| before the first edit | Baselines (always) |
| before the PR | Pre-PR checklist |
| only when the plan names it | measurement sections (Speed check, Memory check, …) |

No profile → read only "Without a profile" in `profile-guide.md` and find
the commands in the repository; its last sentence (the notes become a
profile draft) does not apply. At the
end report one line: "no profile; commands used: …". A profile found wrong,
or a profile tool adapted in a scratch copy (never in the profile or the
repository), is reported in one line at the end, not edited.

## 2. Before the first edit

- The plan names the worktree, its branch and start commit. Default:
  `<main checkout>/.worktrees/<repo>-<topic>`, `<main checkout>` =
  `$(cd "$(git rev-parse --git-common-dir)/.." && pwd -P)`; create it with
  `git worktree add -b <branch> <path> <start>` once the plan is agreed. If
  `.worktrees/` is not ignored, add it to `<main checkout>/.git/info/exclude`.
- No plan-review subagent. Before showing the plan, check it yourself and
  add one line "self-checked: …": every file, function and config value it
  names exists (`git grep`); each commit's spec fixes expected values; each
  changed path gets the checks the profile ties to it.
- Offer a read-only plan-review subagent (run it only if the user agrees)
  when the plan has 4+ commits, changes a public API, config or stored
  format, or the user asks.
- Take the baselines the profile or the plan asks for on the start commit,
  and let every baseline build and run finish before the first edit.
- Never `git stash` (shared across worktrees); use a temporary commit.

## 3. Tests first, by the implementer

Before implementing each commit, write the expected values of NEW
behaviour from the spec, as a list (input, expected result, the spec
sentence it comes from); turn them into tests and see them fail. The only
source of an expected value is the spec text, never the code you are about
to write. Skip this step, saying so in one line, for a change with no spec
(refactor, performance) or a trivial one.

## 4. Implement

Implement until those tests pass. When a test and the code disagree, change
neither: report the test, its spec sentence and what the code does; the
user decides. Before committing, check the structure the commit adds or
extends against `design-principles.md` (read it once per session).

## 5. Verify what the change affects

Affected set, through the profile's path table: for a new commit,
`git diff --name-only <base>...HEAD` plus the working tree; after a fix,
`git diff --name-only <pre-fix SHA> HEAD` only. In order: formatter and linter, audits,
tests of the touched modules and their direct consumers, the path's extra
regression checks, the e2e suite of the touched behaviour (one suite).
Checks the profile defers to the PR do not run here.

Tool output: build quietly, keep logs in a file, bring back result lines
and failure names only. For cargo, failure names come from the `---- `
lines and the `failures:` list (`-q` shows a failure only as `F`):

```bash
log="${TMPDIR:-/tmp}/dcl-$(basename "$(git rev-parse --show-toplevel)")-test.log"
cargo test -q ... >"$log" 2>&1; echo "exit=$?"
grep -E '^test result|^---- |^    [A-Za-z0-9_:]+$|panicked|^error(\[|:)' "$log" | head -60
```

On a failure read only around it (`grep -A`, `sed -n`), never the whole log.

- A step the project cannot run is skipped and reported in one line (what,
  and what it would have covered). Never skip silently.
- A failing check stops the cycle until you find and fix its cause; do not
  wait for the user (a spec test vs. the code: step 4). Change a test expectation only when the change intends
  it, and name it.
- Report each verification as a progress note and keep going: the result
  lines as printed, every failing test's name, and every edit to a
  spec-derived test (diff + reason, or "no test edits").
- Before the review, wait for the user only when a spec test and the code
  disagree, or a regression comparison shows a difference the plan does not
  allow.

## 6. Review

Once every planned commit exists, a read-only subagent runs the
`dev-cycle-code-review` skill at **medium**. Never a built-in review skill,
never high; no model override. Prompt, in one call, in this order (the
skill reads line 1 as level and range):

1. `medium <from SHA>..<to SHA> — Report findings only, no edits.`
2. `Worktree: <path>`
3. one line per item of `design-principles.md` (name + its "Look for" cell);
4. the user's rules (instruction files and this session's decisions);
5. from R2 on: the fix-diff line below, then last the block below, with one
   line per finding of every earlier round, whatever its decision.

```
Earlier rounds (do not re-argue):
- R<round>#<n> <path>:<line> — <finding, one line> — <fixed in "<commit subject>" | not fixed: <reason> | not applicable: <reason>>
User decisions (do not re-argue):
- <one line each>
Changed this round: <files> (git diff <from SHA> <to SHA>)
Verified this round: <checks, one line>
```

Always SHAs, never `HEAD`.

| round | when | from..to | looks at |
| --- | --- | --- | --- |
| R1 | all commits exist | `<base>..<head>` | the whole change |
| R2 | R1's fixes touched the implementation | `<R1 head>..<head after fixes>` | (a) the chosen fixes hold, (b) new defects in the fix diff and its direct callers; principles on the fix diff only |
| R3, R4, … | the previous round's fixes touched the implementation AND the user says run it | previous round's head..now | as R2 |

The fix-diff line, for R2 and later: "The range is the fix diff between two
heads. git log may list rewritten commits; ignore them and the commit
count. The intent of this round is the findings marked `fixed in` below.
Judge by git diff." Record each round's head SHA before fixing. If a
rebase moved the base meanwhile, rebase a copy of the old head onto the
same base in a scratch worktree, never the one under work
(`git worktree add --detach <tmp> <old head SHA>`, then
`git -C <tmp> rebase --onto <new base> <old base>`), use its HEAD SHA as
`from` and remove the scratch worktree. If that rebase conflicts, the round
reviews `<new base>..<head>` at medium instead: same round number, the
block stays, the fix-diff line is left out.

If the skill fails to run, the same subagent reviews by hand and starts
with `manual review — dev-cycle-code-review failed: <reason>`. A report
whose first line is not `dev-cycle-code-review, medium (…)` and gives no
reason is rerun, not used.

Check every finding against the code before reporting: follow a "derives
from" to its source; count call sites by searching the name; decide an
ordering claim from the written-out statement sequence; tone is not
evidence.

**The review ends** after a round with nothing to fix, or whose fixes
touched only docs and tests. "Docs" include doc comments and comments in
production files. "Tests" = code built or run only for tests
(test files and directories, test-only blocks such as Rust `#[cfg(test)]`);
code in the normal build is the implementation, even if only tests call it.
After R2's (or a later round's) fixes touched the implementation: verify
(step 5), then ask the user whether to run the next round; if not, the
review ends.

## 7. Report, then wait

```
방법: <the reviewer's method line>
결론: 고칠 결함 <n>건 / 사실이지만 동작 영향 없음 <n>건 / 해당 없음·이미 처리됨 <n>건

| # | 지적 | 확인 결과 (CONFIRMED/PLAUSIBLE, 한 줄) | 수정안 |
| --- | --- | --- | --- |
(고칠 결함 rows only)

사실이지만 동작 영향 없음: R1#3 <short name>, R1#5 <short name>, …
해당 없음·이미 처리됨: R1#2 <short name — reason>, …
```

- **고칠 결함**: a runtime defect reproducible from the code, or a guard
  silently skipped.
- **사실이지만 동작 영향 없음**: true, no behavioural effect (doc wording,
  log level, test consistency, a path no caller reaches). A design finding
  without runtime effect goes here, its name starting with "설계:".
- **해당 없음·이미 처리됨**: wrong premise, already handled, outside the
  change, or answered in an earlier round.

Always write the labels out. Then STOP: the user picks what to fix, from
any group, and may ask for details of any one.

## 8. Fix

- Put each fix into its commit at once: `git commit --amend` for HEAD,
  otherwise `git commit --fixup=<commit>` then
  `git rebase --autosquash <commit>^` (Git 2.44+; older:
  `GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash <commit>^`). Leave no
  `fixup!` commits. A new commit only when no commit is the fix's home.
- Check the structure the fix adds against `design-principles.md`.
- A fix that changes behaviour: search the repository for comments, docs,
  messages and test names still stating the old behaviour; fix them in the
  same amend. A fix to spec-covered behaviour gets its expected values
  rewritten first, from the spec (step 3).
- Do not rewrite history while a background check uses the tree.
- Then step 5 for the fix's affected set (`git diff --name-only <pre-fix
  SHA> HEAD`), then the next round by the table in step 6, or the end.

## 9. Before the PR (once)

On the final HEAD, with step 5's output rule:

- the slow checks the profile defers here (regression comparisons;
  measurements only when the plan names them), the full suites (compared
  per test with the baseline if one was taken), the full e2e, the profile's
  Pre-PR checklist;
- a test that passed on the base and fails now is a defect: find and fix
  it. One that fails on the base too, or passes on a rerun, is reported;
- a difference the plan does not allow (a regression comparison, a test
  gone or added) stops the cycle; the user decides, and an allowed one is
  written into the plan. A measurement follows its profile's rule.
- A fix here that touched the implementation reopens the review as the next
  round, shaped like R2 over this fix's diff, numbering continuing. It runs
  without asking if it is R2; if it is R3 or later, ask the user first. Then
  this step runs again on the new HEAD. A docs/tests-only fix: verify its
  affected set and rerun this step.

After a history rewrite: identical tree (`git diff --quiet <old> <new>`) →
no rerun; otherwise rerun what the changed files call for. A rebase onto a
new base also moves `<base>`: retake the baselines there and rerun the full
suites.

Report the result and stop.
