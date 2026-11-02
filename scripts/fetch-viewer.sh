#!/usr/bin/env bash
# The viewer packages (OHIF extensions, mode, standalone image) live in passlab/radiarch-ohif. This puts that repository,
# at the commit radiarch is tested with (viewer.ref), into viewer/: what CI, `docker compose --profile viewer` and the
# viewer tests use. Run it again after viewer.ref changes. A viewer/ that is not that checkout is left alone.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

REF="$(tr -d '[:space:]' < viewer.ref)"
URL="${RADIARCH_OHIF_URL:-https://github.com/passlab/radiarch-ohif.git}"
if [ ! -e viewer ]; then
  git clone --quiet "$URL" viewer
elif [ ! -d viewer/.git ]; then
  echo "viewer/ exists and is not a git checkout; move it away first" >&2
  exit 2
fi
git -C viewer fetch --quiet origin
git -C viewer checkout --quiet "$REF"
echo "viewer/ at $(git -C viewer rev-parse --short HEAD)"
