#!/usr/bin/env python3
"""Check a commit-flow group spec against the repository before rendering.

usage: verify_spec.py <group.json>

Checks, per box line (elided lines skipped):
  1. verbatim  — the stripped code line exists in the box's file at `after`
                 (`git show <after>:<path>`), so nothing in a box is paraphrase;
  2. "+" marks — a marked line is an added line of `git diff <before> <after>`
                 for that file, and an unmarked line is not (lines shorter
                 than 4 characters, such as braces, are not judged);
  3. edges     — every `to` names a box of the same figure.
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
    for fi, fig in enumerate(group["figures"]):
        ids = {n["id"] for n in fig["nodes"]}
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
