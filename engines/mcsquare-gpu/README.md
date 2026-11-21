# MCsquare on a GPU (2026-11-21)

A CUDA transport inside radiarch's build of MCsquare. Started as a prototype (the project lead's go, 2026-11-21);
since ADR 0024 radiarch runs it with `RADIARCH_MCSQUARE_DEVICE=gpu` (or `auto` on a host with a GPU); the default
stays the CPU build of `engines/mcsquare-build` (ADR 0023). This directory builds `engines/mcsquare/MCsquare_gpu`,
which runs MCsquare's CPU path by default and the GPU path with `MCSQUARE_GPU=1` (the driver sets it), so both can
be compared on identical inputs.

## What it does

`patches/0006`–`0008` (on top of `engines/mcsquare-build/patches/0001`–`0005`) hand `Simulation_loop` and
`Run_simulation_beamlet` to the GPU when `MCSQUARE_GPU=1`:

- MCsquare's own code reads the configuration, CT, materials, beam data library and plan, samples the primaries
  (`Generate_PBS_particle`, one MKL stream per OpenMP thread, in batches of 2 million), post-processes and writes
  `Dose.mhd`. Only the transport moves.
- `gpu_transport.cu` transports the primaries, one history per GPU thread (the design FRED's and Wan Chan Tseung's
  papers describe), following `hadron_step` step by step for a proton: steps to the voxel boundary, PSTAR/Geant4
  stopping powers per material, restricted energy loss with MCsquare's second-order correction, Gaussian
  straggling, Fippel multiple scattering, hard ionization with the delta electron absorbed locally, the energy cut,
  online dose-to-water. Philox random numbers; dose in float atomics per batch, folded into double after each batch.
- Nuclear interactions (`0007`): MCsquare's proton-proton and ICRU elastic scattering, inelastic events with
  secondary protons, deuterons and alphas (a per-thread stack of 24, transported before the next primary; a full
  stack is counted), recoils deposited locally, mixtures by component. The secondaries' emission angles are
  sampled as the CPU path samples them with `engines/mcsquare-build`'s patch 0005 (upstream issue #42's fix, ADR
  0024); the original read past its angle table, which no GPU can reproduce. (Until ADR 0024 the CPU path had the
  fix only with `MCSQUARE_FIX42=1`; the tables below were measured that way, with the same physics.)
- Influence matrices (`0008`, beamlet mode, what radiarch's optimizer reads): spots are simulated in groups that fit
  a dose-memory budget (`MCSQUARE_GPU_DOSE_BYTES`, default 4 GB), each spot of a group with its own dose grid on the
  device; MCsquare's sampler gives each spot its `Num_Primaries` from the single-spot plan, in parallel over spots.
  `PostProcess_Scoring`'s scaling, the threshold and the compaction run on the device; the host writes the blocks of
  MCsquare's sparse format straight into the merged `Outputs/Sparse_Dose` files (no per-spot temporary files), which
  radiarch's reader (`read_sparse_beamlets`) reads unchanged. Dose-to-water post-processing or segmentation fall back
  to post-processing on the host.
- Robustness scenarios (MCsquare's own mode, which radiarch's robust planning uses): MCsquare applies each
  scenario's setup errors while sampling and its range error to the densities, then calls the two functions above,
  so the GPU runs every scenario (one CUDA start-up per scenario).
- **Not supported** (the run stops with a message): 4D, LET, prompt gammas, energy scoring, an independent scoring
  grid — none of which radiarch asks for. Runs are not bitwise reproducible (the threads append their primaries in
  the order they finish; float atomics).

## Results (cci-aries: AMD EPYC 7413, 48 cores; one NVIDIA A100-PCIE-40GB)

Nuclear interactions off on both paths; the CPU path on 48 threads. Dose differences are over the voxels above 10 %
of the maximum, in % of the maximum; "CPU vs CPU" is a second CPU run with another seed (the noise).

| Case | Primaries | CPU run | GPU run (transport) | GPU − CPU: rms / mean | CPU − CPU: rms / mean |
|---|---|---|---|---|---|
| 150 MeV spot, water, 2 mm | 10⁶ | 1.1 s | 1.0 s (0.08 s) | 0.32 % / −0.008 % | 0.33 % / −0.001 % |
| 100 MeV spot, water | 10⁷ | 5.1 s | 1.6 s (0.32 s) | 0.11 % / +0.001 % | 0.11 % / −0.003 % |
| 200 MeV spot, water | 10⁷ | 14.1 s | 2.0 s (0.75 s) | 0.14 % / +0.001 % | 0.13 % / −0.001 % |
| 13 × 13 spots × 5 layers (110–150 MeV) through bone and lung, 20 × 25 × 20 cm | 10⁷ | 8.1 s | 1.4–1.7 s (0.43–0.53 s) | 1.01 % / −0.015 % | 1.01 % / −0.007 % |
| the same, kernel built with `--use_fast_math` | 10⁷ | | 1.3 s (0.22–0.30 s) | 1.01 % / −0.013 % | |

With nuclear interactions on both paths (CPU with `MCSQUARE_FIX42=1`):

| Case | Primaries | CPU run | GPU run (transport) | GPU − CPU: rms / mean | CPU − CPU: rms / mean | secondaries, lost, clamped |
|---|---|---|---|---|---|---|
| the field through bone and lung | 10⁷ | 8.4 s | 2.0 s (0.84 s) | 1.11 % / −0.023 % | 1.10 % / −0.018 % | 4.3 M, 0, 0 |
| 200 MeV spot, water | 10⁷ | 13.9 s | 2.3 s (1.19 s) | 0.16 % / −0.015 % | 0.16 % / −0.006 % | 7.7 M, 0, 0 |

Influence matrices, nuclear interactions on (CPU with `MCSQUARE_FIX42=1`), the bone/lung field's 845 spots ×
10⁴ protons, 2 mm grid of 1.25 M voxels, radiarch's threshold:

| | CPU run (48 threads) | GPU run | spot integrals: mean / sd of the difference | summed dose: rms / mean | entries |
|---|---|---|---|---|---|
| GPU − CPU | 10.2 s | 2.2 s (transport 0.63 s, compaction and transfer 0.25 s, sampling 0.17 s, writing 0.20 s) | +0.013 % / 0.279 % | 1.165 % / +0.007 % | 26.35 M |
| CPU − CPU (noise) | | | −0.007 % / 0.276 % | 1.162 % / −0.005 % | 26.43 M |

Copying the dense grids back instead of compacting on the device took 2.8 s of GPU time (4 GB per group).

Whole-run wall times against the stock binary OpenTPS ships (`MCsquare_linux`, Intel-compiled, upstream unchanged)
and radiarch's CPU build (ADR 0023), nuclear interactions on, the same seed; median of 3 runs (single thread: 1 run).
aries has 48 cores, 96 hardware threads. In parentheses: speed-up over the stock binary on one thread.

| | stock, 1 thread | stock, 8 | stock, 48 | stock, 96 | radiarch, 1 | radiarch, 8 | radiarch, 48 | radiarch, 96 | GPU (one A100) |
|---|---|---|---|---|---|---|---|---|---|
| bone/lung field, full dose, 10⁷ protons | 251 s (1×) | 33.5 s (7.5×) | 7.1 s (35×) | 5.8 s (43×) | 324 s (0.77×) | 42.6 s (5.9×) | 8.0 s (32×) | 6.9 s (36×) | 1.63 s (154×) |
| the same field's influence matrix, 845 spots × 10⁴ | 217 s (1×) | 31.2 s (6.9×) | 10.2 s (21×) | 9.0 s (24×) | 276 s (0.79×) | 40.1 s (5.4×) | 10.1 s (22×) | 10.5 s (21×) | 1.98 s (109×) |

The GPU's runs use 48 CPU threads for MCsquare's own sampling; their transport took 0.79 s and 0.57 s of the totals.

- **Agreement:** the GPU's dose differs from the CPU's as much as two CPU runs with different seeds do, in water and
  through bone and lung. Fast math changes nothing visible at this statistics; it needs a check at higher
  statistics before it becomes a default.
- **Speed:** transport alone is 13 to 31 million protons a second on one A100 (19–23 M in the heterogeneous field,
  33–45 M with fast math), and takes 1/16 to 1/19 of the 48-core CPU run's whole time (about 1/30 with fast math). A whole run is 3 to 7
  times faster: about 0.5 s goes to CUDA's start-up, 0.2 s to sampling on the CPU, the rest to MCsquare's own input
  and output — fixed costs that a long-running worker, sampling overlapped with transport, and larger runs shrink.
- For scale: FRED quotes about 10–14 M primaries/s on one GPU in water *with* nuclear interactions; this prototype
  has none, which FRED's paper and the profile of MCsquare's CPU path suggest cost tens of percent.

## Status and what is left

1. ~~Nuclear interactions~~ — done (`0007`); nuclear physics costs 40–60 % of the transport rate (8–12 M
   protons/s). Issue #42's fix is in the production CPU build too (ADR 0024).
2. ~~Influence matrices~~ — done (`0008`), dense grids per spot group with compaction on the device (simpler than a
   hash table, and fast on these grids; a patient grid of 50 M voxels fits about 20 spots per group in 4 GB, where a
   hash table would scale better). 4.6 times the 48-core CPU run's speed on the field above.
3. ~~Robustness scenarios and a radiarch setting~~ — done (ADR 0024): `mcsquare_device`, the image's build stage,
   the proton validation cases on the GPU.
4. Open: deterministic runs (ordered primaries, deterministic scoring), one CUDA start-up per worker instead of per
   run, multi-GPU by spot ranges, a high-statistics check of `--use_fast_math` before it becomes a default, LET.

## Build and run

    engines/mcsquare-gpu/build-in-docker.sh           # -> engines/mcsquare/MCsquare_gpu (not committed), as the image
    engines/mcsquare-gpu/build.sh                     # the same with the host's CUDA (glibc of the host)
    python engines/mcsquare-gpu/bench/prepare_inputs.py INPUTS    # in radiarch's environment
    BIN=... INPUTS=... RUNS=... MATERIALS=engines/mcsquare/Materials engines/mcsquare-gpu/bench/run_case.sh hetero gpu g1 10000000 11
    python engines/mcsquare-gpu/bench/compare.py RUNS/hetero-c1 RUNS/hetero-g1 RUNS/hetero-c2

`build-in-docker.sh` needs docker only (ubuntu:22.04 with CUDA 12.6's compiler from NVIDIA's apt repository,
`install-cuda.sh`); `build.sh` needs CUDA (nvcc), plus everything `engines/mcsquare-build/build.sh` needs. The code is
built for compute capability 8.0 (SASS) with PTX that newer GPUs compile on first use; the binary links the CUDA
runtime statically and needs the NVIDIA driver (R525 or newer) at run time.
