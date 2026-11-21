# ADR 0024 — MCsquare: upstream issue #42 fixed, and the transport on a GPU

Date: 2026-11-21. Status: on the project lead's word ("Yes, I would like both recommendations", 2026-11-21);
`dev`, waiting for a merge into `master`.

## Context

ADR 0023 left two things open. First, upstream issue #42: MCsquare samples the emission angle of a nuclear
secondary by interpolating its angle table at the secondary's energy in eV between two table energies in MeV. The
interpolation extrapolates far outside its bracket and the angle index can run past `ICRU_angles`; what it reads
there depends on the binary's memory layout, so the peak-to-entrance ratio and the lateral spread deep in water
differed between OpenTPS's build and radiarch's (up to 0.8 % and 1.7 %), and no build was a reference. Second, the
GPU prototype (`engines/mcsquare-gpu`) had matched the CPU engine within the Monte Carlo noise for full doses and
influence matrices, with the transport about 16 times faster on one A100 than on 48 CPU cores; it used #42's fix,
since a GPU cannot reproduce the read past the table.

The two recommendations the project lead accepted: adopt #42's fix in the production CPU build, re-running the
proton validation; and offer the GPU engine through a setting whose default stays the CPU.

## Decision

1. **Patch 0005 in radiarch's build** (`engines/mcsquare-build/patches/0005`): the secondary's angle table is
   interpolated at the energy the secondary was drawn at, on the table's grid (MeV), before it is rescaled to the
   primary's energy; the rescaled energy is still the one it is transported with. The start-up interpolation of a
   mixture's components keeps its index inside each component's table, as the ICRU branch already did. The build
   of record is now `6113e096…` (`BUILD.txt`; the docker build and a native build on cci-aries agree bit for bit).
   The engine's version is 0.5.0, so cached doses of 0.4.0 are not reused.
2. **`MCsquare_gpu`** (`engines/mcsquare-gpu`): the same source and patches 0001–0005, plus patches 0006–0008 (the
   CUDA transport: electromagnetic and nuclear physics, full dose and influence matrices). MCsquare's own code reads
   the inputs, samples the primaries, applies each robustness scenario's errors and writes the outputs; only the
   transport moves. Radiarch's three kinds of run — a dose, an influence matrix, MCsquare's robustness scenarios —
   all run on it. Built, not committed: in an `ubuntu:22.04` stage of the image with CUDA 12.6's compiler, runtime
   and headers from NVIDIA's apt repository (about 0.5 GB, not the multi-GB CUDA images; glibc 2.35, which the
   `python:3.12-slim` runtime runs), and by `build-in-docker.sh` for developers. It links oneMKL, libgomp,
   libstdc++ and the CUDA runtime statically and needs only glibc and, at run time, the NVIDIA driver (R525 or
   newer). Code for compute capability 8.0 (A100; runs on 8.6 and 8.9) and PTX that newer GPUs compile on first
   use. `RADIARCH_MCSQUARE_GPU=0` builds the image without it.
3. **A setting**, `mcsquare_device` (`RADIARCH_MCSQUARE_DEVICE`; per run, the engine parameter `device`):
   `cpu` (the default) runs `MCsquare_radiarch`; `gpu` runs `MCsquare_gpu` with `MCSQUARE_GPU=1` and fails when the
   binary or a GPU is missing; `auto` runs the GPU binary when it is there and the host shows a GPU, and runs the
   CPU build when the GPU fails to start (the driver recognises the binary's ` ERROR: GPU` line; the log is kept
   as `mcsquare-gpu.log`). `CUDA_VISIBLE_DEVICES` picks the GPU. A device other than `cpu` gives cache keys of
   their own; they follow the setting, not the host, as the optimizer's device does (ADR 0022).
   `docker-compose.gpu.yml` gives the worker a GPU and sets `auto`.
4. **Not bit for bit.** A GPU run is not reproducible: the sampling threads hand over their primaries in the order
   they finish, and the dose is accumulated with floating-point atomics. Two GPU runs with the same seed agree
   within the noise, not digit for digit; a CPU run on one thread with a seed stays reproducible.

## Evidence

**Issue #42's fix against Geant4** (`engines/mcsquare-build/halo/`). The `proton_bragg_peak` phantom (water,
±40 mm, 350 mm deep, 1 mm voxels) and an idealised beam (one Gaussian of 3 mm, 0.1 mrad, no energy spread) at 200
and 225 MeV, 10⁷ protons per MCsquare run, 4·10⁶ per Geant4 run (OpenGATE, `QGSP_BIC_EMZ`, cuts 0.5 mm). Each code
was also run with electromagnetic physics only, and the nuclear halo's share of the lateral variance is the
difference (on minus off), so the codes' multiple-scattering models — which agree within 2–4 % in width — cancel.
The lateral profile is the dose summed over the other axis, its rms over ±40 mm, at half and at 0.8 of the range:

| 200 MeV | rms 0.5 R80 (mm) | nuclear variance (mm²) | vs Geant4 | dose beyond 10 mm | rms 0.8 R80 (mm) | nuclear variance | vs Geant4 |
|---|---|---|---|---|---|---|---|
| Geant4 | 6.72 | 32.6 | | 6.70 % | 7.71 | 34.4 | |
| radiarch, patch 0005 (two seeds) | 6.74 | 33.3–33.4 | +2 % | 6.84 % | 7.35 | 30.6–30.8 | −11 % |
| `MCsquare_gpu` | 6.76 | 33.6 | +3 % | 6.87 % | 7.34 | 30.6 | −11 % |
| radiarch, before (ADR 0023) | 6.04 | 24.4 | −25 % | 5.30 % | 7.08 | 26.8 | −22 % |
| OpenTPS 3.0.1 | 6.04 | 24.4 | −25 % | 5.33 % | 7.14 | 27.6 | −20 % |

| 225 MeV | rms 0.5 R80 (mm) | nuclear variance (mm²) | vs Geant4 | dose beyond 10 mm | rms 0.8 R80 (mm) | nuclear variance | vs Geant4 |
|---|---|---|---|---|---|---|---|
| Geant4 | 7.28 | 38.8 | | 8.03 % | 8.47 | 39.7 | |
| radiarch, patch 0005 (two seeds) | 7.38–7.40 | 40.9–41.3 | +5–6 % | 8.24 % | 8.15 | 36.5–36.6 | −8 % |
| `MCsquare_gpu` | 7.40 | 41.3 | +6 % | 8.23 % | 8.15 | 36.5 | −8 % |
| radiarch, before | 6.63 | 30.5 | −22 % | 6.64 % | 7.83 | 31.4 | −21 % |
| OpenTPS 3.0.1 | 6.64 | 30.5 | −21 % | 6.65 % | 7.90 | 32.5 | −18 % |

With the overrun, both earlier builds put about a fifth to a quarter too little of the dose into the nuclear halo;
with the fix MCsquare is within 2–6 % of Geant4 at half the range and 8–11 % below it at 0.8 of the range. Ranges
(R80 within 0.6 mm of Geant4's) and the electromagnetic part do not change. The peak-to-entrance ratio is above
Geant4's in every MCsquare build, with or without the fix (4.39 against 4.28 at 200 MeV, 4.03 against 4.02 at
225 MeV): that is not the angle table.

**`proton_bragg_peak` with five seeds per build** (the clinical beam data library; mean of five, 400 000 protons a
spot; ADR 0023's table extended):

| Check | OpenTPS | radiarch before | radiarch, patch 0005 |
|---|---|---|---|
| peak-to-entrance, 150 MeV | 4.396 ± 0.008 | 4.361 ± 0.008 | 4.386 ± 0.009 |
| peak-to-entrance, 225 MeV | 3.902 ± 0.012 | 3.877 ± 0.024 | 3.884 ± 0.020 |
| lateral sigma at 0.8 R80, 200 MeV (mm) | 7.709 ± 0.096 | 7.576 ± 0.049 | 7.834 ± 0.057 |
| lateral sigma at 0.8 R80, 225 MeV (mm) | 8.488 ± 0.039 | 8.383 ± 0.052 | 8.752 ± 0.044 |
| R80-20 fall-off, 225 MeV (mm) | 4.978 ± 0.041 | 4.972 ± 0.014 | 4.973 ± 0.028 |
| entrance sigma x, 225 MeV (mm) | 2.894 ± 0.040 | 2.928 ± 0.051 | 2.950 ± 0.037 |

The deep lateral sigma (an rms over ±40 mm, which the halo dominates; informative in the case) grows by 2–4 %, as
the comparison with Geant4 says it should; fall-offs and entrance spot sizes do not move.

**Validation cases**, full mode, cci-aries, all three on each:

| Case | radiarch CPU, patch 0005 (`6113e096…`) | `MCsquare_gpu`, one A100 |
|---|---|---|
| `proton_range_water` | pass (4 of 4) | pass (4 of 4) |
| `proton_bragg_peak` | pass (12 of 12, 8 informative) | pass (12 of 12, 8 informative) |
| `mco_robust_proton` | pass (11 of 11, 26 informative), robust gap 0.0667, CTV Dmin 1.689 Gy | pass (11 of 11), robust gap 0.0643, CTV Dmin 1.687 Gy |

The engine's tests (`test_mcsquare_driver.py`, `test_engine_assets.py`) pass in radiarch's image; with a GPU,
`TestGpuRuns` compares the GPU's dose (with a bone slab), influence matrix and robustness scenarios with the CPU
build's (all within 1–2 %); without one, the real GPU binary's start-up failure sends `auto` to the CPU.

**Speed** (engines/mcsquare-gpu/README.md): on the bone/lung field with nuclear interactions on, a full dose of 10⁷
protons takes 8.0 s on 48 cores with radiarch's build (6.9 s on 96 threads) and 1.6 s on one A100; its 845-spot
influence matrix 10.1 s against 2.0 s. The robust case's Monte Carlo is about a fifth of its time, and the case's
wall time on a loaded host was 1684 s on the CPU against 1494 s with the GPU.

## Consequences

- Doses change, in radiarch's default build: the nuclear halo's variance is a fifth to a quarter larger than before
  (and than OpenTPS's build); at half the range about 1.5 % of a spot's dose moves from within 10 mm of its axis to
  beyond (5.3 % → 6.8 % at 200 MeV); ranges, fall-offs and spot sizes do not change. Plans made with 0.4.0 are not reproduced by 0.5.0; cached
  doses and influence matrices of 0.4.0 are not reused. `mcsquare_build=opentps` keeps the old behaviour for
  comparisons.
- Geant4 is a second Monte Carlo, not a measurement; the remaining differences (8–11 % less halo variance at 0.8 of
  the range, a peak-to-entrance ratio up to 2.6 % higher) are MCsquare's models, not the overrun.
- The GPU is opt-in. CI has no GPU: it builds the GPU binary in the image job and checks that it finds its
  libraries there, and runs the driver's device logic against stand-ins; the GPU's own tests and the validation on
  the GPU run on a GPU host (cci-aries), as here.
- A GPU run is not reproducible bit for bit (decision 4). Deterministic GPU runs, one CUDA start-up per worker
  instead of per run, several GPUs, and fast math are open (`docs/impl-plan.md`).
- The image grows by the GPU binary (about 10 MB) and its build stage by NVIDIA's packages (about 0.5 GB, build only).
- The patch could go upstream with issue #42 (the project lead's call).
