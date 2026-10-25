# Radiarch validation run 20261024-152201 (d458e46)

RESEARCH USE ONLY. NOT FOR CLINICAL USE. Radiarch is a research treatment-planning system; its plans, doses and evaluations must not be used to treat patients.

| Case | Status | Time (s) | Checks |
|---|---|---|---|
| lung_e2e_lctsc | **pass** | 810.2 | 8 pass, 0 fail, 12 informative |
| lung_sbrt_vmat | **pass** | 520.6 | 32 pass, 0 fail, 12 informative |
| lung_vmat_lctsc | **pass** | 2112.9 | 10 pass, 0 fail, 20 informative |
| hn_sib_vmat | **pass** | 2715.6 | 12 pass, 0 fail, 14 informative |

## lung_e2e_lctsc — pass

- note: synthetic 2 cm GTV at the right lung's centroid, CTV +5 mm, PTV +5 mm; 7 coplanar open-field beam models, CCC shipped-scatter Dij, L-BFGS-B; goals from the RTOG 0617 template; a research pipeline check, not a plan quality statement

| Check | Value | Target | Result |
|---|---|---|---|
| LCTSC-Test-S1-101: PTV V60Gy[%] >= 95.0 Gy | 97.82 | >= 95.0 | pass |
| LCTSC-Test-S1-101: PTV D0.03cc[Gy] <= 72.0 Gy | 61.77 | <= 72.0 | informative |
| LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 37.0 Gy | 21.35 | <= 37.0 | pass |
| LCTSC-Test-S1-101: Lungs-GTV Dmean[Gy] <= 20.0 Gy | 10.73 | <= 20.0 | pass |
| LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 50.5 Gy | 12.96 | <= 50.5 | pass |
| LCTSC-Test-S1-101: Esophagus Dmean[Gy] <= 34.0 Gy | 3.9 | <= 34.0 | informative |
| LCTSC-Test-S1-101: Heart V60Gy[%] <= 33.0 Gy | 0 | <= 33.0 | informative |
| LCTSC-Test-S1-101: Heart V45Gy[%] <= 66.0 Gy | 0.01 | <= 66.0 | informative |
| LCTSC-Test-S1-101: Heart V40Gy[%] <= 100.0 Gy | 0.07 | <= 100.0 | informative |
| LCTSC-Test-S1-101: PTV D5 / D95 after normalisation (homogeneity) | 1.017 | ≤ 1.15 (informative) | informative |
| LCTSC-Test-S2-101: PTV V60Gy[%] >= 95.0 Gy | 98.2 | >= 95.0 | pass |
| LCTSC-Test-S2-101: PTV D0.03cc[Gy] <= 72.0 Gy | 61.25 | <= 72.0 | informative |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 37.0 Gy | 19.64 | <= 37.0 | pass |
| LCTSC-Test-S2-101: Lungs-GTV Dmean[Gy] <= 20.0 Gy | 9.61 | <= 20.0 | pass |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5 Gy | 13.5 | <= 50.5 | pass |
| LCTSC-Test-S2-101: Esophagus Dmean[Gy] <= 34.0 Gy | 3.21 | <= 34.0 | informative |
| LCTSC-Test-S2-101: Heart V60Gy[%] <= 33.0 Gy | 0.01 | <= 33.0 | informative |
| LCTSC-Test-S2-101: Heart V45Gy[%] <= 66.0 Gy | 0.45 | <= 66.0 | informative |
| LCTSC-Test-S2-101: Heart V40Gy[%] <= 100.0 Gy | 0.85 | <= 100.0 | informative |
| LCTSC-Test-S2-101: PTV D5 / D95 after normalisation (homogeneity) | 1.012 | ≤ 1.15 (informative) | informative |

## lung_sbrt_vmat — pass

- note: synthetic peripheral GTV in the right lung (radius 12 mm), PTV +5 mm, rings for the SBRT dose fall-off; FMO of the arcs' sector beams with the pb Dij, arcs by sweeping each sector's fluence, control-point doses recomputed and metersets re-optimized (R8); a research pipeline check, not a plan quality statement

| Check | Value | Target | Result |
|---|---|---|---|
| LCTSC-Test-S1-101: PTV V100%[%] >= 95.0 | 95.27 | >= 95.0 | pass |
| LCTSC-Test-S1-101: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S1-101: PTV D0.03cc[%] <= 140.0 | 118 | <= 140.0 | informative |
| LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 10.0 | 2.6 | <= 10.0 | informative |
| LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 21.9 | 11.16 | <= 21.9 | pass |
| LCTSC-Test-S1-101: SpinalCord D0.35cc[Gy] <= 18.0 | 9.25 | <= 18.0 | pass |
| LCTSC-Test-S1-101: SpinalCord D1.2cc[Gy] <= 12.3 | 8.23 | <= 12.3 | pass |
| LCTSC-Test-S1-101: Esophagus D0.03cc[Gy] <= 25.2 | 2.57 | <= 25.2 | pass |
| LCTSC-Test-S1-101: Esophagus D5cc[Gy] <= 17.7 | 0.64 | <= 17.7 | pass |
| LCTSC-Test-S1-101: Heart D0.03cc[Gy] <= 30.0 | 16.99 | <= 30.0 | pass |
| LCTSC-Test-S1-101: Heart D15cc[Gy] <= 24.0 | 10.68 | <= 24.0 | pass |
| LCTSC-Test-S1-101: Lungs D1500cc[Gy] <= 11.6 | 0.55 | <= 11.6 | pass |
| LCTSC-Test-S1-101: Lungs D1000cc[Gy] <= 12.4 | 1.15 | <= 12.4 | pass |
| LCTSC-Test-S1-101: Lungs V12.5Gy[cc] <= 1000.0 | 229.8 | <= 1000.0 | informative |
| LCTSC-Test-S1-101: R100 (PTV 16.0 cc) | 0.956 | < 1.2 (minor ≤ 1.5) | pass |
| LCTSC-Test-S1-101: R50 (PTV 16.0 cc) | 2.287 | < 4.63673 (minor ≤ 5.70509) | pass |
| LCTSC-Test-S1-101: D2cm (PTV 16.0 cc) | 55.9 | < 51.2655 (minor ≤ 59.5818) | pass |
| LCTSC-Test-S1-101: LungV20 (PTV 16.0 cc) | 2.601 | < 10 (minor ≤ 15) | pass |
| LCTSC-Test-S1-101: arcs deliverable at the machine's limits | True | True | pass |
| LCTSC-Test-S1-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 89.1 | informative | informative |
| LCTSC-Test-S1-101: second engine PTV D95, CCC / pb | 0.997 | informative | informative |
| LCTSC-Test-S1-101: second engine PTV D95, CCC / pb, body as water | 1.042 | informative | informative |
| LCTSC-Test-S2-101: PTV V100%[%] >= 95.0 | 96.18 | >= 95.0 | pass |
| LCTSC-Test-S2-101: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S2-101: PTV D0.03cc[%] <= 140.0 | 115.2 | <= 140.0 | informative |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 10.0 | 2.66 | <= 10.0 | informative |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 21.9 | 9.99 | <= 21.9 | pass |
| LCTSC-Test-S2-101: SpinalCord D0.35cc[Gy] <= 18.0 | 8.86 | <= 18.0 | pass |
| LCTSC-Test-S2-101: SpinalCord D1.2cc[Gy] <= 12.3 | 7.35 | <= 12.3 | pass |
| LCTSC-Test-S2-101: Esophagus D0.03cc[Gy] <= 25.2 | 6.22 | <= 25.2 | pass |
| LCTSC-Test-S2-101: Esophagus D5cc[Gy] <= 17.7 | 1.77 | <= 17.7 | pass |
| LCTSC-Test-S2-101: Heart D0.03cc[Gy] <= 30.0 | 17.5 | <= 30.0 | pass |
| LCTSC-Test-S2-101: Heart D15cc[Gy] <= 24.0 | 10.47 | <= 24.0 | pass |
| LCTSC-Test-S2-101: Lungs D1500cc[Gy] <= 11.6 | 0.62 | <= 11.6 | pass |
| LCTSC-Test-S2-101: Lungs D1000cc[Gy] <= 12.4 | 1.22 | <= 12.4 | pass |
| LCTSC-Test-S2-101: Lungs V12.5Gy[cc] <= 1000.0 | 212 | <= 1000.0 | informative |
| LCTSC-Test-S2-101: R100 (PTV 16.3 cc) | 0.972 | < 1.2 (minor ≤ 1.5) | pass |
| LCTSC-Test-S2-101: R50 (PTV 16.3 cc) | 2.267 | < 4.63059 (minor ≤ 5.69589) | pass |
| LCTSC-Test-S2-101: D2cm (PTV 16.3 cc) | 49.28 | < 51.3882 (minor ≤ 59.7352) | pass |
| LCTSC-Test-S2-101: LungV20 (PTV 16.3 cc) | 2.664 | < 10 (minor ≤ 15) | pass |
| LCTSC-Test-S2-101: arcs deliverable at the machine's limits | True | True | pass |
| LCTSC-Test-S2-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 93 | informative | informative |
| LCTSC-Test-S2-101: second engine PTV D95, CCC / pb | 0.988 | informative | informative |
| LCTSC-Test-S2-101: second engine PTV D95, CCC / pb, body as water | 1.059 | informative | informative |

## lung_vmat_lctsc — pass

- note: synthetic 2 cm GTV at the right lung's centroid, CTV +5 mm, PTV +5 mm (the R7 lung case), 60 Gy in 30 fractions; FMO of the arcs' sector beams with the pb Dij, arcs by sweeping each sector's fluence, control-point doses recomputed and metersets re-optimized (R8); a research pipeline check, not a plan quality statement

| Check | Value | Target | Result |
|---|---|---|---|
| LCTSC-Test-S1-101: PTV V60Gy[%] >= 95.0 | 95.66 | >= 95.0 | pass |
| LCTSC-Test-S1-101: PTV D0.03cc[Gy] <= 72.0 | 65.9 | <= 72.0 | informative |
| LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 37.0 | 13.72 | <= 37.0 | pass |
| LCTSC-Test-S1-101: Lungs-GTV Dmean[Gy] <= 20.0 | 7.85 | <= 20.0 | pass |
| LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 50.5 | 17.89 | <= 50.5 | pass |
| LCTSC-Test-S1-101: Esophagus Dmean[Gy] <= 34.0 | 2.72 | <= 34.0 | informative |
| LCTSC-Test-S1-101: Heart V60Gy[%] <= 33.0 | 0 | <= 33.0 | informative |
| LCTSC-Test-S1-101: Heart V45Gy[%] <= 66.0 | 0 | <= 66.0 | informative |
| LCTSC-Test-S1-101: Heart V40Gy[%] <= 100.0 | 0 | <= 100.0 | informative |
| LCTSC-Test-S1-101: PTV D5 / D95 (homogeneity) | 1.061 | ≤ 1.15 (informative) | informative |
| LCTSC-Test-S1-101: Paddick conformity index | 0.91 | informative | informative |
| LCTSC-Test-S1-101: arcs deliverable at the machine's limits | True | True | pass |
| LCTSC-Test-S1-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 83.3 | informative | informative |
| LCTSC-Test-S1-101: second engine PTV D95, CCC / pb | 0.88 | informative | informative |
| LCTSC-Test-S1-101: second engine PTV D95, CCC / pb, body as water | 1.05 | informative | informative |
| LCTSC-Test-S2-101: PTV V60Gy[%] >= 95.0 | 95.74 | >= 95.0 | pass |
| LCTSC-Test-S2-101: PTV D0.03cc[Gy] <= 72.0 | 66.87 | <= 72.0 | informative |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 37.0 | 13.18 | <= 37.0 | pass |
| LCTSC-Test-S2-101: Lungs-GTV Dmean[Gy] <= 20.0 | 8.28 | <= 20.0 | pass |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5 | 20.19 | <= 50.5 | pass |
| LCTSC-Test-S2-101: Esophagus Dmean[Gy] <= 34.0 | 3.24 | <= 34.0 | informative |
| LCTSC-Test-S2-101: Heart V60Gy[%] <= 33.0 | 0 | <= 33.0 | informative |
| LCTSC-Test-S2-101: Heart V45Gy[%] <= 66.0 | 0.11 | <= 66.0 | informative |
| LCTSC-Test-S2-101: Heart V40Gy[%] <= 100.0 | 0.31 | <= 100.0 | informative |
| LCTSC-Test-S2-101: PTV D5 / D95 (homogeneity) | 1.064 | ≤ 1.15 (informative) | informative |
| LCTSC-Test-S2-101: Paddick conformity index | 0.915 | informative | informative |
| LCTSC-Test-S2-101: arcs deliverable at the machine's limits | True | True | pass |
| LCTSC-Test-S2-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 86.4 | informative | informative |
| LCTSC-Test-S2-101: second engine PTV D95, CCC / pb | 0.938 | informative | informative |
| LCTSC-Test-S2-101: second engine PTV D95, CCC / pb, body as water | 1.06 | informative | informative |

## hn_sib_vmat — pass

- note: synthetic oropharynx-like GTV between the parotids, PTV70 +8 mm, PTV56 +25 mm outside PTV70 + 3 mm and the brainstem + 5 mm; two full arcs from the fluence of their sector beams (pb Dij), 70/56 Gy in 35 fractions; NCCN head-and-neck template; a research pipeline check, not a plan quality statement

| Check | Value | Target | Result |
|---|---|---|---|
| 0522c0001: PTV_High D95%[%] >= 95.0 | 100.2 | >= 95.0 | pass |
| 0522c0001: PTV_High D0.03cc[%] <= 110.0 | 112.5 | <= 110.0 | informative |
| 0522c0001: Brainstem D0.03cc[Gy] <= 54.0 | 41.55 | <= 54.0 | pass |
| 0522c0001: Brainstem_PRV D0.03cc[Gy] <= 60.0 | 48.64 | <= 60.0 | informative |
| 0522c0001: OpticChiasm D0.03cc[Gy] <= 54.0 | 0.91 | <= 54.0 | pass |
| 0522c0001: OpticNrv D0.03cc[Gy] <= 54.0 | 0.85 | <= 54.0 | pass |
| 0522c0001: Parotid Dmean[Gy] <= 26.0 | 29.81 | <= 26.0 | informative |
| 0522c0001: Glnd_Submand Dmean[Gy] <= 39.0 | 62.3 | <= 39.0 | informative |
| 0522c0001: Mandible D0.03cc[Gy] <= 70.0 | 62.51 | <= 70.0 | informative |
| 0522c0001: PTV56 D95%[Gy] >= 56.0 | 58.98 | >= 56.0 | pass |
| 0522c0001: PTV70 D5 / D95 (homogeneity) | 1.099 | ≤ 1.10 (informative) | informative |
| 0522c0001: hottest point outside the elective volume (% of 70 Gy) | 98.7 | informative | informative |
| 0522c0001: arcs deliverable at the machine's limits | True | True | pass |
| 0522c0002: PTV_High D95%[%] >= 95.0 | 100.2 | >= 95.0 | pass |
| 0522c0002: PTV_High D0.03cc[%] <= 110.0 | 113.1 | <= 110.0 | informative |
| 0522c0002: Brainstem D0.03cc[Gy] <= 54.0 | 41.05 | <= 54.0 | pass |
| 0522c0002: Brainstem_PRV D0.03cc[Gy] <= 60.0 | 50.97 | <= 60.0 | informative |
| 0522c0002: OpticChiasm D0.03cc[Gy] <= 54.0 | 0.8 | <= 54.0 | pass |
| 0522c0002: OpticNrv D0.03cc[Gy] <= 54.0 | 0.77 | <= 54.0 | pass |
| 0522c0002: Parotid Dmean[Gy] <= 26.0 | 22.35 | <= 26.0 | informative |
| 0522c0002: Glnd_Submand Dmean[Gy] <= 39.0 | 53.72 | <= 39.0 | informative |
| 0522c0002: Mandible D0.03cc[Gy] <= 70.0 | 56.92 | <= 70.0 | informative |
| 0522c0002: PTV56 D95%[Gy] >= 56.0 | 59.56 | >= 56.0 | pass |
| 0522c0002: PTV70 D5 / D95 (homogeneity) | 1.111 | ≤ 1.10 (informative) | informative |
| 0522c0002: hottest point outside the elective volume (% of 70 Gy) | 97.7 | informative | informative |
| 0522c0002: arcs deliverable at the machine's limits | True | True | pass |
