# Engine performance and GPU options

Status: investigation for the project lead, 2026-11-13. Measured on the 96-core server (AMD EPYC 7413, four NVIDIA
A100 40 GB) from commit `ad883f2`. Decided with the project lead the same day: MCsquare's crashed runs are run once
more and the robust proton case runs it on one thread (built); the optimizer moves to the GPU next. Every GPU path
stays behind a setting, and the CPU path stays the default. Radiarch is not for clinical use. Later sections add
what was built afterwards: the optimizer on the GPU (2026-11-13), faster engines (2026-11-14) and MCsquare on the
GPU (2026-11-21; ADR 0023, ADR 0024), which reverses this report's first advice on MCsquare.

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
set's 19 solves 16 s against 1226 s), every graded check passing. A second stage the same day moved the meterset
solves, the robust Pareto sets and second sets too: the protocol case then takes 299 s (6.9 times faster than on the
CPU), TG-119 1004 s (4.5 times), of which its solves are 104 s, and the lung Pareto case 2535 s against 20001 s
(7.9 times, every graded check passing). What remains is the engines: the pencil beam's
influence matrices (about 220 s of the protocol case) and the collapsed cone on the CPU (about 840 s of TG-119), where
a GPU collapsed cone (DoseCUDA, above) would be the next measured trial.

## Faster engines, and a GPU collapsed cone tried (2026-11-14)

The project lead chose four items: the collapsed cone's process count, the pencil beam's GPU influence matrices, its
radiological depth on CPU threads, and a measured trial of DoseCUDA. Measured on the 96-core server and one A100:

| Item | Before | After | Results |
|---|---|---|---|
| Collapsed cone, TG-119 influence matrix, 4 to 32 processes (`RADIARCH_CCC_N_JOBS`; 0 = half the cores, at most 32) | 660 s | 79 s | the same matrix at 4, 8, 16 and 32 processes |
| Pencil beam's radiological depth on its CPU threads, the lung protocol case on the CPU | 2072 s | 1639 s | every value the record's |
| Pencil beam's GPU influence matrices in batches, one fused kernel per batch, the case on one A100 | 299 s | 224 to 227 s | the same matrix bit for bit |

- **The collapsed cone** already ran a process per batch of beamlets, each beamlet alone; only its default, 4, held it
  back. From 8 to 32 processes each doubling halves the time.
- **The radiological depth** samples rays and interpolates them at the voxels, both independent per ray and voxel;
  SciPy's interpolation releases the GIL, so threads give the depths of one thread.
- **On the GPU** the time was not, as first thought, Python waiting between beamlet columns: batching the columns
  alone saved 1 %. It was the interpolation of the kernel tables, which CuPy ran as a separate pass over every
  (beamlet, voxel) pair for each step. One CUDA kernel per batch now computes every pair's value; it repeats CuPy's
  operations in their order and precision, compiled without fused multiply-add, so the matrix is the same bit for bit.
- **The GPU optimizer was not reproducible.** Two GPU runs of the lung protocol case ended on different plans (one
  patient's cord maximum 16.5 and 19.1 Gy): cuSPARSE splits long rows and adds the parts in an order that varies from
  run to run. Both products now sum each row in a fixed order (a warp per row), and two runs give every value the same.
  The CPU path was not affected.

**DoseCUDA** (GPL-2.0, commit `48c0421`), built outside radiarch and run on the harness's Monte Carlo phantoms, graded
with `photon_vs_mc`'s metrics:

| Metric | DoseCUDA | WiscPlan CCC | Monte Carlo |
|---|---|---|---|
| Water 10 × 10: PDD at 10 cm | 63.1 % | 68.1 % | 68.0 % |
| Water 10 × 10: gamma 3 %/3 mm pass | 96.4 % | 98.0 % | — |
| Lung slab 10 × 10: correction factor 50 mm deep (in lung) | 0.772 | 1.008 | 1.002 |
| Lung slab 10 × 10: correction factor 80 mm deep (in lung) | 0.789 | 1.009 | 1.063 |
| Lung slab 2 × 2: dose 80 mm deep over dose 20 mm deep | 0.525 | — | 0.641 |
| Bone slab 10 × 10: correction factor 80 mm deep | 0.911 | 0.929 | 0.941 |

It computed an open 10 × 10 field on 1.7 million voxels in 0.03 s, against WiscPlan's 7 to 20 s, and a 5 × 5 mm
aperture in 7.6 ms. But it gives about 23 % less dose than Monte Carlo inside lung, through its own CT-number path as
through a direct density; it ships one beam model (a TrueBeam 6 MV, hence its lower depth dose); and it has no beamlet
output. Not adopted: WiscPlan at 32 processes builds influence matrices about as fast, with its validated accuracy.
Its speed would suit plan and arc-segment doses once its lung behaviour is explained and a beam model is commissioned
to radiarch's machine.

## The influence store, and the collapsed cone's default (2026-11-14)

The project lead set the collapsed cone's default to 8 processes (it was 4: TG-119's matrix in 295 s rather than 660 s,
the same matrix) and asked for the influence store's compression to be tried.

The store wrote every influence matrix with `np.savez_compressed`: zlib at level 6, on one thread. The lung protocol
case's two matrices (6048 beamlets on 3.6 and 3.7 million voxels, 143 and 158 million values, 2.5 GB as arrays),
written three ways in the radiarch image on the server, the median of three writes:

| Way | Write | Read back | On disk |
|---|---|---|---|
| zlib level 6 (`np.savez_compressed`, before) | 79 s | 8.2 s | 1.04 GB |
| zlib level 1 | 33 s | 9.0 s | 1.18 GB |
| Stored as they are (`np.savez`) | 2.0 s | 1.3 s | 2.47 GB |

Each way gave every array back the same. Per array at level 1, the row pointers deflate 12 times, the beamlet indices
3.0 times and the dose values (float32) 1.6 times: the values cost the most time for the least space.

The store now takes `RADIARCH_INFLUENCE_STORE_COMPRESS_LEVEL`: 0, the default, stores the arrays as they are; 1 to 9
deflate them. Every level writes an `.npz` that `np.load` reads, so matrices stored before and the influence-matrix
download keep working. The lung protocol case with its matrices stored as they are:

| Run | Level 6 (before) | Stored (after) | Results |
|---|---|---|---|
| CPU, 6 threads, the two runs side by side | 1672 s | 1571 s | every value the record's, at both levels |
| One A100 (`pb` and the optimizer on the GPU) | 230 s | 140 s | every value the earlier GPU run's |

On the CPU the store's own writes and reads took 3.3 s against 84.5 s. Two CPU runs made apart differ by tens of
seconds in their other stages (1639 s and 1628 s), so the CPU's comparison is of two runs made at the same time.

The cost is disk: about 2.4 times as much per matrix. The store's cap (`RADIARCH_INFLUENCE_STORE_MAX_GB`, 100 GB) and
its eviction are unchanged, so it holds fewer matrices. A site short on disk sets level 1: 2.1 times smaller than
stored, and 2.4 times faster to write than level 6.

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

**Resolved (2026-11-20, ADR 0023).** The cause was not a race: a proton whose energy became NaN stayed alive and
indexed a nuclear cross-section table at `INT_MIN`. Radiarch now builds MCsquare from upstream's source with its own
patches (`engines/mcsquare-build`, `MCsquare_radiarch`), which drop such particles and fix an out-of-bounds read in
`Transport_to_CT`; the one-thread workaround is gone. Upstream issue #42 (the secondaries' emission angles sampled
with the energy in eV against a table in MeV, reading past the table) was fixed on 2026-11-21 (patch 0005, ADR 0024;
see the Geant4 comparison below). The patched build runs at about 0.8 times the stock binary's speed on one thread
and about 0.9 times on 48 (table below).

## MCsquare on a GPU, built (2026-11-21)

Once MCsquare was built from source (ADR 0023), the project lead asked for a GPU port to be explored, then built into
radiarch behind a setting (ADR 0024). The code is in `engines/mcsquare-gpu` (patches 0006–0008 on top of
`engines/mcsquare-build`'s 0001–0005); its README keeps the full measurements.

### Design

- **Only the transport moves.** MCsquare's own CPU code still reads the configuration, CT, materials, beam data
  library and plan, samples the primaries (one MKL stream per OpenMP thread, in batches of 2 million), applies
  robustness scenarios' errors, post-processes and writes the outputs. One binary, `MCsquare_gpu`, runs MCsquare's
  CPU path by default and the GPU path with `MCSQUARE_GPU=1`, so both can be compared on identical inputs.
- **One proton history per GPU thread**, the design FRED (Schiavi et al. 2017) and Wan Chan Tseung et al. describe,
  following MCsquare's `hadron_step` step by step: steps to the voxel boundary, the same stopping powers per
  material, restricted energy loss with MCsquare's second-order correction, Gaussian straggling, Fippel multiple
  scattering, hard ionization with the delta electron absorbed locally, the energy cut, online dose-to-water.
  Philox random numbers; dose in float atomics per batch, folded into double precision after each batch.
- **Nuclear interactions** (patch 0007): proton–proton and ICRU elastic scattering, inelastic events with secondary
  protons, deuterons and alphas on a per-thread stack of 24 (transported before the next primary; a full stack is
  counted), recoils deposited locally, mixtures by component. The secondaries' angles need issue #42's fix: the
  original read past its table, which a GPU cannot reproduce. That is why the CPU build took the fix as well.
- **Influence matrices** (patch 0008, what radiarch's optimizer reads): spots in groups that fit a dose-memory budget
  (`MCSQUARE_GPU_DOSE_BYTES`, 4 GB by default), each spot with its own dose grid on the device; scaling, the
  threshold and the compaction run on the device, and the host writes MCsquare's sparse format straight into the
  merged output files, which radiarch reads unchanged. Compacting on the device took 0.25 s where copying the dense
  grids back took 2.8 s.
- **Robustness scenarios** needed nothing: MCsquare applies each scenario's setup error in the sampling and its range
  error to the densities, then calls the two functions the GPU replaces.
- **Not supported** (the run stops with a message): 4D, LET, prompt gammas, energy scoring, a separate scoring grid.
  Radiarch asks for none of them.

### In radiarch

- **Setting** `mcsquare_device` (`RADIARCH_MCSQUARE_DEVICE`; per run, the engine parameter `device`): `cpu` (the
  default) runs `MCsquare_radiarch`; `gpu` runs `MCsquare_gpu` and fails without a GPU; `auto` uses the GPU when the
  host shows one and falls back to the CPU build when the GPU fails to start. GPU results get cache keys of their
  own, following the setting, as the optimizer's do (ADR 0022). `docker-compose.gpu.yml` gives the worker a GPU.
- **Build**: a stage of the image, `ubuntu:22.04` with CUDA 12.6's compiler, runtime and headers from NVIDIA's apt
  repository (about 0.5 GB, against several GB for NVIDIA's CUDA images). The binary links oneMKL, libgomp,
  libstdc++ and the CUDA runtime statically; it needs only glibc and the NVIDIA driver (R525 or newer). Code for
  compute capability 8.0 (A100) plus PTX that newer GPUs compile on first use.
- **Tests**: with a GPU, `TestGpuRuns` compares the GPU's dose (through a bone slab), influence matrix and robustness
  scenarios with the CPU build's. CI has no GPU: it builds the binary in the image, checks its libraries resolve,
  and tests the device logic and `auto`'s fallback.

### Speed

Whole-run wall times on the 96-core server and one A100, nuclear interactions on, the same seed; the median of three
runs (one run on one thread). The case: 13 × 13 spots × 5 layers (110–150 MeV, 845 spots) through bone and lung on a
2 mm grid of 1.25 million voxels. Speed-up against the stock binary on one thread in parentheses.

| | Stock, 1 thread | Stock, 48 | Stock, 96 | Patched, 1 | Patched, 48 | Patched, 96 | One A100 |
|---|---|---|---|---|---|---|---|
| Full dose, 10⁷ protons | 251 s | 7.1 s (35×) | 5.8 s (43×) | 324 s (0.77×) | 8.0 s (32×) | 6.9 s (36×) | 1.63 s (154×) |
| Influence matrix, 845 spots × 10⁴ protons | 217 s | 10.2 s (21×) | 9.0 s (24×) | 276 s (0.79×) | 10.1 s (22×) | 10.5 s (21×) | 1.98 s (109×) |

- **Against the patched build on 48 cores**, a run is about 5 times faster on one A100 (4.9× for the dose, 5.1× for
  the influence matrix).
- **The transport alone** is 16 to 19 times faster than the CPU run: 13–31 million protons a second without nuclear
  interactions (19–23 million in the heterogeneous field), 8–12 million with them. A whole run gains less because of
  fixed costs: about 0.5 s to start CUDA, about 0.2 s of sampling on the CPU, and MCsquare's own input and output.
  The influence matrix's 2.2 s split into transport 0.63 s, compaction and transfer 0.25 s, sampling 0.17 s and
  writing 0.20 s.
- **Small runs gain nothing**: a 150 MeV spot with 10⁶ protons took 1.0 s on the GPU against 1.1 s.
- **A robust plan gains little**: `mco_robust_proton` took 1494 s with the GPU against 1684 s on the CPU (on a loaded
  server), because MCsquare is about a fifth of the case's time; the optimizer and evaluation take the rest.
- **Fast math** (`--use_fast_math`) roughly doubles the transport rate again (33–45 million a second) with no visible
  change at these statistics. It stays off until a high-statistics check.

### Agreement with the CPU

Each GPU–CPU difference beside the difference between two CPU runs with different seeds (the Monte Carlo noise), over
the voxels above 10 % of the maximum, in % of the maximum:

| Comparison | GPU − CPU | CPU − CPU (noise) |
|---|---|---|
| Bone/lung field, nuclear off: rms / mean | 1.01 % / −0.015 % | 1.01 % / −0.007 % |
| Bone/lung field, nuclear on | 1.11 % / −0.023 % | 1.10 % / −0.018 % |
| 200 MeV spot in water, nuclear on | 0.16 % / −0.015 % | 0.16 % / −0.006 % |
| Influence matrix: each spot's integral, mean / sd of the difference | +0.013 % / 0.279 % | −0.007 % / 0.276 % |
| Influence matrix: summed dose, rms / mean | 1.165 % / +0.007 % | 1.162 % / −0.005 % |

In the nuclear runs, the 10⁷ primaries made 4.3 to 7.7 million secondaries; no secondary was lost to a full stack.

### Against Geant4, and the validation cases

The nuclear halo's lateral variance (nuclear physics on minus off, so the codes' multiple-scattering models cancel)
in water, against Geant4 (OpenGATE, `QGSP_BIC_EMZ`), at half the range:

| Build | 200 MeV | 225 MeV |
|---|---|---|
| `MCsquare_gpu` | +3 % | +6 % |
| Patched CPU build, with issue #42's fix | +2 % | +5–6 % |
| Earlier builds (the stock binary, radiarch's build before the fix) | −25 % | −21 to −22 % |

At 0.8 of the range both the GPU and the CPU are 11 % (200 MeV) and 8 % (225 MeV) below Geant4: MCsquare's models,
not the GPU. The three proton validation cases pass on both:

| Case | Patched CPU | One A100 |
|---|---|---|
| `proton_range_water` | pass (4 of 4) | pass (4 of 4) |
| `proton_bragg_peak` | pass (12 of 12) | pass (12 of 12) |
| `mco_robust_proton` | pass (11 of 11); robust gap 0.0667, CTV minimum 1.689 Gy | pass (11 of 11); robust gap 0.0643, CTV minimum 1.687 Gy |

### Limits and what is open

- **Not reproducible bit for bit.** GPU threads hand over their primaries in the order they finish and add dose with
  floating-point atomics, so two GPU runs with one seed agree within the noise, not digit for digit. A CPU run on
  one thread with a seed stays reproducible.
- **Open** (`docs/impl-plan.md`): deterministic runs (ordered primaries, deterministic scoring), one CUDA start-up
  per worker instead of per run, several GPUs by spot ranges, the high-statistics check of fast math, LET.

## GPU engines that exist (survey, 2026-11-13)

Licences and activity read from the repositories on 2026-11-13; speed and validation from the papers named.

| Kind | Candidate | Licence | State | What is reported | Fit |
|---|---|---|---|---|---|
| Proton MC | MOQUI (Lee et al., PMB 67:174001, 2022) | MIT | no commit since 2024-05; no releases | CUDA; within 2 % of TOPAS, gamma > 99 % at 2 %/2 mm; a head-and-neck Dij in under 10 min on a consumer GPU; robust setup and density options | a subprocess like MCsquare; its own machine model, so the beam must be recommissioned; no electron transport in air |
| Proton MC | FRED (Schiavi et al., PMB 62:7482, 2017) | proprietary | in clinical QA use | about 10⁷ protons per second per GPU | not open; redistribution unclear |
| Proton MC | gPMC, goPMC, VPMC | not released | — | — | not available |
| Proton MC | an MCsquare GPU port | none found | — | — | — (radiarch built its own on 2026-11-21, above) |
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
   of the case's 2072 s), and split the radiological depth over threads (505 s on one thread). Both built
   (2026-11-14).

For the engines that are programs, adopt rather than port:

4. **MCsquare**: the retry and the proton case on one thread are built (2026-11-13). Finding the race means
   rebuilding MCsquare with AddressSanitizer and the upstream patches; the build needs an older Intel compiler. A GPU
   port of MCsquare is not worth our effort. *Superseded:* MCsquare is built from source with gcc (ADR 0023), the
   crash was a NaN energy rather than a race, and the GPU port was built after all (ADR 0024, section above).
5. **Measured trials, one at a time, against our references**: MOQUI for proton influence matrices (it would also
   replace the crashing engine), DoseCUDA's CCC against WiscPlan, and pyRadMC as a photon Monte Carlo between CCC and
   OpenGATE. Each is adopted only after its own validation case passes; none is a drop-in replacement.
6. **Not now**: learned dose engines, and our own CUDA ports of CCC or MCsquare (DoseCUDA and MOQUI exist).
   *Superseded for MCsquare* (2026-11-21): porting only the transport inside MCsquare kept its beam model, inputs and
   outputs, which MOQUI would have needed recommissioned.

## How these were measured

Each case ran in the radiarch image built from `48c0cc4` with a clean checkout of `ad883f2` mounted over its code,
6 BLAS threads, under cProfile; the GPU runs added CuPy 14.2 (`cupy-cuda12x[ctk]`) and one A100. The products were
timed as the best of five on the influence matrix the GPU run stored. The stage times come from the services' log
lines; cProfile adds little to time spent in NumPy, SciPy and CuPy.

The MCsquare GPU measurements (2026-11-21) used the same server with the CPU build on 48 threads unless a table
says otherwise; the inputs and scripts are in `engines/mcsquare-gpu/bench`, the Geant4 comparison in
`engines/mcsquare-build/halo`.

The store's formats (2026-11-14) were timed on one thread in the same image, with a clean checkout of `c6c07d9`, on
the two matrices a GPU run of the lung protocol case stored; the files were written to the container's own disk and
read back while still in the page cache, as the optimizer reads them right after they are built.
