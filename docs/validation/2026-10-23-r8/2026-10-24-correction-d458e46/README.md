# Correction to the R8 record, 2026-10-24: four planning cases on corrected anatomy

**What was wrong.** From R4 until commit `d458e46`, every geometry *derived* from another
(a PTV or CTV expansion, rings, unions, density overrides) was stored with its x and z axes
swapped against its parent. Planning and evaluation read the same swapped arrays, so each plan
was self-consistent and its checks ran, but the anatomy was mirrored against the beams and the
CT: targets and organs sat in the wrong places relative to the fields. The four cases below
derive their PTVs and rings this way. Their R8 numbers (in the documents of this folder's
parent, run `20261023-192600-52ed834`) are superseded by this run; nothing else in the R8
record derives a geometry, and the engine, Monte Carlo, phantom, TG-119 and cross-check results
stand as recorded. ADR 0015 (Findings) and `docs/impl-log.md` describe the fault and its fix.

**This run.** `20261024-152201-d458e46`: the four cases from a clean checkout of commit
`d458e46`, the fix (`run-summary.md` lists every check, `results.json` holds the full
numbers). A first rerun of uncommitted code gave identical values.

**What changes for review.**

- Every graded check that passed in R8 still passes; none changes status.
- Organ doses change most. With the swapped anatomy, the lung cases' spinal cord,
  oesophagus and heart were largely outside the fields (cord D0.03cc 0 to 0.7 Gy); on the correct
  anatomy the cord receives 10 to 20 Gy and, in the SBRT case, the heart D0.03cc 17 Gy, all
  within their limits. In the head-and-neck case the optic structures fall from 16 to 23 Gy to under
  1 Gy, and the parotid mean rises from 2 to 11 Gy to 22 to 30 Gy (informative; above the 26 Gy
  goal for one patient).
- Statements in the R8 guide about these four cases' organ doses should be read with the
  numbers below.

## Checks whose value changed by 1 or more (Gy, %, or index points)

| Case | Check | R8 (52ed834) | Corrected (d458e46) | Target | Result |
|---|---|---|---|---|---|
| lung_e2e_lctsc | LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 37.0 Gy | 24.41 | 21.35 | <= 37.0 | pass → pass |
| lung_e2e_lctsc | LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 50.5 Gy | 0.0 | 12.96 | <= 50.5 | pass → pass |
| lung_e2e_lctsc | LCTSC-Test-S1-101: Esophagus Dmean[Gy] <= 34.0 Gy | 0.0 | 3.9 | <= 34.0 | informative → informative |
| lung_e2e_lctsc | LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 37.0 Gy | 22.36 | 19.64 | <= 37.0 | pass → pass |
| lung_e2e_lctsc | LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5 Gy | 0.0 | 13.5 | <= 50.5 | pass → pass |
| lung_e2e_lctsc | LCTSC-Test-S2-101: Esophagus Dmean[Gy] <= 34.0 Gy | 0.0 | 3.21 | <= 34.0 | informative → informative |
| lung_sbrt_vmat | LCTSC-Test-S1-101: PTV D0.03cc[%] <= 140.0 | 121.69 | 117.95 | <= 140.0 | informative → informative |
| lung_sbrt_vmat | LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 21.9 | 0.08 | 11.16 | <= 21.9 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S1-101: SpinalCord D0.35cc[Gy] <= 18.0 | 0.08 | 9.25 | <= 18.0 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S1-101: SpinalCord D1.2cc[Gy] <= 12.3 | 0.08 | 8.23 | <= 12.3 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S1-101: Esophagus D0.03cc[Gy] <= 25.2 | 0.08 | 2.57 | <= 25.2 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S1-101: Heart D0.03cc[Gy] <= 30.0 | 0.27 | 16.99 | <= 30.0 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S1-101: Heart D15cc[Gy] <= 24.0 | 0.22 | 10.68 | <= 24.0 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S1-101: Lungs V12.5Gy[cc] <= 1000.0 | 260.44 | 229.85 | <= 1000.0 | informative → informative |
| lung_sbrt_vmat | LCTSC-Test-S1-101: D2cm (PTV 16.0 cc) | 53.866 | 55.899 | < 51.2655 (minor ≤ 59.5818) | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S1-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 90.9 | 89.1 | informative | informative → informative |
| lung_sbrt_vmat | LCTSC-Test-S2-101: PTV V100%[%] >= 95.0 | 95.18 | 96.18 | >= 95.0 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 21.9 | 0.12 | 9.99 | <= 21.9 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S2-101: SpinalCord D0.35cc[Gy] <= 18.0 | 0.12 | 8.86 | <= 18.0 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S2-101: SpinalCord D1.2cc[Gy] <= 12.3 | 0.12 | 7.35 | <= 12.3 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S2-101: Esophagus D0.03cc[Gy] <= 25.2 | 0.17 | 6.22 | <= 25.2 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S2-101: Esophagus D5cc[Gy] <= 17.7 | 0.12 | 1.77 | <= 17.7 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S2-101: Heart D0.03cc[Gy] <= 30.0 | 0.64 | 17.5 | <= 30.0 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S2-101: Heart D15cc[Gy] <= 24.0 | 0.4 | 10.47 | <= 24.0 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S2-101: Lungs V12.5Gy[cc] <= 1000.0 | 207.33 | 211.98 | <= 1000.0 | informative → informative |
| lung_sbrt_vmat | LCTSC-Test-S2-101: D2cm (PTV 16.3 cc) | 50.973 | 49.277 | < 51.3882 (minor ≤ 59.7352) | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S2-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 89.8 | 93.0 | informative | informative → informative |
| lung_vmat_lctsc | LCTSC-Test-S1-101: PTV D0.03cc[Gy] <= 72.0 | 64.76 | 65.9 | <= 72.0 | informative → informative |
| lung_vmat_lctsc | LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 37.0 | 16.04 | 13.72 | <= 37.0 | pass → pass |
| lung_vmat_lctsc | LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 50.5 | 0.61 | 17.89 | <= 50.5 | pass → pass |
| lung_vmat_lctsc | LCTSC-Test-S1-101: Esophagus Dmean[Gy] <= 34.0 | 0.39 | 2.72 | <= 34.0 | informative → informative |
| lung_vmat_lctsc | LCTSC-Test-S1-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 79.5 | 83.3 | informative | informative → informative |
| lung_vmat_lctsc | LCTSC-Test-S2-101: PTV D0.03cc[Gy] <= 72.0 | 65.24 | 66.87 | <= 72.0 | informative → informative |
| lung_vmat_lctsc | LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 37.0 | 15.49 | 13.18 | <= 37.0 | pass → pass |
| lung_vmat_lctsc | LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5 | 0.74 | 20.19 | <= 50.5 | pass → pass |
| lung_vmat_lctsc | LCTSC-Test-S2-101: Esophagus Dmean[Gy] <= 34.0 | 0.52 | 3.24 | <= 34.0 | informative → informative |
| lung_vmat_lctsc | LCTSC-Test-S2-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 84.1 | 86.4 | informative | informative → informative |
| hn_sib_vmat | 0522c0001: PTV_High D0.03cc[%] <= 110.0 | 113.65 | 112.5 | <= 110.0 | informative → informative |
| hn_sib_vmat | 0522c0001: Brainstem D0.03cc[Gy] <= 54.0 | 43.85 | 41.55 | <= 54.0 | pass → pass |
| hn_sib_vmat | 0522c0001: Brainstem_PRV D0.03cc[Gy] <= 60.0 | 52.09 | 48.64 | <= 60.0 | informative → informative |
| hn_sib_vmat | 0522c0001: OpticChiasm D0.03cc[Gy] <= 54.0 | 21.28 | 0.91 | <= 54.0 | pass → pass |
| hn_sib_vmat | 0522c0001: OpticNrv D0.03cc[Gy] <= 54.0 | 23.28 | 0.85 | <= 54.0 | pass → pass |
| hn_sib_vmat | 0522c0001: Parotid Dmean[Gy] <= 26.0 | 11.25 | 29.81 | <= 26.0 | informative → informative |
| hn_sib_vmat | 0522c0001: Glnd_Submand Dmean[Gy] <= 39.0 | 61.1 | 62.3 | <= 39.0 | informative → informative |
| hn_sib_vmat | 0522c0001: hottest point outside the elective volume (% of 70 Gy) | 97.4 | 98.7 | informative | informative → informative |
| hn_sib_vmat | 0522c0002: Brainstem D0.03cc[Gy] <= 54.0 | 43.18 | 41.05 | <= 54.0 | pass → pass |
| hn_sib_vmat | 0522c0002: Brainstem_PRV D0.03cc[Gy] <= 60.0 | 53.41 | 50.97 | <= 60.0 | informative → informative |
| hn_sib_vmat | 0522c0002: OpticChiasm D0.03cc[Gy] <= 54.0 | 15.86 | 0.8 | <= 54.0 | pass → pass |
| hn_sib_vmat | 0522c0002: OpticNrv D0.03cc[Gy] <= 54.0 | 16.09 | 0.77 | <= 54.0 | pass → pass |
| hn_sib_vmat | 0522c0002: Parotid Dmean[Gy] <= 26.0 | 2.47 | 22.35 | <= 26.0 | informative → informative |
| hn_sib_vmat | 0522c0002: Glnd_Submand Dmean[Gy] <= 39.0 | 47.75 | 53.72 | <= 39.0 | informative → informative |
| hn_sib_vmat | 0522c0002: Mandible D0.03cc[Gy] <= 70.0 | 61.74 | 56.92 | <= 70.0 | informative → informative |
| hn_sib_vmat | 0522c0002: hottest point outside the elective volume (% of 70 Gy) | 95.8 | 97.7 | informative | informative → informative |
