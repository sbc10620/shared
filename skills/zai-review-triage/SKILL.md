---
name: zai-review-triage
description: Triage a Z.ai (or any GitHub-Actions bot) code-review comment on a pull request — fetch the bot's latest comment, verify every finding against the actual code, classify each one (a defect to fix / true but no behavioural effect / not applicable or already handled), and report a table plus a stop/continue verdict using those plain labels, not bare letters; code changes happen only for defects to fix and only after the user approves. Response comments cover every finding, in the PR description's language. Use this whenever the user says a Z.ai review (or "bot review", "자동 리뷰", "Z.ai 리뷰") has been posted or updated on a PR, asks to "check the review", "review the review", or "respond to the review" — even if they do not name the bot. Do NOT use it for a human reviewer's comments or for reviewing the PR's own code from scratch.
---

# Z.ai review triage

A review bot re-reads the WHOLE pull request on every push and is built to
always find something. So the question is never "are there findings" — there
always are — but "is any finding worth a commit". This skill answers that
question the same way every round, so a PR does not spend three rounds fixing
comment wording while the human reviewer waits.

The user's standing decisions, learned from PR AGENTIC/ARGO#3392 (three rounds,
two real defects found, ~25 findings total):

- Only **A-grade** findings (real runtime defects, security fail-opens) get
  fixed. Doc nits and defensive code for unreachable paths do not — they are
  "too repetitive" and the next commit that touches that code fixes them.
- A round with zero A findings ENDS the bot review. Hand off to the human
  (CODEOWNERS) review.
- Nothing is pushed, committed, or commented without an explicit instruction.
  The user decides each of those separately.

## Step 1 — Fetch the bot's comment (it is overwritten, not appended)

```bash
gh pr view <PR> --json comments --jq '[.comments[] | select(.author.login=="github-actions")] | last | .body'
```

The bot **edits its single comment in place** on every push. Looking for a
"new" comment finds nothing; the comment count does not change. Always read the
CURRENT body of the bot's comment. Count the round from how many response
comments the user has already posted on the PR.

If no PR number is given, use the open PR for the current branch:
`gh pr list --head "$(git branch --show-current)" --json number`.

## Step 2 — Verify every finding against the code

For each numbered finding, open the file and function it names and check the
claim. Typical checks:

- "X derives from Y" → `rg` the binding and follow it to its source.
- "call sites are A, B, C" → `rg` the function name across the workspace, tests
  excluded, and count.
- "feature/dependency affects other crates" → `cargo tree -e features -i <dep>`
  or `rg '^<dep>' */Cargo.toml`.
- Race / ordering claims → write the sequence down statement by statement.
  Decide from the sequence, not from "that seems unlikely". The one A-grade
  race in #3392 (a TUI reap branch reading a channel one statement too early)
  looked unlikely and was real; a later "turn identity" race looked similar
  and was not, because an aborted task cannot send after its next `.await`.

**The bot's tone is not evidence.** "Blocking", "must-verify", "likely bug"
carry no weight; only what the code does. In #3392 round 3 both "blocking"
items were wrong, and a "minor note" in round 2 was the round's only real fix.

Keep a list of findings already answered in earlier rounds. The bot does not
read its own history and repeats them; a repeat is graded C with "answered in
round N" and no further work.

## Step 3 — Classify each finding

The letters A / B / C below are shorthand for this file and its references
only. **Never show a bare letter to the user or on the PR** — always use the
plain label (column 2), or, if a letter appears anywhere, a legend next to it.

| Grade | Plain label (what the user sees) | Definition | Action |
| --- | --- | --- |
| **A** | 고칠 결함 (defect to fix) | A runtime defect you can reproduce from the code, or a security fail-open (a path where a guard is silently skipped). | Fix — after approval. |
| **B** | 사실이지만 동작 영향 없음 (true, no behavioural effect) | True, but no behavioural effect: doc accuracy, log level, test consistency, defensive checks on paths no current caller can reach, boot-time one-off costs. | Do not fix. List it. |
| **C** | 해당 없음·이미 처리됨 (not applicable / already handled) | The code already handles it; the premise is wrong; it is outside the PR's scope (a `tinicore-traits` type change, another crate, a CI workflow); or it was answered in an earlier round (say which). | List it with the one-line reason. |

Two refinements the user set explicitly:

- A stale doc sentence is B **unless it is the stated premise of a design
  decision elsewhere** ("X does Y, therefore here we do Z") — a wrong premise
  misleads the next agent and the bot alike, so that is "materially wrong" and
  may be fixed. A sentence whose paragraph still reaches the right conclusion
  stays B.
- "Move this earlier so `--connect` still works" style scope narrowing of a
  fail-closed check is B when the user has said "stopping everywhere is fine".
  Do not re-argue a decision the user already made.

See `references/grading.md` for worked examples from #3392 on both sides of
each line.

## Step 4 — Report, then STOP and wait

Report in exactly this shape, in the user's language, with the plain labels
from Step 3 — not bare A / B / C:

```
결론: 고칠 결함 <n>건 / 사실이지만 동작 영향 없음 <n>건 / 해당 없음·이미 처리됨 <n>건
      → <이 라운드에서 종료 가능 | 결함 수정 필요>

| # | 지적 | 판정 | 확인 결과 (한 줄) |
| --- | --- | --- | --- |
| 1 | … | 해당 없음 (1차에서 답변) | … |
| 2 | … | 동작 영향 없음 | … |
```

Every finding gets a row — numbered items, "minor" notes and questions alike.

Then:

- **A = 0** → say the round can end. If the bot labelled any C item
  "blocking", recommend a short rebuttal comment so the human reviewer does not
  stop at that word — and offer it, do not post it.
- **A > 0** → show each fix as pseudo-code (a diff sketch, file and line),
  and ask for approval. Do not edit files yet.
- **Round > 3 with A still appearing** → say so: that is a PR-size signal, not
  a bot signal. Suggest splitting.

Do not fold B items into the plan on your own. If the user picks one, fine.

## Step 5 — After approval: one commit, verified, not pushed

- Fix the approved items in **one commit** (the bot re-reviews on every push,
  so one push per round). Message in English:
  `review(<scope>): address the Z.ai review on PR #<N>` with one paragraph
  per finding: what the bot said, what the code did, what changed. Name the
  findings that were NOT changed and why.
- Verify with the repository's own pre-PR checks (in ARGO: `cargo fmt --check`,
  `cargo clippy --workspace --all-targets -- -D warnings`, the feature-gated
  test suites for the touched crates, the Core-layer audit scripts).
- Stop there. `git push`, PR comments and PR-body edits each wait for their
  own instruction.

## Step 6 — Comment, only when told

Use `references/comment-template.md`. One comment per round, one table, one
line per finding — **every** finding the bot raised (numbered items, minor
notes, questions), including the ones not changed, each with what was done
or why not. Write the comment **in the same language as the PR description**
(check `gh pr view <PR> --json body`), whatever language the conversation
with the user is in. Rounds 1–2 of #3392 were paragraphs and the user called
that too long; round 3's table was right. For follow-ups split out of the PR,
cite an issue number if one exists — the bot will raise them again.

## What this skill never does on its own

- edit code before the user approves the A list
- push, comment, or edit the PR body
- triage a human reviewer's comments (different process: those get answered)
- expand scope to "while I'm here" fixes
