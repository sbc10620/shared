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

STATUS = {
    "new": {"stroke": "#15803d", "head": "#dcfce7", "badge": "신규"},
    "changed": {"stroke": "#c2410c", "head": "#ffedd5", "badge": "변경"},
    "same": {"stroke": "#64748b", "head": "#f1f5f9", "badge": "기존"},
}
KIND_DASH = {"fn": "", "trait": "", "struct": "7 4", "enum": "7 4", "static": "2 3"}
DATA_KINDS = {"struct", "enum", "static", "trait"}

# --- syntax highlighting -------------------------------------------------
# One palette for every language; the token rules are deliberately small
# (C-family shape: Rust, C/C++, Java, Kotlin, Go, TS/JS, Swift).
HL = {
    "kw": "#cf222e", "str": "#0a3069", "num": "#0550ae", "type": "#953800",
    "fn": "#8250df", "macro": "#0550ae", "com": "#6e7781", "attr": "#6e7781",
    "life": "#953800", "plain": "#1f2328",
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


def text_width(s, size=FS):
    return sum(size * (1.02 if ord(ch) > 0x1100 else 0.61) for ch in s)


def callee_names(line, by_id):
    """Identifiers to bold: the called function's own name for each call edge."""
    names = set(line.get("callee", []) if isinstance(line.get("callee"), list) else
                [line["callee"]] if line.get("callee") else [])
    targets = line.get("to") or []
    targets = [targets] if isinstance(targets, str) else targets
    kinds = line.get("edge", "call")
    for i, t in enumerate(targets):
        kind = kinds[i] if isinstance(kinds, list) else kinds
        if kind in ("call", "defer") and t in by_id:
            names.add(re.sub(r"\(.*$", "", by_id[t]["name"]).split("::")[-1])
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


def assign_columns(nodes, by_id):
    """Fill missing `col`: functions by call depth from the roots, data boxes
    one column right of their first user. Explicit `col` values win."""
    if all("col" in n for n in nodes):
        return
    calls = {n["id"]: [t for _, t, k in edges_of(n) if k in ("call", "defer")] for n in nodes}
    called = {t for ts in calls.values() for t in ts}
    depth = {}

    def visit(nid, d, seen):
        if nid in seen:
            return
        if depth.get(nid, -1) >= d:
            return
        depth[nid] = d
        for t in calls.get(nid, []):
            visit(t, d + 1, seen | {nid})

    for n in nodes:
        if n["kind"] not in DATA_KINDS and n["id"] not in called:
            visit(n["id"], 0, set())
    for n in nodes:
        if "col" not in n and n["id"] in depth:
            n["col"] = depth[n["id"]]
    for n in nodes:
        if "col" not in n:
            users = [m["col"] for m in nodes if "col" in m and any(t == n["id"] for _, t, _ in edges_of(m))]
            n["col"] = (min(users) + 1) if users else 0


def node_size(n):
    widths = [text_width(n["kind"] + " " + n["name"], 13) + 70, text_width(n.get("file", ""), 10) + 70]
    if n.get("desc"):
        widths.append(text_width(n["desc"], 11) + 2 * PAD)
    rows = 0
    for ln in n.get("lines", []):
        if ln.get("note"):
            widths.append(text_width("// " + ln["note"]) + GUTTER + 14)
            rows += 1
        widths.append(text_width(ln.get("code", "...")) + GUTTER + 14)
        rows += 1
    w = max(widths) + 2 * PAD
    h = HEAD_H + (18 if n.get("desc") else 0) + rows * LH + PAD + 4
    return max(w, 170), h


def layout(nodes):
    by_id = {n["id"]: n for n in nodes}
    assign_columns(nodes, by_id)
    for n in nodes:
        n["w"], n["h"] = node_size(n)
    cols = sorted({n["col"] for n in nodes})
    x = MARGIN
    col_x = {}
    for c in cols:
        col_x[c] = x
        x += max(n["w"] for n in nodes if n["col"] == c) + COL_GAP
    total_w = x - COL_GAP + MARGIN
    top0 = MARGIN + 70
    col_bottom = {c: top0 for c in cols}
    for c in cols:
        for n in [m for m in nodes if m["col"] == c]:
            y = col_bottom[c]
            a = n.get("align_to")
            if a and "y" in by_id.get(a, {}):
                y = max(y, by_id[a]["y"])
            n["x"], n["y"] = col_x[c], y
            col_bottom[c] = y + n["h"] + ROW_GAP
    return total_w, max(col_bottom.values()), by_id


# --- drawing -------------------------------------------------------------

def code_tspans(code, bold, dim):
    parts = []
    for kind, text in tokens(code):
        color = "#94a3b8" if dim else HL[kind]
        weight = ' font-weight="700"' if (kind == "fn" or kind == "plain") and text in bold else ""
        parts.append(f'<tspan fill="{color}"{weight}>{escape(text)}</tspan>')
    return "".join(parts)


def render_node(n, by_id, out):
    st = STATUS[n.get("status", "same")]
    kind = n["kind"]
    x, y, w, h = n["x"], n["y"], n["w"], n["h"]
    rx = 10 if kind in ("fn", "trait") else 0
    dash = KIND_DASH[kind]
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    out.append(f'<g class="node" id="n-{escape(n["id"])}">')
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="#ffffff" '
               f'stroke="{st["stroke"]}" stroke-width="{2.0 if kind == "static" else 1.8}"{dash_attr}/>')
    inset = 5 if kind == "trait" else 1
    if kind == "trait":
        out.append(f'<rect x="{x+4}" y="{y+4}" width="{w-8}" height="{h-8}" rx="{rx-3}" fill="none" '
                   f'stroke="{st["stroke"]}" stroke-width="1.2"/>')
    out.append(f'<rect x="{x+inset}" y="{y+inset}" width="{w-2*inset}" height="{HEAD_H-inset}" '
               f'rx="{max(rx-2, 0)}" fill="{st["head"]}" fill-opacity="0.85"/>')
    out.append(f'<path d="M{x+inset},{y+HEAD_H} H{x+w-inset}" stroke="{st["stroke"]}" stroke-opacity="0.35"/>')
    out.append(f'<text x="{x+PAD}" y="{y+18}" font-family="{CODE_FONT}" font-size="13" font-weight="700" '
               f'fill="#0f172a" xml:space="preserve"><tspan fill="#64748b" font-weight="400">{kind} </tspan>'
               f'{escape(n["name"])}</text>')
    if n.get("file"):
        out.append(f'<text x="{x+PAD}" y="{y+33}" font-family="{CODE_FONT}" font-size="10" fill="#64748b">'
                   f'{escape(n["file"])}</text>')
    bw = 34
    out.append(f'<rect x="{x+w-bw-8}" y="{y+8}" width="{bw}" height="18" rx="9" fill="{st["stroke"]}"/>')
    out.append(f'<text x="{x+w-8-bw/2}" y="{y+21}" text-anchor="middle" font-family="{TEXT_FONT}" font-size="11" '
               f'font-weight="700" fill="#ffffff">{st["badge"]}</text>')
    cy = y + HEAD_H
    if n.get("desc"):
        out.append(f'<text x="{x+PAD}" y="{cy+15}" font-family="{TEXT_FONT}" font-size="11" fill="#334155">'
                   f'{escape(n["desc"])}</text>')
        cy += 18
    cy += 6
    for ln in n.get("lines", []):
        if ln.get("note"):
            cy += LH
            out.append(f'<text x="{x+PAD+GUTTER}" y="{cy-4}" font-family="{CODE_FONT}" font-size="{FS}" '
                       f'fill="#15803d" xml:space="preserve">// {escape(ln["note"])}</text>')
        cy += LH
        elide = ln.get("elide")
        code = (" " * ln.get("indent", 0)) + "..." if elide else ln["code"]
        dim = bool(ln.get("dim") or elide)
        if ln.get("mark"):
            out.append(f'<rect x="{x+2}" y="{cy-LH+1}" width="{w-4}" height="{LH}" fill="#fef9c3" fill-opacity="0.8"/>')
            out.append(f'<text x="{x+PAD}" y="{cy-4}" font-family="{CODE_FONT}" font-size="{FS}" font-weight="700" '
                       f'fill="#a16207">+</text>')
        body = (f'<tspan fill="#94a3b8">{escape(code)}</tspan>' if elide
                else code_tspans(code, callee_names(ln, by_id), dim))
        out.append(f'<text x="{x+PAD+GUTTER}" y="{cy-4}" font-family="{CODE_FONT}" font-size="{FS}" '
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
                attrs = 'stroke="#94a3b8" stroke-width="1.4" stroke-dasharray="2 4" fill="none"'
            elif kind == "defer":
                attrs = ('stroke="#7c3aed" stroke-width="1.6" stroke-dasharray="8 5" fill="none" '
                         'marker-end="url(#arrow-defer)"')
            else:
                attrs = 'stroke="#1e3a8a" stroke-width="1.5" fill="none" marker-end="url(#arrow)"'
            out.append(f'<path d="{d}" {attrs}/>')
            if ln.get("label"):
                lx, ly = (x1 + x2) / 2, (y1 + y2) / 2 - 6
                tw = text_width(ln["label"], 11) + 10
                col = "#7c3aed" if kind == "defer" else "#1e3a8a"
                out.append(f'<rect x="{lx-tw/2}" y="{ly-12}" width="{tw}" height="17" rx="4" fill="#ffffff" '
                           f'stroke="{col}" stroke-width="0.8"/>')
                out.append(f'<text x="{lx}" y="{ly+1}" text-anchor="middle" font-family="{TEXT_FONT}" '
                           f'font-size="11" fill="{col}">{escape(ln["label"])}</text>')


def render_legend(x, y, out):
    def label(cx, s):
        out.append(f'<text x="{cx}" y="{y}" font-family="{TEXT_FONT}" font-size="12" fill="#334155">{s}</text>')
        return cx + text_width(s, 12) + 22

    out.append(f'<text x="{x}" y="{y}" font-family="{TEXT_FONT}" font-size="12" font-weight="700" '
               f'fill="#0f172a">범례</text>')
    cx = x + 40
    for kind, name in (("fn", "함수"), ("struct", "구조체 · enum"), ("static", "static · const"), ("trait", "트레잇")):
        dash = f' stroke-dasharray="{KIND_DASH[kind]}"' if KIND_DASH[kind] else ""
        rx = 6 if kind in ("fn", "trait") else 0
        out.append(f'<rect x="{cx}" y="{y-13}" width="34" height="18" rx="{rx}" fill="#ffffff" stroke="#334155" '
                   f'stroke-width="1.6"{dash}/>')
        if kind == "trait":
            out.append(f'<rect x="{cx+3}" y="{y-10}" width="28" height="12" rx="3" fill="none" stroke="#334155" '
                       f'stroke-width="1"/>')
        cx = label(cx + 42, name)
    for key in ("new", "changed", "same"):
        st = STATUS[key]
        out.append(f'<rect x="{cx}" y="{y-13}" width="34" height="18" rx="9" fill="{st["stroke"]}"/>')
        out.append(f'<text x="{cx+17}" y="{y}" text-anchor="middle" font-family="{TEXT_FONT}" font-size="11" '
                   f'font-weight="700" fill="#ffffff">{st["badge"]}</text>')
        cx += 46
    cx += 10
    out.append(f'<path d="M{cx},{y-4} h40" stroke="#1e3a8a" stroke-width="1.5" marker-end="url(#arrow)"/>')
    cx = label(cx + 48, "호출 (굵은 글씨가 호출되는 함수)")
    out.append(f'<path d="M{cx},{y-4} h40" stroke="#7c3aed" stroke-width="1.6" stroke-dasharray="8 5" '
               f'marker-end="url(#arrow-defer)"/>')
    cx = label(cx + 48, "나중에 실행(클로저 등록)")
    out.append(f'<path d="M{cx},{y-4} h40" stroke="#94a3b8" stroke-width="1.4" stroke-dasharray="2 4"/>')
    cx = label(cx + 48, "타입 · 데이터 사용")
    out.append(f'<rect x="{cx}" y="{y-13}" width="34" height="18" fill="#fef9c3" stroke="#eab308" stroke-width="0.8"/>')
    out.append(f'<text x="{cx+5}" y="{y}" font-family="{CODE_FONT}" font-size="12" font-weight="700" '
               f'fill="#a16207">+</text>')
    label(cx + 42, "이 범위에서 추가 · 수정된 줄     ...  생략한 코드")


def render(group, fig):
    nodes = fig["nodes"]
    total_w, total_h, by_id = layout(nodes)
    total_w = max(total_w, 1400)
    total_h += 20
    body, edges, head = [], [], []
    for n in nodes:
        render_node(n, by_id, body)
    render_edges(nodes, by_id, edges)
    head.append(f'<text x="{MARGIN}" y="{MARGIN+4}" font-family="{TEXT_FONT}" font-size="18" font-weight="700" '
                f'fill="#0f172a">{escape(fig["title"])}</text>')
    sub = "  ·  ".join(s for s in (group.get("range"), fig.get("caption")) if s)
    head.append(f'<text x="{MARGIN}" y="{MARGIN+24}" font-family="{CODE_FONT}" font-size="11" fill="#475569">'
                f'{escape(sub)}</text>')
    render_legend(MARGIN, MARGIN + 52, head)
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w:.0f}" height="{total_h:.0f}" '
        f'viewBox="0 0 {total_w:.0f} {total_h:.0f}">',
        '<defs>'
        '<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" '
        'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#1e3a8a"/></marker>'
        '<marker id="arrow-defer" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" '
        'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#7c3aed"/></marker>'
        '</defs>',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        *head, *edges, *body, '</svg>',
    ])


def main():
    group = json.load(open(sys.argv[1], encoding="utf-8"))
    fig = group["figures"][int(sys.argv[2])]
    open(sys.argv[3], "w", encoding="utf-8").write(render(group, fig))


if __name__ == "__main__":
    main()
