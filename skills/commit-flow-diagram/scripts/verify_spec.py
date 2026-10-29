#!/usr/bin/env python3
"""Check a commit-flow group spec against the repository before rendering.

usage: verify_spec.py <group.json>

Checks, per box line (elided lines skipped):
  1. verbatim  — the stripped code line exists in the box's file at `after`
                 (`git show <after>:<path>`), so nothing in a box is paraphrase;
  2. "+" marks — judged where the line stands: found inside the box's
                 definition (in box order), a marked line is a line number
                 `git diff <before> <after>` added and an unmarked line is
                 not; a moved line is not added (see added_lines). Lines
                 shorter than 4 characters, such as braces, are not judged;
  3. edges     — every `to` names a box of the same figure;
  4. sameness   — the rules that make two agents produce the same group:
                 no hand layout (`col`, `align_to`), hand-picked `slug` or `dim`;
                 every call/defer line has a note and no note exceeds 40
                 characters; every box is reachable from the figure's entry
                 box; a type/data box over 6 lines shows `...`; a figure
                 holds at most 18 boxes; figure 1 starts at `main()` (or the
                 group states `entry_exception`), and every later figure
                 starts at a box an earlier figure already drew;
  5. folding   — a call line's `hops` is a real call chain at `after` (the
                 line calls hops[0], each hop's body calls the next, the last
                 calls the target box) holding no changed definition and no
                 `via` function; and an unchanged function box is drawn only
                 when it is the entry, a `via` function, the direct caller of
                 a new or changed box, or a branch box (two or more call
                 targets) — any other unchanged function is folded into
                 `hops`.
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
    r"|\b(?:const|static)\s+(?:mut\s+)?([A-Z_][A-Z0-9_]*)\s*:"
    r"|\btype\s+([A-Za-z_]\w*)\s*(?:<[^>]*>)?\s*=")           # type alias
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


MOD_DECL_RE = re.compile(r"^\s*(pub(\([^)]*\))?\s+)?mod\s+\w+\s*;")


def removed_text(repo, before, after):
    """Every `-` line of the whole range (stripped), across all files, so a
    line moved to another file counts as moved, not added."""
    return {l[1:].strip() for l in git(repo, "diff", "-U0", before, after).splitlines()
            if l.startswith("-") and not l.startswith("---")}


_REMOVED = {}
_MOVED_SPANS = {}


def _body(lines, start):
    """The definition starting at lines[start], as stripped code lines
    (blank and comment lines dropped), and its last line index."""
    end = block_end(lines, start)
    body = tuple(l.strip() for l in lines[start:end + 1]
                 if l.strip() and not l.lstrip().startswith(("//", "/*", "*", "#")))
    return body, end


VIS_RE = re.compile(r"^(pub(\([^)]*\))?|public|private|protected|internal|fileprivate)\s+")


def _no_vis(body):
    """`body` with the visibility of its declaration line dropped: a
    definition moved into a module often has to become `pub(super)`."""
    return (VIS_RE.sub("", body[0]),) + body[1:] if body else body


def _bodies(lines, path):
    """[(name, start, end, body)] of every definition in a file."""
    out = []
    for i in range(len(lines)):
        d = definition(lines, i, path)
        if d:
            body, end = _body(lines, i)
            out.append((d[0], i, end, body))
    return out


def moved_spans(repo, before, after):
    """{path: [(name, start, end)]} (0-based, at `after`) of the
    definitions whose code (comments and blank lines aside) equals a
    definition of the same name at `before`, in this file or another (from
    another file, the declaration's visibility may differ): a definition the
    range moved without changing it. Its lines are not added, whatever their
    length."""
    key = (repo, before, after)
    if key in _MOVED_SPANS:
        return _MOVED_SPANS[key]
    old = {}
    for st in git(repo, "diff", "--name-status", "--no-renames", before, after).splitlines():
        old_path = st.split("\t")[-1]
        if not old_path.endswith(SOURCE_EXT):
            continue
        try:
            lines = git(repo, "show", f"{before}:{old_path}").splitlines()
        except subprocess.CalledProcessError:
            continue  # added file
        for name, _, _, body in _bodies(lines, old_path):
            old.setdefault(name, set()).add((old_path, body, _no_vis(body)))
    out = {}
    for path in git(repo, "diff", "--name-only", before, after).splitlines():
        if not path.endswith(SOURCE_EXT):
            continue
        try:
            lines = git(repo, "show", f"{after}:{path}").splitlines()
        except subprocess.CalledProcessError:
            continue  # deleted file
        # Same code: moved. Same code but for the visibility of the
        # declaration: moved, if it came from another file (a visibility
        # change in place is a change).
        out[path] = [(name, a, b) for name, a, b, body in _bodies(lines, path)
                     if any(body == ob or (op != path and _no_vis(body) == nv)
                            for op, ob, nv in old.get(name, ()))]
    _MOVED_SPANS[key] = out
    return out


def changed_definitions(repo, before, after):
    return _definitions(repo, before, after)


def moved_definitions(repo, before, after):
    """{(name, path, line): True} of the definitions the range only moved:
    they hold moved lines (see added_lines) and no line changed in content,
    so they are not in the changed set and are not drawn; the page lists
    them."""
    out = {}
    for path, spans in moved_spans(repo, before, after).items():
        if TEST_PATH.search(path):
            continue  # tests are never drawn, moved or not
        raw = all_added_lines(repo, before, after, path)
        for name, a, b in spans:
            if any(a < n <= b + 1 for n in raw):
                out[(name, path, a + 1)] = True
    return out


def all_added_lines(repo, before, after, path):
    """Line numbers (at `after`) of every `+` line, moved or not."""
    out, new_ln = set(), 0
    for l in git(repo, "diff", "-U0", before, after, "--", path).splitlines():
        h = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", l)
        if h:
            new_ln = int(h.group(1))
        elif l.startswith("+") and not l.startswith("+++"):
            out.add(new_ln)
            new_ln += 1
    return out


def _definitions(repo, before, after):
    """{(name, path, line): True} of every non-test definition the range
    touches, keyed by its declaration so two definitions of one name stay
    apart: for each line the range added or changed in content (a moved
    line, a comment, an attribute, a blank line or a `mod x;` declaration
    does not count — see added_lines), the nearest enclosing definition
    above it (a definition line with no more indentation, or the line
    itself)."""
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
            # An inline test module (`mod tests {`), not a file module
            # declaration (`mod e2e;`), which only names another file.
            if re.match(r"\s*#\[cfg\(test\)\]", l) and i + 1 < len(lines) and \
                    re.match(r"\s*(pub(\([^)]*\))?\s+)?mod\s+\w+\s*\{", lines[i + 1]):
                test_from = i
                break
        touched = added_lines(repo, before, after, path)
        for ln in sorted(touched):
            i = min(ln, len(lines)) - 1
            if i < 0 or (test_from is not None and i >= test_from):
                continue
            if not lines[i].strip() or lines[i].lstrip().startswith(("//", "/*", "*", "#[", "# ", "@")):
                continue  # comment, attribute or blank: not a code change
            if MOD_DECL_RE.match(lines[i]):
                continue  # `mod x;` only names another file
            if re.fullmatch(r"[\s{}()\[\];,]*", lines[i]):
                continue  # only closing brackets: it belongs to no one definition
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
                    out[(d[0], path, j + 1)] = True
                    break
                if lj < ind:
                    ind = lj
    return out


MOVE_MIN = 16  # a removed line this long elsewhere in the file makes an added one a move


def added_lines(repo, before, after, path):
    """Line numbers (1-based, at `after`) of the lines the range added or
    changed in content. A `+` line that only moved or was re-indented does
    not count: its text (without surrounding whitespace) is also a `-` line
    of the same hunk, or, for a line of MOVE_MIN characters or more, a `-`
    line anywhere in the range, this file or another (a definition moved to
    another file is not new). A shorter line (`.iter()`, `return false;`)
    is too common to tell a move from a new line elsewhere."""
    out, new_ln, plus, minus = set(), 0, [], set()
    diff = git(repo, "diff", "-U0", before, after, "--", path).splitlines()
    key = (repo, before, after)
    if key not in _REMOVED:
        _REMOVED[key] = removed_text(repo, before, after)
    removed = _REMOVED[key]

    def flush():
        out.update(n for n, t in plus
                   if t not in minus and not (len(t) >= MOVE_MIN and t in removed))

    for l in diff:
        h = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", l)
        if h:
            flush()
            new_ln, plus, minus = int(h.group(1)), [], set()
        elif l.startswith("+") and not l.startswith("+++"):
            plus.append((new_ln, l[1:].strip()))
            new_ln += 1
        elif l.startswith("-") and not l.startswith("---"):
            minus.add(l[1:].strip())
    flush()
    spans = moved_spans(repo, before, after).get(path, [])
    return {n for n in out if not any(a < n <= b + 1 for _, a, b in spans)}


def block_end(lines, start):
    """Index of the last line of the definition that starts at lines[start]:
    where its braces close, or, with no brace (Python), the last line before
    one indented no deeper than the declaration."""
    depth, opened = 0, False      # braces
    sq, sq_opened = 0, False      # brackets: a `const X: &[T] = &[ … ];` table
    for j in range(start, len(lines)):
        code = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])\'|//.*$', "", lines[j])
        for ch in code:
            if ch == "{":
                depth, opened = depth + 1, True
            elif ch == "}":
                depth -= 1
            elif ch == "[":
                sq += 1
            elif ch == "]":
                sq -= 1
        if sq > 0 and depth <= 0:
            sq_opened = True  # a bracket left open outside any brace
        if sq_opened and sq <= 0 and depth <= 0 and code.rstrip().endswith(";"):
            return j
        if opened and depth <= 0 and sq <= 0:
            return j
        if not opened and lines[j].rstrip().endswith(";") and depth == 0 and sq <= 0 \
                and not lines[start].rstrip().endswith(("(", ",")):
            break  # a declaration with no body
    ind = len(lines[start]) - len(lines[start].lstrip())
    for j in range(start + 1, len(lines)):
        if lines[j].strip() and len(lines[j]) - len(lines[j].lstrip()) <= ind:
            return j - 1
    return len(lines) - 1


def enclosing_header(lines, i):
    """The stripped line of the block that holds the declaration at
    lines[i] (`impl Validator for Card {`, `class X:`), or None at the top
    level."""
    ind = len(lines[i]) - len(lines[i].lstrip())
    for j in range(i - 1, -1, -1):
        l = lines[j]
        if not l.strip() or l.lstrip().startswith(("//", "#", "*", "/*")):
            continue
        if len(l) - len(l.lstrip()) < ind:
            return l.strip()
    return None


def existed_before(after_lines, i, name, old_lines, path):
    """Whether a definition named `name` existed at `before` in the same
    enclosing block (the same `impl … {` / class header) as the one at
    after_lines[i]; at the top level, among top-level definitions."""
    header = enclosing_header(after_lines, i)
    spans = []
    if header is None:
        spans = [(0, len(old_lines) - 1, 0)]
    else:
        for k, l in enumerate(old_lines):
            if l.strip() == header:
                spans.append((k + 1, block_end(old_lines, k), len(l) - len(l.lstrip()) + 1))
    for a, b, min_ind in spans:
        for k in range(a, b + 1):
            l = old_lines[k]
            if header is None and l[:1].isspace():
                continue
            if header is not None and len(l) - len(l.lstrip()) < min_ind:
                continue
            d = definition(old_lines, k, path)
            if d and d[0] == name:
                return True
    return False


def _targets(ln):
    t = ln.get("to") or []
    t = [t] if isinstance(t, str) else t
    k = ln.get("edge", "call")
    return t, (k if isinstance(k, list) else [k] * len(t))


def hop_name(h):
    """`name` or `name@path-suffix` -> (name, suffix)."""
    name, _, where = h.partition("@")
    return name.strip(), where.strip()


def hop_bodies(repo, after, hop, cache):
    """The bodies (lists of source lines) of every non-test definition of a
    hop at `after`; `name@suffix` keeps only definitions in matching paths."""
    if hop in cache:
        return cache[hop]
    name, where = hop_name(hop)
    out = subprocess.run(["git", "-C", repo, "grep", "-nwF", name, after],
                         capture_output=True, text=True).stdout.splitlines()
    bodies, files = [], {}
    for hit in out:
        _, path, line, _ = (hit.split(":", 3) + ["", "", "", ""])[:4]
        if not path.endswith(SOURCE_EXT) or TEST_PATH.search(path) or (where and not path.endswith(where)):
            continue
        if path not in files:
            files[path] = git(repo, "show", f"{after}:{path}").splitlines()
        lines = files[path]
        i = int(line) - 1
        d = definition(lines, i, path)
        if d and d[0] == name:
            bodies.append(lines[i + 1:block_end(lines, i) + 1])
    cache[hop] = bodies
    return bodies


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
                diffs[path] = added_lines(repo, before, after, path)
            # Walk the box's lines in source order inside its definition, so a
            # line is judged where it is, not by its text anywhere in the file.
            try:
                flines = git(repo, "show", f"{after}:{path}").splitlines()
                k0 = int(n["file"].partition(":")[2]) - 1
                span_end = block_end(flines, k0)
            except (subprocess.CalledProcessError, ValueError, IndexError):
                flines, k0, span_end = [], 0, -1
            cursor = k0
            for ln in n.get("lines", []):
                for t in ([ln["to"]] if isinstance(ln.get("to"), str) else ln.get("to") or []):
                    if t not in ids:
                        problems.append(f"fig{fi+1} {n['id']}: edge to unknown box {t!r}")
                if ln.get("elide"):
                    continue
                code = ln["code"].strip()
                if sources[path] and code not in sources[path]:
                    problems.append(f"fig{fi+1} {n['id']}: not verbatim in {path}: {code!r}")
                at = next((k for k in range(cursor, span_end + 1) if flines[k].strip() == code), None)
                if at is None:
                    at = next((k for k in range(k0, span_end + 1) if flines[k].strip() == code), None)
                if at is None:
                    if flines and sources[path] and code in sources[path]:
                        problems.append(f"fig{fi+1} {n['id']}: not inside this box's definition "
                                        f"({n['file']}): {code!r}")
                    continue
                cursor = at + 1
                if len(code) >= 4 and bool(ln.get("mark")) != ((at + 1) in diffs[path]):
                    want = "needs" if (at + 1) in diffs[path] else "must not have"
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
            if (dname, path, int(line)) in changed:
                try:
                    old_lines = git(repo, "show", f"{before}:{path}").splitlines()
                except subprocess.CalledProcessError:
                    old_lines = []  # the file is new
                existed = existed_before(after_lines, int(line) - 1, dname, old_lines, path)
                want = "changed" if existed else "new"
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
                    if ln.get("hops"):
                        callee = hop_name(ln["hops"][0])[0].split("::")[-1]
                    alias = ln.get("callee")
                    names = [callee] + ([alias] if isinstance(alias, str) else list(alias or []))
                    here = ln.get("code", "") + " " + (lines[k - 1].get("code", "") if k else "")
                    if not any(re.search(rf"\b{re.escape(c)}\b", here) for c in names):
                        problems.append(f"fig{fi+1} {n['id']}: the arrow to {t} leaves a line that does not call "
                                        f"`{callee}`: {ln.get('code', '')!r}")
    # Folded calls (`hops`) and which unchanged boxes may stay (Step 1.3).
    via_names = list((group.get("via") or {}).keys())
    changed_names = {name for (name, _, _) in changed}
    body_cache = {}

    def hop_body_lookup(h):
        return hop_bodies(repo, after, h, body_cache)

    def is_via(name):
        return any(re.search(rf"(^|::|\.){re.escape(v)}(\(\))?$", name) or name == v for v in via_names)

    for fi, fig in enumerate(group["figures"]):
        by_id = {n["id"]: n for n in fig["nodes"]}
        called = {t for n in fig["nodes"] for ln in n.get("lines", []) for t, _ in zip(*_targets(ln))}
        for n in fig["nodes"]:
            for ln in n.get("lines", []):
                hops = ln.get("hops")
                if not hops:
                    continue
                tos = [t for t, k in zip(*_targets(ln)) if k != "use"]
                if len(tos) != 1 or tos[0] not in by_id:
                    problems.append(f"fig{fi+1} {n['id']}: a line with `hops` has exactly one call target box")
                    continue
                target = re.split(r"::|\.", re.sub(r"\(.*$", "", by_id[tos[0]]["name"]))[-1].split()[-1]
                chain = [hop_name(h)[0].split("::")[-1] for h in hops] + [target]
                for h, nxt in zip(hops, chain[1:]):
                    hname = hop_name(h)[0].split("::")[-1]
                    if hname in changed_names:
                        problems.append(f"fig{fi+1} {n['id']}: hop `{h}` is a changed definition — draw it as a box")
                    if is_via(hop_name(h)[0]):
                        problems.append(f"fig{fi+1} {n['id']}: hop `{h}` is a `via` function — draw it as a box")
                    bodies = hop_body_lookup(h)
                    if not bodies:
                        problems.append(f"fig{fi+1} {n['id']}: hop `{h}` has no definition at {after} "
                                        "(write `name@path` when the name is ambiguous)")
                    elif not any(re.search(rf"\b{re.escape(nxt)}\b", l) for b in bodies for l in b):
                        problems.append(f"fig{fi+1} {n['id']}: hop `{h}` does not call `{nxt}` at {after}")
        for n in fig["nodes"]:
            if n["kind"] != "fn" or n.get("status") != "same" or n["id"] not in called or is_via(n["name"]):
                continue
            calls = {t for ln in n.get("lines", []) for t, k in zip(*_targets(ln)) if k != "use" and t in by_id}
            hands_off = any(by_id[t].get("status") in ("new", "changed") for t in calls)
            if not hands_off and len(calls) < 2:
                problems.append(f"fig{fi+1} {n['id']}: unchanged `{n['name']}` only passes the path on — fold it "
                                "into the `hops` of the line that calls it (Step 1.3)")
    if len(group["figures"]) > 1 and len(unique) <= 18:
        problems.append(f"{len(unique)} distinct boxes fit in one figure — do not split (Step 2)")
    # A `not_drawn` key names a changed definition: `name`, or, when two
    # changed definitions share the name, `name@path` (a path suffix is
    # enough: `default@install.rs`).
    def nd_matches(key, name, path):
        base, _, where = key.partition("@")
        return base == name and (not where or path.endswith(where))

    not_drawn = group.get("not_drawn", {})
    for key in not_drawn:
        hits = [(n, p) for (n, p, _) in changed if nd_matches(key, n, p)]
        if not hits:
            problems.append(f"not_drawn `{key}` is not a definition this range changed")

    # Completeness: every changed definition is a box (its declaration line),
    # a declaration shown as a line inside a box of the same file (e.g. a
    # const listed in its enum's box), or explained in `not_drawn`.
    box_at = {(n["file"].partition(":")[0], int(n["file"].partition(":")[2] or 0))
              for fig in group["figures"] for n in fig["nodes"]}
    inside = {(n["file"].partition(":")[0], d[0])
              for fig in group["figures"] for n in fig["nodes"]
              for ln in n.get("lines", []) if not ln.get("elide")
              for d in [definition([ln.get("code", "")], 0, n["file"].partition(":")[0])] if d}
    for (name, path, line) in changed:
        if (path, line) in box_at or (path, name) in inside:
            continue
        if any(nd_matches(k, name, path) for k in not_drawn):
            continue
        problems.append(f"changed `{name}` ({path}:{line}) is neither a box nor listed in `not_drawn` with a reason")
    for name, why in not_drawn.items():
        if not str(why).strip():
            problems.append(f"not_drawn `{name}`: give the reason")
    # A `via` function is one every chain to the change must pass (Step 1.3).
    names = [n["name"] for fig in group["figures"] for n in fig["nodes"]]
    for name, why in (group.get("via") or {}).items():
        if not any(re.search(rf"(^|::|\.){re.escape(name)}(\(\))?$", x) or x == name for x in names):
            problems.append(f"via `{name}` is not a box — draw the chain through it")
        if not str(why).strip():
            problems.append(f"via `{name}`: give the reason")
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
