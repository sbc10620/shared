---
name: argo-e2e
description: Verify an ARGO change by RUNNING the real release `argo` binaries (with and without the `guardrails` feature) against a deterministic mock LLM — single-shot, daemon (/api/v1/chat) and boot-refusal cases, judged automatically. Use when asked for an actual run / real-execution check ("실제 실행 검증", "mock LLM으로 돌려봐", "release 빌드로 확인") of guardrails, prompt guard, PII or config-loading behaviour in an ARGO checkout.
---

# ARGO release end-to-end run

Unit tests prove functions; this proves the shipped binary: config.toml →
boot checks → REPL/daemon path → LLM request → tool call → tool-output
guardrail → what the model actually received. Every case is judged by regex
on the output, the number of LLM requests the mock saw, and the tool result
the mock was handed — so "the turn never reached the model" and "the model
got the blocked placeholder, not the payload" are asserted, not eyeballed.

Works with any agent or by hand: everything is a shell script or a
standard-library Python 3.8+ script. Paths below are relative to this
skill's directory (`SKILL_DIR`, the directory holding this file).

## Files

- `scripts/build_release.sh` — builds both release binaries from an ARGO
  checkout and copies them out.
- `scripts/mock_llm.py` — OpenAI-compatible mock. `READFILE <path>` in a user
  message → one `file_read` tool call; after a tool result → `FINAL: tool said
  -> <result>`; else `plain reply`. `READFILES <p1> <p2> … [ECHOFULL:<n>[,<m>…]]` in
  the current user message runs a tool sequence for that turn (one
  `file_read` per request, then a final answer; `ECHOFULL:<n>,<m>` echoes
  those whole results so they are stored as one big assistant reply). The
  `<turn-context>` carrier and the tool-failure nudge are user-role messages
  on the wire and are never taken as the current user message. Logs every
  request (flattened text, whether it offered tools, the daemon log's size
  when it arrived) and every tool result it answered from.
- `scripts/argo_e2e.py` — the driver. The spec schema is in its docstring;
  `--check` validates a spec (keys, modes, regexes) without running anything.
- `specs/guardrails-config.json` — the `[prompt_guard]`, `[tool_output_guard]`
  and `[pii]` config sections: prompt guard on/off against `ignore_prior`,
  tool-output guard withholding a blocked result (and `labels` narrowing or
  warning), PII refusal (`block_only`, narrowed by dotted
  `filter_labels.input`) and masking (`full`, inline tables), the old flat
  keys (`pii_mode`, `user_input_prompt_injection_mode`, …) being ignored
  silently, every boot refusal (unknown key in each section, misspelled
  mode, unknown label, unknown filter-labels layer — whatever the mode), and
  the `noguard` build reporting the sections as ignored.
- `specs/pii-masking-cache.json` — the outbound masking scan cache on the
  daemon path: one conversation, three turns, PII mode `full`, a failed tool
  call, two ~45 KB files with PII; asserts no raw PII ever reaches the model
  and counts the large-scan debug lines per LLM call (see Masking-cache
  check).

## Requirements

- An ARGO checkout with a Rust toolchain (`cargo`); macOS or Linux.
- Python 3.8+ (`python3`). No third-party packages.
- Disk and time for a release build (a cold one takes tens of minutes).

## Steps

1. **Build both binaries** into a directory of your choice (`BINS`):
   ```bash
   BINS=/tmp/argo-e2e-bins
   "$SKILL_DIR/scripts/build_release.sh" /path/to/ARGO "$BINS"
   ```
   - Produces `$BINS/argo-guardrails` and `$BINS/argo-noguard` (identical
     features except `guardrails`) and `$BINS/libdir.txt`.
   - The `webui` feature is off by default: the specs do not need it, and it
     needs npm. `WEBUI=1` turns it on (see Known issues).
   - Run it in the background and write the spec meanwhile. Read the build
     output for `error[` — a failed build copies nothing.
   - Note the commit the binaries were built at (`git log -1 --oneline`).
2. **Pick or write a spec** in `specs/`. Assert behaviour, not wording where
   wording is localised: match rule ids (`ignore_prior`), key paths
   (`prompt_guard\.mode`, `unknown key .mdoe. in \[prompt_guard\]`),
   `llm_calls` (0 = refused before the model), `tool_seen` (what the model
   got), `requests_*` (what every request carried). Boot cases expect
   `refusing to start` plus the specific reason. Check it with
   `python3 "$SKILL_DIR/scripts/argo_e2e.py" <spec> --check`.
3. **Run**:
   ```bash
   python3 "$SKILL_DIR/scripts/argo_e2e.py" "$SKILL_DIR/specs/<spec>.json" \
     --bin guard="$BINS/argo-guardrails" --bin noguard="$BINS/argo-noguard" \
     --lib-dir "$(cat "$BINS/libdir.txt")"
   ```
   - `--lib-dir` is needed on Linux; on macOS the build script already put
     the library on the binaries' rpath, and passing it is harmless.
   - `--only <suite>` runs one suite; `--keep` keeps the work dir (HOME,
     daemon.log, llm.jsonl) for inspection.
4. **Report** PASS/FAIL per suite/case together with the build commit. For a
   FAIL, decide from the kept logs whether the code or the spec is wrong —
   never loosen a regex just to make a case pass.

## Isolation rules (non-negotiable)

- Each suite runs with its own temporary `HOME` — never the operator's
  `~/.argo`.
- The driver picks free ports for the mock and the daemon — never 42617, the
  default an operator's own daemon may hold.
- Provider env vars (`ARGO_*`, `AZURE_OPENAI_*`, `OPENAI_*`, `ANTHROPIC_*`) and
  `RUST_LOG` are stripped so no real provider is ever called and the log
  level is the spec's (`"env": {"RUST_LOG": "debug"}`), not the operator's.
- Processes are stopped by PID only (the driver tracks them). Never
  `pkill -f` a pattern — it can kill the operator's daemon.

## Known behaviour (when writing expectations)

- The driver sets `ARGO_PROVIDER=openai_compat` and `ARGO_MODEL=mock-model`.
  With only `provider = "openai_compat"` in config.toml the single-shot path
  calls the Responses API (`/v1/responses`), which the mock does not speak —
  the run then prints "I didn't produce a response this turn" with one LLM
  call. If you see that, the provider env is missing, not a guard broken.
- Single-shot user-input refusal prints a localised refusal line with the
  rule id; the daemon replies with a neutral refusal text. Both make 0 LLM
  calls.
- A blocked tool result reaches the model as
  `blocked: content withheld from the model; policy classes: PROMPT_INJECTION`.
- Daemon log lines go to stderr (captured into daemon.log).
- Guardrail config lives in three sections — `[pii]` (`mode` off|block_only|
  full, `filter_labels.<input|output|default>`, `demask_tool_args.<tool>`),
  `[prompt_guard]` (`mode` off|on) and `[tool_output_guard]` (`mode`,
  `labels`). There are no config rules: both prompt-injection layers run
  tinicore's built-in rules only. The old flat keys are unknown top-level
  keys and are ignored without a word.
- Every guardrail key is checked at boot in every build and whatever the
  modes; a key a section does not take (`mdoe`, or a top-level key written
  below the header) is refused first. The PII mode typo is reported by the
  CLI (`unrecognized pii.mode "fll"`), not tinicore.
- Only `override`, `embedded_directive` and `comment_directive` block at the
  tool-output layer; `invisible_chars` and `base64_decoded_to_shell` are
  warn-only, and listing one in `labels` prints a warning naming tinicore's
  field (`prompt_injection.tool_output.labels`), not the config key.
- Without the `guardrails` feature, `[tool_output_guard]` and `[pii]` keys
  are reported as ignored ("[pii] keys are set but this build has no
  `guardrails` feature — they are ignored"), and `[prompt_guard] mode = "on"` warns that the
  layer has no rules. An explicit `mode = "off"` is not reported.
- PII `block_only` and `full` (input layer) refuse a card in a USER
  message (the card recognizer is in the `input` layer); a Korean phone is
  only in `default` (masking), so it is masked, not refused. The input
  guardrail scans user messages only, never tool results.
- The daemon keeps a conversation only when the POST names a `session_id`
  (`"session"` in a case); without it every POST is a new conversation. The
  gateway stores only user and assistant messages — tool results are NOT
  history in the next turn, which is why the cache spec echoes the files
  into the stored reply (`ECHOFULL`).
- A tool result is cut to 50,000 chars before the model sees it
  (`tinicore/src/tools/content_budget.rs`, `[output truncated: N bytes
  total, showing first 50000]`); a ~88 KB file reaches the model as 50 KB.

## Masking-cache check (`pii-masking-cache.json`)

What is measured: tinicore logs one debug line per outbound masking pass
whose cache MISSES total more than 64 KiB (`LARGE_SCAN_WARN_BYTES`,
`tinicore/src/agent/pii_masking.rs`, `mask_messages_for_cloud_in_session`).
With `RUST_LOG=debug` the daemon's stderr logger prints it through the
`tracing`→`log` bridge as `[DEBUG] masking pass re-scanned … scanned_bytes=N
threshold=65536 scanned_messages=M detectors=K`. Only that message is
counted; the `llm-output masking pass`, `background egress masking pass` and
`input-guardrail pass` lines are other walks.

Why the scenario has this shape — a "no line" only means something when
the same pass WITHOUT the cache would have crossed 64 KiB, and no single
new text may cross it on its own:

- Each file is ~45 KB: below the 50,000-char tool-output cap (so it reaches
  the model whole), below 64 KiB alone, above it together with the other.
- Turn 1: `READFILES <missing> big1 big2 ECHOFULL:2,3` — requests 0–3. The
  failed read makes tinicore add the nudge to request 1. Request 3 carries
  big1 and big2; with the within-turn record (previous call's batch) it
  scans only big2 (~45 KB, no line); without it, both (~90 KB, a line).
  Expected: 0 lines on every request. The final answer echoes both files,
  so the STORED reply is ~90 KB (tool results are never stored).
- Turn 2: `READFILES big1`. Request 0 must re-scan turn 1's stored reply
  once (it is history for the first time) — exactly one line, 65537–140000
  bytes. This is the positive control (in `require`): without it every
  "no line" would pass vacuously (a debug line that never prints). Request
  1 (big1 again, ~45 KB new) must not log: the reply was just scanned.
- Turn 3: plain message. Request 0 must not log: turn 1's ~90 KB reply is
  covered by the finished-turns record.
- Preconditions (`require`; a failure fails the suite and skips later
  turns): the tool sequence ran (`loop_calls`), every agent-loop request
  (one that offered tools; background calls offer none) carries the
  `<turn-context>` carrier, and turn 1 request 1 carries the nudge "One or
  more tool calls failed" — the internal messages the cache must skip.
- Correctness: no request the mock received (background calls included)
  contains `010-1234-5678` or `4111-1111-1111-1111`; requests carry
  `[SENS:PII:` placeholders.
- Attribution: the mock records daemon.log's byte size when each request
  arrives; the masking pass for request i runs before request i is sent, so
  its line lies between request i-1's offset and request i's. Concurrent
  work (a detached post-turn task) lands in whatever segment it was written
  in, which is why only the outbound pass's message is counted.
  `scanned_bytes` / `scanned_messages` in a FAIL's output say what was
  re-scanned.
- Known result at ARGO `aa6d5cdc4b` (2026-10-07): carrier, nudge, positive
  control and every correctness check pass; the three "no line" checks FAIL
  (turn 1 req 3: 91479 bytes / 6 msgs; turn 2 req 1: 136044 / 5; turn 3 req
  0: 91276 / 6) — the cache never engages on `/api/v1/chat`, because the
  gateway's `AgentLoopConfig` (`tinicore/src/gateway/handler.rs`) sets no
  `conversation_id`/`harness_session_id`, so `session_key()` is `None` and
  the masking pass neither reads nor records a checkpoint.
