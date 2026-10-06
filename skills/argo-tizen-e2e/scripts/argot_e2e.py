#!/usr/bin/env python3
"""Run an argo-tizen spec against the real `argot` binary and a mock LLM.

usage: argot_e2e.py <spec.json> --bin <argot> [--only <suite>] [--keep]

Spec schema:
{
  "suites": [{
    "name": "pg-on",
    "config": "<TOML appended to the base config>",
    "boot": "ok" | "refuse",                 # default "ok"
    "boot_expect": ["<regex>", ...],         # refuse: matched against the daemon's output
    "cases": [{
      "name": "...", "prompt": "...",
      "expect": {
        "refused":     true | false,         # the neutral guard refusal was the reply
        "turn_calls":  <int>,                # agent-loop LLM calls this case made
        "persisted":   true | false,         # the prompt is in the conversation history
        "events":      ["rule:action", ...], # prompt_guard.match events, exact (order-free)
        "llm_saw":     ["<regex>", ...],     # over the text the model was sent
        "llm_not_saw": ["<regex>", ...],
        "reply":       "<regex>"             # over the completed reply text
      }}],
    "resume": {                              # optional, runs after the cases
      "key": "<unique word>",
      "expect_completed": true,              # the resumed fire finished its turn
      "events_absent": ["<rule id>", ...]    # no such prompt_guard.match during the run
    }
  }]
}

Each suite gets its own HOME, ARGOT_DATA_ROOT, free mock and daemon ports,
and a fresh daemon; provider environment variables are stripped. Processes
are stopped by PID only. Exit 1 when any check fails.
"""
import argparse
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
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REFUSAL = "I can't help with that request."
STRIP = ("ARGOT_", "ARGO_", "OPENAI_", "ANTHROPIC_", "AZURE_OPENAI_", "GEMINI_", "GOOGLE_API")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


class Suite:
    def __init__(self, spec, argot, keep):
        self.spec, self.argot, self.keep = spec, argot, keep
        self.work = tempfile.mkdtemp(prefix=f"argot-e2e-{spec['name']}-")
        self.root = os.path.join(self.work, "root")
        os.makedirs(self.root)
        os.makedirs(os.path.join(self.work, "home"))
        self.llm_log = os.path.join(self.work, "llm.jsonl")
        self.mock_port, self.daemon_port = free_port(), free_port()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(STRIP)}
        self.env.update(HOME=os.path.join(self.work, "home"), ARGOT_DATA_ROOT=self.root,
                        ARGOT_BIND=f"127.0.0.1:{self.daemon_port}", TZ="UTC", RUST_LOG="info")
        self.mock = self.daemon = None
        self.results = []

    # ---- processes -------------------------------------------------------
    def start_mock(self):
        self.mock = subprocess.Popen([sys.executable, os.path.join(HERE, "mock_llm.py"),
                                      str(self.mock_port), self.llm_log])
        for _ in range(100):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.mock_port}/", timeout=1)
                return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("mock LLM did not come up")

    def write_config(self):
        base = (f'target_source = "config"\nprovider = "openai"\nmodel = "mock-model"\n'
                f'base_url = "http://127.0.0.1:{self.mock_port}/v1"\napi_key = "mock-key"\n')
        with open(os.path.join(self.root, "config.toml"), "w", encoding="utf-8") as f:
            f.write(base + "\n" + self.spec.get("config", "") + "\n")

    def start_daemon(self):
        out = open(os.path.join(self.work, "daemon.out"), "a")
        self.daemon = subprocess.Popen([self.argot, "daemon"], env=self.env,
                                       stdout=out, stderr=subprocess.STDOUT)

    def wait_ready(self, timeout=90):
        end = time.time() + timeout
        while time.time() < end:
            if self.daemon.poll() is not None:
                return False
            if self.cli(["status", "--json"], timeout=10).returncode == 0:
                return True
            time.sleep(0.3)
        return False

    def stop_daemon(self, sig=signal.SIGTERM):
        if self.daemon and self.daemon.poll() is None:
            self.daemon.send_signal(sig)
            try:
                self.daemon.wait(30)
            except subprocess.TimeoutExpired:
                self.daemon.kill()
                self.daemon.wait()

    def cleanup(self):
        self.stop_daemon()
        if self.mock and self.mock.poll() is None:
            self.mock.terminate()
            self.mock.wait()
        if not self.keep:
            shutil.rmtree(self.work, ignore_errors=True)

    def cli(self, args, timeout=120):
        return subprocess.run([self.argot, *args], env=self.env, capture_output=True,
                              text=True, timeout=timeout)

    # ---- observations ----------------------------------------------------
    def turn_calls(self):
        return [r["call"] for r in read_jsonl(self.llm_log) if "call" in r and r["call"]["kind"] == "turn"]

    def daemon_text(self):
        parts = []
        for p in (os.path.join(self.work, "daemon.out"),
                  os.path.join(self.root, "logs", "argot-daemon.log")):
            if os.path.exists(p):
                with open(p, encoding="utf-8", errors="replace") as f:
                    parts.append(f.read())
        return "\n".join(parts)

    def events(self):
        path = os.path.join(self.root, "logs", "argot-daemon.log")
        if not os.path.exists(path):
            return []
        out = []
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if "prompt_guard.match" not in line:
                    continue
                rule = re.search(r'rule_id[=:]\s*"?([\w.\-]+)', line)
                action = re.search(r'action[=:]\s*"?(\w+)', line)
                out.append(f"{rule.group(1) if rule else '?'}:{action.group(1) if action else '?'}")
        return out

    def persisted(self, conv, prompt):
        r = self.cli(["conversations", "show", conv, "--json"])
        for line in r.stdout.splitlines():
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            if m.get("role") == "user" and prompt in (m.get("text") or ""):
                return True
        return False

    # ---- checks ----------------------------------------------------------
    def check(self, label, ok, detail=""):
        self.results.append((label, ok, detail))

    def run_case(self, i, case):
        exp = case.get("expect", {})
        conv = f"case-{i}"
        calls0, ev0 = len(self.turn_calls()), len(self.events())
        r = self.cli(["--new", "-c", conv, "-p", case["prompt"], "--json"])
        reply = None
        for line in r.stdout.splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "completed" in ev:
                reply = ev["completed"].get("text")
        time.sleep(0.5)  # let the log writer flush the turn's events
        calls = self.turn_calls()[calls0:]
        events = self.events()[ev0:]
        sent = "\n".join(t for c in calls for t in c["texts"])
        name = f"{case['name']}"
        if "refused" in exp:
            self.check(f"{name}: refused={exp['refused']}", (reply == REFUSAL) == exp["refused"],
                       f"reply={reply!r} exit={r.returncode} stderr={r.stderr[-300:]!r}")
        if "turn_calls" in exp:
            self.check(f"{name}: turn_calls={exp['turn_calls']}", len(calls) == exp["turn_calls"],
                       f"got {len(calls)}")
        if "persisted" in exp:
            got = self.persisted(conv, case["prompt"])
            self.check(f"{name}: persisted={exp['persisted']}", got == exp["persisted"], f"got {got}")
        if "events" in exp:
            self.check(f"{name}: events={sorted(exp['events'])}",
                       sorted(events) == sorted(exp["events"]), f"got {events}")
        for rx in exp.get("llm_saw", []):
            self.check(f"{name}: model was sent /{rx}/", re.search(rx, sent) is not None,
                       f"sent={sent[:300]!r}")
        for rx in exp.get("llm_not_saw", []):
            self.check(f"{name}: model was NOT sent /{rx}/", re.search(rx, sent) is None,
                       f"sent={sent[:300]!r}")
        if "reply" in exp:
            self.check(f"{name}: reply /{exp['reply']}/", re.search(exp["reply"], reply or "") is not None,
                       f"reply={reply!r}")

    def run_resume(self, spec):
        key = spec["key"]
        name = f"e2e-resume-{key}"
        args = json.dumps({"name": name, "schedule_expr": "0 0 1 1 *",
                           "prompt": f"RESUME-PLAY {key}", "runs_remaining": 1})
        r = self.cli(["--new", "-c", "resume-author", "-p", f"TOOL cron_create {args}", "--json"])
        listing = self.cli(["routine", "--all", "--json"]).stdout
        rid = conv = None
        for line in listing.splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("name") == name:
                rid, conv = row.get("id"), row.get("conversation_id")
        if not rid:
            self.check("resume: routine created", False, f"author={r.stdout[-300:]!r} list={listing[:300]!r}")
            return
        ev0 = len(self.events())
        self.cli(["routine", "run", rid])
        end = time.time() + 60
        while time.time() < end and not any(x.get("stalled") == key for x in read_jsonl(self.llm_log)):
            time.sleep(0.2)
        stalled = any(x.get("stalled") == key for x in read_jsonl(self.llm_log))
        self.check("resume: fire reached its held turn", stalled)
        if not stalled:
            return
        self.stop_daemon(signal.SIGKILL)
        calls0 = len(self.turn_calls())
        self.start_daemon()
        if not self.wait_ready():
            self.check("resume: daemon restarted", False, self.daemon_text()[-500:])
            return
        end = time.time() + 60
        done = False
        while time.time() < end and not done:
            done = any(f"RESUME-PLAY {key}" in t for c in self.turn_calls()[calls0:] for t in c["texts"])
            if not done:
                time.sleep(0.3)
        time.sleep(1.0)
        if spec.get("expect_completed", True):
            # A routine fire talks in the routine's own conversation, which the
            # plain conversation listing does not show.
            found = bool(conv) and "recovered final answer" in self.cli(
                ["conversations", "show", conv, "--json"]).stdout
            self.check("resume: resumed fire completed after the crash", done and found,
                       f"post-restart turn call={done} reply found={found}")
        events = self.events()[ev0:]
        for rule in spec.get("events_absent", []):
            self.check(f"resume: no {rule} event", not any(e.startswith(rule + ":") for e in events),
                       f"got {events}")

    def run(self):
        self.start_mock()
        self.write_config()
        self.start_daemon()
        if self.spec.get("boot", "ok") == "refuse":
            try:
                self.daemon.wait(60)
                exited = True
            except subprocess.TimeoutExpired:
                exited = False
            self.check("boot refused", exited and self.daemon.returncode != 0,
                       f"exited={exited} code={self.daemon.returncode}")
            text = self.daemon_text()
            for rx in self.spec.get("boot_expect", []):
                self.check(f"boot output /{rx}/", re.search(rx, text) is not None, text[-400:])
            return
        if not self.wait_ready():
            self.check("daemon booted", False, self.daemon_text()[-600:])
            return
        for i, case in enumerate(self.spec.get("cases", [])):
            self.run_case(i, case)
        if "resume" in self.spec:
            self.run_resume(self.spec["resume"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--bin", required=True, help="the argot binary")
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--keep", action="store_true", help="keep each suite's work dir")
    a = ap.parse_args()
    spec = json.load(open(a.spec, encoding="utf-8"))
    argot = os.path.abspath(a.bin)
    failed = 0
    for s in spec["suites"]:
        if a.only and s["name"] not in a.only:
            continue
        suite = Suite(s, argot, a.keep)
        try:
            suite.run()
        except Exception as e:  # report and move on to the next suite
            suite.check("suite ran", False, repr(e))
        finally:
            suite.cleanup()
        bad = [r for r in suite.results if not r[1]]
        failed += len(bad)
        print(f"== {s['name']}: {'PASS' if not bad else 'FAIL'} "
              f"({len(suite.results) - len(bad)}/{len(suite.results)})"
              + (f"  [kept {suite.work}]" if a.keep else ""))
        for label, ok, detail in suite.results:
            print(f"   {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f"\n        {detail}"))
    print("RESULT:", "PASS" if failed == 0 else f"FAIL ({failed})")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
