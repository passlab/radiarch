# Rerun of the R8 record's pencil-beam and VMAT cases, 2026-11-12: the leaf ends' tail, and no edge blur

**What changed.** From commit `0228ec6` on (`pb` 1.2.0, `LEAF_MODEL_VERSION` 4), two findings of the rerun of
2026-11-06 are fixed together (`docs/reports/mlc-leaf-model.md`, "The rounded ends' tail and the pencil beam's edge"):
- A rounded leaf end passes half the leaf gap as a tail beyond its tip, falling off over a few millimetres
  (`LeafModel.leaf_tip_tail_mm`; the synthetic machines take 2.3 mm). Before, each tip moved back by half the gap.
- The pencil beam no longer blurs a field's edge (`penumbra_fwhm_mm` 4.0 → 0.0). The Monte Carlo's source is a point,
  and the fit to it wants no blur. A real machine's commissioning would set its own.
- The lung's lateral kernel scaling exponent is refitted: 0.9 → 0.925.
- `pb_vs_mc` plans each reference field as the Monte Carlo collimates it, and scores the pencil beam on the
  references' own voxels, which sit half a voxel to the side of the harness's phantoms.

Every pencil-beam dose changes, and every dose made through apertures. The pencil-beam cases and the three VMAT cases
are rerun. Their numbers in the record's documents, in `../2026-11-06-mc-leaf-model-727654c/` and in
`../2026-11-10-arc-pairs-toward-jaw-f3a83c7/` are superseded by these runs.

**These runs.** Nine runs, one case per process, from a clean checkout of commit `0228ec6` on the 96-core server, in
the radiarch image built from `48c0cc4` with the checkout mounted over its code: `pb_vs_mc`
(`20261112-133523-0228ec6`), `pb_vs_ccc` (`20261112-132750`), `photon_pdd_10x10_pb` (`20261112-132735`),
`photon_profile_10x10_pb` (`20261112-132636`), `photon_output_vs_field_pb` (`20261112-132643`), `dij_consistency`
(`20261112-133125`), `lung_sbrt_vmat` (`20261112-135033`), `lung_vmat_lctsc` (`20261112-152611`) and `hn_sib_vmat`
(`20261112-143759`). `run-summary.md` lists every check, and `results.json` holds the full numbers.

## The two findings are fixed; one check against CCC now fails

- `pb_vs_mc`: all 35 graded checks pass, none fail. The leaf model fitted to the Agility's references: transmission
  0.198 %, leaf gap 0.96 mm, tip tail 2.32 mm.
- `pb_vs_ccc`: one graded check fails, a recorded finding about CCC (below).
- The other graded checks pass: the three VMAT cases (32, 10 and 12), `dij_consistency` (9), the depth dose and the
  profile.

| Check | 2026-11-06 (`727654c`) | `0228ec6` | Monte Carlo | Tolerance |
|---|---|---|---|---|
| 1 × 1 over 10 × 10, dose at 10 cm | 0.719 (fails) | 0.765 | 0.764 | 5 % |
| 1 × 1, width at half maximum at 10 cm (mm) | 11.37 | 11.77 | 11.52 | 1 mm |
| 2 × 2, width at half maximum (mm) | 22.16 | 22.72 | 22.41 | 1 mm |
| 10 × 10, gamma 3 %/3 mm | 99.71 % | 99.29 % | | ≥ 95 % |
| Irregular field, 10 mm gap (% of open) | 80.06 | 80.60 | 81.17 | 3 points |
| Irregular field, 5 mm gap (% of open) | 53.26 (fails) | 50.87 | 50.06 | 3 points |

Informative: touching closed pairs leak 5.99 % of the open dose within 10 mm of their tips' line, against the Monte
Carlo's 5.90 % (6.36 before).

**`pb_vs_ccc`, 10 mm beamlets: a finding about CCC.** The two engines' gamma 3 %/3 mm on the 10 × 10 cm field in
water is 94.55 %, against at least 95 % (95.63 % before). Most failing points are in the field deeper than 9 cm, where
CCC's shipped scatter cut-off loses dose (R7; this record's question 3). The sharper pencil-beam edge adds the rest,
and at that edge the pencil beam follows the Monte Carlo (`pb_vs_mc`'s gamma 99.29 %). It is recorded in
`src/radiarch/validation/known_findings.yaml`; no tolerance changed. With 5 mm beamlets (informative) it is 97.63 %.

**The engine's own checks.** The depth dose and the output factors do not move (PDD10 67.45 → 67.46 %). The 10 × 10 cm
profile's penumbra (80–20 %, informative) narrows from 5.93 to 4.31 mm without the blur, against a typical measured
7.0 ± 3.0 mm: the synthetic machine has no source size. `dij_consistency`'s proton rows move by Monte Carlo noise
(MCsquare is unchanged); its photon rows stay within their tolerances.

## What the VMAT cases do

Every graded check passes, as before. The pencil beam's sharper edge and the leaf ends' tail change each arc's dose,
and the optimizer finds different plans.
- **Lung SBRT (`lung_sbrt_vmat`).** The first patient's heart maximum falls from 16.40 to 11.57 Gy. Its D2cm (the
  maximum 2 cm from the PTV, in % of the prescription) rises from 54.31 to 57.37: RTOG 0915's minor deviation, as
  before (at most 59.58). The second patient's D2cm falls from 51.65 to 50.05, now within the protocol's limit
  (51.39).
- **Lung, 60 Gy in 30 (`lung_vmat_lctsc`).** The spinal cord maximum rises by 2.7 and 2.5 Gy, to 17.59 and 18.85 Gy,
  far below its limit of 50.5. The coverage stays above 95 %.
- **Head and neck, 70/56 Gy (`hn_sib_vmat`).** The first patient's brainstem maximum rises from 44.33 to 48.46 Gy (limit
  54) and its parotid mean falls from 32.04 to 29.19 Gy (informative; neither run meets 26 Gy). The second patient's
  brainstem maximum falls from 43.30 to 38.57 Gy.
- **The second engine.** CCC's gamma against `pb` on the two lung cases falls by 2.6 to 6.1 points (informative), as on
  the open field: `pb`'s edge is sharper than CCC's.

Every check that moved by 0.3 or more:

Before: the rerun of 2026-11-06 (`727654c`) for `pb_vs_mc`, the rerun of 2026-11-10 (`f3a83c7`) for the three VMAT
cases, and the record's run of 2026-10-23 (`52ed834`) for `pb_vs_ccc` and the profile.

| Case | Check | Before | 0228ec6 | Target | Result |
|---|---|---|---|---|---|
| pb_vs_mc | water_10x10: gamma 3 %/3 mm pass rate (%) | 99.71 | 99.29 | ≥ 95.0 | pass → pass |
| pb_vs_mc | 1x1 over 10x10, dose at 10 cm, pb vs MC | 0.719 | 0.765 | 0.764 ± 0.038 (MC) | fail → pass |
| pb_vs_mc | 1x1: width at half maximum at 10 cm, pb vs MC (mm) | 11.37 | 11.77 | 11.52 ± 1 (MC) | pass → pass |
| pb_vs_mc | 2x2: width at half maximum at 10 cm, pb vs MC (mm) | 22.16 | 22.72 | 22.41 ± 1 (MC) | pass → pass |
| pb_vs_mc | Agility MLC (Monte Carlo): tip tail fitted at 10 cm (mm) | (new check) | 2.32 | informative | — → informative |
| pb_vs_mc | closed pairs touching on the axis: excess dose within 10 mm of the tips' line, pb vs MC (% of open) | 6.36 | 5.99 | 5.90 (MC) | informative → informative |
| pb_vs_mc | irregular MLC field, leaf model: dose 10 mm gap at 20 mm at 10 cm, pb vs MC (% of open) | 80.06 | 80.6 | 81.17 ± 3 (MC) | pass → pass |
| pb_vs_mc | irregular MLC field, leaf model: dose 5 mm gap at -30 mm at 10 cm, pb vs MC (% of open) | 53.26 | 50.87 | 50.06 ± 3 (MC) | fail → pass |
| pb_vs_mc | irregular MLC field, ideal leaves: gamma 3 %/2 mm pass rate, depth 20-200 mm (%) | 99.1 | 99.9 | informative | informative → informative |
| pb_vs_mc | irregular MLC field, ideal leaves: dose 10 mm gap at 20 mm at 10 cm, pb vs MC (% of open) | 77.69 | 79.97 | 81.17 (MC) | informative → informative |
| pb_vs_ccc | water 10 x 10, 5 mm beamlets: gamma 3 %/3 mm pb vs CCC, absolute (%) | 98.99 | 97.63 | ≥ 95.0 | informative → informative |
| pb_vs_ccc | water 10 x 10, 10 mm beamlets: gamma 3 %/3 mm pb vs CCC, absolute (%) | 95.63 | 94.55 | ≥ 95.0 | pass → fail (recorded finding) |
| photon_profile_10x10_pb | penumbra 80–20 % (mm) | 5.93 | 4.31 | 7.0 ± 3.0 | informative → informative |
| lung_sbrt_vmat | LCTSC-Test-S1-101: PTV V100%[%] >= 95.0 | 95.78 | 96.11 | >= 95.0 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S1-101: PTV D0.03cc[%] <= 140.0 | 115.02 | 115.55 | <= 140.0 | informative → informative |
| lung_sbrt_vmat | LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 21.9 | 10.34 | 9.5 | <= 21.9 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S1-101: SpinalCord D0.35cc[Gy] <= 18.0 | 9.24 | 8.84 | <= 18.0 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S1-101: Heart D0.03cc[Gy] <= 30.0 | 16.4 | 11.57 | <= 30.0 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S1-101: Heart D15cc[Gy] <= 24.0 | 10.56 | 8.48 | <= 24.0 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S1-101: Lungs V12.5Gy[cc] <= 1000.0 | 228.18 | 244.32 | <= 1000.0 | informative → informative |
| lung_sbrt_vmat | LCTSC-Test-S1-101: D2cm (PTV 16.0 cc) | 54.31 | 57.37 | < 51.27 (minor ≤ 59.58) | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S1-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 87.8 | 83.7 | informative | informative → informative |
| lung_sbrt_vmat | LCTSC-Test-S2-101: PTV D0.03cc[%] <= 140.0 | 113.76 | 112.53 | <= 140.0 | informative → informative |
| lung_sbrt_vmat | LCTSC-Test-S2-101: SpinalCord D0.35cc[Gy] <= 18.0 | 7.94 | 7.57 | <= 18.0 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S2-101: SpinalCord D1.2cc[Gy] <= 12.3 | 6.92 | 6.21 | <= 12.3 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S2-101: Esophagus D5cc[Gy] <= 17.7 | 3.39 | 2.22 | <= 17.7 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S2-101: Heart D0.03cc[Gy] <= 30.0 | 18.03 | 17.6 | <= 30.0 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S2-101: Lungs V12.5Gy[cc] <= 1000.0 | 217.75 | 213.22 | <= 1000.0 | informative → informative |
| lung_sbrt_vmat | LCTSC-Test-S2-101: D2cm (PTV 16.3 cc) | 51.65 | 50.05 | < 51.39 (minor ≤ 59.74) | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S2-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 92.5 | 89.9 | informative | informative → informative |
| lung_vmat_lctsc | LCTSC-Test-S1-101: PTV D0.03cc[Gy] <= 72.0 | 64.8 | 66.16 | <= 72.0 | informative → informative |
| lung_vmat_lctsc | LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 37.0 | 14.4 | 14.96 | <= 37.0 | pass → pass |
| lung_vmat_lctsc | LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 50.5 | 14.85 | 17.59 | <= 50.5 | pass → pass |
| lung_vmat_lctsc | LCTSC-Test-S1-101: Esophagus Dmean[Gy] <= 34.0 | 3.21 | 2.48 | <= 34.0 | informative → informative |
| lung_vmat_lctsc | LCTSC-Test-S1-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 82.3 | 77.6 | informative | informative → informative |
| lung_vmat_lctsc | LCTSC-Test-S2-101: PTV V60Gy[%] >= 95.0 | 95.96 | 95.58 | >= 95.0 | pass → pass |
| lung_vmat_lctsc | LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5 | 16.4 | 18.85 | <= 50.5 | pass → pass |
| lung_vmat_lctsc | LCTSC-Test-S2-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 85.7 | 79.6 | informative | informative → informative |
| hn_sib_vmat | 0522c0001: PTV_High D0.03cc[%] <= 110.0 | 112.46 | 114.91 | <= 110.0 | informative → informative |
| hn_sib_vmat | 0522c0001: Brainstem D0.03cc[Gy] <= 54.0 | 44.33 | 48.46 | <= 54.0 | pass → pass |
| hn_sib_vmat | 0522c0001: Brainstem_PRV D0.03cc[Gy] <= 60.0 | 52.16 | 53.26 | <= 60.0 | informative → informative |
| hn_sib_vmat | 0522c0001: Parotid Dmean[Gy] <= 26.0 | 32.04 | 29.19 | <= 26.0 | informative → informative |
| hn_sib_vmat | 0522c0001: Glnd_Submand Dmean[Gy] <= 39.0 | 62.2 | 64.02 | <= 39.0 | informative → informative |
| hn_sib_vmat | 0522c0001: Mandible D0.03cc[Gy] <= 70.0 | 62.29 | 65.18 | <= 70.0 | informative → informative |
| hn_sib_vmat | 0522c0001: PTV56 D95%[Gy] >= 56.0 | 59.24 | 59.75 | >= 56.0 | pass → pass |
| hn_sib_vmat | 0522c0001: hottest point outside the elective volume (% of 70 Gy) | 98.2 | 101.5 | informative | informative → informative |
| hn_sib_vmat | 0522c0002: PTV_High D0.03cc[%] <= 110.0 | 112.41 | 109.68 | <= 110.0 | informative → informative |
| hn_sib_vmat | 0522c0002: Brainstem D0.03cc[Gy] <= 54.0 | 43.3 | 38.57 | <= 54.0 | pass → pass |
| hn_sib_vmat | 0522c0002: Brainstem_PRV D0.03cc[Gy] <= 60.0 | 51.65 | 48.58 | <= 60.0 | informative → informative |
| hn_sib_vmat | 0522c0002: Parotid Dmean[Gy] <= 26.0 | 23.4 | 22.34 | <= 26.0 | informative → informative |
| hn_sib_vmat | 0522c0002: Glnd_Submand Dmean[Gy] <= 39.0 | 54.01 | 54.65 | <= 39.0 | informative → informative |
| hn_sib_vmat | 0522c0002: Mandible D0.03cc[Gy] <= 70.0 | 57.08 | 61.66 | <= 70.0 | informative → informative |
| hn_sib_vmat | 0522c0002: hottest point outside the elective volume (% of 70 Gy) | 96.1 | 98.4 | informative | informative → informative |

The engines' Monte Carlo comparisons on jaw-defined fields with CCC, and the fluence-level plans, have no pencil-beam
dose and no apertures, and stand as recorded.

## How to reproduce (optional)

```bash
git clone https://github.com/passlab/radiarch && cd radiarch && git checkout 0228ec6
python3 -m venv .venv && .venv/bin/pip install -e "./src[dev,validation]"     # Python 3.12 or later
.venv/bin/python -m radiarch.validation.run --cases pb_vs_mc
.venv/bin/python -m radiarch.validation.run --cases lung_vmat_lctsc
```

and likewise for the other seven cases, one per process. The cases read their CT, structures and Monte Carlo
references from `RADIARCH_VALIDATION_DATA`, outside the repository.
