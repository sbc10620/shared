#!/usr/bin/env bash
# Build the `argot` binary from an argo-tizen checkout and copy it out.
#
# usage: build_argot.sh <argo-tizen-checkout> <out-dir> [debug|release]
#
# Default profile is debug: incremental and minutes, not tens of minutes,
# and every guard runs the same code in both profiles. Pass `release` to
# check the shipped optimisation level. Writes <out-dir>/argot and
# <out-dir>/commit.txt (the commit the binary was built at).
set -euo pipefail

repo="${1:?usage: build_argot.sh <argo-tizen-checkout> <out-dir> [debug|release]}"
out="${2:?usage: build_argot.sh <argo-tizen-checkout> <out-dir> [debug|release]}"
profile="${3:-debug}"
export PATH="$HOME/.cargo/bin:$PATH"

cd "$repo"
if [ "$profile" = "release" ]; then
    cargo build --locked -p argot --release
    src="target/release/argot"
else
    cargo build --locked -p argot
    src="target/debug/argot"
fi
mkdir -p "$out"
cp "$src" "$out/argot"
git log -1 --oneline > "$out/commit.txt"
if [ -n "$(git status --porcelain)" ]; then
    echo "(working tree had uncommitted changes)" >> "$out/commit.txt"
fi
echo "built $(cat "$out/commit.txt" | head -1) -> $out/argot ($profile)"
