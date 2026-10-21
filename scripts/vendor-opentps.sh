#!/usr/bin/env bash
# vendor-opentps.sh — refresh the vendored OpenTPS core under src/opentps/core.
#
# OpenTPS core (Apache-2.0; the CCC photon engine inside it is GPLv2 and is
# only ever run as a separate subprocess) is vendored rather than installed
# from PyPI so that radiarch can carry a small patch set against it
# (src/opentps/patches/) and ship only the Linux binaries.
#
# Usage:
#   scripts/vendor-opentps.sh [TAG] [UPSTREAM_CLONE]
#     TAG             tag or commit of https://gitlab.com/openmcsquare/opentps
#                     (default: v3.0.1)
#     UPSTREAM_CLONE  an existing clone to export from; without it a temporary
#                     shallow clone of TAG is made
#
# Afterwards: ./scripts/install-dev.sh && pytest tests/opentps tests/test_opentps_integration.py

set -euo pipefail

TAG="${1:-v3.0.1}"
UPSTREAM="${2:-}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${REPO_ROOT}/src/opentps"
PATCH="${DEST}/patches/radiarch-local.patch"

for tool in git rsync patch tar; do
  command -v "$tool" >/dev/null || { echo "missing tool: $tool" >&2; exit 1; }
done

TMP_CLONE=""
if [ -z "${UPSTREAM}" ]; then
  TMP_CLONE="$(mktemp -d)"
  echo "==> Shallow-cloning OpenTPS ${TAG}"
  git clone -q --depth 1 --branch "${TAG}" https://gitlab.com/openmcsquare/opentps.git "${TMP_CLONE}/opentps"
  UPSTREAM="${TMP_CLONE}/opentps"
fi

EXPORT="$(mktemp -d)"
trap 'rm -rf "${EXPORT}" ${TMP_CLONE:+"${TMP_CLONE}"}' EXIT

echo "==> Exporting opentps_core/opentps/core at ${TAG}"
git -C "${UPSTREAM}" archive "${TAG}" opentps_core/opentps/core opentps_core/LICENSE | tar -x -C "${EXPORT}"

echo "==> Replacing ${DEST}/core"
rsync -a --delete "${EXPORT}/opentps_core/opentps/core/" "${DEST}/core/"
cp "${EXPORT}/opentps_core/LICENSE" "${DEST}/LICENSE"

echo "==> Stripping caches and non-Linux binaries"
find "${DEST}/core" -name __pycache__ -type d -prune -exec rm -rf {} +
find "${DEST}/core" \( -name '*.dll' -o -name '*_win.exe' -o -name '*_win.bat' -o -name 'MCsquare_mac' \) -delete
rm -rf "${DEST}/core/processing/doseCalculation/protons/MCsquare/lib_mac"

echo "==> Applying ${PATCH}"
(cd "${DEST}" && patch -p1 --no-backup-if-mismatch -i "${PATCH}")

# machine_model.py accepts a "default" scanner; upstream ships only UCL_Toshiba.
SCANNERS="${DEST}/core/processing/doseCalculation/protons/MCsquare/Scanners"
rm -rf "${SCANNERS}/default"
cp -r "${SCANNERS}/UCL_Toshiba" "${SCANNERS}/default"

chmod +x "${DEST}"/core/processing/doseCalculation/protons/MCsquare/MCsquare* \
         "${DEST}"/core/processing/doseCalculation/photons/CCC_DoseEngine/CCC_DoseEngine 2>/dev/null || true

echo "==> Recording ${TAG}"
sed -i "s/^# Vendored copy of OpenTPS core package (.*)/# Vendored copy of OpenTPS core package (${TAG})/" "${DEST}/__init__.py"
sed -i "s/\*\*OpenTPS Core\*\* ([^)]*)/**OpenTPS Core** (${TAG})/" "${DEST}/ATTRIBUTION.md"

echo
echo "Vendored OpenTPS core ${TAG} into ${DEST}."
echo "Next: ./scripts/install-dev.sh && pytest tests/opentps tests/test_opentps_integration.py"
