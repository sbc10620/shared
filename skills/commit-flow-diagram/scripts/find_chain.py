#!/usr/bin/env python3
"""Find the call chain Step 1.3 asks for: the shortest chain from `main` to
a function, at one revision.

usage: find_chain.py <repo> <rev> <function> --main PATH [--via NAME]
                     [--paths DIR ...] [--max-depth N]

<function> and --via take a bare name (`compile_from_yaml`) or a qualified
one (`PiiSpanDetector::detect`, `cli_entry::run`). --main is the path (or a
path suffix) of the product binary's main (Step 1.2).

Nodes are definitions, not names, so a chain never jumps from one `run` to
an unrelated `run`. A call resolves to the definitions of its name that its
qualifier allows: `Q::name(` / `Q::name` keeps definitions in a file or
directory named Q, or under an `impl … Q …` / `class Q` header (`self`,
`Self`, `super`, `crate` allow all); with no definition matching Q, or with
no qualifier (`x.name(`, `name(`, `(name)` passed as a value), every
definition of the name. A call through a trait object therefore reaches
every impl of the method, as Step 1.3 says.

The search runs from both ends (callers up from the function, callees down
from `main`), one batch of `git grep` per level, growing the side with the
smaller frontier first; ties resolve in `git grep` output order. --via runs
it twice, main → via and via → function, and joins the chains.

Printed per step: the function, its declaration (path:line) and the line
that calls the next one; a call line under a `#[cfg(...)]` / `#if` inside
the caller is flagged for Step 1.3's build-configuration rule. Tests are
never searched.
"""
import argparse
import os
import re
import subprocess
import sys

import decl
from verify_spec import DEF_RE, SOURCE_EXT, TEST_PATH, block_end, enclosing_header

FN_GROUPS = (1, 2, 3, 4, 5)  # DEF_RE groups that declare a function
GREP_CHUNK = 200  # names per `git grep`: one huge alternation makes git grep fail
ANY_QUAL = {"self", "Self", "super", "crate", "this"}
# `Q::name(` / `name(` / `name::<T>(`, or a path `Q::name` used as a value.
CALL_FORMS = re.compile(r"(?:\b(\w+)\s*::\s*)?\b(\w+)\s*(?:::<[^>]*>)?\s*\(|"
                        r"\b(\w+)::(\w+)\b(?!\s*(?:::|\())")
STRINGS = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])\'|//.*$')
COMMENT = ("//", "*", "/*", "#")
IMPORT = re.compile(r"\s*(pub(\([^)]*\))?\s+)?(use|import|from|#include)\b")


def function_name(lines, i, path):
    if decl.is_clike(path):
        f = decl.function(lines, i)
        return f[0] if f else None
    m = DEF_RE.search(lines[i])
    if not m:
        return None
    for g in FN_GROUPS:
        if m.group(g):
            return m.group(g)
    return None


def calls_in(text):
    """[(qualifier, name, kind, arity)] of the calls on a line, in line
    order, string literals and comments left out. kind: "plain" for
    `name(` / `Q::name(` / a path `Q::name`; "self" for `self.name(`;
    "blind" for a method on any other receiver (`x.name(`,
    `self.field.name(`), whose target a name cannot tell — the search
    follows those only into the next waypoint. arity: the number of
    arguments of a method call, or None."""
    text = STRINGS.sub('""', text)
    out = []
    for m in CALL_FORMS.finditer(text):
        if m.group(2):
            before = text[:m.start(2)].rstrip()
            if m.group(1) is None and before.endswith("."):
                kind = "self" if re.search(r"(?<![\w.])(self|this)\s*\.$", before) else "blind"
                args = top_level_args(text, text.find("(", m.end(2) - 1))
                out.append((None, m.group(2), kind, len(args) if args is not None else None))
            else:
                out.append((m.group(1), m.group(2), "plain", None))
        elif m.group(4):
            out.append((m.group(3), m.group(4), "plain", None))
    return out


LANG = {".rs": "rs", ".py": "py", ".go": "go", ".swift": "swift", ".kt": "kt", ".kts": "kt",
        ".java": "jvm", ".ts": "js", ".tsx": "js", ".js": "js", ".jsx": "js", ".mjs": "js",
        ".c": "c", ".h": "c", ".cc": "c", ".cpp": "c", ".hpp": "c", ".cs": "cs", ".m": "c", ".mm": "c"}


def lang(path):
    return LANG.get(os.path.splitext(path)[1])


def top_level_args(text, k):
    """The comma-separated arguments of the parenthesis opening at text[k],
    or None if it does not close in `text`."""
    if k < 0:
        return None
    depth, cur, out = 0, "", []
    for ch in text[k:]:
        if ch in "([{<":
            depth += 1
            if depth == 1 and ch == "(":
                continue
        elif ch in ")]}>":
            depth -= 1
            if depth == 0:
                if cur.strip():
                    out.append(cur.strip())
                return out
        if ch == "," and depth == 1:
            out.append(cur.strip())
            cur = ""
            continue
        cur += ch
    return None


def split_name(s):
    q, _, n = s.rpartition("::")
    return (q.split("::")[-1] or None), n


class Repo:
    def __init__(self, path, rev, paths):
        self.path, self.rev, self.paths = path, rev, paths or ["."]
        self.files, self.defs = {}, {}
        # One `git cat-file --batch` for every file: a `git show` per file
        # costs a process each, and a common name hits thousands of files.
        self.batch = subprocess.Popen(["git", "-C", path, "cat-file", "--batch"],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def grep(self, pattern_of, names):
        hits = []
        for k in range(0, len(names), GREP_CHUNK):
            r = subprocess.run(["git", "-C", self.path, "grep", "-nP", pattern_of(names[k:k + GREP_CHUNK]),
                                self.rev, "--", *self.paths], capture_output=True, text=True)
            if r.returncode > 1:
                sys.exit(f"git grep failed: {r.stderr.strip()}")
            for hit in r.stdout.splitlines():
                parts = hit.split(":", 3)
                if len(parts) < 4:
                    continue
                _, p, ln, text = parts
                if p.endswith(SOURCE_EXT) and not TEST_PATH.search(p) and not text.lstrip().startswith(COMMENT):
                    hits.append((p, int(ln) - 1, text))
        return hits

    def lines(self, path):
        return self.file(path)[0]

    def file(self, path):
        """(lines, function spans [(start, end, name)], test spans, import line indices)."""
        if path not in self.files:
            self.batch.stdin.write(f"{self.rev}:{path}\n".encode())
            self.batch.stdin.flush()
            header = self.batch.stdout.readline().split()
            text = ""
            if len(header) >= 3 and header[1] == b"blob":
                text = self.batch.stdout.read(int(header[2])).decode("utf-8", "replace")
                self.batch.stdout.read(1)
            lines = text.splitlines()
            spans, tests, imports, in_use = [], [], set(), False
            for i, l in enumerate(lines):
                if in_use or IMPORT.match(l):
                    imports.add(i)  # a `use a::{ … };` block may span lines
                    in_use = ";" not in l and not l.rstrip().endswith(")")
                    if IMPORT.match(l) and l.strip().startswith(("from", "import", "#include")):
                        in_use = False
                name = function_name(lines, i, path)
                if name:
                    spans.append((i, block_end(lines, i), name))
                if re.match(r"\s*#\[cfg\(test\)\]", l) and i + 1 < len(lines) and \
                        re.match(r"\s*(pub(\([^)]*\))?\s+)?mod\s+\w+\s*\{", lines[i + 1]):
                    tests.append((i, block_end(lines, i + 1)))
            self.files[path] = (lines, spans, tests, imports)
        return self.files[path]

    def enclosing(self, path, i):
        """The definition (path, decl index, name) innermost around line i."""
        lines, spans, tests, imports = self.file(path)
        if i in imports or any(a <= i <= b for a, b in tests):
            return None
        best = None
        for a, b, name in spans:
            if a < i <= b and (best is None or a > best[1]):
                best = (path, a, name)
        return best

    def load_defs(self, names):
        """Fill self.defs[name] = [(path, decl index, name)] for `names`."""
        todo = [n for n in dict.fromkeys(names) if n not in self.defs]
        for n in todo:
            self.defs[n] = []
        if not todo:
            return
        pat = lambda ns: rf"\b(?:{'|'.join(re.escape(n) for n in ns)})\b"
        for p, i, _ in self.grep(pat, todo):
            lines, spans, tests, _ = self.file(p)
            name = function_name(lines, i, p)
            if name in self.defs and any(a == i for a, _, _ in spans) and \
                    not any(a <= i <= b for a, b in tests):
                d = (p, i, name)
                if d not in self.defs[name]:
                    self.defs[name].append(d)

    def matches(self, d, qual):
        if not qual or qual in ANY_QUAL:
            return True
        path, i, _ = d
        stem = os.path.splitext(os.path.basename(path))[0]
        parent = os.path.basename(os.path.dirname(path))
        if qual == stem or (stem in ("mod", "lib", "index", "__init__") and qual == parent):
            return True
        if qual in {c.replace("-", "_") for c in path.split("/")[:-1]}:
            return True  # a crate or package directory (`tinicli::run_cli`)
        header = enclosing_header(self.lines(path), i) or ""
        return re.search(rf"\b{re.escape(qual)}\b", header) is not None

    def is_method(self, d):
        """Whether a definition sits in an `impl`, `trait`, `class`,
        `interface`, `extension` or `object` block."""
        header = enclosing_header(self.lines(d[0]), d[1]) or ""
        return re.match(r"(pub(\([^)]*\))?\s+)?(unsafe\s+)?(impl|trait|class|interface|extension|object)\b|"
                        r".*\b(class|interface|struct)\b", header) is not None

    def resolve(self, qual, name, kind, arity, from_path):
        """The definitions a call may reach (see the module doc): same
        language; a method call only methods (a Rust one only with as many
        parameters as arguments); a bare call free functions first; `Q::name`
        only definitions under Q, and none when Q is outside the repository."""
        defs = [d for d in self.defs.get(name, []) if lang(d[0]) == lang(from_path)]
        if kind != "plain":
            defs = [d for d in defs if self.is_method(d)]
            if arity is not None and lang(from_path) == "rs":
                defs = [d for d in defs if self.arity(d) in (None, arity)]
            return defs
        if qual is None:
            free = [d for d in defs if not self.is_method(d)]
            return free or defs
        hit = [d for d in defs if self.matches(d, qual)]
        if qual not in ANY_QUAL:
            return hit  # `Q::name` with no definition under Q names an outside item
        return hit or defs

    def arity(self, d):
        """Parameters of a definition, `self` left out, or None if unread."""
        lines = self.lines(d[0])
        text = " ".join(lines[d[1]:d[1] + 30])
        k = text.find("(", text.find(d[2]))
        args = top_level_args(text, k)
        if args is None:
            return None
        return len([a for a in args if not re.fullmatch(r"&?\s*('\w+\s+)?(mut\s+)?self(\s*:.*)?", a)])

    def body_calls(self, d):
        """[(qual, name, kind, arity, line index)] of the calls in a definition's own body."""
        path, i, name = d
        lines = self.lines(path)
        out = []
        for j in range(i + 1, block_end(lines, i) + 1):
            if self.enclosing(path, j) != d or lines[j].lstrip().startswith(COMMENT):
                continue  # a nested definition's line, an import, or a comment
            out.extend((q, n, k, a, j) for q, n, k, a in calls_in(lines[j]))
        return out


def cfg_above(repo, path, decl_i, call_i):
    """A `#[cfg(…)]` / `#if…` between the caller's declaration and the call
    line, at less indentation than the call: the call is conditional."""
    lines = repo.lines(path)
    ind = len(lines[call_i]) - len(lines[call_i].lstrip())
    for j in range(call_i - 1, decl_i, -1):
        l = lines[j]
        lj = len(l) - len(l.lstrip())
        if l.strip() and lj < ind:
            ind = lj
            if re.match(r"\s*#\[cfg\(|\s*#\s*if", l):
                return l.strip()
            k = j - 1
            while k > decl_i and re.match(r"\s*#\[", lines[k]):
                if re.match(r"\s*#\[cfg\(", lines[k]):
                    return lines[k].strip()
                k -= 1
    return None


def call_pattern(names):
    alt = "|".join(re.escape(n) for n in names)
    return rf"\b(?:{alt})\s*(?:::<[^>]*>)?\s*\(|::(?:{alt})\b|[(,]\s*(?:{alt})\s*[),]"


def expand_down(repo, frontier, parent, goal):
    """Callees of every definition in `frontier`; parent[callee] = (caller,
    call line index). A blind method call is followed only into `goal`."""
    calls = {d: repo.body_calls(d) for d in frontier}
    repo.load_defs([c[1] for cs in calls.values() for c in cs])
    nxt = []
    for d in frontier:
        for q, n, k, a, j in calls[d]:
            for c in repo.resolve(q, n, k, a, d[0]):
                if c == d or c in parent or (k == "blind" and c not in goal):
                    continue
                parent[c] = (d, j)
                nxt.append(c)
    return nxt


def expand_up(repo, frontier, parent, allow, goal):
    """Callers of every definition in `frontier`; parent[caller] = (callee,
    call line index). A blind method call counts only into `goal`."""
    names = list(dict.fromkeys(n for _, _, n in frontier))
    repo.load_defs(names)
    want = set(frontier)
    nxt = []
    for p, i, text in repo.grep(call_pattern, names):
        caller = repo.enclosing(p, i)
        if not caller or caller[1] == i or caller in parent or not allow(caller):
            continue
        for q, n, k, a in calls_in(text):
            if n not in repo.defs:
                continue
            hit = [c for c in repo.resolve(q, n, k, a, p)
                   if c in want and c != caller and (k != "blind" or c in goal)]
            if hit and caller not in parent:
                parent[caller] = (hit[0], i)
                nxt.append(caller)
    return nxt


def search(repo, tops, targets, max_depth):
    """Shortest chain from one of `tops` down to one of `targets` (lists of
    definitions). Returns [(definition, call line index or None)] or None."""
    down = {t: None for t in tops}
    up = {t: None for t in targets}
    dist_down = {t: 0 for t in tops}
    dist_up = {t: 0 for t in targets}
    f_down, f_up = list(tops), list(targets)
    top_set, goal = set(tops), set(targets)
    allow = lambda d: d[2] != tops[0][2] or d in top_set  # another binary's main never ends a chain
    meet = next((t for t in tops if t in up), None)
    for _ in range(max_depth):
        if meet or not f_down or not f_up:
            break
        if len(f_down) <= len(f_up):
            f_down = expand_down(repo, f_down, down, goal)
            for n in f_down:
                dist_down[n] = dist_down[down[n][0]] + 1
            side, new, other = "down", f_down, dist_up
        else:
            f_up = expand_up(repo, f_up, up, allow, goal)
            for n in f_up:
                dist_up[n] = dist_up[up[n][0]] + 1
            side, new, other = "up", f_up, dist_down
        print(f"  {side}: {len(new)} new definitions", file=sys.stderr)
        meets = [n for n in new if n in other]
        if meets:
            meet = min(meets, key=lambda n: dist_down[n] + dist_up[n])
    if not meet:
        return None
    chain, n = [], meet
    while down[n] is not None:
        caller, j = down[n]
        chain.append((caller, j))
        n = caller
    chain.reverse()
    n = meet
    while up[n] is not None:
        callee, j = up[n]
        chain.append((n, j))
        n = callee
    chain.append((n, None))
    return chain


def definitions_of(repo, spec):
    qual, name = split_name(spec)
    repo.load_defs([name])
    defs = [d for d in repo.defs[name] if repo.matches(d, qual)]
    if not defs:
        sys.exit(f"no definition of `{spec}` at {repo.rev}")
    return defs


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("repo")
    ap.add_argument("rev")
    ap.add_argument("function")
    ap.add_argument("--main", dest="main_path", required=True,
                    help="path (suffix) of the product binary's main")
    ap.add_argument("--via", action="append",
                    help="a waypoint, in order (repeatable): a `via` function, or a hint where a call "
                         "goes through a method on another receiver (trait dispatch)")
    ap.add_argument("--paths", nargs="*", help="limit the search to these directories")
    ap.add_argument("--max-depth", type=int, default=60)
    a = ap.parse_args()
    repo = Repo(a.repo, a.rev, a.paths)
    repo.load_defs(["main"])
    mains = [d for d in repo.defs["main"] if d[0].endswith(a.main_path)]
    if not mains:
        sys.exit(f"no `main` in {a.main_path} at {a.rev}")
    stops = [definitions_of(repo, w) for w in a.via or []] + [definitions_of(repo, a.function)]
    chain, tops = [], mains
    for spec, stop in zip((a.via or []) + [a.function], stops):
        part = search(repo, tops, stop, a.max_depth)
        if not part:
            sys.exit(f"no chain down to {spec} from {chain[-1][0][2] if chain else 'main'}")
        chain = chain[:-1] + part
        tops = [part[-1][0]]
    for (path, i, name), j in chain:
        if j is None:
            print(f"{name}  ({path}:{i + 1})")
            continue
        cfg = cfg_above(repo, path, i, j)
        flag = f"   [conditional: {cfg}]" if cfg else ""
        print(f"{name}  ({path}:{i + 1})  calls the next at line {j + 1}: {repo.lines(path)[j].strip()}{flag}")


if __name__ == "__main__":
    main()
