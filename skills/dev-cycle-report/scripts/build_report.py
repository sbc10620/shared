#!/usr/bin/env python3
"""Check a dev-cycle report spec against the repository, then build it.

usage: build_report.py <report.json> [<parent-dir>]     check, render, write
       build_report.py --check <report.json>             check only

<parent-dir> defaults to $DEV_CYCLE_REPORT_DIR, else ~/Documents/dev-cycle-reports.
The report directory name is derived: <YYYYMMDD of the head commit>-<repo name
from origin, else the checkout's directory name>-<topic>.

Output:
  <parent-dir>/<name>/
    index.html                  the report, figures inline, opens offline
    fig1-before.mmd/.svg        overall structure at base
    fig2-after.mmd/.svg         overall structure at head
    report.json                 the spec, to rebuild or extend later

Every check runs on every build; there is no option to skip one. Layout and
styling live only in this script, so every report looks the same.
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata

sys.dont_write_bytecode = True

# Appended to every flowchart, so every report marks changes the same way.
CLASS_DEFS = ("\n  classDef new fill:#d3f5d3,stroke:#2f8132"
              "\n  classDef changed fill:#fff1a8,stroke:#9a6700"
              "\n  classDef removed fill:#ffd7d5,stroke:#b42318,stroke-dasharray:4 3")
MERMAID_URL = "https://cdn.jsdelivr.net/npm/mermaid@12.2.0/dist/mermaid.esm.min.mjs"
CHROMES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/opt/pw-browsers/chromium",
    "google-chrome", "chromium", "chromium-browser",
]

TOP_KEYS = {"repo_dir", "base", "head", "topic", "title", "summary", "why",
            "structure", "groups", "records"}
TOP_REQUIRED = TOP_KEYS - {"records"}
WHY_KEYS = {"text", "source", "inferred_from"}
STRUCT_KEYS = {"before", "after", "changes"}
FIG_KEYS = {"mermaid", "identifiers", "caption"}
CHANGE_KEYS = {"kind", "text", "group"}
CHANGE_KINDS = {"new": "새로 생김", "changed": "바뀜", "moved": "옮겨짐", "removed": "없어짐"}
GROUP_KEYS = {"id", "title", "one_line", "why", "commits", "commit_notes",
              "flows", "points", "tests"}
GROUP_REQUIRED = {"id", "title", "one_line", "commits"}
FLOW_KEYS = {"title", "before", "after", "explain"}
SIDE_KEYS = {"code", "refs"}
REF_KEYS = {"path", "lines", "must_contain"}
TEST_KEYS = {"path", "must_contain", "text"}
NOTE_KEYS = {"replaced_by", "note"}
RECORD_KEYS = {"text", "applies_to", "source"}

CODE_COLUMNS = 80  # a pseudocode line wider than this scrolls inside its box
TOPIC_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
UNCHECKED_SOURCE_RE = re.compile(r"^(PR|issue|이슈)?\s*[\w./-]*#\d+$|^https?://", re.I)


class Problems:
    def __init__(self):
        self.errors, self.warnings = [], []

    def err(self, where, msg):
        self.errors.append(f"{where}: {msg}")

    def warn(self, where, msg):
        self.warnings.append(f"{where}: {msg}")


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.decode(errors='replace').strip()}")
    return r


def out(repo, *args):
    return git(repo, *args).stdout.decode(errors="replace")


def keys_ok(p, where, obj, allowed, required=()):
    if not isinstance(obj, dict):
        p.err(where, "must be an object")
        return False
    for k in obj:
        if k not in allowed:
            p.err(where, f"unknown key '{k}'")
    ok = True
    for k in required:
        if k not in obj or obj[k] in (None, "", []):
            p.err(where, f"missing or empty '{k}'")
            ok = False
    return ok


def str_list(p, where, v, min_len=0, max_len=None):
    if not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
        p.err(where, "must be a list of non-empty strings")
        return []
    if len(v) < min_len or (max_len and len(v) > max_len):
        p.err(where, f"needs {min_len}..{max_len or 'any'} items, has {len(v)}")
    return v


def resolve(repo, ref):
    r = git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)
    return r.stdout.decode().strip() if r.returncode == 0 else None


def file_at(repo, sha, path, cache={}):
    key = (repo, sha, path)
    if key not in cache:
        r = git(repo, "show", f"{sha}:{path}", check=False)
        cache[key] = r.stdout.decode(errors="replace").split("\n") if r.returncode == 0 else None
    return cache[key]


def token_re(tok):
    left = r"(?<![A-Za-z0-9_])" if re.match(r"\w", tok) else ""
    right = r"(?![A-Za-z0-9_])" if re.search(r"\w$", tok) else ""
    return re.compile(left + re.escape(tok) + right)


def parse_lines(spec):
    m = re.fullmatch(r"(\d+)(?:-(\d+))?", str(spec).strip())
    if not m:
        return None
    a = int(m.group(1))
    return a, int(m.group(2) or a)


def check_source(p, where, repo, head, src):
    """A source is a path to an existing file (optionally :line), a commit SHA,
    or a PR / issue number or URL (not checkable offline)."""
    if UNCHECKED_SOURCE_RE.search(src.strip()):
        return
    s = src.strip()
    if SHA_RE.match(s):
        if not resolve(repo, s):
            p.err(where, f"source SHA '{s}' does not resolve in {repo}")
        return
    path = os.path.expanduser(re.sub(r":\d+(-\d+)?$", "", s))
    if not os.path.isabs(path) and file_at(repo, head, path) is not None:
        return  # a path in the repository, as head has it
    if not os.path.exists(path if os.path.isabs(path) else os.path.join(repo, path)):
        p.err(where, f"source '{s}' is not an existing file, a commit SHA, a PR/issue number or a URL")


def check(spec, p):
    """Validate the spec; return the facts the page needs (stats, commits, files)."""
    if not keys_ok(p, "report", spec, TOP_KEYS, TOP_REQUIRED):
        return None
    repo = os.path.expanduser(spec.get("repo_dir", ""))
    if not os.path.isdir(repo) or git(repo, "rev-parse", "--git-dir", check=False).returncode != 0:
        p.err("repo_dir", f"'{repo}' is not a git checkout")
        return None
    base, head = resolve(repo, spec.get("base", "")), resolve(repo, spec.get("head", ""))
    if not base:
        p.err("base", f"'{spec.get('base')}' is not a commit")
    if not head:
        p.err("head", f"'{spec.get('head')}' is not a commit")
    if not (base and head):
        return None
    if git(repo, "merge-base", "--is-ancestor", base, head, check=False).returncode != 0:
        p.err("base", "base is not an ancestor of head (use the merge-base for a PR or branch)")
        return None
    if not TOPIC_RE.match(spec.get("topic", "")):
        p.err("topic", "must be kebab-case: lowercase letters, digits and '-'")
    str_list(p, "summary", spec.get("summary", []), 3, 5)

    for i, w in enumerate(spec.get("why", [])):
        where = f"why[{i}]"
        if not keys_ok(p, where, w, WHY_KEYS, {"text"}):
            continue
        if bool(w.get("source")) == bool(w.get("inferred_from")):
            p.err(where, "needs exactly one of 'source' or 'inferred_from' (code location for an inference)")
        if w.get("source"):
            check_source(p, where, repo, head, w["source"])
        if w.get("inferred_from"):
            path = re.sub(r":\d+(-\d+)?$", "", w["inferred_from"])
            if file_at(repo, head, path) is None:
                p.err(where, f"inferred_from '{path}' does not exist at head")
    if not spec.get("why"):
        p.err("why", "is empty")

    commits = out(repo, "rev-list", "--no-merges", "--reverse", f"{base}..{head}").split()
    merges = out(repo, "rev-list", "--merges", "--reverse", f"{base}..{head}").split()
    order = {c: i for i, c in enumerate(commits)}

    def full(sha, where):
        f = resolve(repo, sha) if isinstance(sha, str) and SHA_RE.match(sha) else None
        if not f:
            p.err(where, f"'{sha}' is not a commit SHA")
        elif f not in order:
            p.err(where, f"'{sha}' is not a non-merge commit in base..head")
            return None
        return f

    surviving = blame_counts(repo, base, head, commits)
    owner, group_ids = {}, set()
    groups = spec.get("groups", [])
    if not isinstance(groups, list) or not groups:
        p.err("groups", "needs at least one group")
        groups = []
    for gi, g in enumerate(groups):
        gw = f"groups[{gi}]"
        if not keys_ok(p, gw, g, GROUP_KEYS, GROUP_REQUIRED):
            continue
        if not TOPIC_RE.match(g.get("id", "")):
            p.err(f"{gw}.id", "must be kebab-case")
        if g.get("id") in group_ids:
            p.err(f"{gw}.id", f"duplicate id '{g['id']}'")
        group_ids.add(g.get("id"))
        str_list(p, f"{gw}.why", g.get("why", []))
        str_list(p, f"{gw}.points", g.get("points", []))
        g["_commits"] = []
        for c in g.get("commits", []):
            f = full(c, f"{gw}.commits")
            if not f:
                continue
            if f in owner:
                p.err(f"{gw}.commits", f"{c} is already in group '{owner[f]}'")
            owner[f] = g.get("id")
            g["_commits"].append(f)
        notes = g.get("commit_notes", {})
        g["_notes"] = {}
        for c, n in notes.items():
            nw = f"{gw}.commit_notes[{c}]"
            f = full(c, nw)
            if not f or not keys_ok(p, nw, n, NOTE_KEYS):
                continue
            if f not in g["_commits"]:
                p.err(nw, "the commit is not in this group")
            if bool(n.get("replaced_by")) == bool(n.get("note")):
                p.err(nw, "needs exactly one of 'replaced_by' or 'note'")
            if n.get("replaced_by"):
                r = full(n["replaced_by"], f"{nw}.replaced_by")
                if r and order[r] <= order[f]:
                    p.err(nw, "replaced_by must be a later commit")
                n = {"replaced_by": r} if r else n
            g["_notes"][f] = n
        for fi, fl in enumerate(g.get("flows") or []):
            check_flow(p, f"{gw}.flows[{fi}]", repo, base, head, fl)
        for ti, t in enumerate(g.get("tests", [])):
            tw = f"{gw}.tests[{ti}]"
            if keys_ok(p, tw, t, TEST_KEYS, TEST_KEYS):
                lines = file_at(repo, head, t["path"])
                if lines is None:
                    p.err(tw, f"'{t['path']}' does not exist at head")
                    continue
                for tok in str_list(p, f"{tw}.must_contain", t["must_contain"], 1):
                    if not any(token_re(tok).search(l) for l in lines):
                        p.err(tw, f"'{tok}' is not in {t['path']} at head")
        g["_files"] = sorted({f for c in g["_commits"] for f in changed_files(repo, c)})

    for c in commits:
        if c not in owner:
            p.err("groups", f"commit {c[:10]} ({subject(repo, c)}) is in no group")
        elif surviving.get(c, 0) == 0:
            g = next(g for g in groups if c in g.get("_commits", []))
            if c not in g.get("_notes", {}):
                p.err(f"group '{owner[c]}'", f"commit {c[:10]} has no line left at head; "
                      "add commit_notes with replaced_by (a later commit) or note (e.g. deletions only)")

    # Where figure identifiers are looked up: the first two path components
    # of every file the range changes.
    changed = out(repo, "diff", "--no-renames", "-z", "--name-only", base, head).split("\0")
    dirs = {"/".join(os.path.dirname(f).split("/")[:2]) for f in changed if f}
    scope = [] if "" in dirs else sorted(dirs)  # a changed root file: the whole tree
    st = spec.get("structure", {})
    if keys_ok(p, "structure", st, STRUCT_KEYS, STRUCT_KEYS):
        for side, sha in (("before", base), ("after", head)):
            fw = f"structure.{side}"
            fig = st.get(side)
            if not keys_ok(p, fw, fig, FIG_KEYS, {"mermaid", "identifiers"}):
                continue
            if re.search(r"^\s*(classDef|style)\b", fig["mermaid"], re.M):
                p.err(fw, "do not style nodes; use `class <ids> new|changed|removed` "
                      "(the script defines those three)")
            toks = str_list(p, f"{fw}.identifiers", fig.get("identifiers", []), 1)
            found = grep_words(repo, sha, toks, scope)
            if scope and len(found) < len(toks):  # not near the change: the whole tree
                found |= grep_words(repo, sha, [t for t in toks if t not in found], [])
            for tok in toks:
                if tok not in fig.get("mermaid", ""):
                    p.err(fw, f"identifier '{tok}' is not in the Mermaid text")
                if tok not in found:
                    p.err(fw, f"identifier '{tok}' is not found at {'base' if side == 'before' else 'head'} ({sha[:10]})")
        for ci, ch in enumerate(st.get("changes", [])):
            cw = f"structure.changes[{ci}]"
            if keys_ok(p, cw, ch, CHANGE_KEYS, CHANGE_KEYS):
                if ch["kind"] not in CHANGE_KINDS:
                    p.err(cw, f"kind must be one of {sorted(CHANGE_KINDS)}")
                if ch["group"] not in group_ids:
                    p.err(cw, f"group '{ch['group']}' is not a group id")

    for ri, r in enumerate(spec.get("records", [])):
        rw = f"records[{ri}]"
        if keys_ok(p, rw, r, RECORD_KEYS, RECORD_KEYS):
            if not resolve(repo, r["applies_to"]):
                p.err(rw, f"applies_to '{r['applies_to']}' is not a commit")
            check_source(p, rw, repo, head, r["source"])

    stat = out(repo, "diff", "--shortstat", "--no-renames", base, head).strip()
    nums = [int(x) for x in re.findall(r"(\d+) (?:file|insertion|deletion)", stat)]
    return {"repo": repo, "base": base, "head": head, "commits": commits, "merges": merges,
            "surviving": surviving, "owner": owner, "stat": stat, "nums": nums}


def check_flow(p, where, repo, base, head, fl):
    if not keys_ok(p, where, fl, FLOW_KEYS, {"title", "after", "explain"}):
        return
    str_list(p, f"{where}.explain", fl.get("explain", []), 1)
    for side, sha in (("before", base), ("after", head)):
        at = "base" if side == "before" else "head"
        s = fl.get(side)
        if s is None:
            continue
        sw = f"{where}.{side}"
        if not keys_ok(p, sw, s, SIDE_KEYS, SIDE_KEYS):
            continue
        for n, line in enumerate(s["code"].split("\n"), 1):
            if columns(line) > CODE_COLUMNS:
                p.warn(sw, f"code line {n} is {columns(line)} columns wide (over {CODE_COLUMNS}); "
                       "shorten it or move the comment to its own line")
        for ri, r in enumerate(s["refs"]):
            rw = f"{sw}.refs[{ri}]"
            if not keys_ok(p, rw, r, REF_KEYS, {"path", "must_contain"}):
                continue
            lines = file_at(repo, sha, r["path"])
            if lines is None:
                p.err(rw, f"'{r['path']}' does not exist at {at} ({sha[:10]})")
                continue
            rng = parse_lines(r["lines"]) if r.get("lines") else None
            if r.get("lines") and not rng:
                p.err(rw, "lines must look like '120' or '120-160'")
            for tok in str_list(p, f"{rw}.must_contain", r["must_contain"], 1):
                rx = token_re(tok)
                if not rx.search(s["code"]):
                    p.err(rw, f"'{tok}' is not in the pseudocode above it")
                hits = [i + 1 for i, l in enumerate(lines) if rx.search(l)]
                if not hits:
                    p.err(rw, f"'{tok}' is not in {r['path']} at {at} ({sha[:10]})")
                elif rng and not any(rng[0] <= h <= rng[1] for h in hits):
                    p.warn(rw, f"'{tok}' is outside lines {r['lines']}; found at {hits[:8]}")


def columns(line):
    """Display width: East Asian wide and full-width characters take two."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in line)


def grep_words(repo, sha, toks, scope):
    """The subset of `toks` that occurs at `sha` in the directories `scope`
    (all of the tree when empty), as a whole word when the token starts and
    ends with a word character. A whole large tree costs about a second per
    token, so the caller looks near the change first."""
    found = set()
    for t in toks:
        args = ["grep", "-q", "-I", "-F", "-e", t, sha, "--", *scope]
        if re.match(r"\w", t) and re.search(r"\w$", t):
            args.insert(1, "-w")
        if git(repo, *args, check=False).returncode == 0:
            found.add(t)
    return found


def changed_files(repo, c):
    raw = out(repo, "diff-tree", "-r", "--no-commit-id", "--no-renames", "-z", "--name-only", "--root", c)
    return [f for f in raw.split("\0") if f]


def subject(repo, c):
    return out(repo, "show", "-s", "--format=%s", c).strip()


def blame_counts(repo, base, head, commits):
    """Lines each commit of base..head still owns at head (git blame, boundary = base)."""
    counts = {}
    raw = out(repo, "diff", "--no-renames", "-z", "--name-only", "--diff-filter=AM", base, head)
    for path in (f for f in raw.split("\0") if f):
        r = git(repo, "blame", "--porcelain", f"{base}..{head}", "--", path, check=False)
        if r.returncode != 0:
            continue
        for line in r.stdout.decode(errors="replace").split("\n"):
            m = re.match(r"^([0-9a-f]{40}) \d+ \d+ (\d+)$", line)
            if m:
                counts[m.group(1)] = counts.get(m.group(1), 0) + int(m.group(2))
    return counts


# ---------------------------------------------------------------- rendering

def find_chrome():
    for c in CHROMES:
        if os.path.isabs(c) and os.path.exists(c):
            return c
        if not os.path.isabs(c) and shutil.which(c):
            return shutil.which(c)
    return None


def render_mermaid(sources):
    chrome = find_chrome()
    if not chrome:
        raise RuntimeError("no Chrome/Chromium found; the figures are rendered with headless Chrome")
    page = f"""<!doctype html><html><head><meta charset="utf-8"></head><body>
<script id="src" type="application/json">{json.dumps(sources).replace("</", "<\\/")}</script>
<div id="out"></div>
<script type="module">
const out = document.getElementById('out');
try {{
  const mermaid = (await import('{MERMAID_URL}')).default;
  mermaid.initialize({{startOnLoad:false, theme:'default', securityLevel:'strict',
    themeVariables:{{clusterBkg:'#f6f8fa', clusterBorder:'#d0d7de'}},
    flowchart:{{htmlLabels:false}}, fontFamily:'-apple-system, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif'}});
  const srcs = JSON.parse(document.getElementById('src').textContent);
  for (let i = 0; i < srcs.length; i++) {{
    const pre = document.createElement('pre'); pre.id = 'fig' + i;
    try {{ const r = await mermaid.render('fig' + i + 'svg', srcs[i]); pre.dataset.ok = '1'; pre.textContent = r.svg; }}
    catch (e) {{ pre.dataset.ok = '0'; pre.textContent = String((e && e.message) || e); }}
    out.appendChild(pre);
  }}
}} catch (e) {{ out.dataset.fatal = String(e); }}
out.dataset.done = '1';
</script></body></html>"""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "render.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(page)
        r = subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
                            "--virtual-time-budget=30000", "--dump-dom", "file://" + path],
                           capture_output=True, timeout=120)
    dom = r.stdout.decode(errors="replace")
    if 'data-done="1"' not in dom:
        raise RuntimeError("Mermaid did not finish rendering (is the network reachable?)")
    fatal = re.search(r'data-fatal="([^"]*)"', dom)
    if fatal:
        raise RuntimeError(f"could not load Mermaid from {MERMAID_URL}: {html.unescape(fatal.group(1))}")
    svgs = []
    for i in range(len(sources)):
        m = re.search(rf'<pre id="fig{i}" data-ok="([01])">(.*?)</pre>', dom, re.S)
        if not m:
            raise RuntimeError(f"figure {i + 1}: no render output")
        text = html.unescape(m.group(2))
        if m.group(1) != "1":
            raise RuntimeError(f"figure {i + 1}: Mermaid error: {text}")
        svgs.append(text)
    return svgs


def inline(text):
    """Escape, then allow `code` and **bold** only."""
    t = html.escape(text)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    return re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)


def code_block(side_label, s, sha):
    if s is None:
        return (f'<div class="code"><div class="code-h">{side_label}</div>'
                '<div class="code-empty">이 범위 전에는 없었습니다.</div></div>')
    rows = []
    for line in s["code"].rstrip("\n").split("\n"):
        cls = "add" if line.startswith("+") else "del" if line.startswith("-") else ""
        m = re.match(r"^(.*?)(\s*//.*)$", line)
        body = (html.escape(m.group(1)) + f'<span class="cm">{html.escape(m.group(2))}</span>'
                if m else html.escape(line))
        rows.append(f'<span class="ln {cls}">{body or " "}</span>')
    refs = " · ".join(
        f"<code>{html.escape(r['path'])}{':' + html.escape(str(r['lines'])) if r.get('lines') else ''}</code>"
        for r in s["refs"])
    return (f'<div class="code"><div class="code-h">{side_label} <span class="muted">@ {sha[:10]}</span></div>'
            f'<pre>{"".join(rows)}</pre><div class="refs">실제 코드: {refs}</div></div>')


def page(spec, facts, svgs, name):
    repo, base, head = facts["repo"], facts["base"], facts["head"]
    groups = spec["groups"]
    gtitle = {g["id"]: g["title"] for g in groups}
    nfiles, nadd, ndel = (facts["nums"] + [0, 0, 0])[:3]
    toc = ['<a href="#overview">한눈에 보기</a>', '<a href="#why">왜 바꿨나</a>',
           '<a href="#structure">전체 구조: 전 → 후</a>', '<span class="toc-h">주제별 상세</span>']
    toc += [f'<a class="sub" href="#g-{g["id"]}">{inline(g["title"])}</a>' for g in groups]
    toc += ['<a href="#appendix">부록</a>']

    cards = "".join(
        f'<a class="card" href="#g-{g["id"]}"><b>{inline(g["title"])}</b><span>{inline(g["one_line"])}</span>'
        f'<span class="muted">커밋 {len(g["_commits"])}개</span></a>' for g in groups)
    why = "".join(
        f'<li>{inline(w["text"])} <span class="src">— {"출처: " + inline(w["source"]) if w.get("source") else "추정, 근거: <code>" + html.escape(w["inferred_from"]) + "</code>"}</span></li>'
        for w in spec["why"])
    st = spec["structure"]
    figs = ""
    for label, key, svg, n in (("전", "before", svgs[0], 1), ("후", "after", svgs[1], 2)):
        cap = inline(st[key].get("caption", ""))
        sha = base if key == "before" else head
        figs += (f'<figure><div class="fig-h">{label} <span class="muted">@ {sha[:10]}</span></div>'
                 f'<div class="svg">{svg}</div><figcaption>{cap} <a href="fig{n}-{key}.svg" target="_blank">크게 보기</a> <span class="muted">(fig{n}-{key}.mmd · .svg)</span></figcaption></figure>')
    changes = "".join(
        f'<li><span class="kind k-{c["kind"]}">{CHANGE_KINDS[c["kind"]]}</span> {inline(c["text"])} '
        f'<a class="muted" href="#g-{c["group"]}">→ {inline(gtitle[c["group"]])}</a></li>' for c in st.get("changes", []))

    gsec = ""
    for g in groups:
        flows = ""
        for fl in g.get("flows", []):
            flows += (f'<details class="flow" open><summary>{inline(fl["title"])}</summary>'
                      f'<div class="pair">{code_block("전", fl.get("before"), base)}{code_block("후", fl["after"], head)}</div>'
                      f'<ul>{"".join("<li>" + inline(e) + "</li>" for e in fl["explain"])}</ul></details>')
        points = "".join(f"<li>{inline(x)}</li>" for x in g.get("points", []))
        tests = "".join(f'<li><code>{html.escape(t["path"])}</code> — {inline(t["text"])}</li>' for t in g.get("tests", []))
        clist = ""
        for c in g["_commits"]:
            n = g["_notes"].get(c, {})
            tag = (f' <span class="tag">{html.escape(n["replaced_by"][:10])} 가 대체함</span>' if n.get("replaced_by")
                   else f' <span class="tag">{inline(n["note"])}</span>' if n.get("note") else "")
            clist += f"<li><code>{c[:10]}</code> {html.escape(subject(repo, c))}{tag}</li>"
        files = "".join(f"<li><code>{html.escape(f)}</code></li>" for f in g["_files"])
        gsec += f"""<section id="g-{g['id']}" class="group"><h3>{inline(g['title'])}</h3>
<p class="lead">{inline(g['one_line'])}</p>
{'<h4>왜 바꿨나</h4><ul>' + ''.join('<li>' + inline(w) + '</li>' for w in g.get('why', [])) + '</ul>' if g.get('why') else ''}
{'<h4>동작 흐름: 전 → 후</h4>' + flows if flows else ''}
{'<h4>핵심 포인트</h4><ul>' + points + '</ul>' if points else ''}
{'<h4>이를 보장하는 테스트</h4><ul>' + tests + '</ul>' if tests else ''}
<details><summary>커밋 {len(g['_commits'])}개 · 바뀐 파일 {len(g['_files'])}개</summary>
<ul>{clist}</ul><ul class="files">{files}</ul></details></section>"""

    records = spec.get("records") or []
    rec = ("<ul>" + "".join(
        f'<li>{inline(r["text"])} <span class="src">— 대상 <code>{html.escape(r["applies_to"][:10])}</code>'
        f'{"" if resolve(repo, r["applies_to"]) == head else " <span class=tag>head 아님</span>"}, 출처: {inline(r["source"])}</span></li>'
        for r in records) + "</ul>") if records else "<p>기록 없음.</p>"
    rows = ""
    for c in facts["commits"]:
        rows += (f"<tr><td><code>{c[:10]}</code></td><td>{html.escape(subject(repo, c))}</td>"
                 f"<td>{inline(gtitle.get(facts['owner'].get(c), ''))}</td><td class='num'>{facts['surviving'].get(c, 0)}</td></tr>")
    merges = ("<p>병합 커밋(설명 대상 아님): " + ", ".join(f"<code>{m[:10]}</code>" for m in facts["merges"]) + "</p>"
              if facts["merges"] else "")

    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(spec['title'])}</title>
<style>
:root {{ --bg:#ffffff; --fg:#1f2328; --muted:#59636e; --line:#d1d9e0; --panel:#f6f8fa; --accent:#0969da;
  --add:#dafbe1; --del:#ffebe9; --cm:#6e7781; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0d1117; --fg:#e6edf3; --muted:#9198a1; --line:#3d444d;
  --panel:#161b22; --accent:#4493f8; --add:#12361f; --del:#3c1618; --cm:#8b949e; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.65 -apple-system, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif; }}
nav {{ position:fixed; top:0; left:0; bottom:0; width:240px; overflow:auto; padding:24px 16px; border-right:1px solid var(--line); font-size:14px; }}
nav a, nav .toc-h {{ display:block; padding:3px 0; color:var(--fg); text-decoration:none; }}
nav a.sub {{ padding-left:12px; color:var(--muted); }} nav a:hover {{ color:var(--accent); }}
nav .toc-h {{ color:var(--muted); margin-top:6px; }}
main {{ margin-left:240px; padding:24px 32px 80px; max-width:1400px; }}
@media (max-width:900px) {{ nav {{ position:static; width:auto; border-right:0; border-bottom:1px solid var(--line); }} main {{ margin-left:0; padding:16px; }} }}
h1 {{ font-size:24px; margin:0 0 4px; }}
h2 {{ font-size:20px; margin:40px 0 10px; border-top:1px solid var(--line); padding-top:24px; }}
h3 {{ font-size:18px; margin:28px 0 4px; }} h4 {{ font-size:15px; margin:18px 0 4px; }}
.muted, .src {{ color:var(--muted); font-size:13px; }}
code {{ font:13px ui-monospace, SFMono-Regular, Menlo, monospace; background:var(--panel); padding:1px 4px; border-radius:4px; }}
.stats {{ display:flex; flex-wrap:wrap; gap:8px 20px; color:var(--muted); font-size:14px; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(260px, 1fr)); gap:12px; margin-top:12px; }}
.card {{ display:flex; flex-direction:column; gap:4px; padding:12px 14px; border:1px solid var(--line); border-radius:8px; background:var(--panel); color:var(--fg); text-decoration:none; }}
.card:hover {{ border-color:var(--accent); }}
.figs {{ display:grid; grid-template-columns:1fr; gap:20px; }}
figure {{ margin:0; }} .fig-h, .code-h {{ font-weight:600; margin-bottom:4px; }}
.svg {{ background:#fff; border:1px solid var(--line); border-radius:6px; padding:8px; overflow:auto; }}
.svg svg {{ display:block; margin:0 auto; max-width:100%; max-height:90vh; height:auto; }}
figcaption {{ color:var(--muted); font-size:13px; margin-top:4px; }}
.kind {{ display:inline-block; font-size:12px; padding:0 6px; border-radius:10px; border:1px solid var(--line); margin-right:4px; }}
.k-new {{ background:var(--add); }} .k-removed {{ background:var(--del); }}
.group {{ border-top:1px dashed var(--line); margin-top:24px; }} .lead {{ font-size:16px; margin:2px 0 8px; }}
details > summary {{ cursor:pointer; color:var(--accent); margin:6px 0; }}
.flow {{ margin:8px 0 16px; }}
.pair {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }} .pair > * {{ min-width:0; }}
@media (max-width:1100px) {{ .pair {{ grid-template-columns:1fr; }} }}
.code pre {{ margin:0; padding:10px 0; background:var(--panel); border:1px solid var(--line); border-radius:6px; overflow:auto;
  font:13px/1.55 ui-monospace, SFMono-Regular, Menlo, monospace; }}
.ln {{ display:block; padding:0 12px; white-space:pre; }} .ln.add {{ background:var(--add); }} .ln.del {{ background:var(--del); }}
.cm {{ color:var(--cm); font-style:italic; }}
.code-empty {{ padding:12px; border:1px dashed var(--line); border-radius:6px; color:var(--muted); }}
.refs {{ color:var(--muted); font-size:12px; margin-top:4px; }}
.tag {{ font-size:12px; color:var(--muted); border:1px solid var(--line); border-radius:10px; padding:0 6px; }}
ul.files {{ columns:2; font-size:13px; }}
table {{ border-collapse:collapse; font-size:14px; }} td, th {{ border:1px solid var(--line); padding:4px 8px; text-align:left; }}
td.num {{ text-align:right; }}
</style></head><body>
<nav>{''.join(toc)}</nav>
<main>
<h1>{inline(spec['title'])}</h1>
<p class="muted">{html.escape(name)} · <code>{base[:10]}..{head[:10]}</code> · 이 보고서는 dev-cycle-report 스킬로 만들었습니다.</p>

<h2 id="overview">한눈에 보기</h2>
<ul>{''.join('<li>' + inline(s) + '</li>' for s in spec['summary'])}</ul>
<div class="stats"><span>커밋 {len(facts['commits'])}개</span><span>파일 {nfiles}개</span><span>+{nadd} / −{ndel} 줄</span><span>주제 {len(groups)}개</span></div>
<div class="cards">{cards}</div>

<h2 id="why">왜 바꿨나</h2>
<ul>{why}</ul>

<h2 id="structure">전체 구조: 전 → 후</h2>
<div class="figs">{figs}</div>
<h4>무엇이 달라졌나</h4><ul>{changes}</ul>

<h2 id="groups">주제별 상세</h2>
<p class="muted">유사 코드에서 <span class="ln add" style="display:inline;padding:0 4px">+</span> 줄은 새로 생긴 줄이고, <span class="ln del" style="display:inline;padding:0 4px">-</span> 줄은 없어진 줄입니다. 설명은 범위 전체를 적용한 뒤의 최종 상태 기준입니다.</p>
{gsec}

<h2 id="appendix">부록</h2>
<h4>진행 기록</h4>{rec}
<h4>전체 커밋</h4>
<table><tr><th>커밋</th><th>제목</th><th>주제</th><th>head 에 남은 줄</th></tr>{rows}</table>
{merges}
<h4>더 깊이 보기</h4>
<ul><li>파일별 실제 전후 코드: <code>commit-explain</code> 스킬에 <code>{base[:10]}..{head[:10]}</code> 를 주면 됩니다.</li>
<li>main 에서 시작하는 호출 흐름 그림: <code>commit-flow-diagram</code> 스킬에 같은 범위를 주면 됩니다.</li></ul>
</main></body></html>
"""


def main(argv):
    only_check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    if any(a.startswith("-") for a in args) or not 1 <= len(args) <= (1 if only_check else 2):
        print(__doc__, file=sys.stderr)
        return 2
    with open(args[0], encoding="utf-8") as f:
        spec = json.load(f)
    original = json.loads(json.dumps(spec))  # check() annotates groups in place
    p = Problems()
    facts = check(spec, p)
    for w in p.warnings:
        print("warning:", w, file=sys.stderr)
    for e in p.errors:
        print("error:", e, file=sys.stderr)
    if p.errors or facts is None:
        print(f"{len(p.errors)} problem(s); nothing built", file=sys.stderr)
        return 1
    if only_check:
        print(f"ok: {len(facts['commits'])} commits in {len(spec['groups'])} groups, {len(p.warnings)} warning(s)")
        return 0
    st = spec["structure"]
    try:
        svgs = render_mermaid([st[k]["mermaid"].rstrip() + CLASS_DEFS for k in ("before", "after")])
    except Exception as e:  # noqa: BLE001 - report any render failure as one line
        print("error:", e, file=sys.stderr)
        return 1
    parent = os.path.expanduser(args[1] if len(args) > 1 else
                                os.environ.get("DEV_CYCLE_REPORT_DIR", "~/Documents/dev-cycle-reports"))
    repo = facts["repo"]
    day = out(repo, "show", "-s", "--format=%cd", "--date=format:%Y%m%d", facts["head"]).strip()
    url = git(repo, "remote", "get-url", "origin", check=False).stdout.decode().strip()
    name = (re.sub(r"\.git$", "", url.rstrip("/").split("/")[-1].split(":")[-1]) if url
            else os.path.basename(os.path.abspath(repo)))
    dest = os.path.join(parent, f"{day}-{name}-{spec['topic']}")
    os.makedirs(dest, exist_ok=True)
    for n, key, svg in ((1, "before", svgs[0]), (2, "after", svgs[1])):
        with open(os.path.join(dest, f"fig{n}-{key}.mmd"), "w", encoding="utf-8") as f:
            f.write(st[key]["mermaid"].rstrip() + CLASS_DEFS + "\n")
        with open(os.path.join(dest, f"fig{n}-{key}.svg"), "w", encoding="utf-8") as f:
            f.write(svg)
    with open(os.path.join(dest, "index.html"), "w", encoding="utf-8") as f:
        f.write(page(spec, facts, svgs, name))
    with open(os.path.join(dest, "report.json"), "w", encoding="utf-8") as f:
        json.dump(original, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(dest)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
