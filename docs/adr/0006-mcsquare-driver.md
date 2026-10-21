# ADR 0006 — MCsquare through radiarch's own file-protocol driver

Date: 2026-10-21. Status: accepted. Implements decision 2 of ADR 0005 for the proton engine (roadmap R14).

## Context

Until R14 the proton engine plugin called OpenTPS's `MCsquareDoseCalculator`, which
wrote the engine's input files, ran the binary and read the results, and returned
the dose in OpenTPS's `(x, y, z)` array order. Radiarch's grids are `(z, y, x)`;
the mismatch was invisible on the cubic test phantom and would have transposed
every dose on a real CT. The wrapper also decided the calibration (clinical
tables for everything, so a water phantom was not water), the seed and the
thread count, which made runs irreproducible.

## Decision

`services/dose_engines/mcsquare_driver.py` writes the engine's inputs itself
(MHD CT, scanner tables, beam data library, PBS plan text, configuration from the
engine's own template), runs the binary through its launcher as a subprocess, and
reads the MHD dose and the sparse beamlet files. The plan is radiarch's own
`models/proton_plan.py`; beam models that still hold an OpenTPS plan are adapted
on read. The engine plugin returns `(z, y, x)` doses and influence matrices whose
rows are the geometry's C-order voxels.

Engine assets (launcher, binaries, `Materials/`, `BDL/`, `Scanners/`) are read from
`RADIARCH_MCSQUARE_DIR`, defaulting to `engines/mcsquare/` (R15 moved them there
from the vendored OpenTPS tree). Seed, thread
count, scanner and beam data library are settings and per-request parameters;
`seed > 0` with one thread is reproducible bit for bit.

## Evidence

- The inputs the driver writes are byte-identical to the goldens captured from the
  OpenTPS wrapper (`tests/golden/mcsquare_inputs_simplefantom`): configuration
  (apart from primaries, seed and threads), plan text, CT header and raw block.
- At a fixed seed and one thread the driver's dose equals the wrapper's to
  4 × 10⁻⁸ relative on SimpleFantom and 7 × 10⁻⁹ on a non-cubic water box
  (`tests/test_mcsquare_driver.py`).
- Beamlet columns land where their spots are: BEV +x moves a column along patient
  +x, BEV +y along +z at gantry 0.

## Consequences

- Scenarios are applied to the inputs: a setup shift moves the isocenters, a
  density or range scale rewrites the HU→density table. MCsquare's native
  robustness mode (81/21/random scenarios) is R3's.
- The validation harness's proton case runs through the driver with the
  water-only calibration, against the NIST PSTAR CSDA ranges entered on 2026-10-21.
- The legacy `/plans` workflows ran on OpenTPS until R15 rewrote them on the services.
