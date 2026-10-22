# ADR 0005 — Own the core; run dose engines as subprocess tools; phase OpenTPS out

Date: 2026-10-20. Status: accepted. Supersedes the "defer photon to v2" framing of ADR 0001.

## Context

Radiarch vendors OpenTPS core and imports a thin slice of it (17 modules): DICOM
loading, the CT/ROI/plan data classes, proton spot placement, CT calibration tables
and the MCsquare and CCC wrappers. That slice is where the defects fixed in R0 came
from (the photon plan builder used attribute names OpenTPS does not have; the robust
workflow set parameters OpenTPS does not read), it carries DICOM writers that omit
MLC positions, and every upstream release changes radiarch's dependency set (3.0.1
required numpy 2, nibabel and scikit-image in the core). The physics itself is not
the problem: MCsquare and the WiscPlan collapsed-cone engine are standalone
executables driven by files.

The full evaluation is `docs/reports/tps-evaluation-and-roadmap.md`.

## Decision

1. The **core** — data model, DICOM in and out, plan model, optimizer, evaluation,
   writers — is radiarch's own code.
2. **Engines are subprocess tools** behind radiarch drivers that speak each engine's
   file protocol: MCsquare for protons, the CCC binary for nominal photon dose,
   a Monte Carlo code for validation only. A radiarch-native photon pencil-beam
   engine is the second runtime engine.
3. **OpenTPS is reference code, not a dependency.** The vendored 3.0.1 copy
   (`scripts/vendor-opentps.sh`, `src/opentps/patches/`) stays only until the
   imported pieces have their own implementation (roadmap items R1, R14, R2, R15);
   then `src/opentps` is deleted and `engines/` keeps binaries, data and licences.
   OpenTPS code is adapted where useful under Apache-2.0 with attribution.
4. pyRadPlan and matRad are offline cross-checks and algorithm sources only.

## Consequences

- No new code imports `opentps`; new drivers and models live under `radiarch`.
- Each replacement is gated by a regression test against the current output
  (same binary, same inputs, identical dose and beamlets).
- The GPLv2 CCC engine stays a separate program invoked over files.
