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
- Core audits (before the PR; all must exit 0):
  `python3 scripts/<a>.py` for `audit_core_layer_deps`, `audit_core_product_leak`,
  `audit_core_crate_name_leak`, `audit_reimpl`.
- Panic audits (before the PR, for input-handling changes; baseline in the
  root `CLAUDE.md`):
  `scripts/panic_filter.py`, `scripts/unreachable_filter.py`, `scripts/risky_unwrap.py`.
- A `tinicore-traits` type change: `cargo check --workspace --all-targets`
  (other crates' exhaustive matches) and `cargo test -p tinicore-traits`.
- Full suites (pre-PR): `scripts/test_outcomes_record.sh <outdir>`
  (tinicore all tests, tinicli lib with and without `guardrails`, per-test
  outcomes), then `scripts/test_outcomes_diff.py <baseline-dir> <outdir>`.
  Run it last at its moment: it reuses the lib-test, integration and
  tinicli builds the path tests left, and builds only the remaining test
  binaries, examples and doctests. Do not rerun the path tests only to warm
  the build.
- e2e: the `argo-e2e` skill (release `argo` with and without `guardrails`
  against a mock LLM). Its two release builds of `argo-cli` are the costliest
  builds here and share nothing with the other checks; run every spec
  before the PR (`--only <suite>` runs one suite, e.g. at a milestone's
  end). A
  spec must use the config format of the branch under test (flat `pii_*`
  keys vs the `[pii]` section); write a branch spec when the shipped ones do
  not fit, and keep it out of the repository.
- PII release checks (they share one release build of the tinicore
  library, `--features guardrails,sensitive,test-fixtures`; each binary
  still does its own LTO link):
  - `scripts/detector_vs_regex.sh [test-filter]`: each hand-written
    recognizer against the original regex kept in its YAML comment, on
    shape-focused random and mutated-template texts with the validators
    removed. It reads the rule files in either per-country layout
    (`pii/countries/<cc>/rules.yaml` or `pii/config/<cc>.yaml`) and needs
    the `pii_extensions(&countries)` API, so it does not build on trees
    older than the multilingual branch's selected-tables change. "SKIPPED (not … in
    this tree)" is expected; "SKIPPED (regex or detector did not build)" is
    a failure to investigate.
  - `scripts/pii_base_vs_head.sh`: the base's and HEAD's detection results
    on one corpus (see Baselines). `keep-base <keepdir>` before the first
    edit, `compare-kept <keepdir>` before the PR; `compare
    <base-rev> <workdir>` only when no base was kept or base and HEAD use
    different rule layouts (it checks the base out, so both sides rebuild);
    `dump <workdir> <name>` for the current tree alone, reading
    `<workdir>/corpus.json`.
  - the speed check's `bench_scan` (see Speed check).

## Path → affected checks

The tests column gives the arguments only: tinicore tests are
`cargo test -p tinicore --features guardrails,sensitive,test-fixtures <args>`
(without the features the filters match nothing and the build is not the
one the other checks share).

| changed path | tests (every verification) | extra checks (before the PR, except `cargo check --workspace`: every verification) | e2e suite (before the PR) |
| --- | --- | --- | --- |
| `tinicore/src/guardrails/pii/countries/*/rules.yaml` (older trees: `pii/config/*.yaml`) | `--test guardrails_filter_test --test guardrails_compile_guard_test`, lib `-- guardrails` | PII base-vs-head comparison when `common`'s rule file changed (not for a country's own YAML file: its spec tests cover it); `detector_vs_regex.sh` when a hand-written type was added or its matching logic changed | PII suites |
| `tinicore/src/guardrails/pii/handwritten/`, `pii/validators/`, `pii/countries/*/*.rs`, `pii/rules.rs`, `pii/uuid.rs`, `pii/labels.rs` | lib `-- handwritten guardrails`, filter + compile guard tests | PII base-vs-head comparison when a hand-written detector's logic, a shared validator, `rules.rs`, `uuid.rs` or `labels.rs` changed (not a country's own validator or table); `detector_vs_regex.sh` when a detector was converted, added or its matching logic changed | PII suites |
| `tinicore/src/guardrails/engine/` | lib `-- guardrails`, filter + compile guard + `guardrails_integration_test` | PII base-vs-head comparison | PII + prompt guard suites |
| `tinicore/src/guardrails/prompt_injection/` | lib `-- prompt_injection prompt_guard`, `--test prompt_guard_e2e --test prompt_injection_install_e2e --test gateway_prompt_guard_gate` | — | prompt guard suites |
| `tinicore/src/guardrails/install.rs`, `pii/install.rs`, `pii/detector.rs`, `pii/shared.rs` | lib `-- guardrails`, `--test guardrails_filter_test --test guardrails_country_install_test --test pii_real_rules_egress_e2e` | PII base-vs-head comparison when detection, a layer or the override path changed (`detect`, `resolve_overlaps`, `kinds_for_layer`, `try_from_filter` / `try_for_kinds` in `pii/detector.rs`; the layer, override and country-set filters in `pii/shared.rs`). The dump does not reach `try_for_layer`, `select_countries` or `pii/install.rs`: their own tests cover them | PII + boot suites |
| `tinicore/src/sensitive/` | lib `-- sensitive`, `--test sensitive_slim` | — | PII masking suites |
| `tinicore-traits/src/sensitive.rs` | `cargo test -p tinicore-traits`, lib `-- sensitive guardrails` | `cargo check --workspace --all-targets` | — |
| `tinicli/src/config.rs`, `cli_entry.rs` | `cargo test -p tinicli --lib` with and without `--features guardrails` | — | boot suites |
| anything else | the touched crate's tests filtered to the module | — | only if the path is on a guarded runtime path |

Lib tests run in debug: some release builds fail `debug_assert`-dependent
tests by design.

## Check cost and shared builds

A build is shared when the compiled library is the same: the package,
check (clippy, `cargo check`) vs codegen (tests, examples, binaries), the
profile and the feature set (`$F` = `guardrails,sensitive,test-fixtures`).
A crate's lib-test binary (`--lib`) is its own build; its integration
tests and examples link the ordinary library. Groups, cheapest first:

| group (one build) | checks that share it | cost |
| --- | --- | --- |
| no build | fmt, the Core and panic audits | seconds each |
| `tinicore-traits` | `cargo test -p tinicore-traits` | seconds |
| tinicore library, debug, `$F` | every `--test <name>` (each adds its own test binary); the full suites | build about a minute; each test runs in seconds |
| tinicore lib-test binary, debug, `$F` | every `--lib -- <filter>`; the full suites | build a few minutes; each filter runs in seconds |
| tinicli lib-test binary, one per lane | `cargo test -p tinicli --lib` with and without `guardrails`; the full suites | build a few minutes; runs in seconds |
| check build, one per clippy lane | that lane only (tinicore is re-checked per feature set; lanes share third-party crates when features overlap) | a few minutes per lane |
| check build of the workspace | `cargo check --workspace --all-targets` (shares nothing with the clippy lanes: other feature sets) | a few minutes |
| tinicore library, release, `$F` | `detector_vs_regex.sh`, `pii_base_vs_head.sh`, `bench_scan`, `bench_engine` (each binary does its own LTO link) | build a few minutes; the PII dump runs a few minutes per side, the others seconds |
| tinicore library, release, `$F`, on the VM | the memory check | a VM build per side; about a minute per configuration |
| `argo-cli`, release, two feature sets | every `argo-e2e` spec | the costliest build; each spec under a minute |

Run the checks of one group back to back. Run the full suites last at
their moment.

## When each check runs

The moments are the skill's ("When each check runs"). A phase is e.g.
"finish one country" or "convert KR/US to hand-written detectors".

| when | checks |
| --- | --- |
| before editing (step 2, on the clean commit the phase starts from) | `pii_base_vs_head.sh keep-base` when a path the plan changes asks for the PII base-vs-head comparison (path table); the speed check's bench binaries (same release build) and the memory check's VM binary when the plan names those checks; `test_outcomes_record.sh` on the base when the change may move tests. All of them finish before the first edit: each compiles the tree on disk |
| every verification (after implementing a commit, after each review fix) | fmt, the clippy lane(s) of the touched crates, the tests column of the table above; `cargo check --workspace --all-targets` when `tinicore-traits` changed |
| before the PR (step 9: once the review loop has ended, on the final HEAD) | first, on ONE release build of HEAD, back to back: `pii_base_vs_head.sh compare-kept` when the path table asks for the PII base-vs-head comparison; `detector_vs_regex.sh` when the phase converted a regex to a hand-written detector, added hand-written detectors (a new country's included) or changed a detector's matching logic (shape, boundaries, separators); the speed check when the plan names it. Then the e2e suites of the behaviour the phase changed, and the memory check when the plan names it; then the Pre-PR checklist: full suites (last), every e2e spec, the Core audits |

## Speed check (PII detectors and engine)

`tinicore/src/guardrails/AGENTS.md` "Check it twice" is the rule; this is
how to run it.

No path triggers it: the plan names it for a commit that can change scan
speed (the scan path, a detector, the engine, a validator), or the user
asks. It is reported once, before the PR (every commit made and
the review loop over), next to the base; the user decides what to do with
it. It does not stop the cycle.

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
- Build the base binaries before the first edit (step 2) and keep them,
  copied out of the target directory (the same release build as
  `pii_base_vs_head.sh keep-base`: same features; not when the bench commit
  is cherry-picked into a temporary worktree, which is a separate build).
  At the end, build the head's, then
  run base and head once each, back to back. Rerun only a row whose
  difference looks large: three times, interleaved, and take the median
  (the machine may carry other load; a qemu VM moved results by 10-20 %).
- Report the cost of newly added types apart from the cost of the
  conversion.

## Memory check (idle footprint of the guardrails)

No path triggers it: the plan names it for a commit that can change the
guardrails' memory (engine building or residency, pinning, the compiled
rule set, scan caches and vaults, anything kept across turns), or the user
asks. It is reported once, before the PR (every commit made and
the review loop over), next to the base; the user decides what to do with
it. It does not stop the cycle.

- Tool: `tinicore/examples/guardrails/bench_idle_after_turns` (release,
  `--features guardrails,sensitive,test-fixtures`). It drives real
  in-process `agent_loop` turns against a scripted model and reads live
  heap and PSS at four points (before install, after install, after the
  turns plus `--settle`, after `malloc_trim`). Not part of
  `scanning_benchmark`.
- Run it on the Ubuntu glibc VM (macOS has no PSS). One configuration per
  run: `--guardrails off`, `--pin off`, `--pin on`.
- Build the base binary before the first edit (step 2) and keep it. At the
  end, build the head's and run each configuration once per side. Rerun
  (three runs each) only where a difference looks large.
- Run the configurations ONE AT A TIME, never concurrently: PSS splits the
  binary's file pages between processes running it, so concurrent runs
  distort it (2026-10: the pinned-vs-released gap read 4.5 MB concurrent,
  1.1 MB sequential). Live heap is unaffected.
- Report live heap and PSS only, always next to the `--guardrails off`
  run of the same build, with the points written out ("after install",
  "idle after 200 turns"), not A/B/C/D.
- Before/after a series: put the bench file and its `[[example]]` entry in
  `tinicore/Cargo.toml` into the base revision too (and into the head when
  it lacks them).
  If the base lacks an API the bench uses (e.g. `pin_engines`), adapt the
  base copy only (`turn_scope::pin_for_process()` for the pin) and say so.
  On the VM, build the ARGO tree itself, never the argo-tizen tree: rsync
  the checkout without `target/` and `.git`, build
  `cargo build -p tinicore --example bench_idle_after_turns --release
  --features guardrails,sensitive,test-fixtures`, and copy the binary out
  (the base before the first edit, the head at the end).

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

- Speed and memory checks the plan names: build the base binaries now
  (from the commit the phase starts from) and keep them; see those
  sections. Nothing is measured up front.

- PII base-vs-head comparison, when the path table asks for it: a change
  that must keep detection as it was (the engine, a hand-written detector's
  logic, a shared validator, `labels.rs`, `common.yaml`, the layer, country
  set and `filter_labels` override wiring, and the span selection itself:
  `detect`, `resolve_overlaps`, `kinds_for_layer`, `try_from_filter`,
  `try_for_kinds` in `pii/detector.rs`; the layer, override and
  country-set filters in `pii/shared.rs`). The dump builds its detectors
  through `try_from_filter` and `try_for_kinds`, so it does not reach
  `try_for_layer`, `select_countries` or `pii/install.rs`: those are
  covered by `guardrails_country_install_test` and
  `pii_real_rules_egress_e2e`. A country's own rules and validators are
  covered by their spec tests instead.
  `scripts/pii_base_vs_head.sh keep-base <keepdir>` NOW, on the clean
  commit the phase starts from: it keeps the release dump binary, its
  commit, its rule layout and the dump tool's hash. Before the PR
  `compare-kept <keepdir>` extracts the corpus from HEAD, builds HEAD's
  binary, runs both and diffs, with no checkout. Without a kept base,
  `compare <base-rev> <workdir>` checks the base out instead (both sides
  rebuild).
  The dump records, per country set and layer, the raw matches (A), the
  detector's spans and kinds (S), each layer's `kinds()` set (K), and the
  `filter_labels` override detector per label on the shared slot
  (`override/<label>`, set name `override`). It is a release build and
  spreads the texts over every core; its rows are byte-identical to a
  sequential run. The dump follows the tree it builds: `zz_pii_dump.rs`
  for the per-country layout (one set per country plus `all`), and
  `zz_pii_dump_single.rs` for the single `pii_filter_config.yaml` layout
  (one set, `all`).
  For a per-commit check inside a series:
  `pii_base_vs_head.sh dump <workdir> <name>` at each commit, then
  `pii_dump_diff.py <workdir>/<a>.tsv <workdir>/<b>.tsv`; only to narrow
  down a difference the plan does not explain. Neither runs while the
  commits are being made.
  The allowed differences are decided in the plan; any other difference
  stops the cycle. The dump adds 20k seeded random texts
  (`MATCH_RANDOM=<n>` changes it; base and head must use the same count).
  Do not edit the dump tool between `keep-base` and `compare-kept`: the
  kept binary carries the old tool (`compare-kept` refuses when the tool's
  hash changed). It also refuses when base and HEAD use different rule
  layouts (single file vs per country): across the split, use
  `compare <base-rev>`. Both refusals come before any build.
  For a per-commit `dump`, use the keepdir as `<workdir>` so every dump
  reads the same `corpus.json`; without one, run
  `python3 scripts/pii_corpus.py <workdir>/corpus.json <repo-root>` first.
  Leave `MATCH_SETS` unset: the dump then covers every country set, `all`
  and `override`. If you narrow it (`MATCH_SETS=kr,us,all,override`),
  always keep `override` (it gates the `filter_labels` comparison), keep
  `all` on the single-file layout (its only rule set), and give base and
  head the same value. A phase that only adds a country needs no
  comparison (no base to compare with: its spec tests,
  `detector_vs_regex.sh` and e2e cover it).
- Full-suite outcomes: run `test_outcomes_record.sh` on the base commit when the
  change may move tests (renames, count changes), so `test_outcomes_diff.py` can
  show exactly which tests appeared, disappeared or started failing.

## Pre-PR checklist

- fmt, every clippy lane, the four Core audits (and the panic audits for
  input handling) on the final HEAD.
- `test_outcomes_record.sh` (last, reusing the path tests' builds) +
  `test_outcomes_diff.py` against the baseline: no newly failing test;
  every renamed or removed test is intended and named. Without a baseline,
  every `*_outcomes.txt` must report a non-zero ok count and the run must
  print no `BUILD FAILED` line (a failed build may print no FAILED line),
  and the FAILED lines may name only the intermittent tests listed in
  Pitfalls (rerun those alone to confirm).
- every `argo-e2e` spec that fits the branch, plus the branch's own spec.
- memory: the work-state note for the branch is current.
- push, PR and PR comments wait for their own instruction.
- right before pushing a follow-up to an open PR, check it is still open
  (`gh pr view <n> --json state`): a PR merged meanwhile does not take the
  push, and the follow-up needs a new branch from main and a new PR.

## Outside the cycle: review fallback (after the PR, Z.ai runner down)

The Z.ai review job runs only on the self-hosted `zai-review` runner. When
that runner is down every review job sits queued and fails after 24 h
(check `gh api repos/AGENTIC/ARGO/actions/workflows/code-review.yml/runs`:
no recent success, jobs with no runner). Then a subagent reviews the PR
range at high effort, with its own built-in code review skill or else
`dev-cycle-code-review`, and the result is posted only on instruction, as a
"Claude Review" comment.

## Pitfalls

- Worktrees sharing one `CARGO_TARGET_DIR` share fingerprints for the same
  package ids: cargo may reuse another revision's build and fail or, worse,
  run stale binaries. `touch` the revision's `tinicore-traits`, `tinicore`
  sources before building it, and check the binary's mtime.
- `argo-e2e`'s `build_release.sh` needs `~/.cargo/bin` on PATH; without it
  it fails at once, and a pipeline ending in `tail` reports exit 0 while
  the old binaries stay in place.
- `detector_vs_regex.sh`'s KR entries name `kr_phonenumber` (landline and internet
  phone are its shapes since the KR commit); the Aho-Corasick test shows
  about 400 differing texts for paypal, braintree and
  google_oauth_2_0_refresh_token that origin/main has too — compare the
  count with the base, do not read it as a regression.
  On the single-file layout (main before the multilingual split),
  `kr_mutated_templates` compares `kr_phonenumber` with the landline and
  internet-phone shapes the multilingual tree added (about 4,500 differing
  texts) — expected there; compare the count with the base.

- A dump or test binary compiles whatever is on disk when cargo reaches it.
  Do not edit the tree between starting a run and the binary starting; check
  with `pgrep -f "^/Users/.*deps/<binary>"` (a bare `pgrep -f <name>` also
  matches the shell running the wait loop, and returns at once).
- A `PatternFilter` scan with no turn guard builds the engine on EVERY call;
  a tool that scans many texts must call
  `tinicore::sensitive::turn_scope::pin_for_process()` first (unpinned,
  a dump rebuilds the engine for every text).
- A kept base binary must come from the clean commit the phase starts
  from, never from a tree that already holds part of the change
  (`keep-base` refuses a dirty tree).
- In an unquoted heredoc, backticks in a commit message run as commands; use
  `<<'EOF'` or a message file.
- Process-wide state (a shared slot, a registry) and tests: every test
  that registers into or resets it must be `#[serial]` and reset first.
  CI's guardrails lanes run `cargo nextest` (one process per test), so a
  missed one never fails in CI; it flakes only under `cargo test`
  (locally and in `test_outcomes_record.sh`). When adding such state, grep every
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
- `agent::loop_::e2e::checkpoint_resume::prompt_guard_on_resume_still_blocks_the_real_user_message`
  (tinicore lib) failed once in a filtered `--lib` run and passed in the
  full suite (observed once, 2026-10-22).
- The Ubuntu VM (6 GB, no swap) gets rustc SIGKILLed on ARGO's LTO release
  build of tinicore. Add a temporary swap file before building
  (`sudo fallocate -l 8G /swap.tmp && sudo chmod 600 /swap.tmp && sudo
  mkswap /swap.tmp && sudo swapon /swap.tmp`) and remove it afterwards
  (`sudo swapoff /swap.tmp && sudo rm /swap.tmp`).
