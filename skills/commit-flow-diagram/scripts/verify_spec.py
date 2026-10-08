#!/usr/bin/env python3
"""Check a commit-flow group spec against the repository before rendering.

usage: verify_spec.py <group.json>

Checks, per box line (elided lines skipped):
  1. verbatim  — the stripped code line exists in the box's file at `after`
                 (`git show <after>:<path>`), so nothing in a box is paraphrase;
  2. "+" marks — a marked line is an added line of `git diff <before> <after>`
                 for that file, and an unmarked line is not (lines shorter
                 than 4 characters, such as braces, are not judged);
  3. edges     — every `to` names a box of the same figure;
  4. sameness   — the rules that make two agents produce the same group:
                 no hand layout (`col`, `align_to`), hand-picked `slug` or `dim`;
                 every call/defer line has a note and no note exceeds 40
                 characters; every box is reachable from the figure's entry
                 box; a type/data box over 6 lines shows `...`; a figure
                 holds at most 18 boxes; figure 1 starts at `main()` (or the
                 group states `entry_exception`), and every later figure
                 starts at a box an earlier figure already drew.
Exit 1 with a list on any failure.
"""
import json
import re
import subprocess
import sys

import decl


SOURCE_EXT = (".rs", ".c", ".h", ".cc", ".cpp", ".hpp", ".java", ".kt", ".kts", ".swift",
              ".go", ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cs", ".m", ".mm")
TEST_PATH = re.compile(r"(^|/)(tests?|benches|examples|testdata|fixtures)/|(_test|_tests|\.test|\.spec|Test)\.[a-z]+$")
DEF_RE = re.compile(
    r"\bfn\s+([A-Za-z_]\w*)"                                     # Rust
    r"|\bdef\s+([A-Za-z_]\w*)"                                   # Python
    r"|\bfunc\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)"                 # Go, Swift
    r"|\bfun\s+(?:<[^>]*>\s*)?(?:[\w.]+\.)?([A-Za-z_]\w*)"         # Kotlin
    r"|\bfunction\s+([A-Za-z_]\w*)"                              # JS/TS
    r"|\b(?:struct|enum|trait|union|class|interface|record)\s+([A-Za-z_]\w*)"
    r"|\b(?:const|static)\s+(?:mut\s+)?([A-Z_][A-Z0-9_]*)\s*:")
MAIN_RE = re.compile(r"^\s*(pub\s+)?(async\s+)?fn\s+main\s*\(|\bint\s+main\s*\(|^def\s+main\s*\(|"
                     r"static\s+void\s+main\s*\(|^func\s+main\s*\(|^fun\s+main\s*\(")


def definition(lines, i, path):
    """(name, is_const_or_static) of what lines[i] declares, or None. C, C++
    and Java functions have no keyword, so they are read by decl.function."""
    if decl.is_clike(path):
        f = decl.function(lines, i)
        if f:
            return f[0], False
    m = DEF_RE.search(lines[i])
    if not m:
        return None
    return next(g for g in m.groups() if g), bool(m.group(7))


EXIT_RE = re.compile(r"\breturn\b|\bErr\(|\?;?\s*$|\bexit\(|\bpanic!|\bthrow\b|\braise\b|refuse_to_start|"
                     r"\bbreak\b|\bcontinue\b|=>\s*Ok\(|=>\s*Err")


def changed_definitions(repo, before, after):
    """{name: "path:line"} of every non-test definition the range touches:
    for each added or changed code line (comments, attributes and blank
    lines do not count), the nearest enclosing definition above it (a
    definition line with no more indentation, or the line itself)."""
    out = {}
    names = git(repo, "diff", "--name-only", before, after).splitlines()
    for path in names:
        if not path.endswith(SOURCE_EXT) or TEST_PATH.search(path):
            continue
        try:
            lines = git(repo, "show", f"{after}:{path}").splitlines()
        except subprocess.CalledProcessError:
            continue  # deleted file
        test_from = None
        for i, l in enumerate(lines):
            if re.match(r"\s*#\[cfg\(test\)\]", l) and i + 1 < len(lines) and \
                    re.match(r"\s*(pub\s+)?mod\s", lines[i + 1]):
                test_from = i
                break
        touched = set()
        for h in re.finditer(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@",
                             git(repo, "diff", "-U0", before, after, "--", path), re.M):
            start, count = int(h.group(2)), int(h.group(3) or 1)
            touched.update(range(start, start + max(count, 1)))
        for ln in sorted(touched):
            i = min(ln, len(lines)) - 1
            if i < 0 or (test_from is not None and i >= test_from):
                continue
            if not lines[i].strip() or lines[i].lstrip().startswith(("//", "/*", "*", "#[", "# ", "@")):
                continue  # comment, attribute or blank: not a code change
            ind = len(lines[i]) - len(lines[i].lstrip())
            for j in range(i, -1, -1):
                l = lines[j]
                if not l.strip() or l.lstrip().startswith(("//", "#", "*", "/*")):
                    continue
                lj = len(l) - len(l.lstrip())
                d = definition(lines, j, path)
                if d and d[1] and lj > 0 and j != i:
                    d = None  # a const/static inside a body is not a definition of its own
                if d and (j == i or lj <= ind):
                    out.setdefault(d[0], f"{path}:{j+1}")
                    break
                if lj < ind:
                    ind = lj
    return out


def _targets(ln):
    t = ln.get("to") or []
    t = [t] if isinstance(t, str) else t
    k = ln.get("edge", "call")
    return t, (k if isinstance(k, list) else [k] * len(t))


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=True).stdout


def main():
    group = json.load(open(sys.argv[1], encoding="utf-8"))
    repo, before, after = group["repo"], group["before"], group["after"]
    sources, diffs = {}, {}
    problems = []
    if "slug" in group:
        problems.append("group: remove `slug` — build_group.py derives the directory name")
    drawn = set()  # (name, file) of boxes in earlier figures
    for fi, fig in enumerate(group["figures"]):
        ids = {n["id"] for n in fig["nodes"]}
        if "slug" in fig:
            problems.append(f"fig{fi+1}: remove `slug` — figure files are numbered (fig{fi+1}.svg)")
        if len(ids) > 18:
            problems.append(f"fig{fi+1}: {len(ids)} boxes — split the figure (at most 18)")
        targets = {}
        for n in fig["nodes"]:
            for ln in n.get("lines", []):
                t = ln.get("to")
                for x in ([t] if isinstance(t, str) else t or []):
                    targets.setdefault(n["id"], []).append(x)
        called = {x for xs in targets.values() for x in xs}
        roots = [n["id"] for n in fig["nodes"] if n["id"] not in called]
        root = next((n for n in fig["nodes"] if roots and n["id"] == roots[0]), None)
        if root is None:
            problems.append(f"fig{fi+1}: no entry box (every box is called by another)")
        elif fi == 0 and not re.search(r"(^|::|\.)main\(\)$", root["name"]) and not group.get("entry_exception"):
            problems.append(f"fig1: starts at {root['name']!r} — start at the program's `main()` "
                            "(Step 1), or set group `entry_exception` to why there is none")
        elif fi > 0 and (root["name"], root["file"]) not in drawn:
            problems.append(f"fig{fi+1}: starts at {root['name']!r}, which no earlier figure drew")
        if len(roots) > 1:
            problems.append(f"fig{fi+1}: {len(roots)} entry boxes {roots} — one figure has one entry")
        reach, todo = set(), roots[:1]
        while todo:
            cur = todo.pop()
            if cur not in reach:
                reach.add(cur)
                todo += targets.get(cur, [])
        for n in fig["nodes"]:
            if n["id"] not in reach:
                problems.append(f"fig{fi+1} {n['id']}: not reachable from the entry box {roots[:1]}")
            for key in ("col", "align_to"):
                if key in n:
                    problems.append(f"fig{fi+1} {n['id']}: remove `{key}` — layout is computed")
            if n["kind"] in ("struct", "enum", "static", "trait") and len(n.get("lines", [])) > 6 \
                    and not any(ln.get("elide") for ln in n["lines"]):
                problems.append(f"fig{fi+1} {n['id']}: type box over 6 lines must show only what the flow uses (`...`)")
            prev = {}
            for ln in n.get("lines", []):
                if "dim" in ln:
                    problems.append(f"fig{fi+1} {n['id']}: remove `dim` — every code line renders the same")
                kinds = ln.get("edge", "call")
                kinds = kinds if isinstance(kinds, list) else [kinds]
                # A call split over lines may carry its note on the line above.
                if ln.get("to") and any(k != "use" for k in kinds) and not (ln.get("note") or prev.get("note")):
                    problems.append(f"fig{fi+1} {n['id']}: call line needs a note: {ln.get('code', '')!r}")
                if ln.get("note") and n["kind"] not in ("struct", "enum", "static", "trait"):
                    nxt = n["lines"][n["lines"].index(ln) + 1] if n["lines"].index(ln) + 1 < len(n["lines"]) else {}
                    allowed = (ln.get("to") or (nxt.get("to") and not nxt.get("note")) or ln.get("mark")
                               or EXIT_RE.search(ln.get("code", ""))           # an early exit
                               or EXIT_RE.search(nxt.get("code", ""))          # the condition of one
                               or re.search(r"→ 그림 \d+$", ln["note"]))      # continues in a later figure
                    if not allowed:
                        problems.append(f"fig{fi+1} {n['id']}: note on a line that is not a call, a `+` line "
                                        f"or an early exit: {ln.get('code', '')!r}")
                prev = ln
                if ln.get("note") and len(ln["note"]) > 40:
                    problems.append(f"fig{fi+1} {n['id']}: note over 40 characters: {ln['note']!r}")
        drawn |= {(n["name"], n["file"]) for n in fig["nodes"]}
        for n in fig["nodes"]:
            path = n["file"].split(":")[0]
            if path not in sources:
                try:
                    sources[path] = {l.strip() for l in git(repo, "show", f"{after}:{path}").splitlines()}
                except subprocess.CalledProcessError:
                    problems.append(f"fig{fi+1} {n['id']}: {path} does not exist at {after}")
                    sources[path] = set()
                d = git(repo, "diff", "-U0", before, after, "--", path).splitlines()
                added = {l[1:].strip() for l in d if l.startswith("+") and not l.startswith("+++")}
                removed = {l[1:].strip() for l in d if l.startswith("-") and not l.startswith("---")}
                diffs[path] = added - removed
            for ln in n.get("lines", []):
                for t in ([ln["to"]] if isinstance(ln.get("to"), str) else ln.get("to") or []):
                    if t not in ids:
                        problems.append(f"fig{fi+1} {n['id']}: edge to unknown box {t!r}")
                if ln.get("elide"):
                    continue
                code = ln["code"].strip()
                if sources[path] and code not in sources[path]:
                    problems.append(f"fig{fi+1} {n['id']}: not verbatim in {path}: {code!r}")
                if len(code) >= 4 and bool(ln.get("mark")) != (code in diffs[path]):
                    want = "needs" if code in diffs[path] else "must not have"
                    problems.append(f"fig{fi+1} {n['id']}: {want} a + mark: {code!r}")
    changed = changed_definitions(repo, before, after)
    # Box identity, status and arrows, all against the repository.
    unique = set()
    for fi, fig in enumerate(group["figures"]):
        by_id = {n["id"]: n for n in fig["nodes"]}
        for n in fig["nodes"]:
            path, _, line = n["file"].partition(":")
            unique.add((n["name"], n["file"]))
            try:
                after_lines = git(repo, "show", f"{after}:{path}").splitlines()
                decl_line = after_lines[int(line) - 1]
            except (subprocess.CalledProcessError, ValueError, IndexError):
                problems.append(f"fig{fi+1} {n['id']}: `file` must be path:line of the declaration at {after}")
                continue
            d = definition(after_lines, int(line) - 1, path)
            dname = d[0] if d else None
            if not dname:
                problems.append(f"fig{fi+1} {n['id']}: {n['file']} is not a declaration line: {decl_line.strip()!r}")
                continue
            if not re.search(rf"\b{re.escape(dname)}\b", n["name"]):
                problems.append(f"fig{fi+1} {n['id']}: name {n['name']!r} does not match the declaration `{dname}`")
            if dname in changed:
                try:
                    existed = decl_line.strip() in {l.strip() for l in git(repo, "show", f"{before}:{path}").splitlines()}
                except subprocess.CalledProcessError:
                    existed = False
                want = "changed" if existed else "new"
                # A changed signature line is "changed" when the name existed before.
                if not existed:
                    try:
                        old = git(repo, "show", f"{before}:{path}")
                        if re.search(rf"\b(fn|def|func|fun|function|struct|enum|trait|class|interface|const|static)\s+(mut\s+)?{re.escape(dname)}\b", old):
                            want = "changed"
                        elif decl.is_clike(path):
                            old_lines = old.splitlines()
                            if any(f and f[0] == dname for f in (decl.function(old_lines, k) for k in
                                   range(len(old_lines)) if dname in old_lines[k])):
                                want = "changed"
                    except subprocess.CalledProcessError:
                        pass
            else:
                want = "same"
            if n.get("status") != want:
                problems.append(f"fig{fi+1} {n['id']}: status must be `{want}` (from the diff), not `{n.get('status')}`")
            lines = n.get("lines", [])
            for k, ln in enumerate(lines):
                for t, kind in zip(*_targets(ln)):
                    if kind == "use" or t not in by_id:
                        continue
                    callee = re.split(r"::|\.", re.sub(r"\(.*$", "", by_id[t]["name"]))[-1].split()[-1]
                    alias = ln.get("callee")
                    names = [callee] + ([alias] if isinstance(alias, str) else list(alias or []))
                    here = ln.get("code", "") + " " + (lines[k - 1].get("code", "") if k else "")
                    if not any(re.search(rf"\b{re.escape(c)}\b", here) for c in names):
                        problems.append(f"fig{fi+1} {n['id']}: the arrow to {t} leaves a line that does not call "
                                        f"`{callee}`: {ln.get('code', '')!r}")
    if len(group["figures"]) > 1 and len(unique) <= 18:
        problems.append(f"{len(unique)} distinct boxes fit in one figure — do not split (Step 2)")
    for name in group.get("not_drawn", {}):
        if name not in changed:
            problems.append(f"not_drawn `{name}` is not a definition this range changed")

    # Completeness: every changed definition is a box or explained.
    # Drawn = a box's name, or a declaration shown as a line inside a box
    # (e.g. a const listed in its enum's box).
    boxed = " ".join(n["name"] for fig in group["figures"] for n in fig["nodes"])
    boxed += " " + " ".join(d[0]
                            for fig in group["figures"] for n in fig["nodes"]
                            for ln in n.get("lines", []) if not ln.get("elide")
                            for d in [definition([ln.get("code", "")], 0, n["file"].partition(":")[0])] if d)
    not_drawn = group.get("not_drawn", {})
    for name, where in changed.items():
        if not re.search(rf"\b{re.escape(name)}\b", boxed) and name not in not_drawn:
            problems.append(f"changed `{name}` ({where}) is neither a box nor listed in `not_drawn` with a reason")
    for name, why in not_drawn.items():
        if not str(why).strip():
            problems.append(f"not_drawn `{name}`: give the reason")
    # An entry exception only when the code really has no main.
    if group.get("entry_exception"):
        hits = subprocess.run(["git", "-C", repo, "grep", "-nE",
                               r"fn main\(|int main\(|def main\(|void main\(|func main\(|fun main\(", after],
                              capture_output=True, text=True).stdout.splitlines()
        hits = [h for h in hits if not TEST_PATH.search(h.split(":", 2)[1])]
        if hits:
            problems.append(f"entry_exception set, but the code has a main ({hits[0].split(':', 2)[1]}) — start there")
    for p in problems:
        print(p)
    print(f"{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
