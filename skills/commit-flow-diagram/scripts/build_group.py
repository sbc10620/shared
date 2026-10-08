#!/usr/bin/env python3
"""Build one commit-flow GROUP: a directory holding every figure of one
change, as SVG (+ PNG when a Chrome/Chromium is found) plus one index.html.

usage: build_group.py <group.json> [<parent-dir>] [--no-png]

<parent-dir> defaults to $COMMIT_FLOW_DIR, else ~/Documents/code-flow-diagrams. The
group directory name is derived, never chosen: <YYYYMMDD of the `after`
commit>-<repo name from origin, else its directory name>-<after short sha>, so the same change always
lands in the same place.

Output (the group directory name is derived, see above):
  <parent-dir>/<slug>/
    index.html             every figure inline, zoom/fit/drag, self-contained
    fig1.svg, fig2.svg     one file per figure
    fig1.png, fig2.png     previews (optional)
    spec.json              the group spec, to regenerate or extend later
The layout and styling are fixed so every group looks the same.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from xml.sax.saxutils import escape

sys.dont_write_bytecode = True  # keep the skill directory free of __pycache__
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render  # noqa: E402

CHROMES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/opt/pw-browsers/chromium",
    "google-chrome", "chromium", "chromium-browser",
]


def find_chrome():
    for c in CHROMES:
        path = c if os.path.isabs(c) else shutil.which(c)
        if path and os.path.exists(path):
            return path
    return None


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=True).stdout


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if flags - {"--no-png"}:
        sys.exit(f"unknown option(s): {sorted(flags - {'--no-png'})} — the only option is --no-png")
    spec_path = args[0]
    parent = args[1] if len(args) > 1 else (
        os.environ.get("COMMIT_FLOW_DIR") or os.path.expanduser("~/Documents/code-flow-diagrams"))
    group = json.load(open(spec_path, encoding="utf-8"))
    here = os.path.dirname(os.path.abspath(__file__))
    # Always verified; there is deliberately no way to skip it, because a
    # group that skipped the checks is not the fixed format any more.
    r = subprocess.run([sys.executable, os.path.join(here, "verify_spec.py"), spec_path])
    if r.returncode:
        sys.exit("verify_spec failed: fix the spec until it prints 0 problem(s); nothing was built")
    repo, after = group["repo"], group["after"]
    day = git(repo, "show", "-s", "--format=%cd", "--date=format:%Y%m%d", after).strip()
    sha = git(repo, "rev-parse", "--short=10", after).strip()
    try:  # the repository's own name, the same from every clone or worktree
        url = git(repo, "remote", "get-url", "origin").strip()
        name = re.sub(r"\.git$", "", re.split(r"[/:]", url.rstrip("/"))[-1])
    except subprocess.CalledProcessError:
        name = os.path.basename(git(repo, "rev-parse", "--show-toplevel").strip())
    group["slug"] = f"{day}-{name}-{sha}"
    out_dir = os.path.join(parent, group["slug"])
    os.makedirs(out_dir, exist_ok=True)
    if not group.get("commits"):
        log = git(group["repo"], "log", "--format=%h%x09%s", f'{group["before"]}..{group["after"]}')
        group["commits"] = [l.split("\t", 1) for l in log.splitlines()][::-1]
    # Function headers show their parameters, read from the source at
    # `after` (never written in the spec), trimmed to what the box uses
    # when the list is long.
    files = {}
    for fig in group["figures"]:
        for n in fig["nodes"]:
            if n["kind"] != "fn":
                continue
            path, _, line = n["file"].partition(":")
            if path not in files:
                files[path] = git(repo, "show", f"{after}:{path}").splitlines()
            used = "\n".join(ln.get("code", "") for ln in n.get("lines", []) if not ln.get("elide"))
            n["params"] = render.header_params(render.signature_params(files[path], int(line) - 1), used)
    # A line whose note points at another figure ("→ 그림 N", "그림 N 에서")
    # links to the box of that figure whose name the line calls, so a click
    # on the name jumps there.
    for fig in group["figures"]:
        for n in fig["nodes"]:
            for ln in n.get("lines", []):
                m = re.search(r"그림 (\d+)", ln.get("note") or "")
                if not m or ln.get("elide") or not 1 <= int(m.group(1)) <= len(group["figures"]):
                    continue
                k = int(m.group(1))
                for other in group["figures"][k - 1]["nodes"]:
                    name = render.short_name(other)
                    if re.search(rf"\b{re.escape(name)}\s*\(", ln["code"]):
                        ln["_link"] = (name, k, other["id"])
                        break
    chrome = None if "--no-png" in flags else find_chrome()
    figures = []
    for i, fig in enumerate(group["figures"]):
        name = f'fig{i+1}'  # never a chosen word: the same change gives the same files
        svg = render.render(group, json.loads(json.dumps(fig)))
        open(os.path.join(out_dir, name + ".svg"), "w", encoding="utf-8").write(svg)
        m = re.search(r'width="([\d.]+)" height="([\d.]+)"', svg)
        w, h = float(m.group(1)), float(m.group(2))
        if chrome:
            subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                            f"--screenshot={os.path.abspath(os.path.join(out_dir, name + '.png'))}",
                            f"--window-size={int(w)+1},{int(h)}",
                            "file://" + os.path.abspath(os.path.join(out_dir, name + ".svg"))],
                           capture_output=True)
        inline = svg.replace(m.group(0), f'data-w="{w:.0f}" data-h="{h:.0f}"', 1)
        inline = inline.replace("<svg ", f'<svg role="img" aria-label="{escape(fig["title"])}" ', 1)
        # Box ids repeat across figures (the same function starts figure 1
        # and 2), so the page prefixes them with the figure number.
        inline = inline.replace('<g class="node" id="n-', f'<g class="node" id="f{i+1}-n-')
        figures.append((i, fig, inline))
    clean = json.loads(json.dumps(group))
    clean.pop("slug", None)  # derived at build time, refused in a spec
    for fig in clean["figures"]:
        for n in fig["nodes"]:
            n.pop("params", None)  # derived at build time, not part of the spec
            for ln in n.get("lines", []):
                ln.pop("_link", None)
    json.dump(clean, open(os.path.join(out_dir, "spec.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8").write(page(group, figures))
    print(out_dir)
    print("png:", "written" if chrome else
          "skipped (--no-png)" if "--no-png" in flags else "skipped (no Chrome/Chromium found)")


def page(group, figures):
    intro = group
    page_title = group["title"]
    commits = "".join(
        f'<li><code>{escape(sha)}</code><span>{escape(subj)}</span></li>' for sha, subj in group["commits"]
    )
    toc = "".join(f'<a href="#fig{i+1}">{escape(f["title"])}</a>' for i, f, _ in figures)
    nd = group.get("not_drawn") or {}
    not_drawn = ("" if not nd else
                 '<section class="not-drawn" id="not-drawn"><h2>그림에 없는 변경</h2>'
                 '<p>이 범위에서 바뀌었지만 main() 에서 시작하는 흐름에 박스로 넣지 않은 정의입니다.</p><ul>'
                 + "".join(f'<li><code>{escape(k)}</code><span>{escape(str(v))}</span></li>' for k, v in sorted(nd.items()))
                 + '</ul></section>')
    figures_html = "".join(f'''
<section class="fig" id="fig{i+1}">
  <header class="fig-head">
    <div class="fig-titles">
      <h2>{escape(f["title"])}</h2>
      <p>{escape(f.get("caption", ""))}</p>
    </div>
    <div class="tools" role="group" aria-label="확대 조절">
      <button type="button" data-act="out" aria-label="축소">−</button>
      <output class="zoom-val">100%</output>
      <button type="button" data-act="in" aria-label="확대">+</button>
      <button type="button" data-act="fit">화면 맞춤</button>
      <button type="button" data-act="one">실제 크기</button>
      <button type="button" data-act="full" class="full-btn">전체 화면</button>
    </div>
  </header>
  <div class="canvas" tabindex="0">{svg}</div>
</section>''' for i, f, svg in figures)
    return f'''<title>{escape(page_title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;600;700&family=JetBrains+Mono:wght@400;700&display=swap">
<style>
/* Layout: a narrow reading column for the summary, full-bleed scrollable canvases for the diagrams. */
:root {{
  /* One deliberate dark-gray look, the same for every viewer and theme. */
  --bg: #1f2124;
  --surface: #26282c;
  --ink: #e6edf3;
  --muted: #9da7b3;
  --line: #3a3d43;
  --accent: #79a8ff;
  --paper: #2a2c30;
  --font-text: 'IBM Plex Sans KR', 'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', system-ui, sans-serif;
  --font-code: 'JetBrains Mono', Menlo, Consolas, monospace;
  color-scheme: dark;
}}
* {{ box-sizing: border-box; }}
body {{
  background: var(--bg); color: var(--ink); font-family: var(--font-text);
  font-size: 15px; line-height: 1.6; padding-inline: 16px; padding-block: 28px 48px;
}}
.wrap {{ display: grid; gap: 28px; }}
.intro {{ display: grid; gap: 14px; max-width: 72ch; }}
.eyebrow {{ font-family: var(--font-code); font-size: 12px; letter-spacing: .04em; color: var(--muted); }}
h1 {{ font-size: clamp(22px, 3vw, 30px); line-height: 1.3; margin: 0; text-wrap: balance; }}
.intro p {{ margin: 0; color: var(--muted); }}
.commits {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }}
.commits li {{ display: flex; gap: 12px; align-items: baseline; min-width: 0; }}
.commits code {{ font-family: var(--font-code); font-size: 13px; color: var(--accent); flex: none; }}
.commits span {{ min-width: 0; overflow-wrap: anywhere; }}
.toc {{ display: flex; flex-wrap: wrap; gap: 8px 16px; }}
.toc a {{ color: var(--accent); text-decoration: none; border-bottom: 1px solid currentColor; }}
.rules {{ margin: 0; padding-left: 1.2em; color: var(--muted); display: grid; gap: 4px; }}
.fig {{ background: var(--surface); border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }}
.fig-head {{
  display: flex; flex-wrap: wrap; gap: 12px 24px; align-items: center; justify-content: space-between;
  padding: 14px 16px; border-bottom: 1px solid var(--line);
}}
.fig-titles {{ min-width: 0; }}
.fig-titles h2 {{ margin: 0; font-size: 17px; }}
.fig-titles p {{ margin: 2px 0 0; font-size: 13px; color: var(--muted); }}
.tools {{ display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }}
.tools button {{
  font: inherit; font-size: 13px; color: var(--ink); background: transparent;
  border: 1px solid var(--line); border-radius: 6px; padding: 4px 10px; cursor: pointer;
}}
.tools button:hover {{ border-color: var(--accent); color: var(--accent); }}
.tools button:focus-visible, .canvas:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
.not-drawn {{ display: grid; gap: 8px; max-width: 100ch; }}
.not-drawn h2 {{ margin: 0; font-size: 17px; }}
.not-drawn p {{ margin: 0; color: var(--muted); font-size: 14px; }}
.not-drawn ul {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }}
.not-drawn li {{ display: flex; gap: 12px; align-items: baseline; min-width: 0; }}
.not-drawn code {{ font-family: var(--font-code); font-size: 13px; color: var(--accent); flex: none; }}
.not-drawn span {{ min-width: 0; overflow-wrap: anywhere; }}
.zoom-val {{ font-family: var(--font-code); font-size: 12px; min-width: 4.5ch; text-align: center; font-variant-numeric: tabular-nums; }}
.canvas {{
  overflow: auto; background: var(--paper); max-height: 82vh; cursor: grab;
}}
.canvas.dragging {{ cursor: grabbing; user-select: none; }}
/* A figure scrolls with the wheel only while it has focus (click it); the
   outline shows which one. Otherwise the wheel scrolls the page. */
.canvas:focus {{ outline: 2px solid var(--accent); outline-offset: -2px; }}
.canvas svg {{ display: block; }}
.canvas svg text {{ cursor: text; user-select: text; -webkit-user-select: text; }}
/* An underlined name jumps to its box; the box flashes when reached. */
.canvas svg tspan[data-go] {{ cursor: pointer; }}
.canvas svg tspan[data-go]:hover {{ fill: #ffffff; }}
.canvas svg .node.go-hit > rect:first-child {{ stroke: #ffffff; stroke-width: 4; }}
/* Full screen: the browser's own when the frame allows it, else the figure
   fills the window (the same look either way). */
.fig:fullscreen, .fig.is-max {{
  position: fixed; inset: 0; z-index: 50; border-radius: 0; border: 0;
  display: flex; flex-direction: column; background: var(--surface);
}}
.fig.is-max {{ padding-top: env(safe-area-inset-top, 0px); padding-bottom: env(safe-area-inset-bottom, 0px); }}
.fig:fullscreen .canvas, .fig.is-max .canvas {{ max-height: none; flex: 1; min-height: 0; }}
/* In full screen only the figure shows: no title bar, no buttons. Esc
   closes; + / - / 0 zoom in, zoom out and fit. */
.fig:fullscreen .fig-head, .fig.is-max .fig-head {{ display: none; }}
body.has-max {{ overflow: hidden; }}
</style>

<main class="wrap">
  <div class="intro">
    <div class="eyebrow">{escape(intro["range"])}</div>
    <h1>{escape(group["title"])}</h1>
    <ul class="commits">{commits}</ul>
    <ol class="rules">
      <li>박스 안의 코드는 실제 소스를 그대로 옮겼습니다. <code>...</code> 은 생략한 구간이고, 원래 있던 영어 주석은 빼고 한글 설명(초록 <code>//</code>)으로 바꿨습니다.</li>
      <li>황토색 줄과 <code>+</code> 는 이 커밋 범위에서 추가·수정된 줄입니다. 박스 오른쪽 위 배지는 함수 단위의 신규·변경·기존을 뜻합니다.</li>
      <li>호출하는 줄의 오른쪽 점에서 화살표가 나갑니다. 그림을 클릭하면 테두리가 생기고, 그때부터 휠이 그림 안을 스크롤합니다(그림 밖 클릭이나 Esc로 해제). 빈 곳을 끌면 그림이 움직이고, 글자 위를 끌면 코드를 선택해 복사할 수 있습니다.</li>
      <li>밑줄 친 함수 이름을 클릭하면 그 함수의 박스로 이동합니다. <code>→ 그림 N</code> 처럼 다른 그림으로 이어지는 줄은 그 그림의 박스로 이동합니다.</li>
    </ol>
    <nav class="toc">{toc}</nav>
  </div>
  {figures_html}
  {not_drawn}
</main>

<script>
document.querySelectorAll('.fig').forEach((fig) => {{
  const canvas = fig.querySelector('.canvas');
  const svg = canvas.querySelector('svg');
  const out = fig.querySelector('.zoom-val');
  const w = +svg.dataset.w, h = +svg.dataset.h;
  let scale = 1;
  const apply = () => {{
    svg.setAttribute('width', Math.round(w * scale));
    svg.setAttribute('height', Math.round(h * scale));
    out.textContent = Math.round(scale * 100) + '%';
  }};
  // The page never rescales on its own: a figure opens at actual size and
  // keeps whatever scale it has, so the browser's own zoom (Ctrl/Cmd +/-)
  // is what sizes it. "화면 맞춤" fits the whole figure only when asked.
  const fit = () => {{
    const room = isFull() ? canvas.clientHeight : window.innerHeight * 0.82;
    if (!canvas.clientWidth || !room) return;
    scale = Math.min(1, (canvas.clientWidth - 2) / w, (room - 2) / h);
    apply();
  }};
  fig.querySelector('.tools').addEventListener('click', (e) => {{
    const act = e.target.closest('button')?.dataset.act;
    if (act === 'in') scale = Math.min(10, scale * 1.25);
    if (act === 'out') scale = Math.max(0.05, scale / 1.25);
    if (act === 'one') scale = 1;
    if (act === 'fit') return fit();
    if (act === 'full') return toggleFull();
    apply();
  }});
  // Wheel: unless this figure has focus (or is full screen), scroll the
  // page instead of the figure. Ctrl/Cmd + wheel is the browser's zoom.
  canvas.addEventListener('wheel', (e) => {{
    if (e.ctrlKey || e.metaKey || isFull() || document.activeElement === canvas) return;
    // Sideways wheel (Shift + wheel, trackpad swipe): the page has no
    // horizontal scroll, so the figure keeps it.
    if (e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) return;
    e.preventDefault();
    const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? window.innerHeight : 1;
    window.scrollBy({{ top: e.deltaY * unit, left: 0 }});
  }}, {{ passive: false }});
  canvas.addEventListener('keydown', (e) => {{
    if (e.key === 'Escape' && !isFull()) canvas.blur();
  }});
  let drag = null;
  canvas.addEventListener('pointerdown', (e) => {{
    if (e.pointerType !== 'mouse') return;
    canvas.focus({{ preventScroll: true }});
    // Dragging over text selects it (to copy code); empty space pans.
    if (e.target.closest('text')) return;
    drag = {{ x: e.clientX, y: e.clientY, l: canvas.scrollLeft, t: canvas.scrollTop }};
    canvas.classList.add('dragging');
  }});
  window.addEventListener('pointermove', (e) => {{
    if (!drag) return;
    canvas.scrollLeft = drag.l - (e.clientX - drag.x);
    canvas.scrollTop = drag.t - (e.clientY - drag.y);
  }});
  window.addEventListener('pointerup', () => {{ drag = null; canvas.classList.remove('dragging'); }});
  const fullBtn = fig.querySelector('.full-btn');
  const isFull = () => document.fullscreenElement === fig || fig.classList.contains('is-max');
  const sync = () => {{
    fullBtn.textContent = isFull() ? '전체 화면 닫기' : '전체 화면';
  }};
  const toggleFull = () => {{
    if (isFull()) {{
      if (document.fullscreenElement === fig) document.exitFullscreen().catch(() => {{}});
      fig.classList.remove('is-max');
      document.body.classList.remove('has-max');
      return sync();
    }}
    const fallback = () => {{ fig.classList.add('is-max'); document.body.classList.add('has-max'); sync(); }};
    if (fig.requestFullscreen) fig.requestFullscreen().then(sync, fallback);
    else fallback();
  }};
  document.addEventListener('fullscreenchange', sync);
  document.addEventListener('keydown', (e) => {{
    if (!isFull()) return;
    if (e.key === 'Escape' && fig.classList.contains('is-max')) toggleFull();
    else if (e.key === '+' || e.key === '=') {{ scale = Math.min(10, scale * 1.25); apply(); }}
    else if (e.key === '-') {{ scale = Math.max(0.05, scale / 1.25); apply(); }}
    else if (e.key === '0') fit();
  }});
  apply();
  fig.goTo = (node) => {{
    // Center the box in this figure's canvas at the current scale.
    const b = node.getBBox();
    canvas.scrollTo({{
      left: (b.x + b.width / 2) * scale - canvas.clientWidth / 2,
      top: (b.y + Math.min(b.height, 160) / 2) * scale - canvas.clientHeight / 3,
      behavior: 'smooth',
    }});
    node.classList.remove('go-hit');
    void node.getBBox();
    node.classList.add('go-hit');
    setTimeout(() => node.classList.remove('go-hit'), 1400);
  }};
  fig.leaveFull = () => {{ if (isFull()) toggleFull(); }};
}});
// Click an underlined name: jump to its box (in this figure, or in the
// figure a "→ 그림 N" line continues in). A drag or a text selection made
// over the name is not a click.
let down = null;
document.addEventListener('pointerdown', (e) => {{ down = {{ x: e.clientX, y: e.clientY }}; }}, true);
document.addEventListener('click', (e) => {{
  const t = e.target.closest && e.target.closest('tspan[data-go]');
  if (!t || !down || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 4) return;
  if (String(window.getSelection() || '').length) return;
  const from = t.closest('.fig');
  const fig = t.dataset.goFig ? document.getElementById('fig' + t.dataset.goFig) : from;
  const node = fig && fig.querySelector('#' + CSS.escape(fig.id.replace('fig', 'f') + '-n-' + t.dataset.go));
  if (!node) return;
  if (fig !== from) {{
    from.leaveFull();
    fig.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
  }}
  fig.goTo(node);
}});
</script>
'''


if __name__ == "__main__":
    main()
