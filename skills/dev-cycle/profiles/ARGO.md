# ARGO (AGENTIC/ARGO)

Cargo workspace; Core crates `tinicore`, `tinicore-traits`, host `tinicli`
(binary `argo` from `argo-cli`). The repository's own rules (root and
`tinicore/` `CLAUDE.md`, `tinicore/src/guardrails/pii/AGENTS.md`) come first.

Run every command after `export PATH="$HOME/.cargo/bin:$PATH"`. In zsh a
variable holding several arguments is not split: loop over cargo argument
lists in `bash -c '...'`.

## Commands

- Format: `cargo fmt --all -- --check`
- Lint (every lane CI runs; each `-- -D warnings`):
  - `cargo clippy -p tinicli --all-targets`
  - `cargo clippy -p tinicli --features guardrails --all-targets`
  - `cargo clippy -p tinicore --features guardrails,sensitive,test-fixtures --all-targets`
  - `cargo clippy -p tinicore-traits --all-targets`
- Core audits (all must exit 0):
  `python3 scripts/<a>.py` for `audit_core_layer_deps`, `audit_core_product_leak`,
  `audit_core_crate_name_leak`, `audit_reimpl`.
- Panic audits (input-handling changes; baseline in the root `CLAUDE.md`):
  `scripts/panic_filter.py`, `scripts/unreachable_filter.py`, `scripts/risky_unwrap.py`.
- A `tinicore-traits` type change: `cargo check --workspace --all-targets`
  (other crates' exhaustive matches) and `cargo test -p tinicore-traits`.
- Full suites (pre-PR, ~30-60 min): `scripts/regress_tests.sh <outdir>`
  (tinicore all tests, tinicli lib with and without `guardrails`, per-test
  outcomes), then `scripts/compare_tests.py <baseline-dir> <outdir>`.
- e2e: the `argo-e2e` skill (release `argo` with and without `guardrails`
  against a mock LLM). The release build takes tens of minutes; pick one
  suite with `--only <suite>` in the cycle, run every spec before the PR. A
  spec must use the config format of the branch under test (flat `pii_*`
  keys vs the `[pii]` section); write a branch spec when the shipped ones do
  not fit, and keep it out of the repository.

## Path → affected checks

| changed path | tests | extra checks | e2e suite |
| --- | --- | --- | --- |
| `tinicore/src/guardrails/pii/config/*.yaml` | `--test guardrails_filter_test --test guardrails_compile_guard_test`, lib `-- guardrails` | matching regression; `parity.sh` for a hand-written type | PII suites |
| `tinicore/src/guardrails/pii/handwritten/` | lib `-- handwritten guardrails`, filter + compile guard tests | matching regression; `parity.sh` | PII suites |
| `tinicore/src/guardrails/engine/` | lib `-- guardrails`, filter + compile guard + `guardrails_integration_test` | matching regression | PII + prompt guard suites |
| `tinicore/src/guardrails/prompt_injection/` | lib `-- prompt_injection prompt_guard`, `--test prompt_guard_e2e --test prompt_injection_install_e2e --test gateway_prompt_guard_gate` | — | prompt guard suites |
| `tinicore/src/guardrails/install.rs`, `pii/install.rs` | lib `-- guardrails`, `--test guardrails_country_install_test --test pii_real_rules_egress_e2e` | — | PII + boot suites |
| `tinicore/src/sensitive/` | lib `-- sensitive`, `--test sensitive_slim` | — | PII masking suites |
| `tinicore-traits/src/sensitive.rs` | `cargo test -p tinicore-traits`, lib `-- sensitive guardrails` | `cargo check --workspace --all-targets` | — |
| `tinicli/src/config.rs`, `cli_entry.rs` | `cargo test -p tinicli --lib` with and without `--features guardrails` | — | boot suites |
| anything else | the touched crate's tests filtered to the module | — | only if the path is on a guarded runtime path |

Lib tests run in debug: some release builds fail `debug_assert`-dependent
tests by design.

## Tests: where they live, who writes them

- Unit tests sit inside implementation files (`#[cfg(test)] mod tests`).
  For spec-derived expectations there (e.g. the validator table
  `validate_dispatches_by_method_name` in `engine/validator.rs`: which values
  pass or fail a checksum), the test agent returns a list (validator, input,
  expected result, spec text) and the implementer inserts it unchanged.
- PII detection behaviour is an integration test the test agent writes
  directly: one table per recognizer in
  `tinicore/tests/guardrails/filter_test/{common,kr,us}_rules.rs`
  (`<pii_type>_cases()` of `case(label, text, &[Has|NoType|Span])` rows),
  plus `tables()` registration. Every recognizer needs a row that must
  detect it and one that must not (`layers.rs` guard).
- A recognizer with a lowered `score:` follows the AGENTS.md "Test
  conventions for scored recognizers": a bare value not reported, the value
  beside a context word reported at 0.8 (a separate `#[test]`), and
  `analyze()` reporting nothing for the false positive that motivated the
  score.
- Implementer-owned: counts (`layers.rs`, the 49/52-style type lists),
  `sub_samples()`, `examples/guardrails/common.rs` `diverse_pii_samples()`,
  `detector.rs` mapping lists, and detector-internal unit tests.

## Baselines to take before editing

- Matching regression (any change to PII rules, detectors or the engine):
  `scripts/match_regress.sh compare <base-rev> <workdir>` after the change
  is committed; it dumps the base revision itself, so nothing has to be taken
  up front. For a per-commit check inside a series:
  `match_regress.sh dump <workdir> <name>` at each commit, then
  `match_diff.py <workdir>/<a>.tsv <workdir>/<b>.tsv`.
  The allowed differences are decided in the plan, per commit; any other
  difference stops the cycle.
- Full-suite outcomes: run `regress_tests.sh` on the base commit when the
  change may move tests (renames, count changes), so `compare_tests.py` can
  show exactly which tests appeared, disappeared or started failing.

## Pre-PR checklist

- fmt, every clippy lane, the four Core audits (and the panic audits for
  input handling) on the final HEAD.
- `regress_tests.sh` + `compare_tests.py` against the baseline: no newly
  failing test; every renamed or removed test is intended and named.
- every `argo-e2e` spec that fits the branch, plus the branch's own spec.
- memory: the work-state note for the branch is current.
- push, PR and PR comments wait for their own instruction.

## Pitfalls

- A dump or test binary compiles whatever is on disk when cargo reaches it.
  Do not edit the tree between starting a run and the binary starting; check
  with `pgrep -f "^/Users/.*deps/<binary>"` (a bare `pgrep -f <name>` also
  matches the shell running the wait loop, and returns at once).
- A `PatternFilter` scan with no turn guard builds the engine on EVERY call;
  a tool that scans many texts must call
  `tinicore::sensitive::turn_scope::pin_for_process()` first (a 43k-text
  dump: 15 min pinned, far longer unpinned).
- A base dump must be built from the base commit checked out, never from a
  tree that already holds part of the change.
- In an unquoted heredoc, backticks in a commit message run as commands; use
  `<<'EOF'` or a message file.
- `commands_hub::devices_skips_enroll_when_resolved_name_is_invalid` (tinicli)
  fails intermittently; it passes alone and on re-run.
