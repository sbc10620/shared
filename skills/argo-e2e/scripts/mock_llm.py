#!/usr/bin/env python3
"""OpenAI-compatible mock LLM for ARGO release end-to-end runs.

usage: mock_llm.py <port> <log.jsonl> [<daemon.log>]

Behaviour (deterministic, no network). The "current user message" is the
newest user message that is not runtime-authored — not the `<turn-context>`
carrier and not the tool-failure nudge, both of which reach the wire as
user-role messages.

  * `READFILES <p1> <p2> ... [ECHOFULL:<n>[,<m>...]]` in the current user message
    runs a tool SEQUENCE for this turn: with k tool results after that
    message, the mock asks for `file_read` of p(k+1); once every path has a
    result it answers `FINAL: tool said -> <first 160 chars of the last
    result>`, or, with `ECHOFULL:<n>,<m>`, `FINAL: tool said -> <the whole
    n-th and m-th results of this turn, newline-joined>` (so tool results
    come back as one big stored assistant reply). A request that offers no tools (a background call:
    title, memorize, ...) never gets a tool call; it gets `plain reply`.
  * Otherwise (the original single-step behaviour): once a tool result is
    anywhere in the history the mock answers `FINAL: tool said -> <first 160
    chars of the last tool result>`; else `READFILE <path>` in a user message
    (the newest such message wins) makes it answer with a `file_read` tool
    call; else it answers `plain reply`.

Every request is appended to the log as one JSON line ({"call": {...}}),
holding the request's flattened text (every message's role, text and tool
call arguments), whether it offered tools, the current user message, and —
when a daemon log path is given — that file's size at the moment the
request arrived (`log_offset`), which lets the driver attribute daemon log
lines to the request they were written before. Every tool result the mock
answers from is logged as {"tool_seen": ...}. Supports `stream: true` (SSE
chunks) and plain JSON responses.
"""
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

LOG = None
DAEMON_LOG = None

CARRIER = "<turn-context>"
NUDGE = "One or more tool calls failed"


def log(obj):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def text(m):
    c = m.get("content")
    if isinstance(c, list):
        return " ".join(p.get("text", "") for p in c if isinstance(p, dict))
    return c or ""


def flatten(msgs):
    """Every message's role, text and tool-call arguments, one per line."""
    out = []
    for m in msgs:
        parts = [text(m)]
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function") or {}
            parts.append(f"{fn.get('name', '')}({fn.get('arguments', '')})")
        out.append(f"[{m.get('role')}] " + " ".join(p for p in parts if p))
    return "\n".join(out)


def runtime_authored(t):
    return t.lstrip().startswith(CARRIER) or NUDGE in t


def current_user(msgs):
    """(index, text) of the newest user message the user wrote, or (None, "")."""
    for i in range(len(msgs) - 1, -1, -1):
        m = msgs[i]
        if m.get("role") == "user" and not runtime_authored(text(m)):
            return i, text(m)
    return None, ""


def tool_call(call_id, path):
    return {"tool_calls": [{"id": call_id, "type": "function", "function": {
        "name": "file_read", "arguments": json.dumps({"path": path})}}]}


def decide(msgs, has_tools):
    """(reply, tool result the reply is built from or None)."""
    cur_idx, cur = current_user(msgs)
    seq = re.search(r"READFILES[ \t]+([^\n]+)", cur)
    if seq:
        tokens = seq.group(1).split()
        paths = [t for t in tokens if not t.startswith("ECHOFULL:")]
        echo = next(([int(x) for x in t.split(":", 1)[1].split(",")]
                     for t in tokens if t.startswith("ECHOFULL:")), None)
        results = [text(m) for m in msgs[cur_idx + 1:] if m.get("role") == "tool"]
        if not has_tools:
            return {"content": "plain reply"}, None
        if len(results) < len(paths):
            k = len(results)
            return tool_call(f"call_{cur_idx}_{k}", paths[k]), None
        seen = results[-1] if results else ""
        if echo and all(1 <= n <= len(results) for n in echo):
            return {"content": "FINAL: tool said -> " + "\n".join(results[n - 1] for n in echo)}, seen
        return {"content": "FINAL: tool said -> " + seen[:160].replace("\n", " ")}, seen

    tools = [m for m in msgs if m.get("role") == "tool"]
    users = [text(m) for m in msgs if m.get("role") == "user"]
    want = next((x for x in (re.search(r"READFILE (\S+)", u) for u in reversed(users)) if x), None)
    if tools:
        seen = text(tools[-1])
        return {"content": "FINAL: tool said -> " + seen[:160].replace("\n", " ")}, seen
    if want:
        return tool_call("call_1", want.group(1)), None
    return {"content": "plain reply"}, None


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        # Taken first: every daemon log line written before this request
        # arrived (the request's own masking pass included) is below it.
        offset = None
        if DAEMON_LOG and os.path.exists(DAEMON_LOG):
            offset = os.path.getsize(DAEMON_LOG)
        n = int(self.headers.get("content-length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        msgs = body.get("messages", [])
        has_tools = bool(body.get("tools"))
        _, cur = current_user(msgs)
        log({"call": {"path": self.path, "n_messages": len(msgs),
                      "last_role": (msgs[-1] if msgs else {}).get("role"),
                      "has_tools": has_tools, "log_offset": offset,
                      "current": cur[:300], "text": flatten(msgs)}})
        reply, seen = decide(msgs, has_tools)
        if seen is not None:
            log({"tool_seen": seen[:600]})
        fin = "tool_calls" if "tool_calls" in reply else "stop"
        if body.get("stream"):
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
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
            return
        msg = {"role": "assistant", "content": reply.get("content")}
        if "tool_calls" in reply:
            msg["tool_calls"] = reply["tool_calls"]
        data = json.dumps({"id": "c", "object": "chat.completion", "model": "mock-model",
                           "choices": [{"index": 0, "message": msg, "finish_reason": fin}],
                           "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    LOG = sys.argv[2]
    DAEMON_LOG = sys.argv[3] if len(sys.argv) > 3 else None
    HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
