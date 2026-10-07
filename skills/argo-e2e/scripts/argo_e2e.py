#!/usr/bin/env python3
"""Drive ARGO release binaries against a mock LLM and judge each case.

usage: argo_e2e.py <spec.json> --bin NAME=PATH [--bin NAME=PATH ...]
                   [--lib-dir DIR] [--only SUITE] [--keep]
       argo_e2e.py <spec.json> --check

  --lib-dir  directory holding libobjectbox (build_release.sh writes it to
             <out-dir>/libdir.txt); exported as LD_LIBRARY_PATH and
             DYLD_LIBRARY_PATH for a binary built without an rpath to it.
             Not needed on macOS when build_release.sh added the rpath.
  --check    validate the spec (keys, modes, every regex compiles) and exit;
             runs nothing.

The spec (JSON) holds:
  "files":  {name: content}           fixtures written to <work>/files/;
                                       content is a string, or
                                       {"head": s, "repeat": s, "times": n,
                                        "tail": s} = head + repeat*n + tail
  "suites": [ {
      "name":   str,
      "bin":    NAME                   a --bin NAME, e.g. "guard" / "noguard"
      "config": str                    config.toml text; {MOCK_URL} and {FILES}
                                       are substituted
      "env":    {K: V}                 optional extra env (on top of
                                       ARGO_PROVIDER=openai_compat,
                                       ARGO_MODEL=mock-model), e.g.
                                       {"RUST_LOG": "debug"} for daemon debug
                                       lines
      "cases":  [ {
          "name":     str,
          "mode":     "single" | "daemon" | "boot",
          "message":  str              {FILES} substituted; "boot" may omit it
          "session":  str              daemon only: sent as session_id, so
                                       cases with the same session are turns
                                       of ONE conversation (without it every
                                       POST is a new conversation)
          "expect":   [regex, ...]     each must match the case's output
          "expect_not": [regex, ...]   none may match
          "llm_calls": int             optional exact LLM request count (every
                                       request, background ones included)
          "tool_seen": regex           optional; must match what the model got
          -- over the requests the mock received during the case
             ("loop" requests = the ones that offered tools, i.e. the agent
             loop's own calls; background calls such as title generation
             offer none):
          "loop_calls": int            exact number of loop requests
          "requests_all": [regex]      every loop request matches each
          "requests_any": [regex]      some request (any kind) matches each
          "requests_none": [regex]     no request (any kind) matches any
          "request_at": {"i": [regex]} loop request i (0-based) matches each
          -- daemon only, over the daemon's stderr written during the case:
          "call_log": [ {
              "call":  i | "after" | "turn"
                         i = lines written before loop request i reached the
                         mock and after loop request i-1 did (or after the
                         case began, for i=0); "after" = after the last loop
                         request; "turn" = the whole case
              "match": regex           lines counted; group 1, if any, is
                                       read as an int for "range"
              "count" | "min" | "max": int   on the number of matching lines
              "range": [lo, hi]        every matching line's group 1 in
                                       [lo, hi]
          } ]
          "require": {...}             preconditions: any of the keys above;
                                       when one fails, the case fails AND
                                       every later case of the suite is
                                       reported as not run (FAIL) — use it
                                       for what makes the rest meaningless
      } ]
  } ]

Each suite gets a fresh HOME (<work>/<suite>/home) with the config at
~/.argo/config.toml, and its own mock LLM on a free port. "single" runs
`argo "<message>"` (one-shot); "boot" is the same run, read as "did the boot
refuse" (expect the refusal text); "daemon" starts `argo --daemon` on a free
port once per suite and POSTs each message to /api/v1/chat, judging the
response text plus the daemon's stderr lines written during that request.

Log lines are attributed to loop requests by byte offset: the mock records
the daemon log's size the moment each request arrives, and a pass that
runs before a request is sent (the outbound masking pass) is written below
that offset. Lines from work running concurrently with a request (a
detached post-turn task) land in whichever segment they are written in.

Processes are stopped by PID only. Exit status 1 when any case fails.
"""
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TIMEOUT_SINGLE = 120
TIMEOUT_REQUEST = 180

REQUEST_KEYS = ("loop_calls", "requests_all", "requests_any", "requests_none", "request_at")
JUDGE_KEYS = ("expect", "expect_not", "llm_calls", "tool_seen") + REQUEST_KEYS + ("call_log",)
CASE_KEYS = {"name", "mode", "message", "session", "require"} | set(JUDGE_KEYS)
SUITE_KEYS = {"name", "bin", "config", "env", "cases"}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def read_log(path):
    """(request entries, last tool result the mock answered from)."""
    calls, seen = [], None
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            d = json.loads(line)
            if "call" in d:
                calls.append(d["call"])
            elif "tool_seen" in d:
                seen = d["tool_seen"]
    return calls, seen


def segments(loop, log_bytes, start, end):
    """Daemon log text per loop request, plus "after" and "turn"."""
    segs = {}
    prev = start
    for i, c in enumerate(loop):
        off = c.get("log_offset")
        if off is None:
            return None
        off = max(prev, min(off, end))
        segs[i] = log_bytes[prev:off].decode("utf-8", "replace")
        prev = off
    segs["after"] = log_bytes[prev:end].decode("utf-8", "replace")
    segs["turn"] = log_bytes[start:end].decode("utf-8", "replace")
    return segs


def judge(case, ev):
    """Problems with `case` (a dict of judge keys) against the evidence `ev`."""
    problems = []
    output, calls, seen = ev["output"], ev["calls"], ev["seen"]
    loop = [c for c in calls if c.get("has_tools")]
    for rx in case.get("expect", []):
        if not re.search(rx, output, re.S):
            problems.append(f"missing /{rx}/")
    for rx in case.get("expect_not", []):
        if re.search(rx, output, re.S):
            problems.append(f"unexpected /{rx}/")
    if "llm_calls" in case and len(calls) != case["llm_calls"]:
        problems.append(f"llm_calls={len(calls)} (want {case['llm_calls']})")
    if "tool_seen" in case and not (seen and re.search(case["tool_seen"], seen, re.S)):
        problems.append(f"tool_seen={seen!r} !~ /{case['tool_seen']}/")
    if "loop_calls" in case and len(loop) != case["loop_calls"]:
        problems.append(f"loop_calls={len(loop)} (want {case['loop_calls']})")
    for rx in case.get("requests_all", []):
        bad = [i for i, c in enumerate(loop) if not re.search(rx, c.get("text", ""), re.S)]
        if not loop or bad:
            problems.append(f"loop requests {bad if loop else '(none)'} miss /{rx}/")
    for rx in case.get("requests_any", []):
        if not any(re.search(rx, c.get("text", ""), re.S) for c in calls):
            problems.append(f"no request matches /{rx}/")
    for rx in case.get("requests_none", []):
        hits = [i for i, c in enumerate(calls) if re.search(rx, c.get("text", ""), re.S)]
        if hits:
            problems.append(f"requests {hits} match /{rx}/")
    for idx, rxs in case.get("request_at", {}).items():
        i = int(idx)
        if i >= len(loop):
            problems.append(f"loop request {i} does not exist ({len(loop)} loop requests)")
            continue
        for rx in rxs:
            if not re.search(rx, loop[i].get("text", ""), re.S):
                problems.append(f"loop request {i} misses /{rx}/")
    if case.get("call_log"):
        segs = ev.get("segments")
        if segs is None:
            problems.append("call_log: no daemon log offsets (not a daemon case, or the mock "
                            "had no daemon log path)")
        else:
            for chk in case["call_log"]:
                problems += judge_call_log(chk, segs)
    return problems


def judge_call_log(chk, segs):
    where = chk["call"]
    label = f"call_log[{where}] /{chk['match']}/"
    if where not in segs:
        return [f"{label}: no such segment (loop requests: "
                f"{len([k for k in segs if isinstance(k, int)])})"]
    rx = re.compile(chk["match"])
    hits = [m for m in (rx.search(line) for line in segs[where].splitlines()) if m]
    n = len(hits)
    problems = []
    if "count" in chk and n != chk["count"]:
        problems.append(f"{label}: {n} lines (want {chk['count']})")
    if "min" in chk and n < chk["min"]:
        problems.append(f"{label}: {n} lines (want >= {chk['min']})")
    if "max" in chk and n > chk["max"]:
        problems.append(f"{label}: {n} lines (want <= {chk['max']})")
    if "range" in chk:
        lo, hi = chk["range"]
        for m in hits:
            v = int(m.group(1))
            if not lo <= v <= hi:
                problems.append(f"{label}: value {v} outside [{lo}, {hi}]")
    return problems


# Provider env every run gets after the operator's own is stripped. With
# only `provider = "openai_compat"` in config.toml, the single-shot path
# speaks the Responses API (`/v1/responses`), which the mock does not; the
# env pins the chat-completions path the daemon uses too. A suite may
# override or extend it with its own "env" map.
DEFAULT_ENV = {"ARGO_PROVIDER": "openai_compat", "ARGO_MODEL": "mock-model"}
LIB_DIR = None


def env_for(home, extra=None):
    env = dict(os.environ)
    # Keep the operator's own provider settings (and log level) out of the run.
    for k in list(env):
        if k.startswith(("ARGO_", "AZURE_OPENAI_", "OPENAI_", "ANTHROPIC_")) or k == "RUST_LOG":
            env.pop(k)
    env.update(HOME=home, NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost")
    env.update(DEFAULT_ENV)
    if LIB_DIR:
        for k in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
            env[k] = LIB_DIR + (os.pathsep + env[k] if env.get(k) else "")
    env.update(extra or {})
    return env


def run_suite(suite, bins, work, files_dir):
    sdir = os.path.join(work, suite["name"])
    home = os.path.join(sdir, "home")
    os.makedirs(os.path.join(home, ".argo"), exist_ok=True)
    mock_port = free_port()
    mock_log = os.path.join(sdir, "llm.jsonl")
    dlog_path = os.path.join(sdir, "daemon.log")
    cfg = suite["config"].replace("{MOCK_URL}", f"http://127.0.0.1:{mock_port}/v1").replace("{FILES}", files_dir)
    with open(os.path.join(home, ".argo", "config.toml"), "w", encoding="utf-8") as f:
        f.write(cfg)
    binary = bins[suite["bin"]]
    env = env_for(home, suite.get("env"))
    mock = subprocess.Popen([sys.executable, os.path.join(HERE, "mock_llm.py"), str(mock_port), mock_log,
                             dlog_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    daemon = None
    results = []
    blocked_by = None
    try:
        time.sleep(0.5)
        for case in suite["cases"]:
            if blocked_by:
                results.append((case["name"], [f"not run: precondition failed in {blocked_by}"], ""))
                continue
            open(mock_log, "w").close()
            msg = case.get("message", "hi").replace("{FILES}", files_dir)
            segs = None
            if case["mode"] in ("single", "boot"):
                try:
                    p = subprocess.run([binary, msg], env=env, cwd=sdir, capture_output=True,
                                       text=True, timeout=TIMEOUT_SINGLE)
                    out = p.stdout + p.stderr + f"\n[exit={p.returncode}]"
                except subprocess.TimeoutExpired as e:
                    out = (e.stdout or "") + (e.stderr or "") + "\n[timeout]"
            else:
                if daemon is None:
                    daemon, dport = start_daemon(binary, env, sdir, dlog_path)
                    if daemon is None:
                        out = "daemon did not start:\n" + open(dlog_path, encoding="utf-8", errors="replace").read()[-2000:]
                        results.append((case["name"], ["daemon failed"], out))
                        continue
                before = os.path.getsize(dlog_path)
                session = case.get("session")
                session_id = re.sub(r"[^A-Za-z0-9_-]", "_", f"{suite['name']}-{session}") if session else None
                text = post_chat(dport, msg, dlog_path, session_id)
                time.sleep(1.0)
                with open(dlog_path, "rb") as f:
                    log_bytes = f.read()
                end = len(log_bytes)
                out = f"response: {text}\n" + log_bytes[before:end].decode("utf-8", "replace")
                calls, _ = read_log(mock_log)
                segs = segments([c for c in calls if c.get("has_tools")], log_bytes, before, end)
            calls, seen = read_log(mock_log)
            ev = {"output": out, "calls": calls, "seen": seen, "segments": segs}
            problems = judge(case, ev)
            pre = judge(case.get("require", {}), ev)
            if pre:
                blocked_by = case["name"]
                problems = [f"precondition: {p}" for p in pre] + problems
            results.append((case["name"], problems, out))
    finally:
        if daemon is not None and daemon.poll() is None:
            daemon.send_signal(signal.SIGTERM)
            try:
                daemon.wait(timeout=10)
            except subprocess.TimeoutExpired:
                daemon.kill()
        mock.terminate()
        mock.wait(timeout=5)
    return results


def start_daemon(binary, env, sdir, dlog):
    port = free_port()
    fh = open(dlog, "w", encoding="utf-8")
    proc = subprocess.Popen([binary, "--daemon", "--port", str(port)], env=env, cwd=sdir,
                            stdout=fh, stderr=subprocess.STDOUT)
    for _ in range(90):
        time.sleep(1)
        if proc.poll() is not None:
            return None, None
        if f"127.0.0.1:{port}" in open(dlog, encoding="utf-8", errors="replace").read():
            return proc, port
    proc.kill()
    return None, None


def boot_token(dlog):
    m = re.search(r"(?:boot token|token)[^A-Za-z0-9]*([A-Za-z0-9._-]{20,})",
                  open(dlog, encoding="utf-8", errors="replace").read())
    return m.group(1) if m else None


def post_chat(port, msg, dlog, session_id=None):
    payload = {"message": msg}
    if session_id:
        payload["session_id"] = session_id
    data = json.dumps(payload).encode()
    headers = {"content-type": "application/json"}
    for attempt in range(2):
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/v1/chat", data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_REQUEST) as r:
                body = r.read().decode("utf-8", "replace")
            try:
                return json.loads(body).get("text", body)[:300]
            except json.JSONDecodeError:
                return body[:300]
        except urllib.error.HTTPError as e:
            if e.code == 401 and attempt == 0 and (tok := boot_token(dlog)):
                headers["Authorization"] = f"token {tok}"
                continue
            return f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}"
        except Exception as e:  # noqa: BLE001 — report, don't crash the run
            return f"request failed: {e}"
    return "unauthorised"


def file_content(spec):
    if isinstance(spec, str):
        return spec
    return spec.get("head", "") + spec["repeat"] * int(spec["times"]) + spec.get("tail", "")


def check_spec(spec):
    """Problems with the spec's shape; [] when it is runnable."""
    errs = []

    def rx_ok(where, rx):
        try:
            re.compile(rx)
        except re.error as e:
            errs.append(f"{where}: bad regex /{rx}/: {e}")

    def check_judge(where, d, mode):
        for k in ("expect", "expect_not", "requests_all", "requests_any", "requests_none"):
            for rx in d.get(k, []):
                rx_ok(f"{where}.{k}", rx)
        if "tool_seen" in d:
            rx_ok(f"{where}.tool_seen", d["tool_seen"])
        for idx, rxs in d.get("request_at", {}).items():
            if not str(idx).isdigit():
                errs.append(f"{where}.request_at: index {idx!r} is not a number")
            for rx in rxs:
                rx_ok(f"{where}.request_at[{idx}]", rx)
        for i, chk in enumerate(d.get("call_log", [])):
            w = f"{where}.call_log[{i}]"
            if mode != "daemon":
                errs.append(f"{w}: call_log needs mode daemon")
            if not (isinstance(chk.get("call"), int) or chk.get("call") in ("after", "turn")):
                errs.append(f"{w}: call must be an int, \"after\" or \"turn\"")
            if "match" not in chk:
                errs.append(f"{w}: no match")
            else:
                rx_ok(w, chk["match"])
                if "range" in chk and re.compile(chk["match"]).groups < 1:
                    errs.append(f"{w}: range needs a capture group in match")
            if not any(k in chk for k in ("count", "min", "max", "range")):
                errs.append(f"{w}: asserts nothing (count/min/max/range)")
            extra = set(chk) - {"call", "match", "count", "min", "max", "range"}
            if extra:
                errs.append(f"{w}: unknown keys {sorted(extra)}")

    for name, content in spec.get("files", {}).items():
        if not isinstance(content, str) and not (isinstance(content, dict) and "repeat" in content
                                                 and "times" in content):
            errs.append(f"files.{name}: a string or {{head, repeat, times, tail}}")
    names = set()
    for s in spec.get("suites", []):
        sw = f"suite {s.get('name')}"
        if s.get("name") in names:
            errs.append(f"{sw}: duplicate name")
        names.add(s.get("name"))
        for k in ("name", "bin", "config", "cases"):
            if k not in s:
                errs.append(f"{sw}: no {k}")
        extra = set(s) - SUITE_KEYS
        if extra:
            errs.append(f"{sw}: unknown keys {sorted(extra)}")
        for c in s.get("cases", []):
            cw = f"{sw} / {c.get('name')}"
            mode = c.get("mode")
            if mode not in ("single", "daemon", "boot"):
                errs.append(f"{cw}: mode {mode!r}")
            extra = set(c) - CASE_KEYS
            if extra:
                errs.append(f"{cw}: unknown keys {sorted(extra)}")
            if "session" in c and mode != "daemon":
                errs.append(f"{cw}: session needs mode daemon")
            check_judge(cw, c, mode)
            req = c.get("require", {})
            extra = set(req) - set(JUDGE_KEYS)
            if extra:
                errs.append(f"{cw}.require: unknown keys {sorted(extra)}")
            check_judge(f"{cw}.require", req, mode)
    if not spec.get("suites"):
        errs.append("no suites")
    return errs


def main():
    global LIB_DIR
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    spec_path = args.pop(0)
    bins, only, keep, check = {}, None, False, False
    while args:
        a = args.pop(0)
        if a == "--bin":
            k, v = args.pop(0).split("=", 1)
            bins[k] = os.path.abspath(v)
        elif a == "--lib-dir":
            LIB_DIR = os.path.abspath(args.pop(0))
        elif a == "--only":
            only = args.pop(0)
        elif a == "--keep":
            keep = True
        elif a == "--check":
            check = True
        else:
            sys.exit(f"unknown argument {a!r}")
    spec = json.load(open(spec_path, encoding="utf-8"))
    errs = check_spec(spec)
    if check:
        for e in errs:
            print("SPEC ERROR:", e)
        n_cases = sum(len(s.get("cases", [])) for s in spec.get("suites", []))
        print(f"{spec_path}: {len(spec.get('suites', []))} suites, {n_cases} cases, "
              f"bins: {sorted({s.get('bin') for s in spec.get('suites', [])})}")
        sys.exit(1 if errs else 0)
    if errs:
        sys.exit("spec errors:\n  " + "\n  ".join(errs))
    if not bins:
        sys.exit("give at least one --bin NAME=PATH (the names the spec's suites use)")
    missing = sorted({s["bin"] for s in spec["suites"] if not only or s["name"] == only} - set(bins))
    if missing:
        sys.exit(f"spec needs --bin for: {', '.join(missing)}")
    work = tempfile.mkdtemp(prefix="argo-e2e-")
    files_dir = os.path.join(work, "files")
    os.makedirs(files_dir)
    for name, content in spec.get("files", {}).items():
        with open(os.path.join(files_dir, name), "w", encoding="utf-8") as f:
            f.write(file_content(content))
    failed = 0
    for suite in spec["suites"]:
        if only and suite["name"] != only:
            continue
        print(f"\n=== suite {suite['name']} (bin={suite['bin']})")
        for name, problems, out in run_suite(suite, bins, work, files_dir):
            status = "PASS" if not problems else "FAIL"
            failed += bool(problems)
            print(f"  [{status}] {name}")
            if problems:
                for pr in problems:
                    print(f"         - {pr}")
                tail = "\n".join(l for l in out.splitlines() if l.strip())[-1200:]
                if tail:
                    print("         output tail:\n" + "\n".join("           " + l for l in tail.splitlines()))
    print(f"\nwork dir: {work}" + ("" if keep else " (removed)"))
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    print("RESULT:", "ALL PASS" if not failed else f"{failed} FAILED")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
