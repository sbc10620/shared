#!/usr/bin/env python3
"""Build one commit-flow GROUP: a directory holding every figure of one
change, as SVG (+ PNG when a Chrome/Chromium is found) plus one index.html.

usage: build_group.py <group.json> [<parent-dir>] [--skip-verify] [--no-png]

<parent-dir> defaults to $COMMIT_FLOW_DIR, else ~/code-flow-diagrams. The
group directory name is derived, never chosen: <YYYYMMDD of the `after`
commit>-<repo name from origin, else its directory name>-<after short sha>, so the same change always
lands in the same place.

Output (the group directory name is derived, see above):
  <parent-dir>/<slug>/
    index.html             every figure inline, zoom/fit/drag, self-contained
    fig1-<fig slug>.svg    one file per figure
    fig1-<fig slug>.png    preview (optional)
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
    spec_path = args[0]
    parent = args[1] if len(args) > 1 else (
        os.environ.get("COMMIT_FLOW_DIR") or os.path.expanduser("~/code-flow-diagrams"))
    group = json.load(open(spec_path, encoding="utf-8"))
    here = os.path.dirname(os.path.abspath(__file__))
    if "--skip-verify" not in flags:
        r = subprocess.run([sys.executable, os.path.join(here, "verify_spec.py"), spec_path])
        if r.returncode:
            sys.exit("verify_spec failed; fix the spec (or pass --skip-verify knowingly)")
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
    chrome = None if "--no-png" in flags else find_chrome()
    figures = []
    for i, fig in enumerate(group["figures"]):
        name = f'fig{i+1}-{fig["slug"]}'
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
        figures.append((i, fig, inline))
    json.dump(group, open(os.path.join(out_dir, "spec.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8").write(page(group, figures))
    print(out_dir)
    print("png:", "written" if chrome else "skipped (no Chrome/Chromium found)")


def page(group, figures):
    intro = group
    page_title = group["title"]
    commits = "".join(
        f'<li><code>{escape(sha)}</code><span>{escape(subj)}</span></li>' for sha, subj in group["commits"]
    )
    toc = "".join(f'<a href="#fig{i+1}">{escape(f["title"])}</a>' for i, f, _ in figures)
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
  --bg: #eef1f4;
  --surface: #ffffff;
  --ink: #18212b;
  --muted: #566372;
  --line: #cfd6de;
  --accent: #1e3a8a;
  --paper: #ffffff;
  --font-text: 'IBM Plex Sans KR', 'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', system-ui, sans-serif;
  --font-code: 'JetBrains Mono', Menlo, Consolas, monospace;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg: #12171d; --surface: #1b222b; --ink: #e4e9ef; --muted: #9aa7b6; --line: #2f3a46;
    --accent: #8fb0ff; --paper: #ffffff; color-scheme: dark;
  }}
}}
:root[data-theme="dark"] {{
  --bg: #12171d; --surface: #1b222b; --ink: #e4e9ef; --muted: #9aa7b6; --line: #2f3a46;
  --accent: #8fb0ff; --paper: #ffffff; color-scheme: dark;
}}
* {{ box-sizing: border-box; }}
body {{
  background: var(--bg); color: var(--ink); font-family: var(--font-text);
  font-size: 15px; line-height: 1.6; padding-inline: 16px; padding-block: 28px 48px;
}}
.wrap {{ max-width: 1600px; margin: 0 auto; display: grid; gap: 28px; }}
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
.zoom-val {{ font-family: var(--font-code); font-size: 12px; min-width: 4.5ch; text-align: center; font-variant-numeric: tabular-nums; }}
.canvas {{
  overflow: auto; background: var(--paper); max-height: 82vh; cursor: grab;
}}
.canvas.dragging {{ cursor: grabbing; user-select: none; }}
.canvas svg {{ display: block; }}
/* Full screen: the browser's own when the frame allows it, else the figure
   fills the window (the same look either way). */
.fig:fullscreen, .fig.is-max {{
  position: fixed; inset: 0; z-index: 50; border-radius: 0; border: 0;
  display: flex; flex-direction: column; background: var(--surface);
}}
.fig.is-max {{ padding-top: env(safe-area-inset-top, 0px); padding-bottom: env(safe-area-inset-bottom, 0px); }}
.fig:fullscreen .canvas, .fig.is-max .canvas {{ max-height: none; flex: 1; min-height: 0; }}
body.has-max {{ overflow: hidden; }}
</style>

<main class="wrap">
  <div class="intro">
    <div class="eyebrow">{escape(intro["range"])}</div>
    <h1>{escape(group["title"])}</h1>
    <ul class="commits">{commits}</ul>
    <ol class="rules">
      <li>박스 안의 코드는 실제 소스를 그대로 옮겼습니다. <code>...</code> 은 생략한 구간이고, 원래 있던 영어 주석은 빼고 한글 설명(초록 <code>//</code>)으로 바꿨습니다.</li>
      <li>노란 줄과 <code>+</code> 는 이 커밋 범위에서 추가·수정된 줄입니다. 박스 오른쪽 위 배지는 함수 단위의 신규·변경·기존을 뜻합니다.</li>
      <li>호출하는 줄의 오른쪽 점에서 화살표가 나갑니다. 그림은 드래그하거나 스크롤해서 움직일 수 있습니다.</li>
    </ol>
    <nav class="toc">{toc}</nav>
  </div>
  {figures_html}
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
  const fit = () => {{ scale = Math.min(1, (canvas.clientWidth - 2) / w); apply(); }};
  fig.querySelector('.tools').addEventListener('click', (e) => {{
    const act = e.target.closest('button')?.dataset.act;
    if (act === 'in') scale = Math.min(3, scale * 1.25);
    if (act === 'out') scale = Math.max(0.15, scale / 1.25);
    if (act === 'one') scale = 1;
    if (act === 'fit') return fit();
    if (act === 'full') return toggleFull();
    apply();
  }});
  let drag = null;
  canvas.addEventListener('pointerdown', (e) => {{
    if (e.pointerType !== 'mouse') return;
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
    requestAnimationFrame(fit);
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
    if (e.key === 'Escape' && fig.classList.contains('is-max')) toggleFull();
  }});
  fit();
}});
</script>
'''


if __name__ == "__main__":
    main()
