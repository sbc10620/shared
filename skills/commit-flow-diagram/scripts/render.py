#!/usr/bin/env python3
"""Render one figure of a commit-flow spec into a standalone SVG.

usage: render.py <group.json> <figure-index> <out.svg>

The figure schema is documented in ../SKILL.md ("Spec format"). Standard
library only. The visual format is fixed on purpose: every figure this
skill produces must look the same, so change styling here, never per figure.
"""
import json
import re
import sys
from xml.sax.saxutils import escape

CODE_FONT = "'JetBrains Mono', Menlo, 'SF Mono', Consolas, 'D2Coding', 'Apple SD Gothic Neo', 'Noto Sans KR', monospace"
TEXT_FONT = "'IBM Plex Sans KR', 'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', -apple-system, sans-serif"
FS = 12          # code font size
LH = 17          # line height
PAD = 12         # inner padding
HEAD_H = 40      # header height (kind + name, file)
GUTTER = 14      # left column for the "+" marker
COL_GAP = 110
ROW_GAP = 26
MARGIN = 30

# Dark-gray theme, fixed for every figure (easy on the eyes, prints the
# same on any viewer). CANVAS is the picture ground, BOX the box face.
CANVAS = "#2a2c30"
BOX = "#35383e"
STATUS = {
    "new": {"stroke": "#3fb950", "head": "#21382a", "badge": "신규"},
    "changed": {"stroke": "#f0883e", "head": "#47301f", "badge": "변경"},
    "same": {"stroke": "#8b949e", "head": "#40444b", "badge": "기존"},
}
KIND_DASH = {"fn": "", "trait": "", "struct": "7 4", "enum": "7 4", "static": "2 3"}
DATA_KINDS = {"struct", "enum", "static", "trait"}

# --- syntax highlighting -------------------------------------------------
# One palette for every language; the token rules are deliberately small
# (C-family shape: Rust, C/C++, Java, Kotlin, Go, TS/JS, Swift).
HL = {
    "kw": "#ff7b72", "str": "#a5d6ff", "num": "#79c0ff", "type": "#ffa657",
    "fn": "#d2a8ff", "macro": "#79c0ff", "com": "#8b949e", "attr": "#8b949e",
    "life": "#ffa657", "plain": "#e6edf3",
}
KEYWORDS = set("""
as async await break const continue crate dyn else enum extern false fn for if impl in let loop match mod
move mut pub ref return self Self static struct super trait true type unsafe use where while yield
class def func function interface package import public private protected var val final override new
null nil void int long bool boolean char float double string throw throws try catch finally switch case
default do goto sizeof typedef typeof instanceof this when object lateinit suspend guard
""".split())
TOKEN_RE = re.compile(r"""
  (?P<com>//.*$)
| (?P<attr>\#!?\[[^\]]*\]?)
| (?P<str>b?r\#*"(?:[^"\\]|\\.)*"\#*|b?"(?:[^"\\]|\\.)*"?|'(?:[^'\\]|\\.)')
| (?P<life>'[A-Za-z_]\w*)
| (?P<num>\b\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?[A-Za-z0-9_]*\b)
| (?P<ident>[A-Za-z_]\w*)
| (?P<other>\s+|.)
""", re.VERBOSE)


def tokens(code):
    """Yield (class, text) for a code line."""
    out = []
    for m in TOKEN_RE.finditer(code):
        kind = m.lastgroup
        text = m.group(kind)
        if kind == "ident":
            rest = code[m.end():]
            if text in KEYWORDS:
                kind = "kw"
            elif rest.startswith("!") and not rest.startswith("!="):
                kind = "macro"
            elif rest.lstrip().startswith("(") or rest.startswith("::<"):
                kind = "fn"
            elif text[0].isupper():
                kind = "type"
            else:
                kind = "plain"
        elif kind == "other":
            kind = "plain"
        out.append((kind, text))
    return out


PARAMS_MAX = 48  # longer parameter lists keep only what the box's code uses


def signature_params(lines, start):
    """The parameter list of the declaration at lines[start], verbatim
    pieces joined with ", " — read across lines up to the closing paren."""
    text = "\n".join(lines[start:start + 40])
    m = DECL_NAME_RE.search(text)
    if not m:
        return None
    i = text.find("(", m.end())
    if i < 0 or "{" in text[m.end():i] or ";" in text[m.end():i]:
        return None
    depth, buf, parts = 0, "", []
    for j in range(i + 1, len(text)):
        ch = text[j]
        prev = text[j - 1]
        if ch in "([{" or (ch == "<"):
            depth += 1
        elif ch in ")]}" or (ch == ">" and prev != "-"):
            if depth == 0 and ch == ")":
                parts.append(buf)
                break
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(buf)
            buf = ""
            continue
        buf += ch
    parts = [" ".join(p.split()) for p in parts if p.strip()]
    return parts


def param_name(part):
    """`mut x: T` -> x, `&self` -> self, `T x` -> x, `x int` -> x."""
    head = part.split("=")[0]
    if ":" in head and "::" not in head.split(":")[0]:
        head = head.split(":")[0]
        toks = re.findall(r"[A-Za-z_]\w*", head)
        return toks[-1] if toks else head.strip()
    toks = re.findall(r"[A-Za-z_]\w*", head)
    if not toks:
        return head.strip()
    # Go puts the name first (`x int`), C-like languages last (`int x`).
    return toks[0] if len(toks) == 2 and toks[1][0].islower() and toks[1] in GO_TYPES else toks[-1]


GO_TYPES = {"int", "string", "bool", "error", "byte", "rune", "float64", "int64", "uint", "any"}
DECL_NAME_RE = re.compile(r"\b(?:fn|def|func|fun|function)\s+(?:\([^)]*\)\s*)?(?:<[^>]*>\s*)?(?:[\w.]+\.)?[A-Za-z_]\w*"
                          r"(?:<[^(]*?>)?")


def header_params(parts, used_code):
    """The parameters to show, one per header line: all of them when the
    list is short; otherwise only those the box's code uses (and `self`),
    with `…` standing for each run of the rest."""
    if parts is None:
        return None
    if len(", ".join(parts)) <= PARAMS_MAX:
        return parts
    keep, out = set(), []
    for p in parts:
        name = param_name(p)
        if name in ("self", "this") or re.search(rf"\b{re.escape(name)}\b", used_code):
            keep.add(p)
    skipped = False
    for p in parts:
        if p in keep:
            out.append(p)
            skipped = False
        elif not skipped:
            out.append("…")
            skipped = True
    return out


def text_width(s, size=FS):
    return sum(size * (1.02 if ord(ch) > 0x1100 else 0.61) for ch in s)


def short_name(node):
    """The name a call site uses for a box: `a::b::run()` -> `run`."""
    return re.sub(r"\(.*$", "", node["name"]).split("::")[-1]


def callee_names(line, by_id):
    """Identifiers to underline, each mapped to the box id it jumps to: the
    called function's own name for each call edge, or the `callee` name the
    line uses instead (an `as` import, a re-export)."""
    targets = line.get("to") or []
    targets = [targets] if isinstance(targets, str) else targets
    kinds = line.get("edge", "call")
    code = line.get("code", "")
    names, unmatched = {}, []
    for i, t in enumerate(targets):
        kind = kinds[i] if isinstance(kinds, list) else kinds
        if kind in ("call", "defer") and t in by_id:
            name = short_name(by_id[t])
            if re.search(rf"\b{re.escape(name)}\b", code):
                names[name] = t
            else:
                unmatched.append(t)
    callee = line.get("callee")
    callee = callee if isinstance(callee, list) else [callee] if callee else []
    for i, name in enumerate(callee):
        if name not in names:
            names[name] = unmatched[i] if i < len(unmatched) else (unmatched or [None])[-1]
    return names


# --- layout --------------------------------------------------------------

def edges_of(n):
    for ln in n.get("lines", []):
        targets = ln.get("to")
        if not targets:
            continue
        targets = [targets] if isinstance(targets, str) else targets
        kinds = ln.get("edge", "call")
        for i, t in enumerate(targets):
            yield ln, t, (kinds[i] if isinstance(kinds, list) else kinds)


def visit_order(nodes, by_id):
    """Deterministic box order: depth-first from each root (a function box no
    edge calls), following call lines in source order; a type/data box comes
    right after its first user. Boxes nothing reaches keep spec order."""
    called = {t for n in nodes for _, t, k in edges_of(n) if k != "use"}
    order, seen = [], set()

    def dfs(nid):
        if nid in seen or nid not in by_id:
            return
        seen.add(nid)
        order.append(by_id[nid])
        for _, t, k in edges_of(by_id[nid]):
            if k == "use" and t not in seen and t in by_id:
                seen.add(t)
                order.append(by_id[t])
        for _, t, k in edges_of(by_id[nid]):
            if k != "use":
                dfs(t)

    for n in nodes:
        if n["kind"] not in DATA_KINDS and n["id"] not in called:
            dfs(n["id"])
    order += [n for n in nodes if n["id"] not in seen]
    return order


def assign_columns(order):
    """Column = longest call depth from a root (so every call arrow points
    right); a type/data box sits one column right of its first user."""
    by_id = {n["id"]: n for n in order}
    depth = {}

    def calls_of(nid):
        return [t for _, t, k in edges_of(by_id[nid]) if k != "use" and t in by_id]

    def pass_through(nid):
        # An unchanged box that only forwards the path (one call, nothing
        # else drawn) — a chain of these stacks in one column.
        return by_id[nid].get("status") == "same" and len(calls_of(nid)) == 1

    def walk(nid, d, stack):
        if nid in stack or depth.get(nid, -1) >= d:
            return
        depth[nid] = d
        for t in calls_of(nid):
            step = 0 if pass_through(nid) and pass_through(t) else 1
            walk(t, d + step, stack | {nid})

    called = {t for n in order for _, t, k in edges_of(n) if k != "use"}
    for n in order:
        if n["kind"] not in DATA_KINDS and n["id"] not in called:
            walk(n["id"], 0, frozenset())
    for n in order:
        if "col" not in n and n["id"] in depth:
            n["col"] = depth[n["id"]]
    for n in order:
        if "col" not in n:
            users = [m["col"] for m in order if "col" in m and any(t == n["id"] for _, t, _ in edges_of(m))]
            n["col"] = (users[0] + 1) if users else 0


def node_size(n):
    """Box size, and each line's vertical offset (`_dy`) inside the box."""
    widths = [text_width(n["kind"] + " " + head_lines(n)[0], 13) + 70] + \
             [text_width(l, 12) + 2 * PAD for l in head_lines(n)[1:]] + [text_width(n.get("file", ""), 10) + 70]
    if n.get("desc"):
        widths.append(text_width(n["desc"], 11) + 2 * PAD)
    cy = head_h(n) + (18 if n.get("desc") else 0) + 6
    for ln in n.get("lines", []):
        if ln.get("note"):
            widths.append(text_width("// " + ln["note"]) + GUTTER + 14)
            cy += LH
        widths.append(text_width(ln.get("code", "...")) + GUTTER + 14)
        cy += LH
        ln["_dy"] = cy - LH / 2 - 1
    w = max(widths) + 2 * PAD
    return max(w, 170), cy + PAD + 4


def dedent(n):
    """Drop the indentation every kept line of a box shares, so a call deep
    inside closures or blocks starts at the box's left edge. The spec keeps
    the file's own indentation; this makes the rendering independent of it."""
    code = [ln["code"] for ln in n.get("lines", []) if not ln.get("elide") and ln.get("code", "").strip()]
    if not code:
        return
    cut = min(len(c) - len(c.lstrip(" ")) for c in code)
    for ln in n["lines"]:
        if ln.get("elide"):
            ln["indent"] = max(0, ln.get("indent", 0) - cut)
        elif ln.get("code", "")[:cut].strip() == "":
            ln["code"] = ln["code"][cut:]


def layout(nodes):
    """Place every box. Nothing here depends on how the spec was written
    beyond its boxes and edges, so the same boxes always give the same
    picture. (`col` / `align_to` in a spec still override, for old specs.)"""
    by_id = {n["id"]: n for n in nodes}
    for n in nodes:
        dedent(n)
    order = visit_order(nodes, by_id)
    assign_columns(order)
    for n in order:
        n["w"], n["h"] = node_size(n)
    cols = sorted({n["col"] for n in order})
    x = MARGIN
    col_x = {}
    for c in cols:
        col_x[c] = x
        x += max(n["w"] for n in order if n["col"] == c) + COL_GAP
    total_w = x - COL_GAP + MARGIN
    top0 = MARGIN + 70
    col_bottom = {c: top0 for c in cols}
    for c in cols:
        for n in [m for m in order if m["col"] == c]:
            y = col_bottom[c]
            a = n.get("align_to")
            if a and "y" in by_id.get(a, {}):
                y = max(y, by_id[a]["y"])
            elif "align_to" not in n:
                # Line the box's header up with the first placed line that
                # points at it, so arrows run as flat as the column allows.
                srcs = [m["y"] + ln["_dy"] for m in order if "y" in m
                        for ln, t, _ in edges_of(m) if t == n["id"]]
                if srcs:
                    y = max(y, srcs[0] - 20)
            n["x"], n["y"] = col_x[c], y
            col_bottom[c] = y + n["h"] + ROW_GAP
    return total_w, max(col_bottom.values()), by_id


# --- drawing -------------------------------------------------------------

def code_tspans(code, callees, call_line, link=None):
    """Highlighted code. A line that calls another box is bold italic as a
    whole, and the called name inside it is also underlined. Each underlined
    name carries `data-go` (the box it jumps to on the page). `link` is
    (name, figure, box id) for a line that continues in another figure: that
    name is underlined and jumps to the box in that figure."""
    parts = []
    for kind, text in tokens(code):
        color = HL[kind]
        extra = ""
        if call_line and kind in ("fn", "plain") and text in callees:
            extra = ' text-decoration="underline"'
            if callees[text]:
                extra += f' data-go="{escape(callees[text])}"'
        elif link and kind in ("fn", "plain") and text == link[0]:
            extra = f' text-decoration="underline" data-go="{escape(link[2])}" data-go-fig="{link[1]}"'
        parts.append(f'<tspan fill="{color}"{extra}>{escape(text)}</tspan>')
    style = ' font-weight="700" font-style="italic"' if call_line else ""
    return style, "".join(parts)


PARAM_LH = 15  # one header line per parameter


def head_lines(n):
    """Header text lines: `name(`, one indented line per parameter, `)`;
    just `name()` when there are none (or none could be read)."""
    params = n.get("params") if n["kind"] == "fn" else None
    if not params:
        return [n["name"]]
    base = re.sub(r"\(\)\s*$", "", n["name"])
    return [base + "("] + [f"    {p}," if p != "…" else "    …" for p in params] + [")"]


def head_h(n):
    return HEAD_H + PARAM_LH * (len(head_lines(n)) - 1)


def render_node(n, by_id, out):
    st = STATUS[n.get("status", "same")]
    kind = n["kind"]
    x, y, w, h = n["x"], n["y"], n["w"], n["h"]
    rx = 10 if kind in ("fn", "trait") else 0
    dash = KIND_DASH[kind]
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    out.append(f'<g class="node" id="n-{escape(n["id"])}">')
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{BOX}" '
               f'stroke="{st["stroke"]}" stroke-width="{2.0 if kind == "static" else 1.8}"{dash_attr}/>')
    inset = 5 if kind == "trait" else 1
    if kind == "trait":
        out.append(f'<rect x="{x+4}" y="{y+4}" width="{w-8}" height="{h-8}" rx="{rx-3}" fill="none" '
                   f'stroke="{st["stroke"]}" stroke-width="1.2"/>')
    hh = head_h(n)
    lines_h = head_lines(n)
    out.append(f'<rect x="{x+inset}" y="{y+inset}" width="{w-2*inset}" height="{hh-inset}" '
               f'rx="{max(rx-2, 0)}" fill="{st["head"]}" />')
    out.append(f'<path d="M{x+inset},{y+hh} H{x+w-inset}" stroke="{st["stroke"]}" stroke-opacity="0.35"/>')
    out.append(f'<text x="{x+PAD}" y="{y+18}" font-family="{CODE_FONT}" font-size="13" font-weight="700" '
               f'fill="#e6edf3" xml:space="preserve"><tspan fill="#9da7b3" font-weight="400">{kind} </tspan>'
               f'{escape(lines_h[0])}</text>')
    for k, pl in enumerate(lines_h[1:], start=1):
        _, body = code_tspans(pl, {}, False)
        out.append(f'<text x="{x+PAD}" y="{y+18+PARAM_LH*k}" font-family="{CODE_FONT}" font-size="12" '
                   f'xml:space="preserve">{body}</text>')
    if n.get("file"):
        out.append(f'<text x="{x+PAD}" y="{y+hh-7}" font-family="{CODE_FONT}" font-size="10" fill="#9da7b3">'
                   f'{escape(n["file"])}</text>')
    bw = 34
    out.append(f'<rect x="{x+w-bw-8}" y="{y+8}" width="{bw}" height="18" rx="9" fill="{st["stroke"]}"/>')
    out.append(f'<text x="{x+w-8-bw/2}" y="{y+21}" text-anchor="middle" font-family="{TEXT_FONT}" font-size="11" '
               f'font-weight="700" fill="#16181c">{st["badge"]}</text>')
    cy = y + hh
    if n.get("desc"):
        out.append(f'<text x="{x+PAD}" y="{cy+15}" font-family="{TEXT_FONT}" font-size="11" fill="#c9d1d9">'
                   f'{escape(n["desc"])}</text>')
        cy += 18
    cy += 6
    for ln in n.get("lines", []):
        if ln.get("note"):
            cy += LH
            out.append(f'<text x="{x+PAD+GUTTER}" y="{cy-4}" font-family="{CODE_FONT}" font-size="{FS}" '
                       f'fill="#8fd694" xml:space="preserve">// {escape(ln["note"])}</text>')
        cy += LH
        elide = ln.get("elide")
        code = (" " * ln.get("indent", 0)) + "..." if elide else ln["code"]
        if ln.get("mark"):
            out.append(f'<rect x="{x+2}" y="{cy-LH+1}" width="{w-4}" height="{LH}" fill="#4b4220"/>')
            out.append(f'<text x="{x+PAD}" y="{cy-4}" font-family="{CODE_FONT}" font-size="{FS}" font-weight="700" '
                       f'fill="#e3b341">+</text>')
        call_line = any(k in ("call", "defer") for _, _, k in edges_of({"lines": [ln]}))
        style, body = (("", f'<tspan fill="#7d8590">{escape(code)}</tspan>') if elide
                       else code_tspans(code, callee_names(ln, by_id), call_line, ln.get("_link")))
        out.append(f'<text x="{x+PAD+GUTTER}" y="{cy-4}" font-family="{CODE_FONT}" font-size="{FS}"{style} '
                   f'xml:space="preserve">{body}</text>')
        ln["_y"] = cy - LH / 2 - 1
        if ln.get("to"):
            out.append(f'<circle cx="{x+w}" cy="{ln["_y"]}" r="3.5" fill="{st["stroke"]}"/>')
    out.append('</g>')


def render_edges(nodes, by_id, out):
    for n in nodes:
        for ln, t, kind in edges_of(n):
            tgt = by_id[t]
            x1, y1 = n["x"] + n["w"], ln["_y"]
            if tgt["col"] == n["col"]:
                x2, y2 = tgt["x"] + tgt["w"], tgt["y"] + 20
                xm = max(x1, x2) + 28
                d = f"M{x1},{y1} H{xm} V{y2} H{x2+2}"
            elif tgt["col"] < n["col"]:
                x2, y2 = tgt["x"] + tgt["w"], tgt["y"] + 20
                d = f"M{x1},{y1} C{x1+70},{y1} {x2+70},{y2} {x2+2},{y2}"
            else:
                x2, y2 = tgt["x"], tgt["y"] + 20
                dx = max(40, (x2 - x1) * 0.5)
                d = f"M{x1},{y1} C{x1+dx},{y1} {x2-dx},{y2} {x2-2},{y2}"
            if kind == "use":
                attrs = 'stroke="#7d8590" stroke-width="1.4" stroke-dasharray="2 4" fill="none"'
            elif kind == "defer":
                attrs = ('stroke="#c297ff" stroke-width="1.6" stroke-dasharray="8 5" fill="none" '
                         'marker-end="url(#arrow-defer)"')
            else:
                attrs = 'stroke="#79a8ff" stroke-width="1.5" fill="none" marker-end="url(#arrow)"'
            out.append(f'<path d="{d}" {attrs}/>')
            if ln.get("label"):
                lx, ly = (x1 + x2) / 2, (y1 + y2) / 2 - 6
                tw = text_width(ln["label"], 11) + 10
                col = "#c297ff" if kind == "defer" else "#79a8ff"
                out.append(f'<rect x="{lx-tw/2}" y="{ly-12}" width="{tw}" height="17" rx="4" fill="{BOX}" '
                           f'stroke="{col}" stroke-width="0.8"/>')
                out.append(f'<text x="{lx}" y="{ly+1}" text-anchor="middle" font-family="{TEXT_FONT}" '
                           f'font-size="11" fill="{col}">{escape(ln["label"])}</text>')


def render_legend(x, y, out):
    def label(cx, s):
        out.append(f'<text x="{cx}" y="{y}" font-family="{TEXT_FONT}" font-size="12" fill="#c9d1d9">{s}</text>')
        return cx + text_width(s, 12) + 22

    out.append(f'<text x="{x}" y="{y}" font-family="{TEXT_FONT}" font-size="12" font-weight="700" '
               f'fill="#e6edf3">범례</text>')
    cx = x + 40
    for kind, name in (("fn", "함수"), ("struct", "구조체 · enum"), ("static", "static · const"), ("trait", "트레잇")):
        dash = f' stroke-dasharray="{KIND_DASH[kind]}"' if KIND_DASH[kind] else ""
        rx = 6 if kind in ("fn", "trait") else 0
        out.append(f'<rect x="{cx}" y="{y-13}" width="34" height="18" rx="{rx}" fill="{BOX}" stroke="#c9d1d9" '
                   f'stroke-width="1.6"{dash}/>')
        if kind == "trait":
            out.append(f'<rect x="{cx+3}" y="{y-10}" width="28" height="12" rx="3" fill="none" stroke="#c9d1d9" '
                       f'stroke-width="1"/>')
        cx = label(cx + 42, name)
    for key in ("new", "changed", "same"):
        st = STATUS[key]
        out.append(f'<rect x="{cx}" y="{y-13}" width="34" height="18" rx="9" fill="{st["stroke"]}"/>')
        out.append(f'<text x="{cx+17}" y="{y}" text-anchor="middle" font-family="{TEXT_FONT}" font-size="11" '
                   f'font-weight="700" fill="#16181c">{st["badge"]}</text>')
        cx += 46
    cx += 10
    out.append(f'<path d="M{cx},{y-4} h40" stroke="#79a8ff" stroke-width="1.5" marker-end="url(#arrow)"/>')
    cx = label(cx + 48, "호출 (호출 줄은 굵은 기울임, 호출되는 함수는 밑줄)")
    out.append(f'<path d="M{cx},{y-4} h40" stroke="#c297ff" stroke-width="1.6" stroke-dasharray="8 5" '
               f'marker-end="url(#arrow-defer)"/>')
    cx = label(cx + 48, "나중에 실행(클로저 등록)")
    out.append(f'<path d="M{cx},{y-4} h40" stroke="#7d8590" stroke-width="1.4" stroke-dasharray="2 4"/>')
    cx = label(cx + 48, "타입 · 데이터 사용")
    out.append(f'<rect x="{cx}" y="{y-13}" width="34" height="18" fill="#4b4220" stroke="#e3b341" stroke-width="0.8"/>')
    out.append(f'<text x="{cx+5}" y="{y}" font-family="{CODE_FONT}" font-size="12" font-weight="700" '
               f'fill="#e3b341">+</text>')
    label(cx + 42, "이 범위에서 추가 · 수정된 줄     ...  생략한 코드")


def render(group, fig):
    nodes = fig["nodes"]
    total_w, total_h, by_id = layout(nodes)
    # Write boxes in placement order, so the file itself (not only the
    # picture) is the same however the spec listed them.
    nodes = sorted(nodes, key=lambda n: (n["col"], n["y"], n["id"]))
    total_w = max(total_w, 1400)
    total_h += 20
    body, edges, head = [], [], []
    for n in nodes:
        render_node(n, by_id, body)
    render_edges(nodes, by_id, edges)
    head.append(f'<text x="{MARGIN}" y="{MARGIN+4}" font-family="{TEXT_FONT}" font-size="18" font-weight="700" '
                f'fill="#e6edf3">{escape(fig["title"])}</text>')
    sub = "  ·  ".join(s for s in (group.get("range"), fig.get("caption")) if s)
    head.append(f'<text x="{MARGIN}" y="{MARGIN+24}" font-family="{CODE_FONT}" font-size="11" fill="#9da7b3">'
                f'{escape(sub)}</text>')
    render_legend(MARGIN, MARGIN + 52, head)
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w:.0f}" height="{total_h:.0f}" '
        f'viewBox="0 0 {total_w:.0f} {total_h:.0f}">',
        '<defs>'
        '<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" '
        'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#79a8ff"/></marker>'
        '<marker id="arrow-defer" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" '
        'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#c297ff"/></marker>'
        '</defs>',
        f'<rect width="100%" height="100%" fill="{CANVAS}"/>',
        *head, *edges, *body, '</svg>',
    ])


def main():
    group = json.load(open(sys.argv[1], encoding="utf-8"))
    fig = group["figures"][int(sys.argv[2])]
    open(sys.argv[3], "w", encoding="utf-8").write(render(group, fig))


if __name__ == "__main__":
    main()
