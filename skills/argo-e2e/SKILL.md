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
- `specs/scan-caches.json` — every sha-keyed scan cache on the daemon path
  (PII mode `full`, one conversation per suite, three turns each): the
  outbound masking cache (finished-turns record X + previous-batch record
  W), the LLM-output buffer-pass cache (X only) and the input-guardrail
  prefix checkpoint. Each has a positive control that must log, cross-turn
  "no line" checks, and (outbound) a within-turn check; no raw PII ever
  reaches the model (see Scan-cache checks).

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

## Scan-cache checks (`scan-caches.json`)

What is measured: each cached pass logs ONE debug line when its cache
misses in that pass total more than 64 KiB (`LARGE_SCAN_WARN_BYTES`). With
`RUST_LOG=debug` the daemon's stderr logger prints tinicore's
`tracing::debug!` through the `log` bridge as `[DEBUG] <message>
scanned_bytes=N threshold=65536 …`. Three messages, three regexes:

| Cache | Code | Line starts with |
|---|---|---|
| outbound masking (X + W) | `pii_masking.rs` `mask_messages_for_cloud_in_session`, before every LLM request | `masking pass re-scanned` |
| LLM-output masking (X only) | `pii_masking.rs` `mask_llm_output_in_session`, twice at the end of every turn (`loop_.rs`: once on this turn's `state.produced`, no session; once on the whole buffer, cached) | `llm-output masking pass scanned` |
| input-guardrail prefix checkpoint | `loop_.rs` + `guardrail_scan_cache.rs`, once at turn start over every non-internal user message | `input-guardrail pass re-scanned` |

A "no line" only proves something when the same pass WITHOUT its cache
would have crossed 64 KiB, so every no-line check is paired with that
counterfactual, and every suite has a positive control (in `require`) that
must log — otherwise a debug line that never prints would pass every check.

Sizes the scenario is built around:
- A tool result is cut to 50,000 chars before the model sees it
  (`tools/content_budget.rs`). Each `bigN.txt` is ~45 KB: whole, under
  64 KiB alone, over it with the other one.
- The gateway stores only user and assistant messages, so a tool result
  never comes back as history; `ECHOFULL:2,3` makes turn 1's stored reply
  ~90 KB (both files) so later turns have something big to (not) re-scan.
- `long.txt` is ~70 KB, sent as the user message itself (`{FILE:long.txt}`),
  with no blocked PII (a phone is masked, not refused).

Suite `daemon_masking_caches` (outbound + LLM-output):
- Turn 1 `READFILES <missing> big1 big2 ECHOFULL:2,3`, requests 0–3. The
  failed read makes tinicore add the nudge to request 1. Outbound: 0 lines
  on every request — request 3 holds big1+big2, and without W it would
  scan both (~90 KB). LLM-output: 2 lines after the last request (each
  end-of-turn pass scans this turn's ~90 KB reply) — positive control.
- Turn 2 `READFILES big1`. Outbound: request 0 exactly 1 line in
  65537–140000 (turn 1's reply is re-scanned once as the previous turn —
  positive control); request 1 none (W). LLM-output: 1 line after the last
  request (the buffer pass re-scans turn 1's reply once; this turn's reply
  is small).
- Turn 3 plain. Outbound, LLM-output, input: no line — turn 1's reply is in
  X for both caches.
- Preconditions: tool sequence ran (`loop_calls`), `<turn-context>` in every
  agent-loop request (one that offered tools), nudge "One or more tool
  calls failed" in turn 1 request 1.

Suite `daemon_input_guardrail_cache`:
- Turn 1 = the ~70 KB message: input-guardrail 1 line and outbound 1 line
  before request 0 (both 65537–90000) — positive controls.
- Turn 2 short: input none (the checkpoint covers turn 1's message; without
  it, ~70 KB again); outbound none either — turn 1 made one call, so its
  W (the whole stable batch, the long message included) is still a valid
  prefix of turn 2's batch and is reused. Compare the first suite, where
  turn 1's W holds assistant tool calls with pre-demask placeholders that
  come back demasked, so W misses, X (messages before turn 1's user
  message) is used and turn 1 is re-scanned once.
- Turn 3 short: no line of any kind (X covers turn 1 for the outbound pass,
  the checkpoint for the input pass).

Every turn of both suites: no request the mock received (background calls
included) contains `010-1234-5678` or `4111-1111-1111-1111`, and requests
carry `[SENS:PII:` placeholders.

Attribution and limits:
- The mock records daemon.log's byte size when each request arrives. A
  pass that runs before request i is sent (outbound, input) lies between
  request i-1's offset (or the turn start) and request i's; the
  end-of-turn LLM-output passes land in "after" (after the last request,
  until the response plus one second).
- The two end-of-turn LLM-output passes print the same message; they are
  told apart only by count per turn, not individually.
- Work running concurrently (a detached post-turn task, another
  `agent_loop`) lands in whatever segment it is written in. Only the three
  messages above are counted; `background egress masking pass` is not.
- Context compaction would rebuild the batch and show up as extra lines.

Observed at ARGO `a80c70d758` (2026-10-08), both suites ALL PASS:
`daemon_masking_caches` — turn 1: two LLM-output lines after the last
request (90013 bytes each), nothing else; turn 2: outbound request 0
(91107 bytes, 4 messages) and one LLM-output line after (90077, 2
messages); turn 3: nothing. `daemon_input_guardrail_cache` — turn 1: input
(70074, 1 message) and outbound (78348, 2 messages: the long message and
the carrier) before request 0; turns 2 and 3: nothing.
