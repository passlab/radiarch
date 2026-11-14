# Engine performance and GPU options

Status: investigation for the project lead, 2026-11-13. Measured on the 96-core server (AMD EPYC 7413, four NVIDIA
A100 40 GB) from commit `ad883f2`. Decided with the project lead the same day: MCsquare's crashed runs are run once
more and the robust proton case runs it on one thread (built); the optimizer moves to the GPU next. Every GPU path
stays behind a setting, and the CPU path stays the default. Radiarch is not for clinical use.

## The question

Can the dose engines and the planning around them be made much faster, and does that need our own CUDA ports, or do
GPU engines exist that radiarch could run instead? The engines are radiarch's pencil beam (`pb`, NumPy, with a CuPy
path), the WiscPlan collapsed cone (CCC, a GPLv2 program run as a subprocess), MCsquare (proton Monte Carlo, a
program run as a subprocess) and OpenGATE (photon Monte Carlo for the validation references, run offline).

## Where the time goes today

The records' rerun of 2026-11-12 (`0228ec6`, one case per process, each capped at 6 BLAS threads; 32 for
`mco_protocol_lung`), from the time stamps of each case's log:

| Case | Time | Where it goes |
|---|---|---|
| `mco_protocol_lung` | 5.6 h | 93 % in the optimizer's 239 solves |
| `lung_4d_itv` | 2.3 h | 64 % the plan recomputed on ten breathing phases (`pb`); 17 % influence matrices; 6 % arcs |
| `lung_vmat_lctsc` | 2.0 h | about 70 % dose engines (CCC and `pb`); 21 % geometry; 7 % optimizer |
| `mco_front_tg119` | 1.3 h | 77 % in the optimizer's 84 solves; 10 % CCC |
| `hn_sib_vmat` | 1.2 h | 45 % arc doses (`pb`); 34 % optimizer; 21 % influence matrices |
| `protocol_lung_vmat` | 0.6 h | 50 % influence matrices (`pb`); 29 % arc doses (`pb`); 20 % optimizer |

Two costs dominate: the pencil beam's doses (influence matrices and arc segments) and the optimizer. The optimizer
spends its time in two places, both on one CPU thread: the products with the influence matrix (`Dij @ w` for the dose,
`Dij.T @ g` for the gradient; SciPy's sparse products are single-threaded) and the objective terms evaluated on the
full dose grid.

A profile of `protocol_lung_vmat` (cProfile, 2072 s on the CPU) splits its own time as: the pencil beam's
Python-level code 803 s; its radiological depth through `scipy.ndimage.geometric_transform`, single-threaded, 505 s;
the sparse products 202 s; the objective terms 159 s; compressing influence matrices into the influence store
(`np.savez_compressed`) 86 s.

## The pencil beam on a GPU

`pb` already runs on a GPU through CuPy (ADR 0015, decision 6); the records and the nightly run do not install CuPy.
`protocol_lung_vmat` with `RADIARCH_PB_DEVICE=gpu` on one A100:

| Stage | CPU | GPU | Speed-up |
|---|---|---|---|
| Influence matrices (two patients) | 1032 s | 227–236 s | 4.5× |
| Arc doses, 192 control-point intervals per arc | 593 s | 22 s | 27× |
| Optimizer (CPU in both) | 405 s | 433–460 s | none |
| The case | 2072 s | 728–764 s | 2.8× |

**The GPU's plans differ from the CPU's.** All 18 RTOG 0617 goal values pass, but 6 of the 18 comparisons with the
recorded harness run (made on the CPU) differ by more than their 1 % tolerance; one patient's cord maximum is
16.03 Gy against 18.85 Gy. The doses agree to 3 × 10⁻⁶ (ADR 0015); the likely cause is that influence-matrix
entries at the sampling threshold round differently, and the optimizer settles on another trade-off. A record or a
deployment that changes device is therefore an output change; the records would need a rerun on the device that
makes them.

## The optimizer on a GPU

The products with one of the case's influence matrices (3.7 million voxels × 6048 beamlets, 1.6 × 10⁸ non-zeros,
1.3 GB in single precision):

| | `Dij @ w` | `Dij.T @ g` |
|---|---|---|
| SciPy, one thread (as the optimizer does it) | 281 ms | 290 ms |
| SciPy, rows split over 32 threads | 91 ms | 73 ms |
| CuPy on an A100, the matrix kept on the device | 1.8 ms | 1.9 ms |
| the same, with the copies to and from the host | 3.1 ms | 5.7 ms |

The products become 50 to 150 times faster on the GPU, and threads on the CPU give only 3 to 4 times (the products
are limited by memory bandwidth). The objective terms (a sigmoid and sums over each structure's voxels) are array code
of the kind `pb` already runs through CuPy; we estimate a few milliseconds per evaluation on the GPU (not measured).
Keeping the influence matrix and its transpose on the device and only the weights and the gradient (a few tens of
kilobytes) on the host leaves SciPy's L-BFGS-B unchanged. Robust sets need one matrix per scenario: a matrix of this
size and its transpose take 2.6 GB on the device, so about 14 scenarios fit in one A100's 40 GB.

In the multi-criteria cases the objective terms weigh more than the products. A profile of `mco_front_tg119`
(4510 s on the CPU, CCC influence matrices, 84 solves) puts 3596 s in the solves: about 2140 s in the objective terms
(a generalized EUD and the sigmoid of the dose-volume terms, over the full grid) and about 1070 s in the products.
Both must move to the GPU for the gain.

## The optimizer on a GPU, built (2026-11-13)

ADR 0022: `RADIARCH_OPTIMIZER_DEVICE` (`cpu` by default, `gpu`, `auto`) moves the fluence solves' products and
objective terms to the GPU. On an A100, `protocol_lung_vmat` with `pb` on the GPU as well takes 496 s against 2072 s
on the CPU (its fluence solves 2 to 7 s against 117 to 124 s), and `mco_front_tg119` 2278 s against 4510 s (its first
set's 19 solves 16 s against 1226 s), every graded check passing. The meterset solves still run on the CPU and are
now most of what remains.

## MCsquare: speed, and the crash

MCsquare runs on the CPU with as many threads as it is given. Our binary is the upstream "Release_1.1", built
2024-08-06; upstream has had no release since 2019 and no commit since 2024-09-18.

**The crash.** `mco_robust_proton` errored in the nightly run of 2026-11-13: MCsquare died on a segmentation fault
(exit 139) while computing the robust scenarios' beamlets with 8 threads. Repeated in its fast mode: 4 of 28 runs
crashed with 8 threads, 0 of 24 with one thread. A thread race is therefore the likely cause. Upstream knows no such
crash; its tracker has open out-of-bounds reads (issue #42, and an AddressSanitizer report in merge request !7) that
could also crash at random. One thread doubles the fast case's time (about 110 s against 55 s).

**A retry** (the driver runs a crashed engine once more; built 2026-11-13, ADR 0006): of 16 runs with 8 threads, 3
crashed; the retry recovered 2, and in the third the engine crashed again. A retry makes a crash rarer but does not
remove it, so `mco_robust_proton` now also runs the engine on one thread.

**A separate, borderline check.** In the same runs the check "robust set: the robust gap within the error bound" failed
twice (1 of 16 with 8 threads, 1 of 24 with one), by up to 6 %: in fast mode, with 10⁴ primaries and the seed taken
from the clock, the gap and the bound vary from run to run and sit close together.

## GPU engines that exist (survey, 2026-11-13)

Licences and activity read from the repositories on 2026-11-13; speed and validation from the papers named.

| Kind | Candidate | Licence | State | What is reported | Fit |
|---|---|---|---|---|---|
| Proton MC | MOQUI (Lee et al., PMB 67:174001, 2022) | MIT | no commit since 2024-05; no releases | CUDA; within 2 % of TOPAS, gamma > 99 % at 2 %/2 mm; a head-and-neck Dij in under 10 min on a consumer GPU; robust setup and density options | a subprocess like MCsquare; its own machine model, so the beam must be recommissioned; no electron transport in air |
| Proton MC | FRED (Schiavi et al., PMB 62:7482, 2017) | proprietary | in clinical QA use | about 10⁷ protons per second per GPU | not open; redistribution unclear |
| Proton MC | gPMC, goPMC, VPMC | not released | — | — | not available |
| Proton MC | an MCsquare GPU port | none found | — | — | — |
| Proton pencil beam | DoseCUDA (Bhattacharya et al., JACMP 26:e70093, 2025) | GPL-2.0 | active | 0.28 s per plan; gamma 96 % at 2 %/2 mm against a commercial MC | a separate process (GPL); no per-spot output documented |
| Proton pencil beam | pyRadPlan (BSD-3), PyDoseRT (MIT) | permissive | active | array-API (CuPy, PyTorch); no GPU benchmarks or clinical validation | in-process; young |
| Photon MC | pyRadMC | Apache-2.0 | created 2026-08; pre-1.0 | NVIDIA Warp; a sparse Dij with per-entry uncertainty; self-reported speed only | in-process; check against our OpenGATE references; no linac head model |
| Photon MC | GPUMCD, ARCHER-RT, gDPM | commercial or not released | — | 50–80 s to 1 % for ARCHER-RT | not available |
| Photon CCC | DoseCUDA (photon part) | GPL-2.0 | active | no full-text validation of its CCC found; one 6 MV model | a separate process, as WiscPlan; Dij output would need a patch |
| Photon CCC | Neph et al., Med Phys 46:3719 (2019): multi-GPU beamlet CCC | not released | — | 44–60× on one GPU against a sequential GPU method | the design reference for a GPU beamlet CCC |
| Learned dose | DoTA (protons, GPL-3.0), iDoTA (photons) | GPL-3.0 | research | 5 ms per beamlet on an A100 | not mature enough to replace Monte Carlo |

## Recommendations

The largest gains are in radiarch's own code, and they need no new engine:

1. **Run the optimizer's products and objective terms on the GPU** (CuPy, the array-API pattern `pb` uses; L-BFGS-B
   stays in SciPy; next, behind a setting, with the CPU path as the default). The multi-criteria cases spend 77 to
   93 % of their time there, and the protocol cases 20 %. The products measured 50 to 150 times faster. Independent
   multi-criteria solves can also run on the four GPUs at once.
2. **Install CuPy where a GPU exists and run `pb` on it**: 2.8 times on the protocol case today, and more once (1)
   is done. Plans change with the device, so this is an output change: decide whether the records are made on the
   GPU (and rerun them), or make the GPU's influence matrices round as the CPU's do first.
3. **Two CPU fixes for machines without a GPU**: store influence matrices uncompressed or with a faster codec (86 s
   of the case's 2072 s), and split the radiological depth over threads (505 s on one thread).

For the engines that are programs, adopt rather than port:

4. **MCsquare**: the retry and the proton case on one thread are built (2026-11-13). Finding the race means
   rebuilding MCsquare with AddressSanitizer and the upstream patches; the build needs an older Intel compiler. A GPU
   port of MCsquare is not worth our effort.
5. **Measured trials, one at a time, against our references**: MOQUI for proton influence matrices (it would also
   replace the crashing engine), DoseCUDA's CCC against WiscPlan, and pyRadMC as a photon Monte Carlo between CCC and
   OpenGATE. Each is adopted only after its own validation case passes; none is a drop-in replacement.
6. **Not now**: learned dose engines, and our own CUDA ports of CCC or MCsquare (DoseCUDA and MOQUI exist).

## How these were measured

Each case ran in the radiarch image built from `48c0cc4` with a clean checkout of `ad883f2` mounted over its code,
6 BLAS threads, under cProfile; the GPU runs added CuPy 14.2 (`cupy-cuda12x[ctk]`) and one A100. The products were
timed as the best of five on the influence matrix the GPU run stored. The stage times come from the services' log
lines; cProfile adds little to time spent in NumPy, SciPy and CuPy.
