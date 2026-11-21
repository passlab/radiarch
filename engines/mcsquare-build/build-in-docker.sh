#!/usr/bin/env bash
# build-in-docker.sh — build engines/mcsquare/MCsquare_radiarch in ubuntu:24.04, the toolchain of record (BUILD.txt),
# so that the binary is the one the validation was run on. Needs docker and network. ADR 0023.
#   engines/mcsquare-build/build-in-docker.sh            any toolchain difference is reported
#   RADIARCH_MCSQUARE_EXPECT_RECORD=1 ...                and fails the build (CI)
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
docker run --rm -v "${REPO}:/w" -w /w -e RADIARCH_MCSQUARE_EXPECT_RECORD="${RADIARCH_MCSQUARE_EXPECT_RECORD:-0}" \
  ubuntu:24.04 bash -c "
    set -e
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq >/dev/null
    apt-get install -y -qq --no-install-recommends gcc libc6-dev git python3 python3-venv ca-certificates >/dev/null
    engines/mcsquare-build/build.sh
    chown $(id -u):$(id -g) engines/mcsquare/MCsquare_radiarch"
