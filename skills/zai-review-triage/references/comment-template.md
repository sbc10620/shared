# PR comment templates

One comment per round. One table. One line per finding. Write in the user's
language (Korean for this user); keep code identifiers, file paths and
symbols as-is.

Why short: the bot reads the PR (comments included) on the next push. Long
prose responses become input to the next round and generate more findings
about themselves. The human reviewer wants the verdict, not the reasoning.

## Variant 1 — fixes were made

```markdown
## Z.ai <N>차 리뷰 대응 — 커밋 <short-sha>

| # | 지적 | 처리 |
| --- | --- | --- |
| 1 | <one-line restatement> | <what changed, one line> |
| 2 | <…> | 변경 없음 — <one-line reason> |
| 5 | <…> | <N-1>차에서 답변 완료 |
| – | <minor note> | 후속 (#<issue>) |

검증: fmt · clippy `-D warnings` · <suites and counts> · <gates>.
```

## Variant 2 — no code change (round ends)

```markdown
## Z.ai <N>차 리뷰 대응 — 코드 변경 없음

봇이 블로킹으로 표시한 <items> 은 코드를 확인한 결과 성립하지 않습니다.
나머지는 이전 라운드에서 답했거나 이 PR 범위 밖의 후속 항목이라 이번
라운드는 변경 없이 마무리합니다.

| # | 지적 | 확인 결과 |
| --- | --- | --- |
| 1 | <…> | 성립하지 않습니다. <file:line — what the code actually does> |
| 2 | <…> | 해당 없습니다. <the check that shows it> |
| <rest> | <grouped> | <one line: documented limitation / answered in round N / follow-up> |
```

## Rules

- Only include a "blocking" rebuttal row when the bot used that word; the
  purpose is so the human reviewer does not stop at it.
- Group repeated or C-grade items into one row when they share a reason.
- Never restate the bot's finding in full — the bot's comment is right above.
- Do not include B items you chose not to fix unless the user asked for the
  full list on the PR; the conversation already has it.
