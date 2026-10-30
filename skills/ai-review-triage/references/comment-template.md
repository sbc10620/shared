# PR comment templates

One comment per round. One table. One row per finding.

**Two rules that always hold:**

1. **Every finding gets a row** — every numbered item, every "minor" note,
   every question. A finding that was not changed still gets a row saying
   why ("No change — …"); one already answered says which round. Never drop
   a row because the item was minor or not fixed.
2. **Write the comment in the PR description's language** — check
   `gh pr view <PR> --json body`. An English PR gets an English comment even
   when the conversation with the user is in Korean. Keep code identifiers,
   file paths and symbols as-is.

Why short: the bot reads the PR (comments included) on the next push. Long
prose responses become input to the next round and generate more findings
about themselves. The human reviewer wants the verdict, not the reasoning —
so one line per row, but no row missing.

Use plain response words, never the internal A / B / C grades: **Fixed** /
**No change** / **Answered in round N** / **Accepted** (a documented
limitation) / **Follow-up** (#issue).

## Variant 1 — fixes were made

```markdown
## Z.ai review round <N> — response (commit <short-sha>)

| # | Finding | Response |
| --- | --- | --- |
| 1 | <one-line restatement> | Fixed — <what changed, one line> |
| 2 | <…> | No change — <one-line factual reason> |
| 3 | <…> | Answered in round <N-1> (#<n>). |
| Minor | <…> | Accepted — <the documented limitation> |
| Q1 | <question> | <the answer, with the file/function that shows it> |

Verification: fmt · clippy `-D warnings` · <suites and counts> · <gates>.
```

## Variant 2 — no code change (round ends)

```markdown
## Z.ai review round <N> — response (no code change)

No finding in this round needs a code change, so the bot review ends here
and the PR goes to human review.

| # | Finding | Response |
| --- | --- | --- |
| 1 | <…> | No change — <file:line — what the code actually does> |
| 2 | <…> | Answered in round <N-1> (#<n>). |
| Minor | <…> | <one line> |
```

## Rules

- When the bot called an item "blocking" and it does not hold, say so in that
  row plainly, so the human reviewer does not stop at the word.
- Never restate the bot's finding in full — the bot's comment is right above.
- The Korean variants of these headings are for a Korean PR description only.
