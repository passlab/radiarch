# ADR 0008 — The core is radiarch's own; OpenTPS is gone from the tree

Date: 2026-10-21. Status: accepted. Completes ADR 0005 (roadmap R15).

## Context

ADR 0005 decided that radiarch owns its core and runs dose engines as subprocess
tools, with the vendored OpenTPS 3.0.1 copy kept only until its last imported
modules were replaced. R1 (CCC driver), R14 (MCsquare driver) and R2 (DICOM RT
readers) replaced the engine wrappers and the plan readers. R15 replaced the rest:
the CT and structure-set loaders, the contour rasterizer, the CT calibration, the
proton spot placement, the beam-model and geometry glue, and the legacy `/plans`
workflows.

## Decision

1. **Own loaders**: `radiarch.dicom.ct`, `radiarch.dicom.rtstruct`,
   `radiarch.dicom.case` read a CT series, an RT Structure Set and a planning case
   with pydicom. Rules (slice sorting, HU rescale, spacing, origin) are those the
   previous loader applied, so geometries built before R15 rebuild identically.
2. **Own rasterizer**: `services/contour_raster.py` is a port of OpenTPS's
   partial-volume rasterizer (supersampled polygon fill, XOR for holes, z grouping,
   slice interpolation, 0.5 threshold).
3. **Own calibration**: `services/proton_rsp.py` reads the engine's material
   database and the scanner tables and converts HU to mass density and to relative
   stopping power at 100 MeV; `hu_density.StoichiometricModel` uses the same table.
4. **Own spot placement**: `services/spot_placement.py` builds
   `models/proton_plan.ProtonPlan` directly (hexagonal grid, push to the CT border,
   single-precision ray marching through the RSP image to and through the dilated
   target, layer depths to energies with the Grevillot fits, proximal and distal
   layers, 0.05 MeV layer merging, decreasing-energy order).
5. **Engine assets as data**: `engines/mcsquare` and `engines/ccc` hold the two
   engines; `scripts/fetch-engines.sh` refreshes them from the OpenTPS repository,
   which packages both. `src/opentps`, its patch set and `scripts/vendor-opentps.sh`
   are deleted; `pyproject` ships `radiarch*` only and no longer needs nibabel.
6. **Legacy workflows on the services**: `core/workflows/*` run geometry → beam
   model → dose or optimization → RTDOSE and DVH through the services; the robust
   workflow is a robust optimization over the scenarios of
   `_helpers.robust_scenarios` (worst-case aggregation). The plan record now
   carries the workflow parameters (`PlanParameters`; migration `b7e2c4d9a1f0`),
   which the old workflows read but the old record never stored, and the geometry
   is built on the plan's `scoring_spacing_mm` grid (2 mm by default; the old
   workflows ignored the parameter and always ran on the CT grid).
7. **Settings**: `RADIARCH_DATA_ROOT` (was `RADIARCH_OPENTPS_DATA_ROOT`),
   `RADIARCH_BEAM_LIBRARY_DIR` (was `RADIARCH_OPENTPS_BEAM_LIBRARY`);
   `RADIARCH_OPENTPS_VENV` is gone. The bundled phantom lives in
   `tests/data/SimpleFantomWithStruct`.

## Evidence

Before deletion every port was compared with the vendored code on the same inputs:

| Component | Cases | Result |
|---|---|---|
| CT loader | SimpleFantom; LCTSC-Test-S1-101 | arrays, origin, spacing identical |
| Structure-set loader | same | every polygon identical |
| Rasterizer | SimpleFantom at 4 grids; 5 LCTSC structures at native, 3 mm and half-z grids | masks identical |
| HU → density, HU → RSP | sampled HU | identical |
| Spot placement | SimpleFantom gantry 0; water box gantry 0, 120/couch 15, 300 | bit-identical (energies, spots, order) |
| Spot placement | SimpleFantom gantry 90, 45/20, 270/−30, 180 | see deviation below |
| Goldens (`tests/golden`) | geometry hashes, 846 spots, MCsquare input files | reproduced |

**Deliberate deviation.** The C ray marcher kept the `1e-10` placeholder direction
components. For a negative one, a spot whose coordinate sat exactly on a voxel
boundary was always "at" its next boundary and crawled through the image in 1 µm
steps with single-precision drift (a posterior beam on a 1 mm grid: 200 000 steps per
spot, seconds to tens of seconds per beam). radiarch treats components below 1e-6 as
zero. Posterior and lateral beams on grids whose spacing divides the spot spacing
differ from OpenTPS by a few edge spots or, when such a spot set the minimum depth,
by a layer shift (SimpleFantom at gantry 180: 2027 vs 2074 spots); the deviation is a
float artefact of the old code, not physics. Placement is about 100× faster.

The isocenter is still the target's centre of mass; the request's `isocenter_mm`
is not used, as before. R3 decides whether to honour it.

## Consequences

- No module under `src/radiarch` imports OpenTPS (`tests/test_engine_assets.py`
  checks). `ProtonPlan.from_opentps` stays as a reader of beam models pickled
  before R14.
- Parity tests that needed the vendored code are gone; the goldens are the
  regression reference, and the comparison above is the record.
- The MCsquare and CCC binaries are still the ones OpenTPS packages; building
  them from source is a separate decision (open since ADR 0005).
