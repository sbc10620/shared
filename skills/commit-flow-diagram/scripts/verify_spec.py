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
                 no hand layout (`col`, `align_to`) or hand-picked `slug`;
                 every call/defer line has a note and no note exceeds 40
                 characters; every box is reachable from the figure's entry
                 box; a type/data box over 8 lines shows `...`; a figure
                 holds at most 18 boxes.
Exit 1 with a list on any failure.
"""
import json
import subprocess
import sys


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=True).stdout


def main():
    group = json.load(open(sys.argv[1], encoding="utf-8"))
    repo, before, after = group["repo"], group["before"], group["after"]
    sources, diffs = {}, {}
    problems = []
    if "slug" in group:
        problems.append("group: remove `slug` — build_group.py derives the directory name")
    for fi, fig in enumerate(group["figures"]):
        ids = {n["id"] for n in fig["nodes"]}
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
            if n["kind"] in ("struct", "enum", "static", "trait") and len(n.get("lines", [])) > 8 \
                    and not any(ln.get("elide") for ln in n["lines"]):
                problems.append(f"fig{fi+1} {n['id']}: type box over 8 lines must show only what the flow uses (`...`)")
            prev = {}
            for ln in n.get("lines", []):
                kinds = ln.get("edge", "call")
                kinds = kinds if isinstance(kinds, list) else [kinds]
                # A call split over lines may carry its note on the line above.
                if ln.get("to") and any(k != "use" for k in kinds) and not (ln.get("note") or prev.get("note")):
                    problems.append(f"fig{fi+1} {n['id']}: call line needs a note: {ln.get('code', '')!r}")
                prev = ln
                if ln.get("note") and len(ln["note"]) > 40:
                    problems.append(f"fig{fi+1} {n['id']}: note over 40 characters: {ln['note']!r}")
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
    for p in problems:
        print(p)
    print(f"{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
