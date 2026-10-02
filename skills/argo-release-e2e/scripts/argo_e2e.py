#!/usr/bin/env python3
"""Drive ARGO release binaries against a mock LLM and judge each case.

usage: argo_e2e.py <spec.json> --bin NAME=PATH [--bin NAME=PATH ...]
                   [--lib-dir DIR] [--only SUITE] [--keep]

  --lib-dir  directory holding libobjectbox (build_release.sh writes it to
             <out-dir>/libdir.txt); exported as LD_LIBRARY_PATH and
             DYLD_LIBRARY_PATH for a binary built without an rpath to it.
             Not needed on macOS when build_release.sh added the rpath.

The spec (JSON) holds:
  "files":  {name: content}           fixtures written to <work>/files/
  "suites": [ {
      "name":   str,
      "bin":    NAME                   a --bin NAME, e.g. "guard" / "noguard"
      "config": str                    config.toml text; {MOCK_URL} and {FILES}
                                       are substituted
      "env":    {K: V}                 optional extra env (on top of
                                       ARGO_PROVIDER=openai_compat,
                                       ARGO_MODEL=mock-model)
      "cases":  [ {
          "name":     str,
          "mode":     "single" | "daemon" | "boot",
          "message":  str              {FILES} substituted; "boot" may omit it
          "expect":   [regex, ...]     each must match the case's output
          "expect_not": [regex, ...]   none may match
          "llm_calls": int             optional exact LLM request count
          "tool_seen": regex           optional; must match what the model got
      } ]
  } ]

Each suite gets a fresh HOME (<work>/<suite>/home) with the config at
~/.argo/config.toml, and its own mock LLM on a free port. "single" runs
`argo "<message>"` (one-shot); "boot" is the same run, read as "did the boot
refuse" (expect the refusal text); "daemon" starts `argo --daemon` on a free
port once per suite and POSTs each message to /api/v1/chat, judging the
response text plus the daemon's stderr lines written during that request.

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
TIMEOUT_REQUEST = 120


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def read_log(path):
    calls, seen = 0, None
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            d = json.loads(line)
            if "call" in d:
                calls += 1
            elif "tool_seen" in d:
                seen = d["tool_seen"]
    return calls, seen


def judge(case, output, calls, seen):
    problems = []
    for rx in case.get("expect", []):
        if not re.search(rx, output, re.S):
            problems.append(f"missing /{rx}/")
    for rx in case.get("expect_not", []):
        if re.search(rx, output, re.S):
            problems.append(f"unexpected /{rx}/")
    if "llm_calls" in case and calls != case["llm_calls"]:
        problems.append(f"llm_calls={calls} (want {case['llm_calls']})")
    if "tool_seen" in case and not (seen and re.search(case["tool_seen"], seen, re.S)):
        problems.append(f"tool_seen={seen!r} !~ /{case['tool_seen']}/")
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
    # Keep the operator's own provider settings out of the run.
    for k in list(env):
        if k.startswith(("ARGO_", "AZURE_OPENAI_", "OPENAI_", "ANTHROPIC_")):
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
    cfg = suite["config"].replace("{MOCK_URL}", f"http://127.0.0.1:{mock_port}/v1").replace("{FILES}", files_dir)
    with open(os.path.join(home, ".argo", "config.toml"), "w", encoding="utf-8") as f:
        f.write(cfg)
    binary = bins[suite["bin"]]
    env = env_for(home, suite.get("env"))
    mock = subprocess.Popen([sys.executable, os.path.join(HERE, "mock_llm.py"), str(mock_port), mock_log],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    daemon = None
    results = []
    try:
        time.sleep(0.5)
        for case in suite["cases"]:
            open(mock_log, "w").close()
            msg = case.get("message", "hi").replace("{FILES}", files_dir)
            if case["mode"] in ("single", "boot"):
                try:
                    p = subprocess.run([binary, msg], env=env, cwd=sdir, capture_output=True,
                                       text=True, timeout=TIMEOUT_SINGLE)
                    out = p.stdout + p.stderr + f"\n[exit={p.returncode}]"
                except subprocess.TimeoutExpired as e:
                    out = (e.stdout or "") + (e.stderr or "") + "\n[timeout]"
            else:
                if daemon is None:
                    daemon, dlog, dport = start_daemon(binary, env, sdir)
                    if daemon is None:
                        out = "daemon did not start:\n" + open(dlog, encoding="utf-8", errors="replace").read()[-2000:]
                        results.append((case["name"], ["daemon failed"], out))
                        continue
                before = os.path.getsize(dlog)
                text = post_chat(dport, msg, dlog)
                time.sleep(1.0)
                with open(dlog, encoding="utf-8", errors="replace") as f:
                    f.seek(before)
                    new = f.read()
                out = f"response: {text}\n{new}"
            calls, seen = read_log(mock_log)
            results.append((case["name"], judge(case, out, calls, seen), out))
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


def start_daemon(binary, env, sdir):
    port = free_port()
    dlog = os.path.join(sdir, "daemon.log")
    fh = open(dlog, "w", encoding="utf-8")
    proc = subprocess.Popen([binary, "--daemon", "--port", str(port)], env=env, cwd=sdir,
                            stdout=fh, stderr=subprocess.STDOUT)
    for _ in range(90):
        time.sleep(1)
        if proc.poll() is not None:
            return None, dlog, None
        if f"127.0.0.1:{port}" in open(dlog, encoding="utf-8", errors="replace").read():
            return proc, dlog, port
    proc.kill()
    return None, dlog, None


def boot_token(dlog):
    m = re.search(r"(?:boot token|token)[^A-Za-z0-9]*([A-Za-z0-9._-]{20,})",
                  open(dlog, encoding="utf-8", errors="replace").read())
    return m.group(1) if m else None


def post_chat(port, msg, dlog):
    data = json.dumps({"message": msg}).encode()
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


def main():
    global LIB_DIR
    args = sys.argv[1:]
    spec_path = args.pop(0)
    bins, only, keep = {}, None, False
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
    if not bins:
        sys.exit("give at least one --bin NAME=PATH (the names the spec's suites use)")
    spec = json.load(open(spec_path, encoding="utf-8"))
    missing = sorted({s["bin"] for s in spec["suites"] if not only or s["name"] == only} - set(bins))
    if missing:
        sys.exit(f"spec needs --bin for: {', '.join(missing)}")
    work = tempfile.mkdtemp(prefix="argo-e2e-")
    files_dir = os.path.join(work, "files")
    os.makedirs(files_dir)
    for name, content in spec.get("files", {}).items():
        with open(os.path.join(files_dir, name), "w", encoding="utf-8") as f:
            f.write(content)
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
                print("         output tail:\n" + "\n".join("           " + l for l in tail.splitlines()))
    print(f"\nwork dir: {work}" + ("" if keep else " (removed)"))
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    print("RESULT:", "ALL PASS" if not failed else f"{failed} FAILED")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
