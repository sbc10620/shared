---
name: argo-release-e2e
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
  message → a `file_read` tool call; after a tool result → `FINAL: tool said
  -> <result>`; else `plain reply`. Logs each request and each tool result.
- `scripts/argo_e2e.py` — the driver. The spec schema is in its docstring.
- `specs/*.json` — scenario sets. `guardrails-config-rules.json` covers the
  prompt-injection config rules and the "a mistake in any guardrail key stops
  the boot whatever the mode" principle (PII included).

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
   wording is localised: match rule ids (`ignore_prior`), `llm_calls` (0 =
   refused before the model), `tool_seen` (what the model got). Boot cases
   expect `refusing to start` plus the specific reason.
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
- Provider env vars (`ARGO_*`, `AZURE_OPENAI_*`, `OPENAI_*`, `ANTHROPIC_*`) are
  stripped so no real provider is ever called.
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
- The engine discards zero-width matches, so an empty-matching pattern
  blocks nothing.

## Known issues

- `rquickjs_macro` fails with E0463 when build-override binaries are
  stripped; `build_release.sh` sets
  `CARGO_PROFILE_RELEASE_BUILD_OVERRIDE_STRIP=false`.
- With `WEBUI=1` (2026-10): `tinicli/src/websocket.rs` builds a
  `GatewayRequest` without `run_options` → E0063. If your checkout still has
  it, add `run_options: state.chat_run_options.clone(),` there locally for
  the build, then restore the file (`git checkout -- tinicli/src/websocket.rs`).
  Never commit it.
