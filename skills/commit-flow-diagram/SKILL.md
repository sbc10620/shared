---
name: commit-flow-diagram
description: "Draw what a commit — or a commit range / PR-sized span — changed as a code-flow picture, starting at the program entry point (main) and following the calls down into the changed functions. Each function, struct, enum, static or trait is a box holding its REAL code (verbatim, syntax-highlighted, unrelated parts elided with `...`), with call arrows leaving from the exact call line. Output is always the same fixed format, whatever agent or LLM runs it, as one directory per change holding one SVG (+PNG) per topic and one index.html. Use when the user asks to show, draw, diagram or visualize the code flow / call flow of a commit, a range, a branch or a PR ('코드 흐름 그림', '호출 흐름을 그려줘', '커밋 흐름도')."
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
| Function box | solid outline, rounded corners; header `fn name(params)` with the parameters read from the source (never written in the spec). A list over 48 characters keeps only the parameters the box's code uses (and `self`), with `…` for the rest |
| Struct / enum box | long-dash outline, square corners |
| Static / const box | dotted outline, square corners |
| Trait box | double outline, rounded corners |
| Status | badge + outline color: `신규` green (new in the range), `변경` orange (changed), `기존` gray (unchanged, on the path) |
| Code | verbatim source, syntax-highlighted; `...` = elided code |
| Theme | dark gray everywhere (canvas, boxes, page), GitHub-dark code colors — one look for every viewer |
| Added/changed line | dark amber band + `+` in the gutter |
| Call line | the whole line that calls another box is ***bold italic***; the called name in it is also underlined |
| Call | solid navy arrow from the calling line's right-edge dot to the callee box |
| Deferred run | dashed purple arrow (closure/callback registered now, run later), with a label |
| Uses a type/data | dotted gray line, no arrowhead |
| Note | one green `// …` line above the call it explains |

## Same result on any agent or LLM

Two runs of this skill on the same change — by different agents, models or people — must produce the same group. Everything that can be computed is computed by the scripts, and everything left to judgment follows a mechanical rule below:

| Decided by | What |
| --- | --- |
| scripts (never the spec) | box order, columns, vertical positions, colors, highlighting, bold-italic call lines, legend, directory name, file names, page |
| Step 1 algorithm | which boxes exist |
| Step 3 rules | which lines each box keeps, where `...` goes, which lines carry notes |
| Step 2 rule | how figures split |
| free wording (keep it short and literal) | note text, figure titles and captions, page title |

`verify_spec.py` refuses a spec that sets layout or names by hand, leaves a call line without a note, has a note over 40 characters, holds a box not reachable from the entry box, does not start figure 1 at `main()` (or claims `entry_exception` while a `main` exists), leaves a changed definition neither drawn nor in `not_drawn`, puts a note where notes are not allowed, shows a type box over 6 lines whole, or puts more than 18 boxes in one figure. Only the free wording may differ between runs, so write it plainly: notes say what the call is for at that line (`국가 목록을 프로세스 전역에 고정`), not commentary.

Only `bash`, `git` and `python3` (standard library) are needed, so any agent with a shell can run it; a Chrome/Chromium, if present, adds PNG previews.

## Step 0 — Resolve the input into before / after

Same rules as `commit-explain` Step 0, repeated here so this skill stands alone:

| User gave | before | after |
| --- | --- | --- |
| a single sha | `<sha>~1` | `<sha>` |
| `A..B` | `A` | `B` |
| `A...B`, a branch, a PR | `merge-base(A, B)` | `B` |
| "base X, head Y" | `X` | `Y` |

State the resolved pair to the user in one line before drawing. Read every commit message in `git log before..after` — they say *why*, and they name the topics the figures will split by.

## Step 1 — Choose the boxes (mechanical)

1. **Changed set C** — every function, method, struct, enum, static/const and trait whose definition has an added or removed line in `git diff before after`, excluding tests (`#[cfg(test)]`, `tests/`, `*_test.*`), benches, examples, docs and generated files.
2. **Entry box** — the `main()` of the binary that runs C: a function literally named `main` (`fn main`, `int main`, `def main`, `public static void main`). Several binaries: first pick the one whose crate/package/target name matches the repository name or its product binary, then search paths only to THAT `main` (a shallower path to another binary's `main` does not count); still ambiguous: ask the user once. Never start at a tool, handler or library function because it is closer to the change. Only when the code has no `main` at all (a pure library) start at the public function a host calls, and put the reason in the group's `entry_exception`. The verifier refuses a figure 1 that does not start at `main()` without that field.
3. **Path boxes** — for each function in C, the SHORTEST call chain from `main` to it, found by a backward breadth-first search: list the callers of the function (`git grep -n "<name>(" <after>`, excluding tests), then the callers of those, level by level, until a level contains `main`; the chain through the first `main` reached is the path. Within one level, visit callers in `git grep` output order, so ties resolve the same way every time. A call made through a trait object or callback (`dyn Trait`, a registry, a scheduler) counts as a call from the line that invokes the trait method (`executor.execute(…)`, `tool.call(…)`) to the impl box. Every function on a chain is a box; never draw a call site you did not find.
4. **Callee boxes** — every function in C that a drawn box calls. A trait impl that only delegates (`impl Trait for X { fn f() { self.f() } }`) is a box of its own on the path.
5. **Type boxes** — every type/data item in C that a drawn line reads, writes or constructs, linked with a `use` edge from the first such line.
6. Nothing else. An unchanged function off the path is not drawn even if interesting; an unchanged callee is not drawn (its call line stays, plain).
7. **`not_drawn`** — every definition in C (and only those) that got no box (reached only from tests or benches, not reachable from `main`, a helper only used for an error message, a type shown only as a value) goes into the group's `not_drawn` map as `"name": "reason"` (user's language, one short line). The verifier extracts C from the diff itself and refuses a spec where a changed definition is neither a box, a declaration line inside a box, nor in `not_drawn`; the page lists `not_drawn` under the figures.

## Step 2 — Split into figures by topic

One figure if all boxes fit in **18** — the verifier refuses a split below that. Otherwise split at the topmost changed function on the path (the first box in C reached from the entry): its call lines that lead to boxes, in source order, are taken one by one; each call's subtree goes into the current figure until adding the next would pass 18, then a new figure starts. Figure 1 keeps the entry chain; a later figure starts with that topmost function again, showing only the call lines it continues from (a line that only gives context from an earlier figure stays, with a note `그림 N 에서 …`), so every figure still begins at a box the reader has seen. A call continued in a later figure keeps its line in the earlier one with the note ending `→ 그림 N`.

## Step 3 — Write the spec (`group.json`)

### What goes in a box

- **Verbatim code only.** Every code line is copied from the file at `after` exactly as it is there, indentation included. Never paraphrase, never summarize a block as pseudo-code. The source's own comments are dropped; your notes replace them. The renderer removes the indentation all of a box's lines share, so do not re-indent anything yourself.
- **Elide with `...`** wherever lines are skipped — between kept lines, at the start or end of a body. Use `{"elide": true, "indent": N}` with N = the indentation (in spaces, in the file) of the first line it replaces.
- **What may be elided:** code unrelated to the drawn path, and code that only checks a value's validity without changing what happens next (an assertion, a guard that logs and continues).
- **What must stay:** every line on the path to the next box, every line the range added or changed that the path runs, and — in a changed function — every early exit in its body that changes the result (`return Err(…)`, `refuse_to_start(…)`, `exit`, a `?` that aborts, a fallback `return default`), before or after the path call.
- **Unchanged function on the path:** exactly `...`, the call line that continues the path, `...` — no enclosing `if`, `for`, `match` or closure lines (drop a `...` only where nothing is skipped, e.g. a one-line body). If the call is split over lines, keep the lines of that one call expression. If it calls two or more drawn boxes, keep each such call line, with `...` between them.
- **`+` marks:** on every line the range added or changed in content. A line that only moved or was re-indented is not changed — the verifier compares lines without surrounding whitespace, and it refuses both a missing and a wrong `+`.
- **Struct / enum / static / const boxes show only what the flow uses:** the declaration line, the fields/variants/entries the drawn code reads, writes or the range changed, and `...` for the rest. A type of 6 lines or fewer may be shown whole; longer ones must elide.
- **Notes:** one short note (user's language, at most 40 characters) saying why, written in plain words. Required on every call line that leads to another box (on the line itself or, for a call split over lines, the line just above). Allowed only on: those call lines, a `+` line, an early exit or the condition line right above one, a call continued in a later figure (ending `→ 그림 N`), and lines of type boxes. The verifier refuses a note anywhere else.
- **Header:** `name` is the item's name as a reader would search for it, ending in `()` for functions (`cli_entry::run()`, `PiiCountry::parse()`, `PiiConfig`) — the build fills the parameters in from the declaration; `file` is `path:line` of the declaration line itself (`fn …`, `struct …`) at `after` — the verifier reads that line and checks it declares that name.
- **Status:** `new` (the declaration did not exist at `before`), `changed` (it existed and the range touched it), `same` (not touched). The verifier computes it from the diff and refuses any other value.
- **Arrows:** a call arrow leaves the line that calls the target (or the line just above it, for a call split over lines), and that line must contain the target's name. When the code calls it under another name (an `as` import, a re-export), add `"callee": "<name on the line>"` to that line.

### Spec format

```json
{
  "title": "<page title, user's language>",
  "repo": "/abs/path/to/repo", "before": "<ref>", "after": "<ref>",
  "range": "<repo> · before..after · <entry point>",
  "commits": [["sha", "subject"]],         // optional; filled from git log if absent
  "not_drawn": {"helper_fn": "테스트에서만 호출"},  // every changed definition without a box
  "entry_exception": "…",                  // ONLY when the code has no main at all
  "figures": [{
    "title": "그림 1 · …", "caption": "…",
    "nodes": [{
      "id": "run", "kind": "fn|struct|enum|static|trait", "status": "new|changed|same",
      "name": "cli_entry::run()", "file": "tinicli/src/cli_entry.rs:157",
      "desc": "…",               // optional one-line summary under the header
      "lines": [
        {"elide": true, "indent": 0},
        {"code": "let mut cfg = load_config(&config_path);",
         "note": "config.toml 읽기", "to": "load_config"},
        {"code": "    pii: PiiConfig {", "to": "PiiConfig", "edge": "use"},
        {"code": "        countries: Some(pii_countries),", "mark": "+"},
        {"code": "  || compile(countries))", "to": "compile", "edge": "defer", "label": "턴마다 실행"},
        {"code": "let c = f(&g(x))?;", "to": ["g", "f"]}
      ]}]
  }]
}
```

- `to` + `edge`: `call` (default), `defer`, `use`; a list in `to` for several calls on one line (`edge` may then be a list too).
- `mark: "+"` on lines added or changed in the range — `verify_spec.py` checks you got them right.
- `callee`: the name the line uses for the target when it differs from the box's name (an `as` import, a re-export); it is underlined and lets the verifier match the arrow.
- Node order in the file does not matter: the renderer orders, places and aligns boxes from the edges. Do not add `col`, `align_to`, `slug` or `dim` — the verifier refuses them. Every code line renders the same way; only `...` is gray.

Keep the spec in a file; `examples/argo-pii-locales.json` is a complete two-figure example.

## Step 4 — Verify, then build

```bash
SKILL_DIR=<directory of this file>
python3 "$SKILL_DIR/scripts/verify_spec.py" group.json        # must print "0 problem(s)"
python3 "$SKILL_DIR/scripts/build_group.py" group.json [<parent-dir>]
```

- `verify_spec.py` checks every code line is verbatim at `after`, every `+` matches the diff (and no added line lacks one), every arrow names a box, and every sameness rule above. `build_group.py` runs it first and builds nothing unless it prints `0 problem(s)` — there is no option to skip it. Fix the spec until it passes.
- `build_group.py` writes `<parent-dir>/<YYYYMMDD>-<repo>-<sha>/` — the `after` commit's date, the repository name (from `origin`), its short sha — with `index.html`, `fig1.svg`, `fig2.svg`, …, the matching `.png` previews (when a Chrome/Chromium is installed) and `spec.json`. One change = one directory, and the same change always lands in the same directory (a rebuild overwrites it).
- `<parent-dir>`: the directory the user names; else `$COMMIT_FLOW_DIR`; else `~/Documents/code-flow-diagrams`. Tell the user the full path you wrote.
- `index.html` is self-contained: every figure inline and opened at actual size (100%), never rescaled by the page, so the browser's own zoom sizes it. The mouse wheel scrolls the page; it scrolls a figure only after the reader clicks that figure (an outline shows it; Esc or a click outside releases it). With zoom, fit, actual size, drag to pan, and a full-screen button. Full screen shows the figure alone at its current scale (no title bar or buttons; browser full screen where allowed, otherwise the figure fills the window); Esc closes it, and `+` / `-` / `0` zoom in, zoom out and fit. The page zoom runs from 5% to 1000% (separate from the browser's own zoom).

## Step 5 — Look once, then deliver

Open one PNG (or screenshot `index.html`) and check for overlapping boxes, arrows crossing many boxes, or a box far from its caller. Fix with `col`, `align_to` or node order — never by editing the SVG. Then give the user the directory path; if an artifact/page publishing tool is available, publish `index.html` (it is self-contained) and give the link.

## Pre-send checklist

- [ ] Resolved before/after stated to the user.
- [ ] Boxes chosen by the Step 1 algorithm; every drawn caller came from a grep, starting at the real `main()`; every other changed definition is in `not_drawn` with a reason.
- [ ] `verify_spec.py` printed `0 problem(s)` for the final spec.
- [ ] No paraphrased code; every skip shows `...`; early exits that change the result are still there.
- [ ] Struct/enum/static boxes show only what the flow uses.
- [ ] Every call line leading to a box has one note (≤ 40 chars); no other notes except kept early exits.
- [ ] Figures split by the Step 2 rule when over 18 boxes; boundary calls point to `→ 그림 N`.
- [ ] No `col`, `align_to`, `slug` or `dim` in the spec.
- [ ] Output is one group directory built by `build_group.py`, unedited.
