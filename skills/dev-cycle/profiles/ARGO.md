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
  against a mock LLM). The release build takes tens of minutes; run the
  phase's suites with `--only <suite>` at the end of a phase, every spec
  before the PR. A
  spec must use the config format of the branch under test (flat `pii_*`
  keys vs the `[pii]` section); write a branch spec when the shipped ones do
  not fit, and keep it out of the repository.

## Path → affected checks

| changed path | tests (every verification) | extra checks (end of the phase, except `parity.sh` and `cargo check --workspace`: every verification) | e2e suite (end of the phase) |
| --- | --- | --- | --- |
| `tinicore/src/guardrails/pii/config/*.yaml` | `--test guardrails_filter_test --test guardrails_compile_guard_test`, lib `-- guardrails` | matching regression; `parity.sh` for a hand-written type | PII suites |
| `tinicore/src/guardrails/pii/handwritten/`, `pii/validators/`, `pii/labels.rs` | lib `-- handwritten guardrails`, filter + compile guard tests | matching regression; `parity.sh` | PII suites |
| `tinicore/src/guardrails/engine/` | lib `-- guardrails`, filter + compile guard + `guardrails_integration_test` | matching regression | PII + prompt guard suites |
| `tinicore/src/guardrails/prompt_injection/` | lib `-- prompt_injection prompt_guard`, `--test prompt_guard_e2e --test prompt_injection_install_e2e --test gateway_prompt_guard_gate` | — | prompt guard suites |
| `tinicore/src/guardrails/install.rs`, `pii/install.rs` | lib `-- guardrails`, `--test guardrails_country_install_test --test pii_real_rules_egress_e2e` | — | PII + boot suites |
| `tinicore/src/sensitive/` | lib `-- sensitive`, `--test sensitive_slim` | — | PII masking suites |
| `tinicore-traits/src/sensitive.rs` | `cargo test -p tinicore-traits`, lib `-- sensitive guardrails` | `cargo check --workspace --all-targets` | — |
| `tinicli/src/config.rs`, `cli_entry.rs` | `cargo test -p tinicli --lib` with and without `--features guardrails` | — | boot suites |
| anything else | the touched crate's tests filtered to the module | — | only if the path is on a guarded runtime path |

Lib tests run in debug: some release builds fail `debug_assert`-dependent
tests by design.

## When each check runs

The moments are the skill's ("When each check runs"). Here the slow checks
are the matching regression (two debug builds and two dumps, 20-40 min) and
e2e (a release build and the suite, 20+ min). A phase is e.g. "finish one
country" or "convert KR/US to hand-written detectors".

| when | checks |
| --- | --- |
| every verification (after implementing a commit, after each review fix) | fmt, the clippy lane(s) of the touched crates, the tests column of the table above; `parity.sh` when a hand-written detector's shapes changed; `cargo check --workspace --all-targets` when `tinicore-traits` changed |
| end of a phase (the review loop has ended and the commits are settled) | matching regression against the commit before the phase; the e2e suites of the behaviour the phase changed; for a PII detector or engine change, the speed check below |
| before the PR (once, on the final HEAD) | the Pre-PR checklist: full suites, every e2e spec, the Core audits |

## Speed check (PII detectors and engine)

`tinicore/src/guardrails/AGENTS.md` "Check it twice" is the rule; this is
how to run it.

- Compare against the commit before the phase, not only against the same
  shapes as regex: each detector can match its regex and the whole set
  still be several times slower (2026-10: 3.6x on plain English, found
  only by this comparison).
- `bench_scan --countries <deployed set>`, release: the `free` row (plain
  English), section 4's `free_<code>` rows for countries that have one,
  and the dense rows; `bench_engine` for the peak heap.
- For an older revision without the bench commit, cherry-pick the bench
  commit onto it in a temporary worktree (take the bench side of
  `examples/guardrails/common.rs`), and delete the worktree afterwards.
- Build each revision's binaries once, copy them out, then run them
  interleaved three times and take the median: the machine may carry
  other load (a qemu VM moved results by 10-20 %).
- Report the cost of newly added types apart from the cost of the
  conversion.

## Memory check (idle footprint of the guardrails)

- Tool: `tinicore/examples/guardrails/bench_idle_after_turns` (release,
  `--features guardrails,sensitive,test-fixtures`). It drives real
  in-process `agent_loop` turns against a scripted model and reads live
  heap and PSS at four points (before install, after install, after the
  turns plus `--settle`, after `malloc_trim`). Not part of
  `scanning_benchmark`.
- Run it on the Ubuntu glibc VM (macOS has no PSS). One configuration per
  run: `--guardrails off`, `--pin off`, `--pin on`; three runs each.
- Run the configurations ONE AT A TIME, never concurrently: PSS splits the
  binary's file pages between processes running it, so concurrent runs
  distort it (2026-10: the pinned-vs-released gap read 4.5 MB concurrent,
  1.1 MB sequential). Live heap is unaffected.
- Report live heap and PSS only, always next to the `--guardrails off`
  run of the same build, with the points written out ("after install",
  "idle after 200 turns"), not A/B/C/D.
- Before/after a series: put the bench file into the base revision too.
  If the base lacks an API the bench uses (e.g. `pin_engines`), adapt the
  base copy only (`turn_scope::pin_for_process()` for the pin) and say so.
  For the VM, build both inside the argo-tizen tree: the base is its
  `tini/` (check the guardrails paths match ARGO's base), the head is that
  tree plus `git diff <base> HEAD -- tinicore tinicore-traits` applied with
  `git apply --directory=tini`.

## Tests: where they live, who writes them

- Unit tests sit inside implementation files (`#[cfg(test)] mod tests`).
  For spec-derived expectations there (e.g. a country's validator table
  `validators_accept_and_refuse_by_spec` in `pii/validators/<code>.rs`: which
  values pass or fail a checksum), the test agent returns a list (validator,
  input, expected result, spec text) and the implementer inserts it unchanged.
- PII detection behaviour is an integration test the test agent writes
  directly: one table per recognizer in
  `tinicore/tests/guardrails/filter_test/{common,<code>}_rules.rs`
  (`<pii_type>_cases()` of `case(label, text, &[Has|NoType|Span])` rows),
  plus `tables()` registration. Every recognizer needs a row that must
  detect it and one that must not (`layers.rs` guard).
- A recognizer with a lowered `score:` follows the AGENTS.md "Test
  conventions for scored recognizers": a bare value not reported, the value
  beside a context word reported at 0.8 (a separate `#[test]`), and
  `analyze()` reporting nothing for the false positive that motivated the
  score.
- Implementer-owned: `examples/guardrails/common.rs` `diverse_pii_samples()`,
  the hand-written comparison rows (`handwritten/tests/<code>.rs`), and
  detector-internal unit tests. (A recognizer's kind is its YAML `label:`;
  there is no mapping list to update.)

## Baselines to take before editing

- Matching regression (any change to PII rules, detectors or the engine).
  The dump compares, per country set and layer, the raw matches (A), the
  detector's spans and kinds (S), each layer's `kinds()` set (K), and the
  `filter_labels` override detector per label on the shared slot
  (`override/<label>`, set name `override`):
  `scripts/match_regress.sh compare <base-rev> <workdir>` after the change
  is committed; it dumps the base revision itself, so nothing has to be taken
  up front. For a per-commit check inside a series:
  `match_regress.sh dump <workdir> <name>` at each commit, then
  `match_diff.py <workdir>/<a>.tsv <workdir>/<b>.tsv`.
  The allowed differences are decided in the plan, per commit; any other
  difference stops the cycle. The dump adds 20k seeded random texts
  (`MATCH_RANDOM=<n>` changes it; base and head must use the same count,
  so never edit the dump tool while a compare is running: each dump copies
  it in when it starts).
  Which country sets to dump (`MATCH_SETS=kr,us`, default every set plus
  `all`): the countries whose own files changed; every existing country
  when shared code changed (the engine, a hand-written detector,
  common.yaml, a shared validator); none for a commit that only adds a
  country (it has no base to compare with: its spec tests, parity and e2e
  cover it). Add `all` only when cross-country overlaps matter.
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
- right before pushing a follow-up to an open PR, check it is still open
  (`gh pr view <n> --json state`): a PR merged meanwhile does not take the
  push, and the follow-up needs a new branch from main and a new PR.

## Review fallback (Z.ai runner down)

The Z.ai review job runs only on the self-hosted `zai-review` runner. When
that runner is down every review job sits queued and fails after 24 h
(check `gh api repos/AGENTIC/ARGO/actions/workflows/code-review.yml/runs`:
no recent success, jobs with no runner). Then a subagent runs
`/code-review` high over the PR range, and the result is posted only on
instruction, as a "Claude Review" comment.

## Pitfalls

- Worktrees sharing one `CARGO_TARGET_DIR` share fingerprints for the same
  package ids: cargo may reuse another revision's build and fail or, worse,
  run stale binaries. `touch` the revision's `tinicore-traits`, `tinicore`
  sources before building it, and check the binary's mtime.
- `argo-e2e`'s `build_release.sh` needs `~/.cargo/bin` on PATH; without it
  it fails at once, and a pipeline ending in `tail` reports exit 0 while
  the old binaries stay in place.
- `parity.sh`'s KR entries name `kr_phonenumber` (landline and internet
  phone are its shapes since the KR commit); the Aho-Corasick test shows
  about 400 differing texts for paypal, braintree and
  google_oauth_2_0_refresh_token that origin/main has too — compare the
  count with the base, do not read it as a regression.

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
- Process-wide state (a shared slot, a registry) and tests: every test
  that registers into or resets it must be `#[serial]` and reset first.
  CI's guardrails lanes run `cargo nextest` (one process per test), so a
  missed one never fails in CI; it flakes only under `cargo test`
  (locally and in `regress_tests.sh`). When adding such state, grep every
  test that touches it.
- An issue in another repository is never written `argo-tizen #1689` in an
  ARGO commit message or PR body: GitHub links `#1689` to ARGO's own
  number. Write "argo-tizen issue 1689" (plain text, which also leaves no
  cross-reference on that issue).
- Gate a commit on cargo's exit code (`if cargo clippy …; then git commit
  …; fi`), never `cargo clippy … | grep …; git commit …` (the pipe's status
  is grep's). `cargo clippy` does not refresh the binary: `cargo build`
  before running it.
- `commands_hub::devices_skips_enroll_when_resolved_name_is_invalid` (tinicli)
  fails intermittently; it passes alone and on re-run.
