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

## Step 3a — Opening overview (top of the answer, required)

The answer always opens with an overview, before any per-item section, so the reader knows what the commits are for before reading code. Order at the top of the answer:

1. The one-line resolved `before_ref`/`after_ref` from Step 0.
2. A `## 개요` section with two parts, in this order:

**커밋 메시지 요약** — what the author said, condensed. Read the full messages (subject *and* body), oldest first:

```bash
git log --reverse --format='%h %s%n%b%n---' <before_ref>..<after_ref>
```

- Single commit: the short sha and the subject, then 1–3 bullets condensing the body (the motivation, the issue/PR it references, any stated caveat). If the body is empty, say "본문 없음" instead of inventing one.
- Range: a table, one row per commit, oldest → newest — `| 커밋 | 메시지 요약 |` with the short sha and a one-line Korean summary. Mark commits that cancel each other out or fix an earlier commit in the same range (Step 1) in their row. If the range has more than ~15 commits, group rows by theme (e.g. "리뷰 대응 4건") instead of listing each one.
- Summarize in Korean; don't paste the message verbatim (quote only a short phrase when the exact wording matters, e.g. an issue number or a config key).

**무엇을 하는 커밋인가** — what the change as a whole does, in 2–4 bullets:

- the problem or goal it addresses;
- the main approach (the one or two mechanisms the per-item sections will show);
- scope: which modules/areas it touches and roughly how big (`git diff --stat` totals);
- any behavior change a user or caller will notice (new default, renamed key, removed path) — or "외부 동작 변화 없음" when it is a pure refactor.

Ground these bullets in both the messages and the diff. If the two disagree — the message claims something the diff doesn't do, or the diff does something the message never mentions — say so here explicitly; that mismatch is often the most useful fact in the whole answer. Keep this section descriptive: engineering opinions belong in each item's **변경관련 의견** and in 종합 의견, not in the overview.

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

**호출 흐름:** (optional — see below; a small visual diagram, not a bullet list)
```text
<caller 1> ──"<condition/arg>"──┐
                                 ├─▶ <shared callee>
<caller 2> ──"<condition/arg>"──┘
```
```

**Code highlighting — required, in every CLI.** Terminal and chat renderers (Claude Code, Codex CLI, Gemini CLI, Cursor, GitHub, VS Code, most markdown viewers) highlight a fenced block only when the opening fence names its language, so every fence in the answer carries a language tag — never a bare ` ``` `:

- `Before`/`After` blocks: the language of the file the code came from, chosen by extension from this table (first match wins). Keep that tag even though `After` lines carry `+` markers — do NOT switch to `diff`, which drops the language colors.

  | Extension | Tag | Extension | Tag |
  | --- | --- | --- | --- |
  | `.rs` | `rust` | `.py` | `python` |
  | `.c` `.h` | `c` | `.cc` `.cpp` `.hpp` | `cpp` |
  | `.java` | `java` | `.kt` `.kts` | `kotlin` |
  | `.swift` | `swift` | `.go` | `go` |
  | `.ts` `.tsx` | `typescript` | `.js` `.jsx` `.mjs` | `javascript` |
  | `.sh` `.bash` | `bash` | `.toml` | `toml` |
  | `.yaml` `.yml` | `yaml` | `.json` | `json` |
  | `.md` | `markdown` | `.sql` | `sql` |
  | `Cargo.lock`, other lockfiles | `toml` / `json` by format | anything else | `text` |

- A block showing raw `git diff` output: `diff`.
- Shell commands: `bash`. The **호출 흐름** diagram: `text` (plain, so box-drawing characters are not colored as code).
- Nested fences in this document's templates are illustrative; in the real answer, write each fence at top level with its tag.

**Before/After blocks must be verbatim.** Every line inside a `Before`/`After` fence is real source pulled from `git diff`/`git show` — never replace an actual line (or a whole match arm, function body, etc.) with a prose summary of what it does and present that inside the fence as if it were code. If a block is too long to show in full, elide the untouched middle explicitly (`// ... unchanged ...`) rather than substituting a paraphrase, or show the full block anyway — do not silently swap code for commentary. This applies even when the paraphrase is accurate; the reader must be able to trust that anything inside a fenced block is copy-pasteable from the real file. The line annotations below are the one sanctioned addition on top of verbatim source — they append a marker/comment, they never replace or reword the underlying code text.

**Line annotations (required in every Before/After block):**

Annotations are explanatory comments you add on top of the verbatim code so a reader can follow the change without opening the repo. They are the part of the answer that does the explaining *inside* the code, so put them wherever a reader would otherwise stop and ask "why is this here?" — not only on the lines listed below.

0. **Language and form — always Korean.** Every annotation comment is written in **Korean**, regardless of the repo's own comment language or the language the user wrote in. Keep code identifiers (`build_request()`, `MaskMode::Strict`, config keys) in their original form inside the Korean sentence. Use the comment syntax of the block's language (`//` for Rust/C/Java/TS/Go, `#` for Python/bash/YAML/TOML, `--` for SQL, `<!-- -->` for Markdown/HTML), placed either at the end of the line or on its own line directly above it when the explanation is longer than a short phrase. Existing comments that are part of the real source stay verbatim in their original language — never translate or reword them; the Korean annotation is added next to them, which also lets the reader tell the source's comments apart from yours.
1. **Added-line marker.** Every line in an `After` block that does not exist in the corresponding `Before` block gets a leading `+` (before the line's own indentation) — mirrors `git diff` output. Lines unchanged from `Before` (context) get no `+`. `Before` blocks never get a `+` — nothing in a `Before` block is "added" relative to itself.
2. **Function-call purpose comment.** On a line that calls another function/method, append a trailing comment naming the call and stating *why it is called at this specific site* — not a restatement of what the function generically does. ("`build_request()` 재호출 목적: 마스킹된 요청으로 HTTP 요청을 다시 만듦" beats "build_request는 요청을 만드는 함수".)
3. **Function-declaration summary comment.** Immediately above any function/method declaration (`fn ...`) shown in the block, add one line stating what that function does overall, from the reader's point of view (not implementation detail).
4. **Explain wherever explanation is needed.** Beyond calls and declarations, annotate a line when its meaning or reason is not obvious from the code alone. Typical cases:
   - a changed or new **condition / branch** (`if`, `match` arm, early `return`, `?` propagation): say what case it catches and what happens in that case (`// 마스킹이 꺼져 있으면 원문 그대로 반환 — 기존 동작 유지`);
   - a **magic value or constant** (a size limit, timeout, regex, default): say what it means and, if the diff or commit message shows it, why that value;
   - a line in a `Before` block that **disappears or changes** in `After`: say so and what replaced it (`// After 에서 삭제: 검사를 install 단계로 옮김`), so the reader can match Before to After line by line;
   - **error handling / fallback** paths: say what failure is handled and what the caller sees;
   - **type, signature or ownership changes** (a parameter becoming `Option`, `&str` → `String`, a new generic bound): say what the change enables or forbids for callers;
   - the exact line a **변경된 내용** bullet points at, when the connection isn't obvious from the surrounding code.
5. **Don't annotate everything.** Trivial lines (field-copy assignments, braces, blank lines, imports, simple literals whose meaning is plain) get no comment. One short comment per idea; if a block would need a comment on nearly every line, the explanation belongs in **변경된 내용**, not in the fence. Annotations explain *what this line does in this change and why*; they never repeat the identifier name as the explanation (`// handle_error 호출` is not an explanation).

Example (Rust, `After` block — note the Korean annotations next to the verbatim English source comment):

```rust
// 요청 본문을 마스킹한 뒤 LLM 으로 보낼 최종 요청을 만듦
fn prepare_request(cfg: &Config, body: &str) -> Result<Request> {
    // Fast path.
+   if cfg.pii.mode == PiiMode::Off {          // 마스킹이 꺼진 설정이면 원문 그대로 보냄 — 새로 추가된 우회 경로
+       return build_request(body);            // build_request() 호출 목적: 원문 본문으로 바로 요청 생성
+   }
    let masked = mask_pii(body, &cfg.pii)?;    // mask_pii() 호출 목적: 본문 속 PII 를 치환, 실패 시 요청 자체를 중단
    build_request(&masked)                     // build_request() 호출 목적: 마스킹된 본문으로 요청 생성
}
```

**Self-check before sending:** for every bullet in **변경된 내용**, confirm it points at a line actually visible in that item's Before/After blocks. If a bullet describes something the shown code doesn't contain (e.g. "installs X" but the fence never shows the call that installs X), the fence was truncated or paraphrased — fix the fence, don't adjust the bullet to match a shortcut. Also confirm every `+` marker is correct (present exactly on lines absent from `Before`), that call/declaration comments describe purpose, not just restate the name, and that every annotation you added is in Korean while the source's own comments are left untouched.

Rules for the two bullet sections:

- **변경된 내용** is purely descriptive. No "should have", no "this is risky" — just what changed. If a reader skipped the code blocks entirely, these bullets alone should tell them what happened.
- **변경관련 의견** is a real opinion, not a compliment or a restatement. Ground every opinion in evidence you can point to, not generic best-practice text:
  - Check the repo's own conventions before criticizing a choice (`grep` for the pattern elsewhere, check CLAUDE.md / AGENTS.md rules) — if the commit follows an established local pattern, say so rather than criticizing it in a vacuum.
  - Prefer concrete, checkable claims ("this identifier has 0 remaining references at HEAD, but nothing in this diff addresses external consumers of the old crate" beats "this could break things").
  - It's fine — expected — to have no opinion on a purely mechanical change (a lockfile bump, a straightforward module registration). Don't manufacture a critique to fill the section; write "없음 — <one-line reason>" instead.
  - Where you'd genuinely have done it differently, say what you'd have done, not just what's wrong with what's there.
  - Flag scope/blast-radius concerns explicitly: default-on feature flags, renamed public identifiers, config that used to be hot-reloadable and is now compiled in, anything that silently changes behavior for consumers not touched by the diff.

**호출 흐름 (call flow) — add when it clarifies, skip when it doesn't:**

Add this section to an item when the function(s) it introduces or changes have **more than one caller**, or sit in a **chain the reader would otherwise have to reconstruct themselves** (a value threaded through several hops before it matters, a shared helper feeding two or three different call sites with different arguments). Skip it when the item's only caller is already fully visible inside the Before/After block — repeating that there would be padding.

- Find every real caller with `grep -rn "<fn_name>(" --include="*.rs" .` (or the language equivalent) — never list a call site you have not confirmed exists.
- Draw it as a small diagram inside a fenced code block — boxes/arrows, not a bullet list. Plain ASCII box-and-arrow art is the default (renders as-is in any markdown viewer, including a terminal); reach for a `mermaid` fence instead only when you know the output destination renders Mermaid. Either way: one node per caller and per shared callee, one arrow per call labeled with the condition/argument that determines that path (e.g. `has_masking → Some(AlreadyMasked)`).
- Keep node/edge labels short — file:function names and the deciding condition, not full code or full paths. This is a map, not a second code dump; the Before/After block already carries the verbatim code.
- If the argument passed differs meaningfully per call site (e.g. a flag that's `Some(A)` at one site, `Some(B)` at another, `None` at a third), the arrow label says what makes it differ — the condition, not just the value.
- A plain table is an acceptable fallback only when the relationship genuinely resists drawing (e.g. many call sites varying along more dimensions than fit on arrows legibly) — reach for the diagram first.

## Step 5 — Wrap-up

End with a short "종합 의견" (a few bullets, not a new essay) only if there's a cross-cutting concern that doesn't belong to any single item — e.g. "this commit mixes a pure move with a rename, which is fine mechanically but makes the diff unreviewable as a unit." Skip this section if every concern was already covered per-item; don't pad.

## Step 6 — Pre-send checklist

Before sending the final answer, verify it against each of these (they point back to the rule that spells out the detail — this list is a scan, not a restatement):

- [ ] Step 0: resolved `before_ref`/`after_ref` stated to the user up front.
- [ ] Step 3a: the answer opens with `## 개요` — 커밋 메시지 요약 (single commit: subject + body bullets; range: oldest-first table) and 무엇을 하는 커밋인가 (goal, approach, scope, user-visible behavior change) — written in Korean, descriptive only, with any message/diff mismatch called out.
- [ ] Step 2: every item's header carries `[확인됨]` or `[추정]`, and every `[추정]` block's reconstruction is labeled as such, not presented as `git show` output.
- [ ] Step 4 code highlighting: every fence has a language tag from the table (`text` for the call-flow diagram) — no bare ``` fence anywhere in the answer.
- [ ] Step 4 verbatim rule: every line inside a Before/After fence is real — none swapped for a prose summary.
- [ ] Step 4 line annotations: `+` markers correct on every added line (and absent from `Before`), function calls carry a purpose comment, function declarations carry a one-line summary above them, non-obvious lines (changed conditions, constants, removed Before lines, error paths, signature changes) carry an explanation, and trivial lines are left uncommented.
- [ ] Step 4 annotation language: every added annotation comment is in Korean, uses the block language's comment syntax, keeps identifiers in their original form, and no original source comment was translated or reworded.
- [ ] Step 4 self-check: every **변경된 내용** bullet is backed by a line actually visible in that item's Before/After.
- [ ] Step 4 opinion rules: every **변경관련 의견** bullet is either grounded in checkable evidence (a grep result, a convention found elsewhere, a concrete blast-radius path) or explicitly "없음 — <reason>" — none are generic best-practice filler.
- [ ] Step 3/5: large-diff prioritization was stated when applicable, and 종합 의견 only appears if it covers a cross-cutting concern not already in a per-item opinion.
- [ ] Step 4 호출 흐름: present only where a function has multiple real (grep-confirmed) callers or a multi-hop chain, absent where the sole caller is already shown in Before/After; every call site listed actually exists; rendered as a box/arrow (or Mermaid) diagram, not a bullet list or table, unless the relationship genuinely resisted drawing.

## What NOT to do

- Don't jump straight into per-item Before/After — the `## 개요` overview (Step 3a) always comes first, and it summarizes the messages rather than pasting them.

- Don't show only the changed lines without surrounding context — the user explicitly wants to recognize *where* in the file the change sits.
- Don't write annotation comments in English (or mirror the repo's comment language) — annotations are always Korean; only the source's own existing comments stay as they are.
- Don't paraphrase real code into a descriptive comment inside a Before/After fence (e.g. turning a multi-line match arm into `/* installs X */`) — this silently drops the exact call the reader came to verify, and produces a "변경된 내용" bullet that claims more than the fence shows. Elide explicitly or show it in full.
- Don't present an inferred "before" as if it came from `git show` — always carry the `[추정]` label through to the section header.
- Don't write opinions that are true of almost any diff ("could use more tests", "consider documentation") — every opinion must be specific to what this diff actually did.
- Don't spawn a subagent for this — it's a focused, single-thread investigation over one commit or range; do it inline.
- Don't walk the range commit-by-commit — one cumulative before/after per file (Step 0's endpoints), not N sequential diffs for N commits.
- Don't invent or guess a call site in a 호출 흐름 section — every caller listed must come back from an actual `grep`/`git grep` for the function name; if there's only one caller and it's already in the Before/After block, omit the section entirely rather than restating it.
