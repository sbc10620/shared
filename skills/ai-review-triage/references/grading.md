# Grading reference — worked examples from AGENTIC/ARGO#3392

Three rounds of Z.ai review on a 15-commit guardrails PR. Every finding below
was verified against the code before it was graded; the bot's own severity
label is shown so the gap between label and grade is visible.

## A — fixed

| Round | Bot label | Finding | Why A |
| --- | --- | --- | --- |
| 1 | Higher priority | TUI reap branch: the bottom-of-loop drain and `is_finished()` are two statements; the task (another worker thread) can send `TurnComplete` and return in between, so the fallback commits the still-masked stream and the real answer is later ignored as late. | Written out as a step-by-step sequence it was reachable. Fix: drain again inside the `is_finished()` branch, extract the branch to a function so a test calls the same code; mutation-checked (delete the drain → test fails). |
| 2 | High priority | `install_guardrails` did `guard.take()` → merge → put back. An unwind mid-merge leaves the slot `None`; the poisoned lock is recovered with `into_inner`, so every later turn runs with no guardrails, silently. The comment claimed the worst case was "an install that did not complete". | Security fail-open + a wrong invariant comment. Fix: merge in place through `&mut` (`Arc::get_mut`), slot never `None`. |

## B — listed, not fixed (user decision)

| Round | Bot label | Finding | Why B |
| --- | --- | --- | --- |
| 2 | High priority | `ENV_INSTALLED` is `load` at entry / `store` after install — not atomic against a concurrent second caller. | Boot path, single thread, documented as the contract. Reachable only by a future host doing parallel init. 3-line `swap` fix exists; user chose not to. |
| 3 | Medium | `install_pii` failure exits the whole CLI, including `--connect` (a thin client that serves no turns). | True. User: "stopping everywhere is fine" — one rule, no exceptions. Do not re-argue. |
| 3 | Nit | `record_checkpoint` has `debug_assert_eq!(slots.len(), verified_len)`; compiled out in release. | Single caller constructs both from one walk; the invariant is structural. `debug_assert` is the Rust idiom for exactly this. |
| 3 | Nit | `guardrails::audit` detect line logs at `debug` on clean scans. | Only visible under `RUST_LOG=debug`, which is "show me everything". `grep -v` handles it. |
| 3 | (root of a "blocking" claim) | `caller_owes_guidance` doc says `has_masking` "derives from `config.sensitive` alone" — stale since `resolve_sensitive`. | The paragraph's conclusion is still right, so not "materially wrong". Borderline: it IS a premise sentence and it DID mislead the bot. Fix on the next commit that touches that file. |
| 3 | Blocking | Add `regex-automata/unicode` to the `guardrails` feature instead of relying on `regex`'s explicit opt-in forwarding it. | One-line, zero cost, but the coupling is documented in `Cargo.toml` and fail-closed if broken. B. |

## C — answered once, then just cited

| Round | Bot label | Finding | Why C |
| --- | --- | --- | --- |
| 1 | Medium | `regex-automata` without default features makes `\d` ASCII-only → fail-open. | Premise wrong twice: `regex` (with `unicode`) is always in the graph via feature unification, and without it a Unicode-mode `\d` is a **parse error** → DFA build fails → boot refused. Fail-closed, not fail-open. |
| 1 | Medium | `warn_input_history_gap_once` removal left the module doc's "OnceLock around `resolve`" stale. | `resolve` still latches (`OnceLock` at its line 511). The doc was not stale. (The removed limitation text WAS undocumented — that half was fixed.) |
| 2 | High priority | `install_pii` now appends to the global set and pollutes other tests in the tinicli binary. | The test asserts on line 1 that nothing else installed masking; the module doc names it the sole installer; no other tinicli lib test runs an input pass; CI uses nextest (one process per test). A latch would change nothing. |
| 2 | High priority | Restructure chains as `Vec<Arc<dyn Guardrail>>` so appending never needs unique ownership. | The four chain aliases live in `tinicore-traits` and every host builds `vec![Box::new(..)]`. Contract-crate breaking change → follow-up issue, not this PR. |
| 3 | **Blocking** | `has_masking` reads `config.sensitive` only, so tinicli turns re-mask every LLM call. | `has_masking = masking.is_some()` where `masking` is built from `resolve_sensitive(&config)` — global fallback included. The bot read the stale doc sentence above, not the code. |
| 3 | **Blocking** | Workspace `regex-automata` `default-features = false` silently changes every member. | `rg '^regex-automata' */Cargo.toml` → tinicore is the only direct dependent. |
| 3 | Likely bug | `TurnComplete` carries no turn id; turn 1's answer could land in turn 2. | Requires the aborted task to complete its `send` after `abort()` (only possible in the microseconds between its last `.await` and `send`) AND the user to submit turn 2 inside that window; the top-of-loop drain consumes the stale event first otherwise. |
| 1, 3 | Note | `inbound_admission_e2e.rs` comment lists three call sites; the old text listed seven. | `rg` shows exactly three production call sites; the others were removed before this branch. Bot repeated it in round 3 verbatim — cited round 1. |
| 2, 3 | Medium | Boot builds the PII engine ~6 times (2 per layer). | True; boot-time one-off (~15 ms each). User: keep. Repeated in round 3 — cited. |

## Patterns worth remembering

- The bot's most confident labels ("blocking") were its least accurate.
- Its best find (round 2, `take()` window) was filed as one item among five
  "high priority" ones, four of which were B/C. Grade every item, not the
  headline.
- Every round after the first repeated ≥2 items from earlier rounds. Keep the
  answered list.
- Doc drift the user chose to leave: `caller_owes_guidance` premise sentence;
  `PiiFilter::analyze`/`mask` `Result` migration note; `target = "guardrails"`
  (field) vs `target: "guardrails"` (real target) at two pre-existing log
  sites. Fix these when the surrounding code is next touched.
