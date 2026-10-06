#!/usr/bin/env python3
"""OpenAI-compatible mock LLM for argo-tizen (`argot`) end-to-end runs.

usage: mock_llm.py <port> <log.jsonl>

Deterministic, no network. The directive is read from the newest user
message that carries one (the trailing `<turn-context>` carrier never does):

  TOOL <name> <json-args>   first call: a tool call to <name> with <json-args>;
                            once a tool result follows, `FINAL: <result head>`.
  RESUME-PLAY <key>         a routine fire that survives a daemon crash:
                            first a `bash_run` tool call, then — the first time
                            a tool result is seen for <key> — the reply is
                            HELD (the connection stays open, logged as
                            {"stalled": key}) so the driver can kill the
                            daemon mid-turn; every later call answers
                            `recovered final answer`.
  anything else             `plain reply`.

A request that offers `tools` is the agent loop's turn ("kind": "turn");
one without is an auxiliary call such as memory extraction ("aux"). Every
request is appended to the log as {"call": {...}} with the text of every
non-system message, so the driver can count turns and check what the model
was actually sent (PII masking). Supports `stream: true` (SSE) and JSON.
"""
import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1])
LOG = sys.argv[2]
LOCK = threading.Lock()
STALLED = set()
RELEASE = threading.Event()


def log(obj):
    with LOCK:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def text(m):
    c = m.get("content")
    if isinstance(c, list):
        return " ".join(p.get("text", "") for p in c if isinstance(p, dict))
    return c or ""


def directive(msgs):
    """(kind, match, index of the user message carrying it) or (None, None, -1)."""
    for i in range(len(msgs) - 1, -1, -1):
        m = msgs[i]
        if m.get("role") != "user":
            continue
        t = text(m)
        if t.lstrip().startswith("<turn-context>"):
            continue  # the runtime's own carrier, never a directive
        r = re.search(r"TOOL (\w+) (\{.*\})", t, re.S)
        if r:
            return "tool", r, i
        r = re.search(r"RESUME-PLAY (\S+)", t)
        if r:
            return "resume", r, i
    return None, None, -1


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self):
        # The driver's readiness probe.
        data = b"ok"
        self.send_response(200)
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        msgs = body.get("messages", [])
        kind = "turn" if body.get("tools") else "aux"
        log({"call": {"path": self.path, "kind": kind, "stream": bool(body.get("stream")),
                      "texts": [text(m) for m in msgs if m.get("role") != "system"]}})
        reply = {"content": "plain reply"}
        if kind == "turn":
            d, m, at = directive(msgs)
            tool_after = [x for x in msgs[at + 1:] if x.get("role") == "tool"] if d else []
            if d == "tool":
                if tool_after:
                    reply = {"content": "FINAL: " + text(tool_after[-1])[:160].replace("\n", " ")}
                else:
                    reply = {"tool_calls": [{"id": "call_1", "type": "function", "function": {
                        "name": m.group(1), "arguments": m.group(2)}}]}
            elif d == "resume":
                key = m.group(1)
                if not tool_after:
                    reply = {"tool_calls": [{"id": "call_1", "type": "function", "function": {
                        "name": "bash_run", "arguments": json.dumps({"command": "printf resume-ok"})}}]}
                else:
                    with LOCK:
                        first = key not in STALLED
                        STALLED.add(key)
                    if first:
                        log({"stalled": key})
                        # Hold the turn open until the daemon is killed (the
                        # socket breaks) or the driver gives up.
                        RELEASE.wait(600)
                        return
                    reply = {"content": "recovered final answer"}
        fin = "tool_calls" if "tool_calls" in reply else "stop"
        try:
            if body.get("stream"):
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.send_header("connection", "close")
                self.end_headers()
                delta = {"role": "assistant"}
                if "content" in reply:
                    delta["content"] = reply["content"]
                if "tool_calls" in reply:
                    delta["tool_calls"] = [dict(tc, index=0) for tc in reply["tool_calls"]]
                for ch in (
                    {"id": "c", "object": "chat.completion.chunk", "model": "mock-model",
                     "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                    {"id": "c", "object": "chat.completion.chunk", "model": "mock-model",
                     "choices": [{"index": 0, "delta": {}, "finish_reason": fin}]},
                    {"id": "c", "object": "chat.completion.chunk", "model": "mock-model", "choices": [],
                     "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
                ):
                    self.wfile.write(("data: " + json.dumps(ch) + "\n\n").encode())
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
                self.close_connection = True
                return
            msg = {"role": "assistant", "content": reply.get("content")}
            if "tool_calls" in reply:
                msg["tool_calls"] = reply["tool_calls"]
            data = json.dumps({"id": "c", "object": "chat.completion", "model": "mock-model",
                               "choices": [{"index": 0, "message": msg, "finish_reason": fin}],
                               "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                                         "total_tokens": 2}}).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
