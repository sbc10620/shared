---
name: commit-explain
description: Explain a git commit — or a commit range / PR-sized span of commits — item-by-item, each with real before/after code, a factual "what changed" summary, and an honest engineering opinion — grounded in repo evidence, not generic advice. Use when the user asks to explain, review, or walk through what a particular commit (by hash) or a range of commits (branch, PR, "these last N commits") changed.
user-invocable: true
allowed-tools: Bash, Read, Grep, Glob
---

# Commit Explain

Explain a change so a reader who has not seen the diff can follow it without opening the repo. The target is either a single commit or a range of commits (a PR, a feature branch, "the last N commits") — same output shape either way, because a range is explained as ONE cumulative before/after per file, not as a replay of each intermediate commit. This is a **read-only investigation** — never modify, stage, or commit anything.

The final answer to the user is written in **Korean**, in outline/bullet style (개조식: terse noun-ending phrases, not full sentences). This document itself stays in English per the project's rule that Claude-facing skill docs are English regardless of output language.

## Step 0 — Resolve the target into before_ref / after_ref

Figure out what the user gave you and normalize it to two refs before doing anything else:

| User gave | before_ref | after_ref | notes |
| --- | --- | --- | --- |
| a single sha | `<sha>~1` | `<sha>` | the existing single-commit case |
| `A..B` (two dots) | `A` | `B` | literal range, exactly the commits reachable from B but not A |
| `A...B` (three dots) | `merge-base(A,B)` | `B` | PR/branch-review semantics — diffs B against where it forked from A, ignoring anything A gained meanwhile. **Default to this for "review this branch/PR against main" style requests.** |
| a bare branch/ref name | `merge-base(current-branch-or-main, ref)` | `ref` | treat like `main...ref` |
| two args given separately ("base X, head Y") | `X` | `Y` | same as `X...Y` unless the user explicitly says literal range |

Compute it explicitly, e.g. `git merge-base main feature-branch`, and state the resolved `before_ref`/`after_ref` to the user in one line up front so they can sanity-check your interpretation before you produce ten sections of analysis on the wrong range.

Everywhere below, `<sha>` in a single-commit command generalizes to the pair `<before_ref> <after_ref>` for a range — e.g. `git show <sha> -- <path>` becomes `git diff <before_ref> <after_ref> -- <path>`.

## Step 1 — Scope the change

```bash
git diff --stat <before_ref> <after_ref>
```

For a range, also list what composes it and read every commit message in it — this is often the only source for *why*, not just *what*:

```bash
git log --oneline <before_ref>..<after_ref>
```

Two things to watch for that are specific to ranges:
- **Net-cancelling churn.** If two commits in the log touch the same file in opposite directions (a change then its revert, a rename then a rename back), the endpoint-to-endpoint diff already nets this out correctly — but call it out in the summary ("N개 커밋 중 2개는 서로 상쇄") so the user isn't confused when the file list is shorter than the commit count suggested.
- **A commit range is not one author's one intent.** Read the individual commit messages for sub-narratives (bug fix folded into a feature, a follow-up correcting an earlier commit in the same range) rather than treating the whole span as a single homogeneous story.

If the stat list is short (a handful of files), just walk every file. If it's large (dozens of files, thousands of lines — routine for a multi-commit range), do NOT dump the whole diff — identify the load-bearing subset first (see Step 2) and summarize the rest as a category.

## Step 2 — Classify every changed file: confirmed vs inferred

This is the step most likely to be skipped, and skipping it produces a fabricated diff.

For each file in the stat, check whether it existed at `before_ref`:

```bash
git cat-file -e <before_ref>:<path>  # exit 0 → file existed before, real before/after possible
```

- **Confirmed** — the file existed before the change (an ordinary edit, or a rename git detected). Pull the real diff with enough surrounding context to be readable:
  ```bash
  git diff <before_ref> <after_ref> -- <path>          # default context
  git diff -U8 <before_ref> <after_ref> -- <path>      # widen context if a hunk reads as disconnected
  ```
  Never hand-trim the hunk down to just the `+`/`-` lines — keep the untouched lines around it so the reader sees where the change lands.

- **Inferred** — the file has no prior version at `before_ref` (e.g. code vendored in from an external crate/repo the commit message describes, a pure `git mv` that git failed to detect as one, first-time addition of generated output). There is no real "before" to show. Two options, always labeled explicitly, never presented as fact:
  1. If a commit message in the range names the transformation ("renamed X to Y", "moved from path A to B", "changed default to Z") — reconstruct the "before" as **[Inferred]** by inverting that described transformation on the "after" code, and say so in the label.
  2. If there's nothing to reconstruct from — skip before/after for that file and just describe what it now contains.

  Verify inferences instead of guessing blind: `git grep` the OLD name/path across the repo at `after_ref` and at HEAD — a zero-hit result is evidence the rename was intentional and complete; a stray hit is itself a finding worth reporting.
  ```bash
  git grep -n "<old-name>" <after_ref> -- <scope>
  git grep -rn "<old-name>" -- <scope>   # still there at HEAD?
  ```

Never blend confirmed and inferred content in the same code block without a label — the reader must always know which lines are verified diff output and which are reconstructed narrative.

## Step 3 — Prioritize when the diff is large

Rank what to walk through in full, in this order:

1. **Wiring/integration points** — files that existed before and changed (module registration, feature flags, config, dependency graph). These are almost always short, confirmed, and carry the most meaning per line.
2. **Cross-cutting renames or identity changes** — a changed string/name/const that other code or other repos might match against (function names used as log/metric identifiers, public API names, config keys). Flag these even if small, because they're the ones likely to break something outside the diff's own scope.
3. **Bulk moved/vendored code** — large blocks of new files with no real "before" in this repo. Summarize as a category (line counts, what module they form) rather than walking each file; call out only files with genuinely new logic (not just relocated).
4. **Generated/lockfile changes** — one line, no opinion needed, mention and move on.

State this priority explicitly to the user when the diff is large, so they know why some files got full before/after and others got a one-line mention.

## Step 4 — Per-item output shape

For every item worth walking through, in this exact shape:

```
### <item title> [확인됨 | 추정]

**Before**
```<lang>
<code with surrounding context>
```

**After**
```<lang>
<code with surrounding context>
```

**변경된 내용:**
- <bullet, terse, factual — what literally changed, no opinion>
- ...

**변경관련 의견:**
- <bullet, terse, an honest engineering opinion>
- ...
```

Rules for the two bullet sections:

- **변경된 내용** is purely descriptive. No "should have", no "this is risky" — just what changed. If a reader skipped the code blocks entirely, these bullets alone should tell them what happened.
- **변경관련 의견** is a real opinion, not a compliment or a restatement. Ground every opinion in evidence you can point to, not generic best-practice text:
  - Check the repo's own conventions before criticizing a choice (`grep` for the pattern elsewhere, check CLAUDE.md / AGENTS.md rules) — if the commit follows an established local pattern, say so rather than criticizing it in a vacuum.
  - Prefer concrete, checkable claims ("this identifier has 0 remaining references at HEAD, but nothing in this diff addresses external consumers of the old crate" beats "this could break things").
  - It's fine — expected — to have no opinion on a purely mechanical change (a lockfile bump, a straightforward module registration). Don't manufacture a critique to fill the section; write "없음 — <one-line reason>" instead.
  - Where you'd genuinely have done it differently, say what you'd have done, not just what's wrong with what's there.
  - Flag scope/blast-radius concerns explicitly: default-on feature flags, renamed public identifiers, config that used to be hot-reloadable and is now compiled in, anything that silently changes behavior for consumers not touched by the diff.

## Step 5 — Wrap-up

End with a short "종합 의견" (a few bullets, not a new essay) only if there's a cross-cutting concern that doesn't belong to any single item — e.g. "this commit mixes a pure move with a rename, which is fine mechanically but makes the diff unreviewable as a unit." Skip this section if every concern was already covered per-item; don't pad.

## What NOT to do

- Don't show only the changed lines without surrounding context — the user explicitly wants to recognize *where* in the file the change sits.
- Don't present an inferred "before" as if it came from `git show` — always carry the `[추정]` label through to the section header.
- Don't write opinions that are true of almost any diff ("could use more tests", "consider documentation") — every opinion must be specific to what this diff actually did.
- Don't spawn a subagent for this — it's a focused, single-thread investigation over one commit or range; do it inline.
- Don't walk the range commit-by-commit — one cumulative before/after per file (Step 0's endpoints), not N sequential diffs for N commits.
