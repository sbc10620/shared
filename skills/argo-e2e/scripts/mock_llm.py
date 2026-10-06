#!/usr/bin/env python3
"""OpenAI-compatible mock LLM for ARGO release end-to-end runs.

usage: mock_llm.py <port> <log.jsonl>

Behaviour (deterministic, no network):
  * A user message containing `READFILE <path>` makes the mock answer with a
    `file_read` tool call for <path>. The newest such user message wins.
  * Once a tool result is in the history, the mock answers
    `FINAL: tool said -> <first 160 chars of the last tool result>` — so the
    reply shows exactly what the model was handed (the tool-output guardrail
    replaces a blocked result before the model sees it).
  * Otherwise it answers `plain reply`.

Every request is appended to the log as one JSON line ({"call": …}); every
tool result the mock sees is logged as {"tool_seen": …}. The driver counts
LLM calls and reads the tool result from there. Supports `stream: true`
(SSE chunks) and plain JSON responses.
"""
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(sys.argv[1])
LOG = sys.argv[2]


def log(obj):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def text(m):
    c = m.get("content")
    if isinstance(c, list):
        return " ".join(p.get("text", "") for p in c if isinstance(p, dict))
    return c or ""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        msgs = body.get("messages", [])
        log({"call": {"path": self.path, "n_messages": len(msgs),
                      "last_role": (msgs[-1] if msgs else {}).get("role")}})
        tools = [m for m in msgs if m.get("role") == "tool"]
        users = [text(m) for m in msgs if m.get("role") == "user"]
        want = next((x for x in (re.search(r"READFILE (\S+)", u) for u in reversed(users)) if x), None)
        if tools:
            seen = text(tools[-1])
            log({"tool_seen": seen[:600]})
            reply = {"content": "FINAL: tool said -> " + seen[:160].replace("\n", " ")}
        elif want:
            reply = {"tool_calls": [{"id": "call_1", "type": "function", "function": {
                "name": "file_read", "arguments": json.dumps({"path": want.group(1)})}}]}
        else:
            reply = {"content": "plain reply"}
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


HTTPServer(("127.0.0.1", PORT), H).serve_forever()
