# ADR 0023 — MCsquare built from source, with radiarch's patches

Date: 2026-11-20. Status: built on the project lead's word ("Yes please fix", 2026-11-20); the engine as
radiarch's default waits for the merge into `master`. Replaces the single-thread workaround of 2026-11-13
(ADR 0006, last bullet).

## Context

The MCsquare binaries radiarch ran were the ones OpenTPS 3.0.1 ships: Intel-compiled, statically linked,
from upstream's `master` of 2024. In multithreaded beamlet runs they crashed now and then on a segmentation fault
(the nightly of 2026-11-13; 4 of 28 fast runs of `mco_robust_proton` with 8 threads). The workaround was a retry
in the driver and one thread for that case.

The investigation of 2026-11-20 (inputs of one 8-thread `mco_robust_proton` run captured and replayed outside
radiarch on cci-aries):

- **Where it crashes.** OpenTPS's binary crashed in 4 of 300 replays (and 3 of 28 in an earlier batch); every core
  dump shows the same place: `total_Nuclear_cross_section`, called from `get_interaction_type` in `hadron_step`,
  with a table index of `INT_MIN` — `(int)floor(NaN)`. A proton with a NaN energy reached the cross-section
  lookup, whose only guard is `index >= 249`.
- **How a NaN energy survives.** `hadron_step` retires a particle when `T - dE <= Ecut`; with `dE` NaN that test is
  false, the particle stays alive with `T = NaN`, and the lookup a few lines later reads 8 GB below the table.
  Where the NaN first comes from in the Intel binary was not pinned down: it depends on the build (gcc builds of
  the same source produced one in 300 runs; the Intel build's fast floating-point model and vector code differ).
  No race was found: ThreadSanitizer reported nothing beyond OpenMP's barriers, which it cannot see, and the
  2026-11-13 evidence for one (0 crashes in 24 single-thread case runs against 4 in 28 with 8 threads) is weak at
  these rates. The mechanism above does not need a second thread (not tested on one thread at these numbers).
- **A second defect, found on the way.** AddressSanitizer reported `Transport_to_CT` reading `Translation[3]`, past
  its 3-element array, for every particle whose line never enters the CT (about 12 000 per beamlet run of the
  robust case). In the Intel binary that slot is the return address, so the energy loss came out about 0 and no
  harm was done there; in a gcc build it is whatever the stack holds.
- **Known upstream defects, not fixed here.** AddressSanitizer also reports reads past the end of the nuclear tables
  (`Interp_Nuclear_Cross_section` at start-up; the secondary emission angle index in
  `Compute_Nuclear_Inelastic_*`, upstream issue #42, which also reports the secondaries' angles sampled with the
  energy in eV against brackets in MeV, and up to about 21 % less dose just outside a field's edge). Fixing them
  changes the physics; that is the project lead's decision (open in `impl-plan.md`).

## Decision

1. **radiarch builds MCsquare.** `engines/mcsquare-build/build.sh` clones upstream at the `gcc` branch's commit
   `3ed27f5` (2024-11-04: `master` with the Cilk array notation replaced by OpenMP SIMD loops, so that gcc compiles
   it, and MKL made optional), applies `patches/`, and links a static binary with gcc and oneMKL 2024.2.2 from PyPI:
   `engines/mcsquare/MCsquare_radiarch`. Static, because the `python:3.12-slim` image has no OpenMP runtime.
   **Built, not committed** (the project lead, 2026-11-20; 6 MB, over the repositories' file limit): the image
   builds it in an `ubuntu:24.04` stage, the CI jobs that run MCsquare build it in the same container
   (`build-in-docker.sh`, cached by the recipe's files), developers run that script once. The build is reproducible
   bit for bit on that toolchain, with the sources in a fixed order (a glob sorted by the locale changed the link
   order, and with it the binary); it ends by comparing the binary's SHA-256 with `BUILD.txt`, and in CI and the
   image a different binary fails the build, since the layout decides what the overrunning reads below find.
2. **Four patches** (each a `git format-patch` with its reasons):
   - `0001` makes the `gcc` branch's MKL path work: `Init_RND` set only its own copy of the stream handle, so every
     MKL random-number call failed. With it the engine draws from MKL's MCG59 with `master`'s seeds, as OpenTPS's
     binaries do (the branch's fallback without MKL is `rand_r`: 31-bit numbers from a 32-bit state).
   - `0002` leaves a particle whose line never enters the CT outside, where it is counted as generated outside the
     geometry, instead of reading `Translation[3]`.
   - `0003` drops a particle whose energy or energy loss is not a finite number — before each step and after its
     continuous energy loss — scores nothing for it, counts it, and ends the run with a warning when the count is
     not zero. The driver reads the warning into `MCsquareRun.dropped_particles` and the log.
   - `0004` builds each beamlet's output folder by appending to the path; `sprintf(path, "%sBeamlet_%d/", path, …)`
     read and wrote one buffer, which C leaves undefined. The Intel build happened to give the intended path; gcc
     at `-O3` wrote over the prefix, the beamlet files landed in the work directory, and the merged influence matrix
     was never written (the engine still exited 0).
3. **Compiler flags.** `-O3 -march=x86-64-v3 -ffast-math -fno-finite-math-only -flto`: AVX2 and FMA (every machine
   radiarch runs on has them; a CPU without them stops on an illegal instruction), the fast floating-point model
   the Intel build uses too, except finite-math, which would fold patch 0003's `isfinite` away.
4. **A setting.** `mcsquare_build` (`RADIARCH_MCSQUARE_BUILD`): `radiarch` (the default) runs `MCsquare_radiarch`
   directly; `opentps` runs OpenTPS's launcher and binaries as before. The engine digest and fingerprint name the
   build, so results of the two builds never share a cache entry. The engine's version is 0.4.0.
5. **The material database through a short link (2026-11-21).** MCsquare builds its nuclear-data file names in
   100-byte buffers from the materials directory, the material's name and the file's name. An install path
   longer than about 45 characters overran them: OpenTPS's build silently (it overran its stack in CI all
   along), radiarch's build stops on glibc's check ("buffer overflow detected", CI's checkout under
   `/home/runner/work/...`). The driver links `Materials` into each work directory and gives the engine that
   relative name. Larger buffers in the engine are the upstream fix; changing the binary needs a re-validation.
6. **The workaround goes.** `mco_robust_proton` runs MCsquare on 8 threads again. The driver's retry on a crash
   stays, as a guard.

## Evidence

Replays of the two captured inputs that had crashed, 8 threads each, cci-aries (AMD EPYC 7413):

| Build | Runs | Crashes | Particles dropped (runs with any) |
|---|---|---|---|
| OpenTPS 3.0.1 (Intel) | 300 | 4 (all in `total_Nuclear_cross_section`) | — |
| radiarch, `-O3` (patches 0001–0003; its beamlet outputs were misplaced, see 0004) | 300 | 0 | 1 run |
| radiarch, final (patches 0001–0004, the flags of decision 3) | 300 | 0 | none |

Time on one captured beamlet input with 10x the primaries (8 threads, a quiet host, 4 runs each): OpenTPS's binary
16.6 s (one more run crashed after 2.1 s), radiarch's 20.8 s, so about 1.25 times. Flag variants, measured side by
side under load: `-O3` 1.8 times OpenTPS's time, `-O3 -march=x86-64-v3 -fno-math-errno` 1.5, with fast math 1.26,
with link-time optimization 1.21 (the final flags), with profile-guided optimization on top 1.20. One thread: 1.22,
so the difference is the compiled code, not OpenMP; the profile has no single hot spot.

The validation cases on both builds, same commit, full mode, on cci-aries: `proton_range_water` (R80 at 100 to
225 MeV within 0.1 mm of each other), `proton_bragg_peak` and `mco_robust_proton` pass on both, with the same
checks passing (the robust case took 1820 s with radiarch's build and 1398 s with OpenTPS's, 8 threads each). The
radiarch-side tests that run the engine pass against the binary (81, among them `Dij @ w` against the direct dose
within 1 %).

`proton_bragg_peak` with five seeds per build (mean ± standard deviation of the five; 400 000 primaries a spot):

| Check | OpenTPS | radiarch | radiarch, strict IEEE | clamped, fast | clamped, strict |
|---|---|---|---|---|---|
| R80-20 fall-off, 225 MeV (mm) | 4.978 ± 0.041 | 4.972 ± 0.014 | 4.967 ± 0.034 | 4.969 ± 0.055 | 4.954 ± 0.030 |
| entrance sigma x, 225 MeV (mm) | 2.894 ± 0.040 | 2.928 ± 0.051 | 2.907 ± 0.020 | 2.937 ± 0.025 | 2.924 ± 0.026 |
| peak-to-entrance, 150 MeV | 4.396 ± 0.008 | 4.361 ± 0.008 | 4.306 ± 0.019 | 4.315 ± 0.011 | 4.311 ± 0.028 |
| peak-to-entrance, 225 MeV | 3.902 ± 0.012 | 3.877 ± 0.024 | 3.798 ± 0.013 | 3.801 ± 0.025 | 3.777 ± 0.012 |
| lateral sigma at 0.8 R80, 200 MeV (mm) | 7.709 ± 0.096 | 7.576 ± 0.049 | 7.419 ± 0.045 | 7.470 ± 0.042 | 7.428 ± 0.057 |
| lateral sigma at 0.8 R80, 225 MeV (mm) | 8.488 ± 0.039 | 8.383 ± 0.052 | 8.293 ± 0.042 | 8.297 ± 0.041 | 8.269 ± 0.075 |

Ranges, fall-offs and entrance spot sizes agree between all builds within the noise. The peak-to-entrance ratio
and the lateral spread deep in water, which nuclear interactions shape, do not: radiarch's build is up to 0.8 % and
1.7 % below OpenTPS's. "Strict IEEE" is the same source without fast math (`-O3 -march=x86-64-v3 -fno-math-errno`):
further off, so the flags are not the cause. "Clamped" adds upstream's bounds checks for the nuclear tables (the
emission angle index and the start-up interpolation, as in upstream merge request !7) to both: the two then agree
with each other and with the strict build. So these two quantities depend on what lies past the end of the angle
table in a given binary — in OpenTPS's binary as much as in radiarch's — and no build is the reference for them
until upstream issue #42 is fixed. Clamping alone is not that fix (it sends the out-of-range secondaries to the
165–180° bin); it is not applied.

## Consequences

- The proton Monte Carlo takes about 1.25 times as long per run as OpenTPS's binary. The robust case's nightly runs
  faster than before all the same, since it is back on 8 threads. Intel's oneAPI compiler (`icx`) would compile the
  `gcc` branch too and may close the gap; it is free but not open source, and not tried.
- Doses from the two builds are not the same: ranges, fall-offs and spot sizes agree within the noise; the
  peak-to-entrance ratio (up to 0.8 % lower) and the lateral spread deep in water (up to 1.7 % lower at 200 MeV)
  differ because both builds read past the end of the nuclear angle table (upstream issue #42). `opentps` stays
  available for comparison. Fixing #42 is the project lead's decision and needs a reference to check against.
- `scripts/fetch-engines.sh` refreshes OpenTPS's files and leaves `MCsquare_radiarch` and the oneMKL licence alone.
- oneMKL is under the Intel Simplified Software License: redistribution in binary form is allowed with its notice,
  which is `engines/mcsquare/LICENSE-oneMKL.txt` (and its third-party notices beside it). OpenTPS's binaries link
  oneMKL statically too.
- The patches could go upstream (the project lead's call); a fixed upstream release would replace them.
