#!/usr/bin/env bash
# fetch-engines.sh — refresh the dose engine assets under engines/ from upstream.
#
# radiarch runs two engines as separate programs over files:
#   engines/mcsquare  MCsquare (Apache-2.0): launcher, Linux binaries, Materials/,
#                     BDL/, Scanners/ — taken from the copy OpenTPS core ships.
#   engines/ccc       WiscPlan collapsed-cone photon engine (GPLv2): CCC_DoseEngine
#                     source + Linux binary, kernels, LINAC data — taken from the
#                     copy OpenTPS core ships.
# Nothing else of OpenTPS is used; radiarch's own core replaced it (ADR 0005, 0008).
#
# Usage:
#   scripts/fetch-engines.sh [TAG] [UPSTREAM_CLONE]
#     TAG             tag or commit of https://gitlab.com/openmcsquare/opentps
#                     (default: v3.0.1)
#     UPSTREAM_CLONE  an existing clone to export from; without it a temporary
#                     shallow clone of TAG is made
#
# Afterwards: pytest tests/test_engine_assets.py tests/test_goldens.py

set -euo pipefail

TAG="${1:-v3.0.1}"
UPSTREAM="${2:-}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${REPO_ROOT}/engines"
SRC_PROTONS="opentps_core/opentps/core/processing/doseCalculation/protons/MCsquare"
SRC_PHOTONS="opentps_core/opentps/core/processing/doseCalculation/photons"

for tool in git rsync tar; do
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

echo "==> Exporting engine assets at ${TAG}"
git -C "${UPSTREAM}" archive "${TAG}" "${SRC_PROTONS}" "${SRC_PHOTONS}" opentps_core/LICENSE | tar -x -C "${EXPORT}"

echo "==> Replacing ${DEST}/mcsquare"
rsync -a --delete \
  --exclude '__init__.py' --exclude '__pycache__' \
  --exclude '*.dll' --exclude '*_win.exe' --exclude '*_win.bat' --exclude 'MCsquare_mac*' --exclude 'lib_mac' \
  "${EXPORT}/${SRC_PROTONS}/" "${DEST}/mcsquare/"
cp "${EXPORT}/opentps_core/LICENSE" "${DEST}/mcsquare/LICENSE-OpenTPS"

echo "==> Replacing ${DEST}/ccc"
rsync -a --delete \
  --exclude '__init__.py' --exclude '__pycache__' --exclude '*.py' \
  --exclude 'Makefile.win' --exclude 'shiftBeamlets*' \
  "${EXPORT}/${SRC_PHOTONS}/" "${DEST}/ccc/"

echo "==> POSIX launcher and executable bits"
# upstream's launcher is a bash script with CRLF endings on some tags
sed -i 's/\r$//' "${DEST}/mcsquare/MCsquare"
chmod +x "${DEST}/mcsquare/MCsquare" "${DEST}"/mcsquare/MCsquare_* "${DEST}/ccc/CCC_DoseEngine/CCC_DoseEngine"

# radiarch accepts a "default" scanner; upstream ships only UCL_Toshiba.
SCANNERS="${DEST}/mcsquare/Scanners"
rm -rf "${SCANNERS}/default"
cp -r "${SCANNERS}/UCL_Toshiba" "${SCANNERS}/default"

echo "Done. Run: pytest tests/test_engine_assets.py tests/test_goldens.py"
