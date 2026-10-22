# Building the CCC engine

`CCC_DoseEngine/` is the WiscPlan collapsed-cone convolution engine (GPLv2, see
`licenseWiscPlan.txt`) as shipped with OpenTPS 3.0.1, with one change by the
Radiarch Project (R7, 2026-10-21): the two constants that truncate scatter,
`doseCutoffThreshold` (0.005: a beamlet's dose below this fraction of its
maximum is dropped) and `RSAFE` (2.0 cm: voxels farther than this from the
aperture cylinder are never computed), are read at run time from the
environment variables `CCC_DOSE_CUTOFF` and `CCC_RSAFE_CM` (`defs.h`,
`convolution.cpp`). Unset, the shipped values apply and the output is bit for
bit the shipped binary's (`tests/test_goldens.py`).

Rebuild on Linux (the tracked `*.o` files are Windows objects and must not be
linked):

```bash
cd engines/ccc/CCC_DoseEngine && make clean && make && git checkout -- '*.o'
```

Radiarch's driver sets the variables per run: `params["scatter"]` is
`shipped` (the default, for influence matrices) or `full` (cutoff 1e-4, mask
10 cm; about 45× slower; R7 found it no closer to Monte Carlo with these kernels, see ADR 0014), or
`dose_cutoff` / `rsafe_cm` directly; `RADIARCH_CCC_SCATTER` is the
installation default. The output-factor calibration is keyed by the setting.
