#!/usr/bin/env bash
# run.sh — the nuclear-halo check of ADR 0024: MCsquare builds against Geant4 on the proton_bragg_peak phantom.
#   OUT=dir GATE_PYTHON=python-with-opengate RADIARCH_PYTHON=python-with-radiarch \
#     engines/mcsquare-build/halo/run.sh tag1=/path/to/MCsquare_binary [tag2=...]
# A tag ending in "gpu" runs its binary with MCSQUARE_GPU=1. About an hour on 48 cores (Geant4 most of it).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; REPO="$(cd "${HERE}/../../.." && pwd)"
OUT="${OUT:?OUT=directory}"; mkdir -p "${OUT}/runs" "${OUT}/g4"
"${RADIARCH_PYTHON:-python}" "${HERE}/prepare.py" "${OUT}/inputs"
export INPUTS="${OUT}/inputs" RUNS="${OUT}/runs" MATERIALS="${REPO}/engines/mcsquare/Materials"
for spec in "$@"; do
  tag="${spec%%=*}"; bin="${spec#*=}"; mode=cpu; case "${tag}" in *gpu) mode=gpu ;; esac
  for c in w200n w225n w200e w225e; do BIN="${bin}" bash "${REPO}/engines/mcsquare-gpu/bench/run_case.sh" "${c}" "${mode}" "${tag}" "" 11; done
done
for e in 200.484 225.217; do for ph in QGSP_BIC_EMZ G4EmStandardPhysics_option4; do
  "${GATE_PYTHON:-python}" "${HERE}/geant4.py" "${e}" "${ph}" 4e6 "$(nproc)" 7 "${OUT}/g4/${e%.*}-${ph}" > "${OUT}/g4-${e%.*}-${ph}.log" 2>&1
done; done
"${GATE_PYTHON:-python}" "${HERE}/analyse.py" "${OUT}/runs" "${OUT}/g4" | tee "${OUT}/summary.txt"
python3 "${HERE}/table.py" "${OUT}/summary.txt"
