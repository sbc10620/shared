---
name: dev-cycle-code-review
description: "Review a commit range or a pull request for real defects and report findings only, with no edits: gather the change and its context, look for defects at medium depth (one careful correctness pass) or high depth (several separate angles), verify every candidate against the code, and report the confirmed and plausible ones in a fixed format whose first line names the method. Agent-neutral: it needs only git, a shell and file reading; it uses sub-agents when the agent can start them and sequential passes otherwise. Use it as the dev-cycle reviewer when the agent has no built-in code review skill, or whenever the user asks for a review of a range ('리뷰해줘', 'review this range', 'review the PR') and no built-in review skill is available. Do NOT use it to fix code, to triage a review bot's comment (ai-review-triage does that), or to review a plan."
---

# Code review for the development cycle

A reviewer that any coding agent can run. It answers one question for a
range of commits: **what in this change would behave wrongly, and how do we
know?** It never edits, commits, pushes or comments; the caller decides what
happens to each finding.

This document is agent-facing and stays in English. The report is written in
English unless the caller asks for another language; the caller translates it
for the user.

## Input

The caller passes, in one message:

```
<level> <base>..<head> — Report findings only, no edits.
<focus lines: one per design principle ("<name>: <what to look for>"),
 the user's guiding rules, earlier rounds' findings and decisions marked
 "do not re-argue", and what changed this round>
```

- `<level>` is `medium` or `high`. Missing → `medium`.
- The caller names the worktree; run every command there (`git -C <path>`).
- The range may instead be a PR number: take `baseRefName` and `headRefOid`
  from `gh pr view <N> --json baseRefName,headRefOid`, run
  `git fetch origin <baseRefName> pull/<N>/head`, and review
  `$(git merge-base origin/<baseRefName> <headRefOid>)..<headRefOid>`.
- Everything after the first line is **focus**: it adds what to look for and
  what not to raise. It never narrows the correctness pass.
- When there are earlier rounds (or milestones), the focus ends with the
  caller's record of them, in this block:

  ```
  Earlier rounds (do not re-argue):
  - R<round>#<n> <path>:<line> — <the finding, one line> — <decision>
  User decisions (do not re-argue):
  - <a decision the user made, one line>
  Changed this round: <files> (git diff <previous round's head SHA> <head SHA>)
  Verified this round: <the checks run, one line>
  ```

  `<line>` is as of the round the finding was raised; with milestones the id
  is `M<milestone>R<round>#<n>`. `<decision>` is `fixed in "<commit
  subject>"`, `not fixed: <reason>` or `not applicable: <reason>`. See "Later rounds" for how each is used.

## Step 1 — Gather the change and its context

```bash
git log --oneline <base>..<head>
git diff --stat <base>..<head>
git diff <base>..<head>
```

- For every changed hunk, read the **whole enclosing function** (or type),
  not only the hunk, at `<head>` (`git show <head>:<path>`).
- For every changed function, type, constant or default, find its callers
  and readers across the repository (`git grep -n '<name>' <head>`), tests included, and
  note the ones outside the diff. A change is only as safe as its callers.
- Read the repository's own rules that govern the touched paths:
  `AGENTS.md` / `CLAUDE.md` in the repository root and in each touched
  directory and its parents up to the repository root.
- Write down, before looking for defects, what the change is meant to do
  (from commit messages and the focus). A finding is a gap between that
  intent and what the code does.

Scope: judge what the range adds or changes, plus existing code the change
makes reachable or relies on in a new way. A problem in untouched code that
the change does not reach is out of scope; mention it at most once under
"Not covered".

## Step 2 — Look for defects

### `medium`: one careful pass

Go through the diff file by file. For each hunk ask the questions of the
`high` angles below, but in one pass. Keep only candidates you would bet on
after reading the code twice. Prefer few real findings over many guesses.

### `high`: separate angles

Run each angle as its own pass with a fresh look. If the agent can start
sub-agents, give each angle to its own read-only sub-agent in parallel (the
diff, the context notes from Step 1, its angle, the focus); otherwise run the
angles one after another and write each angle's candidates down before
starting the next, so one angle's conclusions do not steer the next.

1. **Correctness and edge cases** — empty, single, maximum and boundary
   inputs; off-by-one; byte vs character offsets and non-ASCII text; integer
   overflow and narrowing casts (32-bit targets included); `None` / null /
   error values; the first and the last iteration.
2. **Behaviour change and regressions** — every caller and reader found in
   Step 1: does each still get what it relied on (return value, order,
   default, error, side effect, timing)? Changed defaults and renamed or
   removed items; serialised or persisted formats; public API.
3. **Concurrency, lifetime and failure handling** — lock order and scope,
   check-then-act, a value read before another thread can update it,
   cancellation and early return between paired steps, panics and `unwrap`
   on input-derived data, resources not released, retries, and **fail-open
   guards**: any path where a check, a filter or a guard is silently skipped.
4. **Consistency** — code vs configuration vs tests vs docs and comments:
   a comment, doc, error message or test name that still states the old
   behaviour; two places that must agree and now do not.
5. **Repository rules and design principles** — the rules from Step 1 and
   each design principle in the focus, applied only to structure the change
   adds or extends. Report a principle only with concrete code and what it
   changes for a caller, never in the abstract.
6. **Tests** — new behaviour with no test that would fail without it; a test
   that cannot fail (asserts nothing that the change affects); a test
   expectation edited to match a regression.

For every candidate, record: where (`path:line` at `<head>`), the claim in
one sentence, and the concrete input or state that would show it.

## Step 3 — Verify every candidate

Each candidate is checked against the code before it is reported. Try to
refute it:

- "X comes from Y" → follow the binding to its source.
- "callers are A, B, C" → search the name across the repository and count.
- a race or ordering claim → write the sequence down statement by statement,
  per thread, and decide from the sequence, not from how likely it sounds.
- a missing check → find whether an earlier layer already guarantees it.
- a wrong result → build the concrete input and walk the code with it.
- a claim about a test → read the test and what it asserts.

Then give each surviving candidate a verdict:

- **CONFIRMED** — the failure follows from the code for a concrete input or
  state you can name.
- **PLAUSIBLE** — the reasoning holds but depends on something you could not
  check (runtime configuration, an external service, an unread dependency).
  Say what would confirm it.
- Refuted → drop it, and list it in one line under "Checked and dropped".

At `high`, verify in a separate pass from finding (a separate sub-agent per
angle's candidates if the agent can start them), and ask the verifier to
argue against the finding first. At `medium`, verify inline but still read
the code again before keeping a finding.

**Tone is not evidence.** Do not upgrade a finding because it sounds serious,
and do not keep one because the finder was sure.

## Step 4 — Report

The first line is the method actually used, exactly:

```
dev-cycle-code-review, <medium|high> (<sequential passes|parallel sub-agents>)
```

When this skill runs because a built-in review skill failed, one line goes
before it: `built-in review skill failed: <reason>`.

Then:

```
Range: <base>..<head> (<n> commits, <m> files)
Findings: <k>

### 1. <the claim, one line> — <category> — <CONFIRMED|PLAUSIBLE>
- Where: <path>:<line>
- What: <one sentence: what the code does and why it is wrong>
- Failure scenario: <concrete input or state> → <wrong result>
- Suggested fix: <file, line, the change; a sketch, not applied>

### 2. …

## Checked and dropped
- <candidate, one line> — <why it does not hold>

## Not covered
- <what was not checked and why: a path not read, a claim needing a run>
```

- Rank findings most severe first: security fail-open and data loss, then
  wrong output, crash, regression for an existing caller, consistency, docs,
  tests.
- `<category>` is one of: `correctness`, `regression`, `concurrency`,
  `error-handling`, `security`, `consistency`, `docs`, `tests`,
  `performance`, `design: <principle>`.
- With no findings, write `Findings: 0` and keep "Checked and dropped" and
  "Not covered": they show what the round looked at.
- Keep every finding to these lines. The caller classifies them and talks to
  the user; long prose here only costs the caller time.

## Later rounds

When there are earlier rounds, the focus carries the earlier findings and the
user's decisions:

- `not fixed` and `not applicable` lines, and every "User decisions" line:
  do not raise them again, unless this round's change made the problem
  worse — then say what changed and cite the line (`R1#3`).
- `fixed in` lines: check that the fix holds and did not break
  anything else; report a problem with the fix as a new finding that cites
  the line, never the original finding again.
- Look hardest at "Changed this round", but still run the pass over the
  whole range: a fix can break code it did not touch.

## Never

- edit files, stage, commit, push, or post comments or reviews
- report formatting or lint findings a project tool enforces (formatter,
  linter), unless they hide a defect
- report a preference as a defect, or a principle without concrete code
- widen the scope to untouched code the change does not reach
