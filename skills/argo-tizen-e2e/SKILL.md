---
name: argo-tizen-e2e
description: Verify an argo-tizen (argot) change by RUNNING the real `argot` daemon against a deterministic mock LLM — prompt-guard modes and their events, PII refusal and outbound masking, boot refusal on a bad guardrail key, and an automation fire that resumes after a daemon crash — each case judged automatically. Use when asked for an actual run / real-execution check ("실제 실행 검증", "mock LLM으로 돌려봐", "e2e로 확인") of guardrails, prompt guard, PII or config-loading behaviour in an argo-tizen checkout. For ARGO (tinicli) use argo-release-e2e instead.
---

# argo-tizen end-to-end run

Unit tests prove functions; this proves the binary: config.toml → boot
checks → `argot` client → daemon turn → pre-persist gate → LLM request →
what the model was actually sent → what was stored. Every case is judged
from the outside: the reply text, the number of agent-loop LLM calls the
mock saw, whether the prompt landed in the conversation history, the
`prompt_guard.match` events in the daemon log, and the text the model
received. "Refused before the model", "masked on the way out" and "one event
per match" are asserted, not eyeballed.

Works with any agent or by hand: a shell script and standard-library
Python 3.8+ scripts. Paths below are relative to this skill's directory
(`SKILL_DIR`).

## Files

- `scripts/build_argot.sh` — builds `argot` from an argo-tizen checkout
  (debug by default, `release` optional) and copies it out with the commit.
- `scripts/mock_llm.py` — OpenAI-compatible mock (SSE and JSON). Directives
  in the newest user message: `TOOL <name> <json>` (a tool call, then
  `FINAL: …`), `RESUME-PLAY <key>` (a `bash_run` call, then the reply is
  held once so the driver can kill the daemon mid-turn, then
  `recovered final answer`); otherwise `plain reply`. Logs every request
  with its non-system texts; a request offering `tools` is an agent turn.
- `scripts/argot_e2e.py` — the driver. The spec schema is in its docstring.
- `specs/guardrails.json` — the current guardrail matrix:
  - `pg-off|on|warn|block`: tinicore built-in rules (old baseline phrase,
    a rule Argot never had, `invisible_payload`), Argot's forged
    `<turn-context>` / `<argot-context>` tags (incl. a Hangul letter right
    after the tag — the ASCII `\b`), a benign prompt; events exactly once
    per match; resume after a crash under on/warn/block.
  - `tool-output-off|on` (+ with the prompt guard, + resume): a tool result
    carrying a forged tag or a built-in rule match reaches the model as
    `blocked: content withheld from the model; …` under
    `[safety.tool_output_guard] mode = "on"`, raw under `off`. Commands use
    printf octal escapes (`\074` = `<`) so the tag exists only in the tool
    result, never in the user's prompt.
  - `pii-off|block-only|full`: card / RRN refused before storage, phone
    passed raw or masked (`[SENS:PII:PHONE:…]`) only on the way out.
  - `pii-full-with-prompt-guard`: guard refuses first; a PII refusal fires
    no guard event.
  - `boot-*`: an unknown prompt-guard mode, an unknown tool-output-guard mode and a `credential` filter label
    (even with PII off) stop the daemon.

## Steps

1. **Build** (run it in the background while you read the spec):
   ```bash
   BINS=/tmp/argot-e2e-bins
   "$SKILL_DIR/scripts/build_argot.sh" /path/to/argo-tizen "$BINS"
   ```
   Note the commit in `$BINS/commit.txt`. A failed build copies nothing.
2. **Pick or write a spec** in `specs/`. Assert behaviour: rule ids and
   actions in `events`, `turn_calls` (0 = refused before the model),
   `persisted`, `llm_saw` / `llm_not_saw` for what the model received. Boot
   cases set `"boot": "refuse"` plus a `boot_expect` regex.
3. **Run**:
   ```bash
   python3 "$SKILL_DIR/scripts/argot_e2e.py" "$SKILL_DIR/specs/guardrails.json" --bin "$BINS/argot"
   ```
   `--only <suite>` (repeatable) runs selected suites; `--keep` keeps each
   suite's work dir (`root/` data root with `logs/argot-daemon.log`,
   `daemon.out`, `llm.jsonl`).
4. **Report** PASS/FAIL per suite and case together with the build commit.
   For a FAIL, read the kept logs and decide whether the code or the spec is
   wrong — never loosen an expectation just to make a case pass.

## Isolation rules (non-negotiable)

- Each suite gets its own temporary `HOME` and `ARGOT_DATA_ROOT` — never the
  operator's `~/.argot`.
- The driver picks free ports for the mock and the daemon (`ARGOT_BIND`),
  so an operator's own daemon is never contacted.
- Provider environment variables (`ARGOT_*`, `ARGO_*`, `OPENAI_*`,
  `ANTHROPIC_*`, `AZURE_OPENAI_*`, `GEMINI_*`) are stripped, so no real
  provider is ever called.
- Processes are stopped by PID only. Never `pkill -f` a pattern.

## Known behaviour (when writing expectations)

- The guard refusal reply is the neutral `I can't help with that request.`
  for both prompt-guard and PII refusals.
- A normal turn makes one agent-loop call (`turn_calls: 1`); memory
  extraction makes extra `aux` calls, which are not counted.
- `prompt_guard.match` events are the daemon's WARN log lines in
  `<data_root>/logs/argot-daemon.log`; PII refusals emit none of them.
- A block reports only the first blocking rule (`ignore_prior` for the old
  baseline phrase); a warn-only message reports every matching rule once.
- PII `full` masks only the outbound text; the stored history keeps the raw
  value. Email has no recognizer and is never masked.
- A routine fire talks in the routine's own conversation
  (`argot routine --all --json` → `conversation_id`), which the plain
  conversation list does not show.
- The resume check proved its worth: a build that put the forged-tag rules
  into `agent_loop`'s rule set fails `pg-on` resume (the checkpointed
  `<turn-context>` carrier is scanned as the user's message).
