#!/usr/bin/env bash
# Build the two release `argo` binaries the e2e driver runs, and copy them out.
#
# usage: build_release.sh <argo-checkout> <out-dir>
#   env WEBUI=1        also enable the `webui` feature (needs npm + network to
#                      build argo-webui/dist once; not needed by the e2e specs)
#   env EXTRA_FEATURES comma-separated features added to BOTH builds
#
# Produces <out-dir>/argo-guardrails and <out-dir>/argo-noguard (same
# features, with/without `guardrails`). Both builds write target/release/argo,
# so each is copied right after it is built. Prints the objectbox library dir
# to <out-dir>/libdir.txt; on macOS it is also added to each binary's rpath,
# elsewhere pass it to the driver with --lib-dir.
set -euo pipefail

REPO="$(cd "$1" && pwd)"
OUT="$(mkdir -p "$2" && cd "$2" && pwd)"
cd "$REPO"

# rquickjs_macro fails to build (E0463) when build-override binaries are stripped.
export CARGO_PROFILE_RELEASE_BUILD_OVERRIDE_STRIP=false

FEATURES="tinicore/pii-audit-plaintext"
if [ "${WEBUI:-0}" = "1" ]; then
  FEATURES="$FEATURES,webui"
  if [ ! -d argo-webui/dist ]; then
    # npm rewrites the lock file; restore it afterwards if it was clean.
    lock_clean=0
    git diff --quiet -- argo-webui/package-lock.json && lock_clean=1
    (cd argo-webui && npm install && npm run build)
    [ "$lock_clean" = 1 ] && git checkout -- argo-webui/package-lock.json
  fi
fi
[ -n "${EXTRA_FEATURES:-}" ] && FEATURES="$FEATURES,$EXTRA_FEATURES"

build() {  # <name> <features>
  echo ">> cargo build --release -p argo-cli --features $2"
  cargo build --release -p argo-cli --features "$2"
  local lib
  lib="$(ls -d target/release/build/tinicore-*/out/objectbox-*/lib 2>/dev/null | head -1 || true)"
  if [ -n "$lib" ]; then
    lib="$(cd "$lib" && pwd)"
    echo "$lib" > "$OUT/libdir.txt"
    if [ "$(uname)" = "Darwin" ]; then
      # argo-cli has no build.rs, so the binary has no rpath to libobjectbox.dylib.
      install_name_tool -add_rpath "$lib" target/release/argo 2>/dev/null || true
      codesign -s - -f target/release/argo 2>/dev/null || true
    fi
  fi
  cp target/release/argo "$OUT/$1"
  echo ">> $OUT/$1"
}

build argo-guardrails "guardrails,$FEATURES"
build argo-noguard "$FEATURES"
echo "built at $(git log -1 --oneline)"
