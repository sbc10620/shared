# Project profiles

A profile is `profiles/<repo>.md` in the dev-cycle skill's directory,
`<repo>` being the `origin` remote's repository name. It holds what the
cycle needs to know about one repository: which commands to run, which
changed paths call for which checks, and at which moment each check runs.
Read this file when a repository has no profile, when a profile turns out
wrong or incomplete, or when a profile tool had to be adapted for a branch.

## Without a profile

Discover from the repository: its `AGENTS.md` / `CLAUDE.md`, CI workflow
files, `Cargo.toml` / `package.json` / `Makefile` test targets, and any e2e
skill named for the project. Note what you used; at the end of the cycle
(step 11) it becomes a profile draft.

## What a profile holds

```markdown
# <repo>

## Commands
- formatter / linter (every configuration that CI runs)
- audits
- full test suites (pre-PR), and what they reuse from the earlier checks
- e2e: the skill or script, how to pick one suite

## Path → affected checks
| changed path | tests | extra checks | e2e suite |

## Check cost and shared builds
| group (what must match to share the build) | checks | cost |   (cheapest first; coarse units, not minutes)

## When each check runs
| when | checks |   (before editing / every verification / after the review loop / before the PR)

## Tests: where they live, who writes them
- where new behaviour's tests go (files, tables), and whether unit tests sit
  inside implementation files (then the test agent returns values only)

## Baselines to take before editing
## Pre-PR checklist
## Pitfalls (things that cost time before)
```

## Assigning checks to moments

- Fast checks (formatter, linter, the touched modules' tests) belong to
  every verification. Anything that needs a release build, a whole-suite
  run or a base-vs-head comparison belongs after the review loop or before
  the PR.
- A check given no moment runs only when a plan names it or the user asks.
- A check that compares before and after needs its base built before the
  first edit (step 2) and kept outside the target directory, so that at the
  end only HEAD is built. Checking the base out later rebuilds both sides
  and changes the tree under any other running check.

## Shared builds and cost order

Checks share a build only when the compiled library is the same: the
package, check vs codegen, the build profile and the feature set. List the
groups of checks that share a build, cheapest first. At one moment the
orchestrator runs a group back to back so the build happens once, and runs
a wider check (a full suite) after the narrower ones whose builds it
reuses.

## Tools a profile ships

Scripts a profile needs live beside it in `profiles/<repo>/scripts/`. They
are personal tooling: never added to the project repository, and left out
of the shared copy of the skill.

A tool that does not fit the branch under test (it calls an API the branch
or the base lacks, or expects a file layout the tree does not have) is
adapted in a scratch copy during the cycle (step 5). When the cycle ends,
judge each adaptation: would the tool be better off working this way on
every branch (a layout or API difference that will recur, not a one-off
workaround)? If so, propose folding it into the profile's tool so that one
tool serves both, together with the profile text that describes the tool.
Once the user agrees, change the tool, update the profile, and sync the
shared copy. A one-off adaptation stays in scratch.

## Changing a profile

Show a profile draft, or a diff of the profile, built from the commands
that were actually used, and save it only after approval. Then sync the
shared copy of the skill (without the scripts).
