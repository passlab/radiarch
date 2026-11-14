# ADR 0022 — The optimizer on a GPU, behind a setting

Date: 2026-11-13. Status: decided by the project lead and built, 2026-11-13. Follows the investigation in
`docs/reports/engine-performance.md`.

## Context

The optimizer spends its time in two places, both on one CPU thread: the products with the influence matrix
(`Dij @ w` for the dose, `Dij.T @ g` for the gradient; SciPy's sparse products are single-threaded) and the objective
terms, evaluated over the full dose grid. They are 77 to 93 % of the multi-criteria cases' time and about 20 % of the
protocol cases'. On an A100 the products on one of the lung protocol's matrices take 1.8 ms against 281 ms; the
pencil beam already runs on a GPU through CuPy (ADR 0015, decision 6). The project lead decided that every GPU path
stays behind a setting and that the CPU path stays the default.

## Decision

1. **A setting.** `optimizer_device` (`RADIARCH_OPTIMIZER_DEVICE`): `cpu` (the default), `gpu` (an error when CuPy or
   a CUDA device is missing) or `auto` (the GPU when it works). `services/array_backend.py` holds the device, the
   helpers and the device's influence matrices.
2. **What moves.** On the GPU each scenario's influence matrix and its transpose are kept on the device in float64
   CSR; the structures' masks and the dose live there too, and the objective terms and hard-constraint terms are
   evaluated there. SciPy's L-BFGS-B stays on the host and exchanges only the weights and their gradient with the
   device. This covers the fluence optimization (nominal and robust), its hard constraints, the nominal Pareto sets,
   their projection and the deliverable plan's projection; and, in a second stage the same day, the meterset solves
   (the arcs' intervals, an aperture plan's segments, with their hard constraints), the robust Pareto sets (their
   stacked doses on the navigation voxels) and second sets over a deliverable plan's metersets (R11.11). A problem's
   matrices are put on the device when a solve first needs them.
3. **Written once.** The objectives keep their NumPy code: CuPy arrays take NumPy's functions over through NumPy's
   dispatch protocols, and only the conversion on entry names the module. The hard-constraint terms keep their
   multipliers on the mask's device. On the CPU every operation is the one radiarch ran before.
4. **The dose in float64 on the GPU.** The CPU path's fluence optimization doses through the engines'
   `apply_influence`, in float32; the GPU path computes the dose in float64, as the Pareto sets' solves already did
   (R11.8). A GPU result therefore agrees with the CPU's to the solver's tolerance, not digit for digit.
5. **Cache keys by the setting.** A result made under `gpu` or `auto` is stored under a key of its own; under `cpu`
   the keys are unchanged, so every stored result keeps its key. The key follows the setting, not the hardware, so the
   API (which may have no GPU) and the worker compute the same key. A result made on the GPU says so in its notes
   ("solved on the GPU").
6. **A fallback.** When a problem's matrices and their transposes (about 24 bytes per non-zero) would take more than
   80 % of the GPU's free memory, the problem is solved on the CPU, with a warning.

## Evidence

`tests/test_optimizer_device.py`: the setting, the keys and the fallbacks everywhere; on a GPU, every objective and
hard-constraint term and both products against the CPU's to a relative 10⁻¹², and a run that reaches the CPU run's
cost to 10⁻⁴. The optimizer's other tests pass with the setting at `gpu` too, except two that assume host arrays and
CPU notes, now written for both.

Measured on an A100 (2026-11-13, from `cea180c` with this change):

| Case | CPU | GPU | The fluence solves |
|---|---|---|---|
| `protocol_lung_vmat` (`pb` on the GPU too) | 2072 s | 496 s | 4 of them: 117 to 124 s each on the CPU, 2 to 7 s on the GPU |
| `mco_front_tg119` (CCC) | 4510 s | 2278 s | the first set's 19: 1226 s on the CPU, 16 s on the GPU |

What remains is the meterset solves (the arcs' intervals, a deliverable plan's segments, a second set), still on the
CPU: about 200 s of the protocol case and 1360 s of TG-119. On the GPU every graded check of TG-119 passes, among them
the first set's deliverable core D5 (22.07 Gy; 22.45 on the CPU, a recorded finding); the first sets' error bounds lie
within 0.002 of the CPU record's (0.6457 against 0.6443 for TG-119, 0.5592 against 0.5604 for the lung protocol's 16
plans). The protocol case's 18 goal values pass; 4 of its 18 comparisons with the CPU-made record differ by more than
1 %.

The second stage (the meterset solves, robust Pareto sets and second sets): the whole test suite passes on the CPU
default (1238) and with the setting at `gpu` on an A100 (1266, the device tests included); on a GPU the meterset
solves reach the CPU's cost to 10⁻⁶, and the stacked operators, worst cases and scenario-wise sums agree with the
CPU's to 10⁻¹². Measured on an A100 with it:

| Case | CPU | GPU, first stage | GPU, both stages | What remains |
|---|---|---|---|---|
| `protocol_lung_vmat` (`pb` on the GPU too) | 2072 s | 496 s | 299 s | the pencil beam's influence matrices, about 220 s; the meterset solves take 1.6 to 4.9 s (81 to 83 s on the CPU) |
| `mco_front_tg119` (CCC) | 4510 s | 2278 s | 1004 s | the CCC engine on the CPU, about 840 s; every solve together 104 s |
| `mco_protocol_lung` (`pb` on the CPU) | 20001 s (the record's, 32 threads) | — | 2535 s | the arcs' doses by the pencil beam on the CPU, about 320 s, and building the problems |

TG-119 passes every graded check on the GPU: the first set's error bound 0.6427 (the record's 0.6443), the deliverable
plan's core D5 21.63 Gy (22.45 Gy in the record, a recorded finding there). The protocol case's goal values pass;
5 of its 18 comparisons with the CPU-made record differ by more than 1 %. The lung Pareto case passes every graded
check (37; the record's 38 included a best-of-set check of the arcs' second set, which has no converged plan here, 1
of 11 in the record); its first set's error bound is 0.5639 (0.5604), its second sets' 0.4501 and 0.9413 (0.3893 and
0.8545): they start from deliverable plans that differ a little, and converge poorly on either device. With the
optimizer on the GPU, the engines are what is left: the pencil beam's influence matrices and the collapsed cone.

## Consequences

- The validation records are made on the CPU; a deployment that sets `gpu` or `auto` makes plans that differ from
  them within the solver's tolerance.
- Still on the CPU: the engines (the pencil beam has its own setting), building each problem's matrices, and the small
  linear programs of the Pareto sets' sandwich and navigation.
- A GPU's memory bounds the problems it takes: about 14 scenarios of the lung protocol's matrix size fit in 40 GB.
