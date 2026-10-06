---
name: commit-flow-diagram
description: Draw what a commit — or a commit range / PR-sized span — changed as a code-flow picture, starting at the program entry point (main) and following the calls down into the changed functions. Each function, struct, enum, static or trait is a box holding its REAL code (verbatim, syntax-highlighted, unrelated parts elided with `...`), with call arrows leaving from the exact call line. Output is always the same fixed format: one directory per change holding one SVG (+PNG) per topic and one index.html. Use when the user asks to show, draw, diagram or visualize the code flow / call flow of a commit, a range, a branch or a PR ("코드 흐름 그림", "호출 흐름을 그려줘", "커밋 흐름도").
user-invocable: true
allowed-tools: Bash, Read, Grep, Glob, Write, Edit
---

# Commit Flow Diagram

Turn a change into a picture a reader can follow without opening the repo: from `main()` down to every function the change touches, each shown as a box with its real code, connected by arrows that leave from the line that makes the call.

This document stays in English (Claude-facing). Everything the reader sees in the figures — notes, titles, captions — is written in the user's language (Korean for this user).

## The format is fixed — never vary it

Every group this skill produces must look the same, whoever runs it and on whatever repository. The renderer (`scripts/render.py`) and the page builder (`scripts/build_group.py`) ARE the format: boxes, outlines, colors, badges, highlighting, arrows, legend, HTML page. Do not hand-edit an SVG, restyle a figure, add a one-off color, or render with any other tool. If the format itself must change, change the scripts (and this file) so every future group changes with it. All content variation lives in the spec (`group.json`) only.

| Element | Fixed rendering |
| --- | --- |
| Function box | solid outline, rounded corners |
| Struct / enum box | long-dash outline, square corners |
| Static / const box | dotted outline, square corners |
| Trait box | double outline, rounded corners |
| Status | badge + outline color: `신규` green (new in the range), `변경` orange (changed), `기존` gray (unchanged, on the path) |
| Code | verbatim source, syntax-highlighted; `...` = elided code |
| Added/changed line | yellow band + `+` in the gutter |
| Called function | its name is **bold** on the calling line |
| Call | solid navy arrow from the calling line's right-edge dot to the callee box |
| Deferred run | dashed purple arrow (closure/callback registered now, run later), with a label |
| Uses a type/data | dotted gray line, no arrowhead |
| Note | one green `// …` line above the call it explains |

## Step 0 — Resolve the input into before / after

Same rules as `commit-explain` Step 0, repeated here so this skill stands alone:

| User gave | before | after |
| --- | --- | --- |
| a single sha | `<sha>~1` | `<sha>` |
| `A..B` | `A` | `B` |
| `A...B`, a branch, a PR | `merge-base(A, B)` | `B` |
| "base X, head Y" | `X` | `Y` |

State the resolved pair to the user in one line before drawing. Read every commit message in `git log before..after` — they say *why*, and they name the topics the figures will split by.

## Step 1 — Find the paths to draw

1. List the changed functions/types: `git diff --stat before after`, then read each hunk. Tests, benches, docs and generated files are not drawn.
2. Find the program entry point of the binary that runs the changed code (`fn main`, `main()`, `Application.onCreate`, a request handler for a server…). If the change is in a library with several hosts, pick the host the user cares about; if unclear, ask.
3. Walk from the entry point to each changed function with `grep -rn "<fn>("` — every caller you draw must be a call site you found, never a guess. Unchanged functions on the way are kept to the single call that continues the path.
4. Follow each changed function down to the changed functions it calls, and to the types/data it reads or writes that the change touches.

## Step 2 — Split into figures by topic

One figure per topic, all in one group. Split when a figure would exceed about **14 boxes or 6 columns**, or when the change has two independent stories (e.g. "decide the setting" vs "build the engine with it"). A boundary call that continues in the next figure keeps its line, with the note ending `→ 그림 N`; the next figure starts from that same call line (dimmed lines show the context it came from).

## Step 3 — Write the spec (`group.json`)

### What goes in a box

- **Verbatim code only.** Every code line is copied from the file at `after`, keeping its indentation relative to the function body. Never paraphrase, never summarize a block as pseudo-code. The source's own comments are dropped; your notes replace them.
- **Elide with `...`** wherever lines are skipped — between kept lines, at the start or end of a body. Use `{"elide": true, "indent": N}` so the `...` sits at the indentation of what it replaces.
- **What may be elided:** code unrelated to the drawn path, and code that only checks a value's validity without changing what happens next (an assertion, a guard that logs and continues).
- **What must stay:** every line on the path to the next box, every line the range added or changed that the path runs, and every early exit that changes the result — `return Err(…)`, `refuse_to_start(…)`, `exit`, a `?` that aborts, a fallback `return default`.
- **Unchanged function on the path:** `...`, the one call line that continues the path, `...`.
- **Struct / enum / static / const boxes show only what the flow uses:** the declaration line, the fields/variants/entries the drawn code reads, writes or the range changed, and `...` for the rest. Short types (about 6 lines or fewer) may be shown whole.
- **Notes:** one short note (user's language) above each call line that leads to another box, saying why it is called *here*; optionally above a deciding branch. Not on every line.
- **Header:** `name` is the item's name as a reader would search for it (`cli_entry::run()`, `PiiCountry::parse()`, `PiiConfig`); `file` is `path:line` of the declaration at `after`.

### Spec format

```json
{
  "slug": "YYYYMMDD-<topic>",            // the group directory name
  "title": "<page title, user's language>",
  "repo": "/abs/path/to/repo", "before": "<ref>", "after": "<ref>",
  "range": "<repo> · before..after · <entry point>",
  "commits": [["sha", "subject"]],         // optional; filled from git log if absent
  "figures": [{
    "slug": "country-resolve",
    "title": "그림 1 · …", "caption": "…",
    "nodes": [{
      "id": "run", "kind": "fn|struct|enum|static|trait", "status": "new|changed|same",
      "name": "cli_entry::run()", "file": "tinicli/src/cli_entry.rs:157",
      "col": 1,                  // optional; default = call depth from the entry box
      "align_to": "other_id",    // optional; top no higher than that box (keeps arrows short)
      "desc": "…",               // optional one-line summary under the header
      "lines": [
        {"elide": true, "indent": 0},
        {"code": "let mut cfg = load_config(&config_path);",
         "note": "config.toml 읽기", "to": "load_config"},
        {"code": "    pii: PiiConfig {", "to": "PiiConfig", "edge": "use"},
        {"code": "        countries: Some(pii_countries),", "mark": "+"},
        {"code": "  || compile(countries))", "to": "compile", "edge": "defer", "label": "턴마다 실행"},
        {"code": "let c = f(&g(x))?;", "to": ["g", "f"]},
        {"code": "build_pii(config.pii)?;", "dim": true}
      ]}]
  }]
}
```

- `to` + `edge`: `call` (default), `defer`, `use`; a list in `to` for several calls on one line (`edge` may then be a list too).
- `mark: "+"` on lines added or changed in the range — `verify_spec.py` checks you got them right.
- `dim: true` for context lines that are not part of this figure's story (shown gray).
- `callee`: name(s) to bold when the callee box's name differs from the identifier on the line.
- Order nodes as they should stack inside each column (top to bottom). Put a type box right after the box that uses it.

Keep the spec in a file; `examples/argo-pii-locales.json` is a complete two-figure example.

## Step 4 — Verify, then build

```bash
SKILL_DIR=<directory of this file>
python3 "$SKILL_DIR/scripts/verify_spec.py" group.json        # must print "0 problem(s)"
python3 "$SKILL_DIR/scripts/build_group.py" group.json <parent-dir>
```

- `verify_spec.py` checks every code line is verbatim at `after`, every `+` matches the diff (and no added line lacks one), and every arrow names a box. Fix the spec until it passes; `build_group.py` refuses to build otherwise.
- `build_group.py` writes `<parent-dir>/<slug>/` with `index.html`, `figN-<slug>.svg`, `figN-<slug>.png` (when a Chrome/Chromium is installed) and `spec.json`. One change = one directory, so groups stay apart when several sit side by side.
- `<parent-dir>` is where the user keeps pictures; ask once if you do not know it.

## Step 5 — Look once, then deliver

Open one PNG (or screenshot `index.html`) and check for overlapping boxes, arrows crossing many boxes, or a box far from its caller. Fix with `col`, `align_to` or node order — never by editing the SVG. Then give the user the directory path; if an artifact/page publishing tool is available, publish `index.html` (it is self-contained) and give the link.

## Pre-send checklist

- [ ] Resolved before/after stated to the user.
- [ ] Every drawn caller came from a grep, starting at the real entry point.
- [ ] `verify_spec.py` printed `0 problem(s)` for the final spec.
- [ ] No paraphrased code; every skip shows `...`; early exits that change the result are still there.
- [ ] Struct/enum/static boxes show only what the flow uses.
- [ ] Every call line leading to a box has a note and its callee shows bold.
- [ ] Figures split by topic when large; boundary calls point to `→ 그림 N`.
- [ ] Output is one group directory built by `build_group.py`, unedited.
