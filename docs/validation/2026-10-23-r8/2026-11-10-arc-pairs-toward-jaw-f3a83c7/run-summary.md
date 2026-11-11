# Radiarch validation run 20261110-190036-f3a83c7 + 20261110-203936-f3a83c7 + 20261110-194944-f3a83c7

RESEARCH USE ONLY. NOT FOR CLINICAL USE. Radiarch is a research treatment-planning system; its plans, doses and evaluations must not be used to treat patients.

The cases ran one per process from commit f3a83c7: `lung_sbrt_vmat` (20261110-190036), `lung_vmat_lctsc` (20261110-203936), `hn_sib_vmat` (20261110-194944).

| Case | Status | Time (s) | Checks |
|---|---|---|---|
| lung_sbrt_vmat | **pass** | 1287.7 | 32 pass, 0 fail, 12 informative |
| lung_vmat_lctsc | **pass** | 7227.5 | 10 pass, 0 fail, 20 informative |
| hn_sib_vmat | **pass** | 4235.3 | 12 pass, 0 fail, 14 informative |

## lung_sbrt_vmat — pass

- note: synthetic peripheral GTV in the right lung (radius 12 mm), PTV +5 mm, rings for the SBRT dose fall-off; FMO of the arcs' sector beams with the pb Dij, arcs by sweeping each sector's fluence, control-point doses recomputed and metersets re-optimized (R8); a research pipeline check, not a plan quality statement

| Check | Value | Target | Result |
|---|---|---|---|
| LCTSC-Test-S1-101: PTV V100%[%] >= 95.0 | 95.78 | >= 95.0 | pass |
| LCTSC-Test-S1-101: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S1-101: PTV D0.03cc[%] <= 140.0 | 115 | <= 140.0 | informative |
| LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 10.0 | 2.68 | <= 10.0 | informative |
| LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 21.9 | 10.34 | <= 21.9 | pass |
| LCTSC-Test-S1-101: SpinalCord D0.35cc[Gy] <= 18.0 | 9.24 | <= 18.0 | pass |
| LCTSC-Test-S1-101: SpinalCord D1.2cc[Gy] <= 12.3 | 8.04 | <= 12.3 | pass |
| LCTSC-Test-S1-101: Esophagus D0.03cc[Gy] <= 25.2 | 2.02 | <= 25.2 | pass |
| LCTSC-Test-S1-101: Esophagus D5cc[Gy] <= 17.7 | 0.66 | <= 17.7 | pass |
| LCTSC-Test-S1-101: Heart D0.03cc[Gy] <= 30.0 | 16.4 | <= 30.0 | pass |
| LCTSC-Test-S1-101: Heart D15cc[Gy] <= 24.0 | 10.56 | <= 24.0 | pass |
| LCTSC-Test-S1-101: Lungs D1500cc[Gy] <= 11.6 | 0.55 | <= 11.6 | pass |
| LCTSC-Test-S1-101: Lungs D1000cc[Gy] <= 12.4 | 1.18 | <= 12.4 | pass |
| LCTSC-Test-S1-101: Lungs V12.5Gy[cc] <= 1000.0 | 228.2 | <= 1000.0 | informative |
| LCTSC-Test-S1-101: R100 (PTV 16.0 cc) | 0.961 | < 1.2 (minor ≤ 1.5) | pass |
| LCTSC-Test-S1-101: R50 (PTV 16.0 cc) | 2.373 | < 4.63673 (minor ≤ 5.70509) | pass |
| LCTSC-Test-S1-101: D2cm (PTV 16.0 cc) | 54.31 | < 51.2655 (minor ≤ 59.5818) | pass |
| LCTSC-Test-S1-101: LungV20 (PTV 16.0 cc) | 2.681 | < 10 (minor ≤ 15) | pass |
| LCTSC-Test-S1-101: arcs deliverable at the machine's limits | True | True | pass |
| LCTSC-Test-S1-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 87.8 | informative | informative |
| LCTSC-Test-S1-101: second engine PTV D95, CCC / pb | 0.986 | informative | informative |
| LCTSC-Test-S1-101: second engine PTV D95, CCC / pb, body as water | 1.025 | informative | informative |
| LCTSC-Test-S2-101: PTV V100%[%] >= 95.0 | 95.35 | >= 95.0 | pass |
| LCTSC-Test-S2-101: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S2-101: PTV D0.03cc[%] <= 140.0 | 113.8 | <= 140.0 | informative |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 10.0 | 2.71 | <= 10.0 | informative |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 21.9 | 8.7 | <= 21.9 | pass |
| LCTSC-Test-S2-101: SpinalCord D0.35cc[Gy] <= 18.0 | 7.94 | <= 18.0 | pass |
| LCTSC-Test-S2-101: SpinalCord D1.2cc[Gy] <= 12.3 | 6.92 | <= 12.3 | pass |
| LCTSC-Test-S2-101: Esophagus D0.03cc[Gy] <= 25.2 | 5.46 | <= 25.2 | pass |
| LCTSC-Test-S2-101: Esophagus D5cc[Gy] <= 17.7 | 3.39 | <= 17.7 | pass |
| LCTSC-Test-S2-101: Heart D0.03cc[Gy] <= 30.0 | 18.03 | <= 30.0 | pass |
| LCTSC-Test-S2-101: Heart D15cc[Gy] <= 24.0 | 10.42 | <= 24.0 | pass |
| LCTSC-Test-S2-101: Lungs D1500cc[Gy] <= 11.6 | 0.68 | <= 11.6 | pass |
| LCTSC-Test-S2-101: Lungs D1000cc[Gy] <= 12.4 | 1.35 | <= 12.4 | pass |
| LCTSC-Test-S2-101: Lungs V12.5Gy[cc] <= 1000.0 | 217.8 | <= 1000.0 | informative |
| LCTSC-Test-S2-101: R100 (PTV 16.3 cc) | 0.962 | < 1.2 (minor ≤ 1.5) | pass |
| LCTSC-Test-S2-101: R50 (PTV 16.3 cc) | 2.473 | < 4.63059 (minor ≤ 5.69589) | pass |
| LCTSC-Test-S2-101: D2cm (PTV 16.3 cc) | 51.65 | < 51.3882 (minor ≤ 59.7352) | pass |
| LCTSC-Test-S2-101: LungV20 (PTV 16.3 cc) | 2.707 | < 10 (minor ≤ 15) | pass |
| LCTSC-Test-S2-101: arcs deliverable at the machine's limits | True | True | pass |
| LCTSC-Test-S2-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 92.5 | informative | informative |
| LCTSC-Test-S2-101: second engine PTV D95, CCC / pb | 0.975 | informative | informative |
| LCTSC-Test-S2-101: second engine PTV D95, CCC / pb, body as water | 1.053 | informative | informative |

## lung_vmat_lctsc — pass

- note: synthetic 2 cm GTV at the right lung's centroid, CTV +5 mm, PTV +5 mm (the R7 lung case), 60 Gy in 30 fractions; FMO of the arcs' sector beams with the pb Dij, arcs by sweeping each sector's fluence, control-point doses recomputed and metersets re-optimized (R8); a research pipeline check, not a plan quality statement

| Check | Value | Target | Result |
|---|---|---|---|
| LCTSC-Test-S1-101: PTV V60Gy[%] >= 95.0 | 95.94 | >= 95.0 | pass |
| LCTSC-Test-S1-101: PTV D0.03cc[Gy] <= 72.0 | 64.8 | <= 72.0 | informative |
| LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 37.0 | 14.4 | <= 37.0 | pass |
| LCTSC-Test-S1-101: Lungs-GTV Dmean[Gy] <= 20.0 | 8.2 | <= 20.0 | pass |
| LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 50.5 | 14.85 | <= 50.5 | pass |
| LCTSC-Test-S1-101: Esophagus Dmean[Gy] <= 34.0 | 3.21 | <= 34.0 | informative |
| LCTSC-Test-S1-101: Heart V60Gy[%] <= 33.0 | 0 | <= 33.0 | informative |
| LCTSC-Test-S1-101: Heart V45Gy[%] <= 66.0 | 0 | <= 66.0 | informative |
| LCTSC-Test-S1-101: Heart V40Gy[%] <= 100.0 | 0 | <= 100.0 | informative |
| LCTSC-Test-S1-101: PTV D5 / D95 (homogeneity) | 1.053 | ≤ 1.15 (informative) | informative |
| LCTSC-Test-S1-101: Paddick conformity index | 0.919 | informative | informative |
| LCTSC-Test-S1-101: arcs deliverable at the machine's limits | True | True | pass |
| LCTSC-Test-S1-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 82.3 | informative | informative |
| LCTSC-Test-S1-101: second engine PTV D95, CCC / pb | 0.878 | informative | informative |
| LCTSC-Test-S1-101: second engine PTV D95, CCC / pb, body as water | 1.041 | informative | informative |
| LCTSC-Test-S2-101: PTV V60Gy[%] >= 95.0 | 95.96 | >= 95.0 | pass |
| LCTSC-Test-S2-101: PTV D0.03cc[Gy] <= 72.0 | 65.39 | <= 72.0 | informative |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 37.0 | 13.88 | <= 37.0 | pass |
| LCTSC-Test-S2-101: Lungs-GTV Dmean[Gy] <= 20.0 | 8.54 | <= 20.0 | pass |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5 | 16.4 | <= 50.5 | pass |
| LCTSC-Test-S2-101: Esophagus Dmean[Gy] <= 34.0 | 3.14 | <= 34.0 | informative |
| LCTSC-Test-S2-101: Heart V60Gy[%] <= 33.0 | 0 | <= 33.0 | informative |
| LCTSC-Test-S2-101: Heart V45Gy[%] <= 66.0 | 0.15 | <= 66.0 | informative |
| LCTSC-Test-S2-101: Heart V40Gy[%] <= 100.0 | 0.38 | <= 100.0 | informative |
| LCTSC-Test-S2-101: PTV D5 / D95 (homogeneity) | 1.058 | ≤ 1.15 (informative) | informative |
| LCTSC-Test-S2-101: Paddick conformity index | 0.91 | informative | informative |
| LCTSC-Test-S2-101: arcs deliverable at the machine's limits | True | True | pass |
| LCTSC-Test-S2-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 85.7 | informative | informative |
| LCTSC-Test-S2-101: second engine PTV D95, CCC / pb | 0.929 | informative | informative |
| LCTSC-Test-S2-101: second engine PTV D95, CCC / pb, body as water | 1.051 | informative | informative |

## hn_sib_vmat — pass

- note: synthetic oropharynx-like GTV between the parotids, PTV70 +8 mm, PTV56 +25 mm outside PTV70 + 3 mm and the brainstem + 5 mm; two full arcs from the fluence of their sector beams (pb Dij), 70/56 Gy in 35 fractions; NCCN head-and-neck template; a research pipeline check, not a plan quality statement

| Check | Value | Target | Result |
|---|---|---|---|
| 0522c0001: PTV_High D95%[%] >= 95.0 | 100.2 | >= 95.0 | pass |
| 0522c0001: PTV_High D0.03cc[%] <= 110.0 | 112.5 | <= 110.0 | informative |
| 0522c0001: Brainstem D0.03cc[Gy] <= 54.0 | 44.33 | <= 54.0 | pass |
| 0522c0001: Brainstem_PRV D0.03cc[Gy] <= 60.0 | 52.16 | <= 60.0 | informative |
| 0522c0001: OpticChiasm D0.03cc[Gy] <= 54.0 | 0.95 | <= 54.0 | pass |
| 0522c0001: OpticNrv D0.03cc[Gy] <= 54.0 | 0.88 | <= 54.0 | pass |
| 0522c0001: Parotid Dmean[Gy] <= 26.0 | 32.04 | <= 26.0 | informative |
| 0522c0001: Glnd_Submand Dmean[Gy] <= 39.0 | 62.2 | <= 39.0 | informative |
| 0522c0001: Mandible D0.03cc[Gy] <= 70.0 | 62.29 | <= 70.0 | informative |
| 0522c0001: PTV56 D95%[Gy] >= 56.0 | 59.24 | >= 56.0 | pass |
| 0522c0001: PTV70 D5 / D95 (homogeneity) | 1.097 | ≤ 1.10 (informative) | informative |
| 0522c0001: hottest point outside the elective volume (% of 70 Gy) | 98.2 | informative | informative |
| 0522c0001: arcs deliverable at the machine's limits | True | True | pass |
| 0522c0002: PTV_High D95%[%] >= 95.0 | 100.2 | >= 95.0 | pass |
| 0522c0002: PTV_High D0.03cc[%] <= 110.0 | 112.4 | <= 110.0 | informative |
| 0522c0002: Brainstem D0.03cc[Gy] <= 54.0 | 43.3 | <= 54.0 | pass |
| 0522c0002: Brainstem_PRV D0.03cc[Gy] <= 60.0 | 51.65 | <= 60.0 | informative |
| 0522c0002: OpticChiasm D0.03cc[Gy] <= 54.0 | 0.83 | <= 54.0 | pass |
| 0522c0002: OpticNrv D0.03cc[Gy] <= 54.0 | 0.8 | <= 54.0 | pass |
| 0522c0002: Parotid Dmean[Gy] <= 26.0 | 23.4 | <= 26.0 | informative |
| 0522c0002: Glnd_Submand Dmean[Gy] <= 39.0 | 54.01 | <= 39.0 | informative |
| 0522c0002: Mandible D0.03cc[Gy] <= 70.0 | 57.08 | <= 70.0 | informative |
| 0522c0002: PTV56 D95%[Gy] >= 56.0 | 59.82 | >= 56.0 | pass |
| 0522c0002: PTV70 D5 / D95 (homogeneity) | 1.104 | ≤ 1.10 (informative) | informative |
| 0522c0002: hottest point outside the elective volume (% of 70 Gy) | 96.1 | informative | informative |
| 0522c0002: arcs deliverable at the machine's limits | True | True | pass |
