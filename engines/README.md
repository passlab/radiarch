# Dose engine assets

radiarch computes dose with two engines run as separate programs that
exchange files with radiarch's drivers (`src/radiarch/services/dose_engines/`).
Nothing in radiarch links to or imports them.

| Directory | Engine | Licence | Driver |
|---|---|---|---|
| `mcsquare/` | MCsquare proton Monte Carlo: launcher `MCsquare`, Linux binaries (SSE4, AVX, AVX2, AVX-512), `Materials/`, `BDL/`, `Scanners/` | Apache-2.0 (`LICENSE-OpenTPS` covers the copy, which is the one OpenTPS core ships) | `mcsquare_driver.py` |
| `ccc/` | WiscPlan collapsed-cone photon engine: `CCC_DoseEngine/` (source and Linux binary), `Kernels_6MV/`, `Kernels_differentFluence/`, `LINAC/` | GPLv2 (`licenseWiscPlan.txt`); subprocess only | `ccc_driver.py` |

`RADIARCH_MCSQUARE_DIR` and `RADIARCH_CCC_ENGINE_DIR` point the drivers elsewhere;
by default they use these directories (or `/app/engines` in the container image).
`scripts/fetch-engines.sh <tag>` refreshes both from the OpenTPS repository, the
upstream that packages them; `Scanners/default` is a copy of `UCL_Toshiba` added
by radiarch. `tests/test_engine_assets.py` checks the layout.
