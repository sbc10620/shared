---
name: dev-cycle-report
description: "Build a top-down HTML report that explains a PR or a commit range (typically one produced by the dev-cycle skill) for understanding the code: why it changed, how the overall structure changed (before/after package diagrams named and nested by module, each job in words with its functions in parentheses, «use» edges checked against the code), then per topic the before/after call sequences and Python-flavoured pseudocode with an explanation of every function and every call. Commits are grouped by topic and only the final state is explained, never an intermediate state a later commit replaced. Every code reference, figure name and source is checked against the repository by scripts/build_report.py before anything is built. Agent-neutral: it needs only git, a shell, Python 3, a Chrome or Chromium and network access; it uses a sub-agent for the accuracy review when the agent can start one. Use when the user asks for a report, overview or structural explanation of a PR, branch or commit range ('변경 보고서', 'PR 보고서', '구조 설명 보고서', '이 PR 이 뭘 바꿨는지 보고서로'). For per-file before/after code use commit-explain; for a call-flow picture from main use commit-flow-diagram."
---

# Dev-cycle report

The reader wants to understand the change, top-down, without opening the
diff: first why, then how the structure moved, then how each flow works
now. `commit-explain` (per-file code) and `commit-flow-diagram` (call
chains from main) answer the detailed questions; this report is the map
above them.

This document is agent-facing and works with any coding agent. It stays in
English. The report is written in **Korean**, in full sentences of
합니다체 (…합니다, …습니다), never the plain 다. ending (the script warns):
the script's fixed labels (전, 후, 담당, 입력, 출력, …) are Korean.

**Needs:** git, a shell, Python 3, a Chrome or Chromium (headless, found on
the usual paths), and network access to jsdelivr for Mermaid at build time.
The built page opens offline.

**Read-only** for the repository under report: never modify, stage or
commit anything there. The only writes are the report directory and, when
the user's instructions say so, a commit of it.

## 1. Fix the range

Turn what the user gave into two full SHAs:

| User gave | base | head |
| --- | --- | --- |
| an open PR | `git merge-base origin/<PR base branch> <PR head>` after fetching both | the PR head |
| a merged PR | `<merge commit>^1` | `<merge commit>^2` (or the PR head) |
| a branch | `git merge-base origin/<default branch> <branch>` | the branch tip |
| `A..B` | `A` | `B` |
| `A...B` | `git merge-base A B` | `B` |

Fetch first when the refs are remote. From here on use SHAs only, never
`HEAD` or a branch name: the branch can move while you work.

## 2. Gather the sources (read only)

The "why" must come from somewhere a reader can open later:

- git: commit messages, `git diff --stat <base> <head>`, the cumulative diff;
- the PR description and comments (`gh pr view`), when `gh` is
  authenticated;
- the user's design documents, plans and reviews, wherever the user's
  instructions say they keep them;
- the agent's own plan and memory files, if the agent keeps any (for
  example Claude Code's `~/.claude/plans/*.md` and
  `~/.claude/projects/*/memory/`). These are leads, not sources: follow
  them to the commit, document or PR they point to and cite that. When
  only the agent's file holds the fact (a user's decision, a review
  record), cite it as `agent:<file name without extension>`; the page
  shows "에이전트 기록(name)". A path into an agent's private directory
  is refused as a source, because reports are often published.

Rules:

- A plan file can be overwritten by later work. Use one only when its
  content actually covers this range (it names the range's identifiers,
  branch or commits). If it is the agent's own file, cite it as
  `agent:<name>` (above) and give its modified time in `text`
  (`YYYY-MM-DD HH:MM`). When a document or commit and an agent file say
  the same thing, cite the document or commit.
- The current conversation is not a source: nobody can check it later.
  Something learned only from it is written as an inference (below) or
  left out.
- No source → write the item as an **inference** with the code location it
  rests on (`inferred_from`). The page labels it 추정.
- A process record (review rounds, test or e2e results) always names the
  commit it applies to (`applies_to`): a result measured on a WIP commit is
  not a result for head, and the page tags it "head 아님". If that
  commit's tree equals head's (`git diff --quiet <it> <head>` succeeds),
  you may put head in `applies_to` and say in `text` that the check ran on
  that same tree. Quote result
  lines as the tool printed them when the source has them; otherwise give
  the summary and its source path. No record at all → leave `records`
  empty; the page says 기록 없음.

## 3. Group the commits; explain the final state

- Put every non-merge commit of `base..head` in exactly one group. Groups
  are topics a reader would name ("언어별 규칙을 고르는 메커니즘"), not
  commit types. A run of commits doing the same thing to different items
  (one language each) is one group. Trivial commits go to a group titled
  기타 (id `misc`), which needs no `why` and no `flows`.
- Describe the **cumulative** change `base..head`, never a replay of
  commits. When a later commit rewrites what an earlier one did, explain
  only what head has; the earlier commit stays in its group's commit list.
- When several groups touch one file, a changed line belongs to the group
  of the commit that wrote it last (`git blame <base>..<head> -- <file>`),
  and a removed line to the group of the commit that removed it.
- The script counts, per commit, the lines it still owns at head. A commit
  with none must carry `commit_notes`: `replaced_by` (the later commit that
  rewrote it) or `note` (e.g. "삭제만 함"; also for a commit whose lines a
  merge commit's conflict resolution replaced). The page tags it.

## 4. Write report.json

```json
{
  "repo_dir": "/abs/path/to/checkout",
  "base": "<sha>", "head": "<sha>",
  "topic": "kebab-case-topic",
  "title": "한국어 제목",
  "summary": ["3~5 sentences: what the change does, end to end"],
  "why": [
    {"text": "문제·목표·결정 한 문장", "source": "<file path | path:line | commit SHA | PR #n | repo#n | URL>"},
    {"text": "...", "inferred_from": "<path at head>:<line>"}
  ],
  "impact": [{"kind": "config|boot|api|behavior|sync", "text": "쓰는 쪽에서 달라지는 점",
              "fns": ["resolve_pii_countries"], "snippet": "[pii]\nlocales = [\"ko_KR\"]", "source": "..."}],
  "glossary": {"DFA chunk": "한 줄 설명", "anchor": "..."},
  "structure": {
    "before": {"caption": "...", "packages": [...], "edges": [...]},
    "after": {
      "caption": "...",
      "packages": [
        {"id": "clipii", "path": "tinicli/src/guardrails/pii.rs", "note": "PII 설정",
         "nodes": [{"id": "rpc", "role": "설정으로 나라 목록을 정함",
                    "fns": ["resolve_pii_countries"], "mark": "new"}]},
        {"id": "shared", "path": "tinicore/src/guardrails/pii/shared.rs", "note": "공유 엔진",
         "nodes": [{"id": "sel", "role": "나라 목록을 프로세스에 한 번 고정함",
                    "fns": ["select_countries"], "mark": "new"}]},
        {"id": "rules", "path": "tinicore/src/guardrails/pii/countries", "note": "나라별 규칙",
         "mark": "new",
         "nodes": [{"id": "rules", "role": "공통 규칙 + 나라별 규칙", "kind": "data", "fns": ["RULES"]}]}
      ],
      "edges": [{"from": "shared", "to": "rules"}]
    },
    "changes": [{"kind": "new|changed|moved|removed",
                 "text": "무엇이 바뀌었는지, 코드 이름 없이",
                 "fns": ["select_countries"], "group": "<topic group id>"}]
  },
  "groups": [{
    "id": "kebab-id", "title": "주제", "one_line": "한 문장 요약",
    "why": ["이 주제가 필요한 이유 (optional for 기타)"],
    "commits": ["<sha>", "..."],
    "commit_notes": {"<sha>": {"replaced_by": "<later sha>"}},
    "flows": [{
      "title": "흐름 이름 (예: 부팅 때 나라를 정하는 흐름)",
      "sequence": {
        "before": {"layers": [{"name": "tinicli", "path": "tinicli/src",
                               "participants": [{"id": "run", "name": "run"}]}],
                   "steps": [{"from": "run", "to": "inst", "call": "install(config)", "reply": "결과"},
                             {"from": "inst", "to": "run", "call": "설치 결과", "dashed": true}]},
        "after": {"layers": [...], "steps": [...]}
      },
      "before": {"code": "pseudocode", "refs": [{"path": "...", "lines": "120-160", "must_contain": ["fn_name"]}]},
      "after":  {"code": "pseudocode", "refs": [{"path": "...", "lines": "88-140", "must_contain": ["fn_name"]}]},
      "calls": {"called_fn": "그 함수가 하는 일, 한 줄"},
      "example": {"test": {"path": "tests/x.rs", "must_contain": ["test_fn"]},
                  "steps": ["실제 입력이 흐름의 한 단계를 지나는 모습", "..."]},
      "explain": ["이 흐름에서 읽어야 할 점, 한 문장씩"]
    }],
    "points": ["핵심 포인트"],
    "tests": [{"path": "tests/x.rs", "must_contain": ["test_fn"], "text": "이 테스트가 보장하는 것"}]
  }],
  "records": [{"text": "리뷰 3라운드(high, medium, medium)...", "applies_to": "<sha>", "source": "<path>"}]
}
```

Writing rules:

- **Top-down.** `summary` and the group `one_line`s must make sense to
  someone who reads nothing else. Details go further down.
- **Structure figures** (the part the reader came for) are package
  diagrams of the static structure; the call order lives in the flows'
  `sequence`. The script draws them; there is no raw Mermaid.
  - A **package** is the language's namespace unit: a Rust module (a file,
    or a directory with its `mod.rs`), a Java/Kotlin or Go package, a
    Python module or package. Give its `path`; the script derives its
    module name (`tinicore/src/guardrails/pii/shared.rs` →
    `tinicore::guardrails::pii::shared`, `…/pii/mod.rs` and `…/pii/` →
    `tinicore::guardrails::pii`; the crate is the directory above
    `src/`; `mod`, `lib`, `main`, `__init__`, `index` stand for their
    directory; `::` in a Cargo workspace, `.` elsewhere). Set `module` only
    when that rule names it wrongly. `path` must exist at that side.
  - Nesting comes from the module names: each listed package is a box
    whose tab shows its last name segment and the Korean `note`; the
    modules above it are drawn as outlines, from the crate down, and a
    chain of modules with one child each is merged (`guardrails::pii`). A
    listed package that also has listed children is drawn inside its own
    outline as "(이 모듈 자신)". `mark` on a package colours its tab.
  - Keep each package to at most four rows; past that, list its
    sub-modules instead (the script warns).
  - A data file (a rule YAML, a table) is not a package: show it as a
    `kind: "data"` row in the package of the module that loads or embeds
    it, with the constant or table that holds it in `fns` (the name must
    occur under that package's `path`, like any `fns`).
  - Each **node** is a row inside a package: one job, written as a Korean
    sentence in `role` ("나라 목록을 프로세스에 한 번 고정함"), never a
    function name. `fns` names at most two functions (or types, constants)
    that do the job, shown under the role in parentheses. The script checks
    that each name occurs inside the package's `path` at that side; put a
    function in the package that defines it, not one that only calls it
    (the script cannot tell the two apart). `kind: "data"` marks a rule
    file or table («data»). `mark` colours the row and prefixes `+` / `~` /
    `−`: in `after`, `new` or `changed`; in `before`, `removed` for a job
    head drops and `changed` for one head changes.
  - `edges` join packages (by id): a dashed «use» dependency, from the
    user to the used, drawn without text (the legend says what a dashed
    arrow means; give `label` only for another relation). The script
    refuses an edge unless a file under `from`'s `path`, at that side,
    contains `to`'s last module name or one of the functions in `to`'s
    rows as a whole word. A package with no edge at all draws a warning: a
    reader takes it for unconnected. If the edge fails its check, the
    package you drew is probably not the one that does the using (draw
    the module that makes the call, e.g. the entry point rather than a
    settings module).
  - Keep each figure to about 15 rows. Use the same package and node ids in
    `before` and `after` for the same thing, so the two can be compared.
    The page explains the colours and boxes in a legend under the figures.
  - `changes` lists, in sentences, what is new, changed, moved or removed,
    each pointing at the topic group that explains it (for a change several
    groups shaped, the group whose commits wrote most of what carries it
    at head). The `text` says
    what changed without code names; `fns` (up to three) names the
    functions that carry it, shown after the sentence as "담당: …".
    Removed items' `fns` are looked up at base. Code-like words in `text`
    or `role` draw a warning. The page sorts the list: 새로 생김, 바뀜,
    옮겨짐, 없어짐.
- **Flows**: one per behaviour a reader would ask about ("boot picks the
  countries"), from its entry point down to the changed part.
  - `sequence` (for a flow that crosses packages): the call order before
    and after, with one box per layer (a package, as in the structure
    figure) holding the functions that take part, and the calls in order.
    `reply` draws the answer right after a call; a step with
    `dashed: true` is a later return. Participants must be found in their
    layer's `path`. Omit `before` when the flow is new.
  - **Pseudocode** (`before.code`, `after.code`) is Python-flavoured, for
    a reader who may know neither Python nor the project's language:
    - Keywords: `def`, `if` / `elif` / `else`, `for … in`, `while`,
      `return`, `raise`, `and` / `or` / `not`. Blocks by indentation.
      Anything else in plain Korean ("if requested 가 없으면:"). The page
      shows a legend of these.
    - Refused: `//` comments, Rust (`fn`, `let`, `match`, `impl`, `pub`),
      `lambda`, `yield`, `self.`, `with`, `is None`, list comprehensions,
      slicing `a[i:j]`.
    - A `## ` row is an explanation box, not code. Right above every `def`
      put at least three (the script refuses it otherwise):
      `## <function name>: what it does`, `## 입력: name — what it holds,
      …` (`없음` when none), `## 출력: what it returns, and the errors it
      raises` (`없음` when nothing). Add more `## ` rows before a step a
      reader would not follow. A `# ` note at the end of a line says what
      a variable holds ("# 호스트가 넘긴 나라 목록").
    - Use the real names of functions, types and config keys; elide
      unrelated parts with `...`. Never drop an early return or branch
      that changes the result.
    - `+` in column 0, before the indent, marks a line new at head; `-` a
      line in `before` that is gone at head.
    - Code lines stay within 80 columns (a Korean character counts two);
      move a long note to a `## ` row above.
    - Each side has at least one `refs` entry; every `must_contain` name
      must appear in the pseudocode and in that file at that side. `lines`
      is a hint; a miss prints a warning with the real line numbers — fix
      the hint. Omit `before` when the flow did not exist at base.
  - `calls` explains, in one line each, every name the pseudocode calls
    (`name(` or `obj.name(`) that is not a `def` of the same flow, except
    the value wrappers `Ok(`, `Err(`, `Some(`; the
    script refuses a flow with an unexplained call. The page lists them
    under the code as "이 흐름에서 부르는 함수".
  - `example` walks one real input through the flow in 2 to 6 steps
    ("`locales = [\"ko_KR\"]` → `[Kr]` → 공통 + 한국 규칙 → 주민번호는 찾고 SSN
    은 찾지 않음"). Take the input and the outcome from a test, never
    invent them, and name that test: a test name missing from the named
    file at head is an error; a flow with no example draws a warning.
  - The page shows a flow in this order: pseudocode, the called functions,
    the example, the call sequence, then `explain`. The sequence has no
    explanations of its own; it relies on the parts above it.
- **Impact** (`impact`): what changes for whoever uses the code, apart
  from its structure — a new config key (with a `snippet`), a new reason
  the program refuses to start, a changed public API, a behaviour a user
  sees, what another repository must do when it takes the change. `kind`
  is one of config, boot, api, behavior, sync; `fns` are checked at head.
- **Glossary** (`glossary`): every term a reader may not know that the
  report uses more than once (DFA chunk, anchor, layer, …), one line each.
  The script warns about a term the report never uses.
- On the page, hovering a function name shows its one-line explanation
  (from its `## name:` row or its `calls` line) and clicking jumps there;
  glossary terms work the same, marked once per section. Only names that
  read as identifiers (with `_`, `.` or a capital) are linked, so give a
  plain-word function an explanation where it matters anyway. In the call
  sequences, each participant box and each call label is linked as a
  whole (a participant box even when its name is a plain word).
- **Tests**: name the tests that pin the group's behaviour, with what
  each guarantees in one sentence.

## 5. Check and build

```bash
S=<this skill's directory>/scripts/build_report.py
python3 "$S" --check report.json          # every check, no output files
python3 "$S" report.json <parent-dir>     # check, render, write
```

`<parent-dir>` is where the user's instructions keep reports; otherwise
`$DEV_CYCLE_REPORT_DIR`, else `~/Documents/dev-cycle-reports`. The
directory name is derived: `<YYYYMMDD of head>-<origin repo name, else the
checkout's directory name>-<topic>`.

Every check always runs and the script names each failure; fix the spec,
never the script. Errors stop the build; warnings are printed and the
build goes on, but fix them unless there is a reason not to. The
warnings are: a `lines` hint that misses, a pseudocode line over 80
columns, a block with assignments but no `# ` note, code-like words in a
`role` or a change's `text`, more than two `fns` in a row, more than four
rows in a package, more than about 15 rows in a figure, a package with no
edge, a `calls` entry never called, a flow without `example`, a glossary
term the report never uses, and a sentence ending in a plain 다. Everything else this document calls required or refused is
an error. A source that is a path is looked up in the repository
at head first, then on disk; a SHA must resolve; `#n`, `repo#n` and URLs
are not checked. Mermaid syntax is checked only by the build: the figures
are rendered there, by headless Chrome with a pinned Mermaid, and inlined
as SVG. No Chrome or no network fails the build with the reason.

## 6. Accuracy review (read-only, once)

Have a separate read-only reviewer check the built `report.json` against
the code and the sources: a sub-agent when the agent can start one,
otherwise the agent itself in a fresh pass that re-reads the code instead
of its own notes (say which in the reply). Give it the repository path and
the two SHAs. It checks:

- every package, row and arrow of both figures: the role says what its
  functions really do, at the right side, in the package that defines
  them;
- every `why` source exists and still says what the report claims;
- every `## ` explanation, `# ` note, `calls` line and sequence step is
  true at its side, and nothing describes a state a later commit replaced;
- no major change of the range is missing, and nothing outside it is
  described.

Verify each finding against the code yourself, fold in the ones that hold,
rebuild, and list the rejected ones with the reason in your reply. Review
again only when the fixes were large. If a background reviewer's result
never arrives, start a new one on the current spec rather than waiting.

## 7. Hand over

- Optionally screenshot the page (headless Chrome) to check the layout;
  fix problems in the spec, never in `index.html`.
- When the user's instructions say reports go to a git repository they
  publish, commit the report directory there and push as they allow.
- Reply in the user's language with: the path, the summary in one or two
  sentences, the groups, and the review findings you did not apply.

Real code blocks belong to commit-explain and call graphs of every
function to commit-flow-diagram; this report keeps to pseudocode and
packages.
