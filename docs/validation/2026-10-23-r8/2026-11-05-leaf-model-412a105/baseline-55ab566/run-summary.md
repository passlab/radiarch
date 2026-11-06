# Radiarch validation run 20261105-235948-55ab566 + 20261106-004016-55ab566 + 20261106-005331-55ab566

RESEARCH USE ONLY. NOT FOR CLINICAL USE. Radiarch is a research treatment-planning system; its plans, doses and evaluations must not be used to treat patients.

The cases ran one per process from commit 55ab566: `lung_sbrt_vmat` (20261105-235948), `lung_vmat_lctsc` (20261106-004016), `hn_sib_vmat` (20261106-005331).

| Case | Status | Time (s) | Checks |
|---|---|---|---|
| lung_sbrt_vmat | **pass** | 819.2 | 32 pass, 0 fail, 12 informative |
| lung_vmat_lctsc | **pass** | 3246.2 | 10 pass, 0 fail, 20 informative |
| hn_sib_vmat | **pass** | 4041.4 | 12 pass, 0 fail, 14 informative |

## lung_sbrt_vmat — pass

- note: synthetic peripheral GTV in the right lung (radius 12 mm), PTV +5 mm, rings for the SBRT dose fall-off; FMO of the arcs' sector beams with the pb Dij, arcs by sweeping each sector's fluence, control-point doses recomputed and metersets re-optimized (R8); a research pipeline check, not a plan quality statement

| Check | Value | Target | Result |
|---|---|---|---|
| LCTSC-Test-S1-101: PTV V100%[%] >= 95.0 | 95.1 | >= 95.0 | pass |
| LCTSC-Test-S1-101: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S1-101: PTV D0.03cc[%] <= 140.0 | 115.5 | <= 140.0 | informative |
| LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 10.0 | 2.61 | <= 10.0 | informative |
| LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 21.9 | 10.69 | <= 21.9 | pass |
| LCTSC-Test-S1-101: SpinalCord D0.35cc[Gy] <= 18.0 | 8.87 | <= 18.0 | pass |
| LCTSC-Test-S1-101: SpinalCord D1.2cc[Gy] <= 12.3 | 7.85 | <= 12.3 | pass |
| LCTSC-Test-S1-101: Esophagus D0.03cc[Gy] <= 25.2 | 2.07 | <= 25.2 | pass |
| LCTSC-Test-S1-101: Esophagus D5cc[Gy] <= 17.7 | 0.53 | <= 17.7 | pass |
| LCTSC-Test-S1-101: Heart D0.03cc[Gy] <= 30.0 | 17.94 | <= 30.0 | pass |
| LCTSC-Test-S1-101: Heart D15cc[Gy] <= 24.0 | 11.38 | <= 24.0 | pass |
| LCTSC-Test-S1-101: Lungs D1500cc[Gy] <= 11.6 | 0.51 | <= 11.6 | pass |
| LCTSC-Test-S1-101: Lungs D1000cc[Gy] <= 12.4 | 1.11 | <= 12.4 | pass |
| LCTSC-Test-S1-101: Lungs V12.5Gy[cc] <= 1000.0 | 223.1 | <= 1000.0 | informative |
| LCTSC-Test-S1-101: R100 (PTV 16.0 cc) | 0.956 | < 1.2 (minor ≤ 1.5) | pass |
| LCTSC-Test-S1-101: R50 (PTV 16.0 cc) | 2.221 | < 4.63673 (minor ≤ 5.70509) | pass |
| LCTSC-Test-S1-101: D2cm (PTV 16.0 cc) | 53.19 | < 51.2655 (minor ≤ 59.5818) | pass |
| LCTSC-Test-S1-101: LungV20 (PTV 16.0 cc) | 2.606 | < 10 (minor ≤ 15) | pass |
| LCTSC-Test-S1-101: arcs deliverable at the machine's limits | True | True | pass |
| LCTSC-Test-S1-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 88.2 | informative | informative |
| LCTSC-Test-S1-101: second engine PTV D95, CCC / pb | 0.987 | informative | informative |
| LCTSC-Test-S1-101: second engine PTV D95, CCC / pb, body as water | 1.035 | informative | informative |
| LCTSC-Test-S2-101: PTV V100%[%] >= 95.0 | 95.51 | >= 95.0 | pass |
| LCTSC-Test-S2-101: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S2-101: PTV D0.03cc[%] <= 140.0 | 113.8 | <= 140.0 | informative |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 10.0 | 2.6 | <= 10.0 | informative |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 21.9 | 10.21 | <= 21.9 | pass |
| LCTSC-Test-S2-101: SpinalCord D0.35cc[Gy] <= 18.0 | 9.17 | <= 18.0 | pass |
| LCTSC-Test-S2-101: SpinalCord D1.2cc[Gy] <= 12.3 | 7.7 | <= 12.3 | pass |
| LCTSC-Test-S2-101: Esophagus D0.03cc[Gy] <= 25.2 | 7.14 | <= 25.2 | pass |
| LCTSC-Test-S2-101: Esophagus D5cc[Gy] <= 17.7 | 3.83 | <= 17.7 | pass |
| LCTSC-Test-S2-101: Heart D0.03cc[Gy] <= 30.0 | 18.57 | <= 30.0 | pass |
| LCTSC-Test-S2-101: Heart D15cc[Gy] <= 24.0 | 10.44 | <= 24.0 | pass |
| LCTSC-Test-S2-101: Lungs D1500cc[Gy] <= 11.6 | 0.66 | <= 11.6 | pass |
| LCTSC-Test-S2-101: Lungs D1000cc[Gy] <= 12.4 | 1.24 | <= 12.4 | pass |
| LCTSC-Test-S2-101: Lungs V12.5Gy[cc] <= 1000.0 | 211.7 | <= 1000.0 | informative |
| LCTSC-Test-S2-101: R100 (PTV 16.3 cc) | 0.963 | < 1.2 (minor ≤ 1.5) | pass |
| LCTSC-Test-S2-101: R50 (PTV 16.3 cc) | 2.228 | < 4.63059 (minor ≤ 5.69589) | pass |
| LCTSC-Test-S2-101: D2cm (PTV 16.3 cc) | 51.04 | < 51.3882 (minor ≤ 59.7352) | pass |
| LCTSC-Test-S2-101: LungV20 (PTV 16.3 cc) | 2.603 | < 10 (minor ≤ 15) | pass |
| LCTSC-Test-S2-101: arcs deliverable at the machine's limits | True | True | pass |
| LCTSC-Test-S2-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 93 | informative | informative |
| LCTSC-Test-S2-101: second engine PTV D95, CCC / pb | 0.977 | informative | informative |
| LCTSC-Test-S2-101: second engine PTV D95, CCC / pb, body as water | 1.064 | informative | informative |

## lung_vmat_lctsc — pass

- note: synthetic 2 cm GTV at the right lung's centroid, CTV +5 mm, PTV +5 mm (the R7 lung case), 60 Gy in 30 fractions; FMO of the arcs' sector beams with the pb Dij, arcs by sweeping each sector's fluence, control-point doses recomputed and metersets re-optimized (R8); a research pipeline check, not a plan quality statement

| Check | Value | Target | Result |
|---|---|---|---|
| LCTSC-Test-S1-101: PTV V60Gy[%] >= 95.0 | 95.76 | >= 95.0 | pass |
| LCTSC-Test-S1-101: PTV D0.03cc[Gy] <= 72.0 | 65.57 | <= 72.0 | informative |
| LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 37.0 | 13.67 | <= 37.0 | pass |
| LCTSC-Test-S1-101: Lungs-GTV Dmean[Gy] <= 20.0 | 7.88 | <= 20.0 | pass |
| LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 50.5 | 15.2 | <= 50.5 | pass |
| LCTSC-Test-S1-101: Esophagus Dmean[Gy] <= 34.0 | 2.78 | <= 34.0 | informative |
| LCTSC-Test-S1-101: Heart V60Gy[%] <= 33.0 | 0 | <= 33.0 | informative |
| LCTSC-Test-S1-101: Heart V45Gy[%] <= 66.0 | 0 | <= 66.0 | informative |
| LCTSC-Test-S1-101: Heart V40Gy[%] <= 100.0 | 0 | <= 100.0 | informative |
| LCTSC-Test-S1-101: PTV D5 / D95 (homogeneity) | 1.061 | ≤ 1.15 (informative) | informative |
| LCTSC-Test-S1-101: Paddick conformity index | 0.912 | informative | informative |
| LCTSC-Test-S1-101: arcs deliverable at the machine's limits | True | True | pass |
| LCTSC-Test-S1-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 83.1 | informative | informative |
| LCTSC-Test-S1-101: second engine PTV D95, CCC / pb | 0.881 | informative | informative |
| LCTSC-Test-S1-101: second engine PTV D95, CCC / pb, body as water | 1.05 | informative | informative |
| LCTSC-Test-S2-101: PTV V60Gy[%] >= 95.0 | 95.58 | >= 95.0 | pass |
| LCTSC-Test-S2-101: PTV D0.03cc[Gy] <= 72.0 | 65.79 | <= 72.0 | informative |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 37.0 | 13.11 | <= 37.0 | pass |
| LCTSC-Test-S2-101: Lungs-GTV Dmean[Gy] <= 20.0 | 8.17 | <= 20.0 | pass |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5 | 16.77 | <= 50.5 | pass |
| LCTSC-Test-S2-101: Esophagus Dmean[Gy] <= 34.0 | 3.01 | <= 34.0 | informative |
| LCTSC-Test-S2-101: Heart V60Gy[%] <= 33.0 | 0 | <= 33.0 | informative |
| LCTSC-Test-S2-101: Heart V45Gy[%] <= 66.0 | 0.11 | <= 66.0 | informative |
| LCTSC-Test-S2-101: Heart V40Gy[%] <= 100.0 | 0.33 | <= 100.0 | informative |
| LCTSC-Test-S2-101: PTV D5 / D95 (homogeneity) | 1.062 | ≤ 1.15 (informative) | informative |
| LCTSC-Test-S2-101: Paddick conformity index | 0.906 | informative | informative |
| LCTSC-Test-S2-101: arcs deliverable at the machine's limits | True | True | pass |
| LCTSC-Test-S2-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 86.3 | informative | informative |
| LCTSC-Test-S2-101: second engine PTV D95, CCC / pb | 0.935 | informative | informative |
| LCTSC-Test-S2-101: second engine PTV D95, CCC / pb, body as water | 1.058 | informative | informative |

## hn_sib_vmat — pass

- note: synthetic oropharynx-like GTV between the parotids, PTV70 +8 mm, PTV56 +25 mm outside PTV70 + 3 mm and the brainstem + 5 mm; two full arcs from the fluence of their sector beams (pb Dij), 70/56 Gy in 35 fractions; NCCN head-and-neck template; a research pipeline check, not a plan quality statement

| Check | Value | Target | Result |
|---|---|---|---|
| 0522c0001: PTV_High D95%[%] >= 95.0 | 100.2 | >= 95.0 | pass |
| 0522c0001: PTV_High D0.03cc[%] <= 110.0 | 112.3 | <= 110.0 | informative |
| 0522c0001: Brainstem D0.03cc[Gy] <= 54.0 | 42.54 | <= 54.0 | pass |
| 0522c0001: Brainstem_PRV D0.03cc[Gy] <= 60.0 | 51.89 | <= 60.0 | informative |
| 0522c0001: OpticChiasm D0.03cc[Gy] <= 54.0 | 0.92 | <= 54.0 | pass |
| 0522c0001: OpticNrv D0.03cc[Gy] <= 54.0 | 0.85 | <= 54.0 | pass |
| 0522c0001: Parotid Dmean[Gy] <= 26.0 | 30.69 | <= 26.0 | informative |
| 0522c0001: Glnd_Submand Dmean[Gy] <= 39.0 | 61.73 | <= 39.0 | informative |
| 0522c0001: Mandible D0.03cc[Gy] <= 70.0 | 62.54 | <= 70.0 | informative |
| 0522c0001: PTV56 D95%[Gy] >= 56.0 | 59.02 | >= 56.0 | pass |
| 0522c0001: PTV70 D5 / D95 (homogeneity) | 1.096 | ≤ 1.10 (informative) | informative |
| 0522c0001: hottest point outside the elective volume (% of 70 Gy) | 98.6 | informative | informative |
| 0522c0001: arcs deliverable at the machine's limits | True | True | pass |
| 0522c0002: PTV_High D95%[%] >= 95.0 | 100.2 | >= 95.0 | pass |
| 0522c0002: PTV_High D0.03cc[%] <= 110.0 | 112.2 | <= 110.0 | informative |
| 0522c0002: Brainstem D0.03cc[Gy] <= 54.0 | 44.64 | <= 54.0 | pass |
| 0522c0002: Brainstem_PRV D0.03cc[Gy] <= 60.0 | 53.94 | <= 60.0 | informative |
| 0522c0002: OpticChiasm D0.03cc[Gy] <= 54.0 | 0.8 | <= 54.0 | pass |
| 0522c0002: OpticNrv D0.03cc[Gy] <= 54.0 | 0.77 | <= 54.0 | pass |
| 0522c0002: Parotid Dmean[Gy] <= 26.0 | 21.88 | <= 26.0 | informative |
| 0522c0002: Glnd_Submand Dmean[Gy] <= 39.0 | 53.4 | <= 39.0 | informative |
| 0522c0002: Mandible D0.03cc[Gy] <= 70.0 | 57.05 | <= 70.0 | informative |
| 0522c0002: PTV56 D95%[Gy] >= 56.0 | 59.8 | >= 56.0 | pass |
| 0522c0002: PTV70 D5 / D95 (homogeneity) | 1.106 | ≤ 1.10 (informative) | informative |
| 0522c0002: hottest point outside the elective volume (% of 70 Gy) | 98.1 | informative | informative |
| 0522c0002: arcs deliverable at the machine's limits | True | True | pass |
