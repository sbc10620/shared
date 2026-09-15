---
name: argo-pii-locale
description: Write (or extend) the per-locale PII reference document that justifies every country-specific recognizer in ARGO's tinicore guardrails YAML — one Markdown file per locale, same template, same verification steps, reviewed by a subagent before it is pushed. Use when the user asks to write, continue, or update the PII document for a locale such as ko_KR, de_DE, fr_FR, it_IT, es_ES, en_GB, en_IN, pt_BR, es_MX, vi_VN, th_TH, pl_PL (or says "다음 국가", "PII 문서 작성"). Do NOT use it for code changes to the guardrails engine; the document only records evidence and proposed follow-up work.
user-invocable: true
allowed-tools: Read, Grep, Glob, Write, Edit, Bash, Agent
---

# ARGO PII locale document

Thirteen locales (en_US, ko_KR, en_GB, de_DE, fr_FR, it_IT, es_ES, en_IN,
pt_BR, es_MX, vi_VN, th_TH, pl_PL) each get one document that explains why
each country-specific recognizer belongs in
`tinicore/src/guardrails/config/pii_filter_config.yaml`. The documents must
be interchangeable in shape so they can later be read side by side and turned
into YAML + validators. This skill fixes the shape and the verification steps.

Reference material — read both before writing anything:

- Template: `~/Works/shared/docs/_template-argo-pii-locale.md`. Section 0 is
  common to every locale and is copied verbatim. Sections 1–5 are filled in.
- Finished example: `~/Works/shared/docs/20260914-argo-pii-en_US.md`. Match
  its depth per item, not just its headings.

Standing decisions the user has already made (do not re-ask):

- The document lives ONLY in `~/Works/shared/docs/YYYYMMDD-argo-pii-<locale>.md`.
  Do not create a copy inside the ARGO repository.
- Prose is Korean; `pii_type` keys, regex, statute names, and code identifiers
  stay in their original form.
- Country-specific items only. Card numbers, API keys, passwords, email, IP
  addresses are common and are out of scope. Items already present in the
  YAML are included anyway, marked "기존", because the document is the
  evidence for why they are there.
- No Bixby reference material is available; ignore it.
- Commit and push to `shared` only when the user asks; they normally ask for
  the first push and then for each review round.

## Step 1 — Ground the document in the code, not in memory

The engine is in the ARGO worktree (`~/Works/ARGO-pii-multilanguage` at the
time of writing; check `git worktree list` if unsure). Before writing:

```bash
grep -nE '^  <cc>_[a-z_]+:$' tinicore/src/guardrails/config/pii_filter_config.yaml
```

For every existing `<cc>_*` recognizer, quote its `patterns`,
`context_words`, `validation_methods`, `layers`, and `boundary_check*` fields
exactly. Re-check the facts the common section 0 relies on only if the code
may have moved since en_US was written:

- `validator.rs` — which validators exist (`luhn`, `rrn`, `phonenumber` as of
  2026-09-15) and that `validate()` is fail-open for unknown names.
- `recognizer.rs` — `SCORE_THRESHOLD`/`DEFAULT_SCORE`/`BOOSTED_SCORE`
  (0.5/0.5/1.0), `DEFAULT_CHUNK_SIZE` (30), pids are per pattern,
  `passes_boundary_check` rejects an adjacent ASCII alphanumeric byte.
- `handwritten/aho_corasick_detector.rs` — anchors are case-sensitive.

If any of these changed, update section 0 of the template first, then the
new document.

## Step 2 — Enumerate candidates per locale

Sources, in order of preference: the country's data-protection statute and
supervising authority, then the identifier issuer's own format specification,
then Presidio / Google DLP / Microsoft Purview recognizer lists as a checklist
of what others detect. Typical candidate families:

- national ID / resident registration / tax number (checksum common)
- passport, driver license, health insurance / social security number
- bank account (national format; IBAN is common across many locales — mark
  it as a candidate for the shared item set, do not duplicate per locale)
- phone number (fixed prefixes such as `010` make Aho-Corasick viable)
- vehicle registration / VIN (VIN is international — shared candidate)
- anything the statute lists explicitly as sensitive

For each candidate answer the four criteria: statute + authority; what it is
and why exposure is harmful; deterministic detectability; validator
availability. Keep an item even without a validator if the statute treats it
as high-risk.

## Step 3 — Verify before you write

Every regex row in the document must be executed:

```python
import re
# (?-u:\b) -> \b ; boundary_check -> reject if adjacent char is alphanumeric
```

Run each pattern against its "매칭 예시" and its "거부" counter-examples.
Compute every checksum example (Luhn, mod 97, mod 11, weighted sums) with a
short script and record only values that pass. Prefer the issuer's own
published example over an invented one. Never use a real person's number.

Rules that produced defects in the en_US review and must be checked every
time:

- No lookahead / lookbehind / backreference (lazy DFA cannot compile them);
  exclusion rules go to a validator or a handwritten detector.
- A pattern that is digits-only, or a single letter plus digits, is low
  precision. Mark it **score 사용 필요** and explain that context_words do
  not filter today (they only raise 0.5 → 1.0 against a 0.5 threshold).
- If you replace a pattern that carried `(?-u:\b)`, either keep the anchor
  or say `boundary_check: true` must be added with it.
- Do not put `\(` in two alternations of the same pattern (it made the
  en_US phone pattern miss `(212) 555-0123`).
- Lists and ranges that an agency revises (ITIN groups, EIN prefixes, area
  codes) get "최신 공고로 재확인 필요".
- Anything you are not sure of gets "확인 필요", not a confident sentence.
- Inside Markdown tables, escape `|` in regex as `\|`. Check every table row
  has the same number of cells as its header.

## Step 4 — Write the document

Copy the template, fill sections 1–5, delete the HTML comment and the
checklist section. Keep the three-column regex table
(`regex | 매칭 예시 | 비고`) and the three 비고 labels exactly as defined in
section 0: 기본 / score 사용 고려 / **score 사용 필요**. The summary table in
section 2 must agree with section 3 and section 5 item by item (the second
en_US review found three such mismatches).

## Step 5 — Subagent review, then apply

Spawn one `general-purpose` agent with the review prompt used for en_US: it
must (1) diff the document's claims against the code files listed in Step 1
with file:line evidence, (2) execute every regex row and checksum example,
(3) look for internal contradictions between sections 2, 3, and 5, and
(4) judge statute names and identifier formats from its own knowledge,
marking uncertainty as "확인 필요". Report format: 오류 / 불확실 / 개선 제안 /
검증 통과 항목.

Before applying a finding, re-verify the high-impact ones yourself (a
reviewer's claim about engine behavior is checked in the code, a regex claim
is re-run). Apply fixes, re-run the table-cell check, and report to the user
which findings were applied, which were left as "확인 필요", and why.

## Step 6 — Hand off

Tell the user the file path, line count, the adopted / conditional / rejected
item counts, and the items still marked "확인 필요". Update the
`argo-pii-multilanguage-work-state` memory with which locales are done.
