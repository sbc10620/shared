---
name: dev-cycle-report
description: "Build a top-down HTML report that explains a PR or a commit range (typically one produced by the dev-cycle skill) for understanding the code: why it changed, how the overall structure changed (before/after Mermaid figures), then per-topic annotated pseudocode of each flow before and after. Commits are grouped by topic and only the final state is explained, never an intermediate state a later commit replaced. Every code reference, figure identifier and source is checked against the repository by scripts/build_report.py before anything is built. Use when the user asks for a report, overview or structural explanation of a PR, branch or commit range ('변경 보고서', 'PR 보고서', '구조 설명 보고서', '이 PR 이 뭘 바꿨는지 보고서로'). For per-file before/after code use commit-explain; for a call-flow picture from main use commit-flow-diagram."
user-invocable: true
---

# Dev-cycle report

The reader wants to understand the change, top-down, without opening the
diff: first why, then how the structure moved, then how each flow works
now. `commit-explain` (per-file code) and `commit-flow-diagram` (call
chains from main) answer the detailed questions; this report is the map
above them and links to them instead of repeating them.

This document is agent-facing and stays in English. The report itself is
written in **Korean** (the user's language), in full sentences.

Investigation is **read-only** for the repository under report: never
modify, stage or commit anything there. The only writes are the report
directory and, when the user's setup says so, a commit of it.

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
- documents: design docs, plans and reviews in the user's notes repository
  (for this user `~/Works/shared/{docs,plans,reviews}`), memory state files
  (`~/.claude/projects/*/memory/`), plan files (`~/.claude/plans/*.md`);
- the PR description and comments (`gh pr view`), when `gh` is authenticated.

Rules:

- A plan file is overwritten by later work. Use one only when its content
  actually covers this range (it names the range's identifiers, branch or
  commits). Cite its path in `source` and its modified time in `text`.
- The current conversation is not a source: nobody can check it later.
  Something learned only from the conversation is either written down as
  an inference (below) or left out.
- No source → write the item as an **inference** with the code location it
  rests on (`inferred_from`). The page labels it 추정.
- A process record (review rounds, test or e2e results) always names the
  commit it applies to (`applies_to`): a result measured on a WIP commit is
  not a result for head. Quote result lines as the tool printed them when
  the source has them; otherwise give the summary and its source path. No
  record at all → leave `records` empty; the page says 기록 없음.

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
    {"text": "문제·목표·결정 한 문장", "source": "<file path | path:line | commit SHA | PR #n | URL>"},
    {"text": "...", "inferred_from": "<path at head>:<line>"}
  ],
  "structure": {
    "before": {"mermaid": "flowchart TB ...", "identifiers": ["RealName"], "caption": "..."},
    "after":  {"mermaid": "flowchart TB ...", "identifiers": ["RealName", "NewName"], "caption": "..."},
    "changes": [{"kind": "new|changed|moved|removed", "text": "...", "group": "<group id>"}]
  },
  "groups": [{
    "id": "kebab-id", "title": "주제", "one_line": "한 문장 요약",
    "why": ["이 주제가 필요한 이유 (optional for 기타)"],
    "commits": ["<sha>", "..."],
    "commit_notes": {"<sha>": {"replaced_by": "<later sha>"}},
    "flows": [{
      "title": "흐름 이름 (예: 부팅 때 언어를 고르는 흐름)",
      "before": {"code": "pseudocode", "refs": [{"path": "...", "lines": "120-160", "must_contain": ["fn_name"]}]},
      "after":  {"code": "pseudocode", "refs": [{"path": "...", "lines": "88-140", "must_contain": ["fn_name"]}]},
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
- **Structure figures** (the part the reader came for):
  - Draw components (modules, types, config, entry points) and how they
    connect, not every function. Keep each figure to about 15 nodes.
  - Draw `before` at base and `after` at head with the same node ids for
    the same things, so the eye can compare them. Mark nodes with
    `class <ids> new` or `class <ids> changed` in `after`, and
    `class <ids> removed` in `before`. The script defines those three
    classes; a spec with its own `classDef` or `style` is refused.
  - Every real code name in a node goes in `identifiers`: the script checks
    each one is in the Mermaid text and exists in the tree at that side.
    Plain descriptive labels (Korean words) need no entry.
  - Label an edge with its order ("1 먼저", "2 설치 뒤") when the order is
    what the change is about.
  - `changes` lists, in sentences, what is new, changed, moved or removed,
    each pointing at the group that explains it.
- **Pseudocode** (`flows`):
  - One flow per behaviour a reader would ask about ("a turn scans the
    input", "boot picks the languages"). Show the path from its entry
    point down to the changed part.
  - Use the real names of functions, types and config keys; write control
    flow language-neutrally; elide unrelated parts with `...`. Never drop
    an early return or branch that changes the result.
  - Comments are Korean, after `//`. Put `+` in column 0, before the
    indent, on a line that is new at head, and `-` on a line in `before`
    that is gone at head.
  - Keep each line within 80 columns (a Korean character counts two); the
    script warns otherwise. Put a long comment on its own line above the
    code it explains, with the same prefix and indent.
  - Each side has at least one `refs` entry; every `must_contain` name
    must appear in the pseudocode and in that file at that side. `lines`
    is a hint; a miss prints a warning with the real line numbers — fix the
    hint. Omit `before` when the flow did not exist at base.
- **Tests**: name the tests that pin the group's behaviour, with what
  each guarantees in one sentence.

## 5. Check and build

```bash
S=~/.agents/skills/dev-cycle-report/scripts/build_report.py
python3 "$S" --check report.json          # every check, no output files
python3 "$S" report.json <parent-dir>     # check, render, write
```

`<parent-dir>` defaults to `$DEV_CYCLE_REPORT_DIR`, else
`~/Documents/dev-cycle-reports`; this user passes `~/Works/shared/reports`.
The directory name is derived: `<YYYYMMDD of head>-<origin repo name, else
the checkout's directory name>-<topic>`.

Every check always runs and the script names each failure; fix the spec,
never the script. A source that is a path is looked up in the repository
at head first, then on disk; a SHA must resolve; `#n`, `repo#n` and URLs
are not checked. Mermaid syntax is checked only by the build: the figures
are rendered there, by headless Chrome with a pinned Mermaid, and inlined
as SVG, so the page opens offline. No Chrome or no network fails the build.

## 6. Accuracy review (one read-only subagent)

Give a subagent the repository path, the two SHAs and the built
`report.json` (an agent that cannot start one does this pass itself, and
says so), and have it check, against the code and the sources:

- every node and arrow of both figures (exists, connects as drawn, at the
  right side);
- every `why` source exists and still says what the report claims;
- each flow describes head, not a state a later commit replaced;
- no major change of the range is missing, and nothing outside it is
  described.

Verify each finding against the code yourself, fold in the ones that hold,
rebuild, and list the rejected ones with the reason in your reply. Review
again only when the fixes were large.

## 7. Hand over

- Optionally screenshot the page to check the layout; fix problems in the
  spec, never in `index.html`.
- When the parent directory is a git repository the user publishes (this
  user: `~/Works/shared`, push allowed without asking), commit the report
  directory and push.
- Reply in Korean with: the path, the summary in one or two sentences, the
  groups, and the review findings you did not apply. A record whose
  `applies_to` is not head is tagged "head 아님" on the page.

Real code blocks belong to commit-explain and call graphs of every
function to commit-flow-diagram; this report keeps to pseudocode and
components.
