# Radiarch validation run 20261023-192600-52ed834

RESEARCH USE ONLY. NOT FOR CLINICAL USE. Radiarch is a research treatment-planning system; its plans, doses and evaluations must not be used to treat patients.

| Case | Status | Time (s) | Checks |
|---|---|---|---|
| dij_consistency | **pass** | 542.1 | 9 pass, 0 fail, 0 informative |
| dvh_crosscheck_pancreatic | **fail** | 256.5 | 47 pass, 3 fail, 19 informative |
| gamma_crosscheck_synthetic | **pass** | 5.7 | 4 pass, 0 fail, 0 informative |
| geometry_volumes_lctsc | **fail** | 123.8 | 29 pass, 1 fail, 0 informative |
| hn_sib_vmat | **pass** | 1931.7 | 12 pass, 0 fail, 14 informative |
| lung_e2e_lctsc | **pass** | 531.8 | 8 pass, 0 fail, 12 informative |
| lung_sbrt_vmat | **pass** | 453.9 | 32 pass, 0 fail, 12 informative |
| lung_vmat_lctsc | **pass** | 1530.0 | 10 pass, 0 fail, 20 informative |
| pb_vs_ccc | **pass** | 6.0 | 3 pass, 0 fail, 4 informative |
| pb_vs_mc | **pass** | 3.7 | 27 pass, 0 fail, 7 informative |
| photon_heterogeneity_slabs | **info** | 123.4 | 0 pass, 0 fail, 6 informative |
| photon_output_vs_field | **info** | 623.5 | 0 pass, 0 fail, 3 informative |
| photon_output_vs_field_pb | **info** | 1.6 | 0 pass, 0 fail, 3 informative |
| photon_pdd_10x10 | **pass** | 40.8 | 3 pass, 0 fail, 1 informative |
| photon_pdd_10x10_pb | **pass** | 0.2 | 2 pass, 0 fail, 2 informative |
| photon_profile_10x10 | **pass** | 40.8 | 2 pass, 0 fail, 1 informative |
| photon_profile_10x10_pb | **pass** | 0.2 | 2 pass, 0 fail, 1 informative |
| photon_vs_mc | **fail** | 13.6 | 26 pass, 14 fail, 2 informative |
| photon_vs_pyradplan | **info** | 0.4 | 0 pass, 0 fail, 13 informative |
| proton_bragg_peak | **pass** | 8.0 | 12 pass, 0 fail, 8 informative |
| proton_range_water | **pass** | 3.6 | 4 pass, 0 fail, 0 informative |
| tg119_planning | **pass** | 2626.3 | 24 pass, 0 fail, 0 informative |

## dij_consistency — pass


| Check | Value | Target | Result |
|---|---|---|---|
| ccc: integral ratio Dij·w / forward | 1 | 1 ± 0.0001 | pass |
| ccc: correlation above 1 % of max | 1 | ≥ 0.9999 | pass |
| ccc: high-dose (≥ 50 % of max) p95 relative error | 1.183e-07 | ≤ 0.001 | pass |
| mcsquare: integral ratio Dij·w / forward | 0.9808 | 1 ± 0.05 | pass |
| mcsquare: correlation above 1 % of max | 0.9978 | ≥ 0.95 | pass |
| mcsquare: high-dose (≥ 50 % of max) p95 relative error | 0.07357 | ≤ 0.15 | pass |
| pb: integral ratio Dij·w / forward | 0.9979 | 1 ± 0.03 | pass |
| pb: correlation above 1 % of max | 0.9999 | ≥ 0.999 | pass |
| pb: high-dose (≥ 50 % of max) p95 relative error | 0.009179 | ≤ 0.02 | pass |

## dvh_crosscheck_pancreatic — fail

- note: dicompyler-core 0.5.6 in its own uv environment (Python 3.12, pydicom 2); radiarch on pydicom 3

| Check | Value | Target | Result |
|---|---|---|---|
| Pancreas-CT-CB_001 Bowel_sm_planCT mean (Gy) | 16.62 | 16.441 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_001 Bowel_sm_planCT max (Gy) | 40.1 | 39.560 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_001 Bowel_sm_planCT d95 (Gy) | 4.227 | 3.950 ± 5.0 % (dicompyler-core) | informative |
| Pancreas-CT-CB_001 LUNG_L mean (Gy) | 0.569 | 0.572 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_001 LUNG_L max (Gy) | 12.55 | 12.440 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_001 LUNG_L d95 (Gy) | 0.063 | 0.050 ± 5.0 % (dicompyler-core) | informative |
| Pancreas-CT-CB_001 LUNG_R mean (Gy) | 0.483 | 0.486 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_001 LUNG_R max (Gy) | 8.02 | 8.020 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_001 LUNG_R d95 (Gy) | 0 | 0.010 ± 5.0 % (dicompyler-core) | informative |
| Pancreas-CT-CB_001 ROI mean (Gy) | 38.51 | 38.531 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_001 ROI max (Gy) | 74.16 | 74.040 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_001 ROI d95 (Gy) | 25.39 | 25.190 ± 5.0 % (dicompyler-core) | informative |
| Pancreas-CT-CB_001 Stomach_duo_planCT mean (Gy) | 16.98 | 17.116 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_001 Stomach_duo_planCT max (Gy) | 42.94 | 43.100 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_001 Stomach_duo_planCT d95 (Gy) | 1.457 | 1.470 ± 5.0 % (dicompyler-core) | informative |
| Pancreas-CT-CB_002 Bowel_sm_planCT mean (Gy) | 5.718 | 5.687 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_002 Bowel_sm_planCT max (Gy) | 30.8 | 29.440 ± 3.0 % (dicompyler-core) | FAIL |
| Pancreas-CT-CB_002 Bowel_sm_planCT d95 (Gy) | 1.251 | 1.290 ± 5.0 % (dicompyler-core) | informative |
| Pancreas-CT-CB_002 LUNG_L mean (Gy) | 0.173 | 0.173 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_002 LUNG_L max (Gy) | 10.38 | 10.030 ± 3.0 % (dicompyler-core) | FAIL |
| Pancreas-CT-CB_002 LUNG_R mean (Gy) | 0.304 | 0.304 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_002 LUNG_R max (Gy) | 20.79 | 20.390 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_002 ROI mean (Gy) | 29.5 | 29.711 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_002 ROI max (Gy) | 39.12 | 39.070 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_002 ROI d95 (Gy) | 11.14 | 12.660 ± 5.0 % (dicompyler-core) | informative |
| Pancreas-CT-CB_002 Stomach_duo_planCT mean (Gy) | 7.674 | 7.684 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_002 Stomach_duo_planCT max (Gy) | 32.27 | 32.530 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_002 Stomach_duo_planCT d95 (Gy) | 0.573 | 0.570 ± 5.0 % (dicompyler-core) | informative |
| Pancreas-CT-CB_003 Bowel_sm_planCT mean (Gy) | 9.591 | 9.564 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_003 Bowel_sm_planCT max (Gy) | 40.95 | 40.960 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_003 Bowel_sm_planCT d95 (Gy) | 0.772 | 0.770 ± 5.0 % (dicompyler-core) | informative |
| Pancreas-CT-CB_003 LUNG_L mean (Gy) | 0.792 | 0.787 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_003 LUNG_L max (Gy) | 3.278 | 3.260 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_003 LUNG_L d95 (Gy) | 0.353 | 0.350 ± 5.0 % (dicompyler-core) | informative |
| Pancreas-CT-CB_003 LUNG_R mean (Gy) | 0.776 | 0.778 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_003 LUNG_R max (Gy) | 4.095 | 4.100 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_003 LUNG_R d95 (Gy) | 0.441 | 0.440 ± 5.0 % (dicompyler-core) | informative |
| Pancreas-CT-CB_003 ROI mean (Gy) | 47.92 | 48.014 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_003 ROI max (Gy) | 78.06 | 78.070 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_003 ROI d95 (Gy) | 20.03 | 20.150 ± 5.0 % (dicompyler-core) | informative |
| Pancreas-CT-CB_003 Stomach_duo_planCT mean (Gy) | 13.99 | 14.081 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_003 Stomach_duo_planCT max (Gy) | 63.83 | 63.840 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_003 Stomach_duo_planCT d95 (Gy) | 1.76 | 1.750 ± 5.0 % (dicompyler-core) | informative |
| Pancreas-CT-CB_004 Bowel_sm_planCT mean (Gy) | 22.4 | 22.277 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_004 Bowel_sm_planCT max (Gy) | 47.31 | 47.320 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_004 Bowel_sm_planCT d95 (Gy) | 2.962 | 2.960 ± 5.0 % (dicompyler-core) | informative |
| Pancreas-CT-CB_004 LUNG_L mean (Gy) | 1.621 | 1.605 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_004 LUNG_L max (Gy) | 49.33 | 49.160 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_004 LUNG_R mean (Gy) | 1.29 | 1.291 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_004 LUNG_R max (Gy) | 49.56 | 50.580 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_004 ROI mean (Gy) | 47.26 | 47.342 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_004 ROI max (Gy) | 81.85 | 81.860 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_004 ROI d95 (Gy) | 19.16 | 19.250 ± 5.0 % (dicompyler-core) | informative |
| Pancreas-CT-CB_004 Stomach_duo_planCT mean (Gy) | 31.93 | 31.976 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_004 Stomach_duo_planCT max (Gy) | 55.45 | 55.430 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_004 Stomach_duo_planCT d95 (Gy) | 15.17 | 14.910 ± 5.0 % (dicompyler-core) | informative |
| Pancreas-CT-CB_005 Bowel_sm_planCT mean (Gy) | 17.39 | 17.009 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_005 Bowel_sm_planCT max (Gy) | 50.41 | 50.210 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_005 Bowel_sm_planCT d95 (Gy) | 2.489 | 2.490 ± 5.0 % (dicompyler-core) | informative |
| Pancreas-CT-CB_005 LUNG_L mean (Gy) | 1.095 | 1.090 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_005 LUNG_L max (Gy) | 27.21 | 25.990 ± 3.0 % (dicompyler-core) | FAIL |
| Pancreas-CT-CB_005 LUNG_R mean (Gy) | 0.687 | 0.686 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_005 LUNG_R max (Gy) | 22.62 | 22.830 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_005 ROI mean (Gy) | 52.29 | 52.346 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_005 ROI max (Gy) | 104.6 | 104.580 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_005 ROI d95 (Gy) | 25.62 | 25.590 ± 5.0 % (dicompyler-core) | informative |
| Pancreas-CT-CB_005 Stomach_duo_planCT mean (Gy) | 32.12 | 32.358 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_005 Stomach_duo_planCT max (Gy) | 67.76 | 67.770 ± 3.0 % (dicompyler-core) | pass |
| Pancreas-CT-CB_005 Stomach_duo_planCT d95 (Gy) | 4.21 | 4.230 ± 5.0 % (dicompyler-core) | informative |

## gamma_crosscheck_synthetic — pass


| Check | Value | Target | Result |
|---|---|---|---|
| gamma pass rate, identical | 100 | 100.00 % ± 2.0 points (pymedphys) | pass |
| gamma pass rate, scaled_2pct | 100 | 100.00 % ± 2.0 points (pymedphys) | pass |
| gamma pass rate, shifted_1mm | 100 | 100.00 % ± 2.0 points (pymedphys) | pass |
| gamma pass rate, shifted_3mm_scaled_4pct | 56.21 | 55.75 % ± 2.0 points (pymedphys) | pass |

## geometry_volumes_lctsc — fail


| Check | Value | Target | Result |
|---|---|---|---|
| LCTSC-Test-S1-101 Esophagus volume | 28.3 | 27.7 cc ± 5.0 % | pass |
| LCTSC-Test-S1-101 Heart volume | 790.4 | 790.3 cc ± 5.0 % | pass |
| LCTSC-Test-S1-101 Lung_L volume | 1792 | 1780.9 cc ± 5.0 % | pass |
| LCTSC-Test-S1-101 Lung_R volume | 2151 | 2139.1 cc ± 5.0 % | pass |
| LCTSC-Test-S1-101 SpinalCord volume | 63.3 | 62.7 cc ± 5.0 % | pass |
| LCTSC-Test-S1-102 Esophagus volume | 32.8 | 32.3 cc ± 5.0 % | pass |
| LCTSC-Test-S1-102 Heart volume | 673.8 | 673.8 cc ± 5.0 % | pass |
| LCTSC-Test-S1-102 Lung_L volume | 1476 | 1467.1 cc ± 5.0 % | pass |
| LCTSC-Test-S1-102 Lung_R volume | 1863 | 1853.3 cc ± 5.0 % | pass |
| LCTSC-Test-S1-102 SpinalCord volume | 68.5 | 67.7 cc ± 5.0 % | pass |
| LCTSC-Test-S2-101 Esophagus volume | 63.6 | 61.3 cc ± 5.0 % | pass |
| LCTSC-Test-S2-101 Heart volume | 993.1 | 992.7 cc ± 5.0 % | pass |
| LCTSC-Test-S2-101 Lung_L volume | 1860 | 1841.4 cc ± 5.0 % | pass |
| LCTSC-Test-S2-101 Lung_R volume | 1735 | 1715.9 cc ± 5.0 % | pass |
| LCTSC-Test-S2-101 SpinalCord volume | 76.6 | 74.5 cc ± 5.0 % | pass |
| LCTSC-Test-S2-102 Esophagus volume | 39.7 | 37.8 cc ± 5.0 % | FAIL |
| LCTSC-Test-S2-102 Heart volume | 1123 | 1123.3 cc ± 5.0 % | pass |
| LCTSC-Test-S2-102 Lung_L volume | 2361 | 2339.2 cc ± 5.0 % | pass |
| LCTSC-Test-S2-102 Lung_R volume | 2787 | 2762.3 cc ± 5.0 % | pass |
| LCTSC-Test-S2-102 SpinalCord volume | 99.5 | 96.9 cc ± 5.0 % | pass |
| LCTSC-Test-S3-101 Esophagus volume | 62.1 | 62.0 cc ± 5.0 % | pass |
| LCTSC-Test-S3-101 Heart volume | 836.1 | 835.7 cc ± 5.0 % | pass |
| LCTSC-Test-S3-101 Lung_L volume | 504.2 | 503.9 cc ± 5.0 % | pass |
| LCTSC-Test-S3-101 Lung_R volume | 1724 | 1719.9 cc ± 5.0 % | pass |
| LCTSC-Test-S3-101 SpinalCord volume | 37.3 | 37.1 cc ± 5.0 % | pass |
| LCTSC-Test-S3-102 Esophagus volume | 55.2 | 55.1 cc ± 5.0 % | pass |
| LCTSC-Test-S3-102 Heart volume | 1175 | 1171.6 cc ± 5.0 % | pass |
| LCTSC-Test-S3-102 Lung_L volume | 1675 | 1669.4 cc ± 5.0 % | pass |
| LCTSC-Test-S3-102 Lung_R volume | 2332 | 2326.1 cc ± 5.0 % | pass |
| LCTSC-Test-S3-102 SpinalCord volume | 43.1 | 43.0 cc ± 5.0 % | pass |

## hn_sib_vmat — pass

- note: synthetic oropharynx-like GTV between the parotids, PTV70 +8 mm, PTV56 +25 mm outside PTV70 + 3 mm and the brainstem + 5 mm; two full arcs from the fluence of their sector beams (pb Dij), 70/56 Gy in 35 fractions; NCCN head-and-neck template; a research pipeline check, not a plan quality statement

| Check | Value | Target | Result |
|---|---|---|---|
| 0522c0001: PTV_High D95%[%] >= 95.0 | 100.2 | >= 95.0 | pass |
| 0522c0001: PTV_High D0.03cc[%] <= 110.0 | 113.7 | <= 110.0 | informative |
| 0522c0001: Brainstem D0.03cc[Gy] <= 54.0 | 43.85 | <= 54.0 | pass |
| 0522c0001: Brainstem_PRV D0.03cc[Gy] <= 60.0 | 52.09 | <= 60.0 | informative |
| 0522c0001: OpticChiasm D0.03cc[Gy] <= 54.0 | 21.28 | <= 54.0 | pass |
| 0522c0001: OpticNrv D0.03cc[Gy] <= 54.0 | 23.28 | <= 54.0 | pass |
| 0522c0001: Parotid Dmean[Gy] <= 26.0 | 11.25 | <= 26.0 | informative |
| 0522c0001: Glnd_Submand Dmean[Gy] <= 39.0 | 61.1 | <= 39.0 | informative |
| 0522c0001: Mandible D0.03cc[Gy] <= 70.0 | 62.52 | <= 70.0 | informative |
| 0522c0001: PTV56 D95%[Gy] >= 56.0 | 58.54 | >= 56.0 | pass |
| 0522c0001: PTV70 D5 / D95 (homogeneity) | 1.112 | ≤ 1.10 (informative) | informative |
| 0522c0001: hottest point outside the elective volume (% of 70 Gy) | 97.4 | informative | informative |
| 0522c0001: arcs deliverable at the machine's limits | True | True | pass |
| 0522c0002: PTV_High D95%[%] >= 95.0 | 100.2 | >= 95.0 | pass |
| 0522c0002: PTV_High D0.03cc[%] <= 110.0 | 112.2 | <= 110.0 | informative |
| 0522c0002: Brainstem D0.03cc[Gy] <= 54.0 | 43.18 | <= 54.0 | pass |
| 0522c0002: Brainstem_PRV D0.03cc[Gy] <= 60.0 | 53.41 | <= 60.0 | informative |
| 0522c0002: OpticChiasm D0.03cc[Gy] <= 54.0 | 15.86 | <= 54.0 | pass |
| 0522c0002: OpticNrv D0.03cc[Gy] <= 54.0 | 16.09 | <= 54.0 | pass |
| 0522c0002: Parotid Dmean[Gy] <= 26.0 | 2.47 | <= 26.0 | informative |
| 0522c0002: Glnd_Submand Dmean[Gy] <= 39.0 | 47.75 | <= 39.0 | informative |
| 0522c0002: Mandible D0.03cc[Gy] <= 70.0 | 61.74 | <= 70.0 | informative |
| 0522c0002: PTV56 D95%[Gy] >= 56.0 | 58.81 | >= 56.0 | pass |
| 0522c0002: PTV70 D5 / D95 (homogeneity) | 1.101 | ≤ 1.10 (informative) | informative |
| 0522c0002: hottest point outside the elective volume (% of 70 Gy) | 95.8 | informative | informative |
| 0522c0002: arcs deliverable at the machine's limits | True | True | pass |

## lung_e2e_lctsc — pass

- note: synthetic 2 cm GTV at the right lung's centroid, CTV +5 mm, PTV +5 mm; 7 coplanar open-field beam models, CCC shipped-scatter Dij, L-BFGS-B; goals from the RTOG 0617 template; a research pipeline check, not a plan quality statement

| Check | Value | Target | Result |
|---|---|---|---|
| LCTSC-Test-S1-101: PTV V60Gy[%] >= 95.0 Gy | 97.48 | >= 95.0 | pass |
| LCTSC-Test-S1-101: PTV D0.03cc[Gy] <= 72.0 Gy | 61.95 | <= 72.0 | informative |
| LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 37.0 Gy | 24.41 | <= 37.0 | pass |
| LCTSC-Test-S1-101: Lungs-GTV Dmean[Gy] <= 20.0 Gy | 11.33 | <= 20.0 | pass |
| LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 50.5 Gy | 0 | <= 50.5 | pass |
| LCTSC-Test-S1-101: Esophagus Dmean[Gy] <= 34.0 Gy | 0 | <= 34.0 | informative |
| LCTSC-Test-S1-101: Heart V60Gy[%] <= 33.0 Gy | 0 | <= 33.0 | informative |
| LCTSC-Test-S1-101: Heart V45Gy[%] <= 66.0 Gy | 0 | <= 66.0 | informative |
| LCTSC-Test-S1-101: Heart V40Gy[%] <= 100.0 Gy | 0 | <= 100.0 | informative |
| LCTSC-Test-S1-101: PTV D5 / D95 after normalisation (homogeneity) | 1.02 | ≤ 1.15 (informative) | informative |
| LCTSC-Test-S2-101: PTV V60Gy[%] >= 95.0 Gy | 97.95 | >= 95.0 | pass |
| LCTSC-Test-S2-101: PTV D0.03cc[Gy] <= 72.0 Gy | 61.31 | <= 72.0 | informative |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 37.0 Gy | 22.36 | <= 37.0 | pass |
| LCTSC-Test-S2-101: Lungs-GTV Dmean[Gy] <= 20.0 Gy | 9.7 | <= 20.0 | pass |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5 Gy | 0 | <= 50.5 | pass |
| LCTSC-Test-S2-101: Esophagus Dmean[Gy] <= 34.0 Gy | 0 | <= 34.0 | informative |
| LCTSC-Test-S2-101: Heart V60Gy[%] <= 33.0 Gy | 0 | <= 33.0 | informative |
| LCTSC-Test-S2-101: Heart V45Gy[%] <= 66.0 Gy | 0.11 | <= 66.0 | informative |
| LCTSC-Test-S2-101: Heart V40Gy[%] <= 100.0 Gy | 0.23 | <= 100.0 | informative |
| LCTSC-Test-S2-101: PTV D5 / D95 after normalisation (homogeneity) | 1.012 | ≤ 1.15 (informative) | informative |

## lung_sbrt_vmat — pass

- note: synthetic peripheral GTV in the right lung (radius 12 mm), PTV +5 mm, rings for the SBRT dose fall-off; FMO of the arcs' sector beams with the pb Dij, arcs by sweeping each sector's fluence, control-point doses recomputed and metersets re-optimized (R8); a research pipeline check, not a plan quality statement

| Check | Value | Target | Result |
|---|---|---|---|
| LCTSC-Test-S1-101: PTV V100%[%] >= 95.0 | 95.1 | >= 95.0 | pass |
| LCTSC-Test-S1-101: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S1-101: PTV D0.03cc[%] <= 140.0 | 121.7 | <= 140.0 | informative |
| LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 10.0 | 3.41 | <= 10.0 | informative |
| LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 21.9 | 0.08 | <= 21.9 | pass |
| LCTSC-Test-S1-101: SpinalCord D0.35cc[Gy] <= 18.0 | 0.08 | <= 18.0 | pass |
| LCTSC-Test-S1-101: SpinalCord D1.2cc[Gy] <= 12.3 | 0.08 | <= 12.3 | pass |
| LCTSC-Test-S1-101: Esophagus D0.03cc[Gy] <= 25.2 | 0.08 | <= 25.2 | pass |
| LCTSC-Test-S1-101: Esophagus D5cc[Gy] <= 17.7 | 0.07 | <= 17.7 | pass |
| LCTSC-Test-S1-101: Heart D0.03cc[Gy] <= 30.0 | 0.27 | <= 30.0 | pass |
| LCTSC-Test-S1-101: Heart D15cc[Gy] <= 24.0 | 0.22 | <= 24.0 | pass |
| LCTSC-Test-S1-101: Lungs D1500cc[Gy] <= 11.6 | 0.4 | <= 11.6 | pass |
| LCTSC-Test-S1-101: Lungs D1000cc[Gy] <= 12.4 | 0.77 | <= 12.4 | pass |
| LCTSC-Test-S1-101: Lungs V12.5Gy[cc] <= 1000.0 | 260.4 | <= 1000.0 | informative |
| LCTSC-Test-S1-101: R100 (PTV 16.0 cc) | 1 | < 1.2 (minor ≤ 1.5) | pass |
| LCTSC-Test-S1-101: R50 (PTV 16.0 cc) | 2.13 | < 4.63673 (minor ≤ 5.70509) | pass |
| LCTSC-Test-S1-101: D2cm (PTV 16.0 cc) | 53.87 | < 51.2655 (minor ≤ 59.5818) | pass |
| LCTSC-Test-S1-101: LungV20 (PTV 16.0 cc) | 3.415 | < 10 (minor ≤ 15) | pass |
| LCTSC-Test-S1-101: arcs deliverable at the machine's limits | True | True | pass |
| LCTSC-Test-S1-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 90.9 | informative | informative |
| LCTSC-Test-S1-101: second engine PTV D95, CCC / pb | 0.956 | informative | informative |
| LCTSC-Test-S1-101: second engine PTV D95, CCC / pb, body as water | 1.055 | informative | informative |
| LCTSC-Test-S2-101: PTV V100%[%] >= 95.0 | 95.18 | >= 95.0 | pass |
| LCTSC-Test-S2-101: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S2-101: PTV D0.03cc[%] <= 140.0 | 114.4 | <= 140.0 | informative |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 10.0 | 2.92 | <= 10.0 | informative |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 21.9 | 0.12 | <= 21.9 | pass |
| LCTSC-Test-S2-101: SpinalCord D0.35cc[Gy] <= 18.0 | 0.12 | <= 18.0 | pass |
| LCTSC-Test-S2-101: SpinalCord D1.2cc[Gy] <= 12.3 | 0.12 | <= 12.3 | pass |
| LCTSC-Test-S2-101: Esophagus D0.03cc[Gy] <= 25.2 | 0.17 | <= 25.2 | pass |
| LCTSC-Test-S2-101: Esophagus D5cc[Gy] <= 17.7 | 0.12 | <= 17.7 | pass |
| LCTSC-Test-S2-101: Heart D0.03cc[Gy] <= 30.0 | 0.64 | <= 30.0 | pass |
| LCTSC-Test-S2-101: Heart D15cc[Gy] <= 24.0 | 0.4 | <= 24.0 | pass |
| LCTSC-Test-S2-101: Lungs D1500cc[Gy] <= 11.6 | 0.3 | <= 11.6 | pass |
| LCTSC-Test-S2-101: Lungs D1000cc[Gy] <= 12.4 | 0.65 | <= 12.4 | pass |
| LCTSC-Test-S2-101: Lungs V12.5Gy[cc] <= 1000.0 | 207.3 | <= 1000.0 | informative |
| LCTSC-Test-S2-101: R100 (PTV 16.3 cc) | 0.988 | < 1.2 (minor ≤ 1.5) | pass |
| LCTSC-Test-S2-101: R50 (PTV 16.3 cc) | 2.404 | < 4.63059 (minor ≤ 5.69589) | pass |
| LCTSC-Test-S2-101: D2cm (PTV 16.3 cc) | 50.97 | < 51.3882 (minor ≤ 59.7352) | pass |
| LCTSC-Test-S2-101: LungV20 (PTV 16.3 cc) | 2.923 | < 10 (minor ≤ 15) | pass |
| LCTSC-Test-S2-101: arcs deliverable at the machine's limits | True | True | pass |
| LCTSC-Test-S2-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 89.8 | informative | informative |
| LCTSC-Test-S2-101: second engine PTV D95, CCC / pb | 1.018 | informative | informative |
| LCTSC-Test-S2-101: second engine PTV D95, CCC / pb, body as water | 1.074 | informative | informative |

## lung_vmat_lctsc — pass

- note: synthetic 2 cm GTV at the right lung's centroid, CTV +5 mm, PTV +5 mm (the R7 lung case), 60 Gy in 30 fractions; FMO of the arcs' sector beams with the pb Dij, arcs by sweeping each sector's fluence, control-point doses recomputed and metersets re-optimized (R8); a research pipeline check, not a plan quality statement

| Check | Value | Target | Result |
|---|---|---|---|
| LCTSC-Test-S1-101: PTV V60Gy[%] >= 95.0 | 95.57 | >= 95.0 | pass |
| LCTSC-Test-S1-101: PTV D0.03cc[Gy] <= 72.0 | 64.76 | <= 72.0 | informative |
| LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 37.0 | 16.04 | <= 37.0 | pass |
| LCTSC-Test-S1-101: Lungs-GTV Dmean[Gy] <= 20.0 | 8.26 | <= 20.0 | pass |
| LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 50.5 | 0.61 | <= 50.5 | pass |
| LCTSC-Test-S1-101: Esophagus Dmean[Gy] <= 34.0 | 0.39 | <= 34.0 | informative |
| LCTSC-Test-S1-101: Heart V60Gy[%] <= 33.0 | 0 | <= 33.0 | informative |
| LCTSC-Test-S1-101: Heart V45Gy[%] <= 66.0 | 0 | <= 66.0 | informative |
| LCTSC-Test-S1-101: Heart V40Gy[%] <= 100.0 | 0 | <= 100.0 | informative |
| LCTSC-Test-S1-101: PTV D5 / D95 (homogeneity) | 1.054 | ≤ 1.15 (informative) | informative |
| LCTSC-Test-S1-101: Paddick conformity index | 0.917 | informative | informative |
| LCTSC-Test-S1-101: arcs deliverable at the machine's limits | True | True | pass |
| LCTSC-Test-S1-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 79.5 | informative | informative |
| LCTSC-Test-S1-101: second engine PTV D95, CCC / pb | 0.861 | informative | informative |
| LCTSC-Test-S1-101: second engine PTV D95, CCC / pb, body as water | 1.048 | informative | informative |
| LCTSC-Test-S2-101: PTV V60Gy[%] >= 95.0 | 95.96 | >= 95.0 | pass |
| LCTSC-Test-S2-101: PTV D0.03cc[Gy] <= 72.0 | 65.24 | <= 72.0 | informative |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 37.0 | 15.49 | <= 37.0 | pass |
| LCTSC-Test-S2-101: Lungs-GTV Dmean[Gy] <= 20.0 | 8.12 | <= 20.0 | pass |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5 | 0.74 | <= 50.5 | pass |
| LCTSC-Test-S2-101: Esophagus Dmean[Gy] <= 34.0 | 0.52 | <= 34.0 | informative |
| LCTSC-Test-S2-101: Heart V60Gy[%] <= 33.0 | 0 | <= 33.0 | informative |
| LCTSC-Test-S2-101: Heart V45Gy[%] <= 66.0 | 0.02 | <= 66.0 | informative |
| LCTSC-Test-S2-101: Heart V40Gy[%] <= 100.0 | 0.06 | <= 100.0 | informative |
| LCTSC-Test-S2-101: PTV D5 / D95 (homogeneity) | 1.058 | ≤ 1.15 (informative) | informative |
| LCTSC-Test-S2-101: Paddick conformity index | 0.923 | informative | informative |
| LCTSC-Test-S2-101: arcs deliverable at the machine's limits | True | True | pass |
| LCTSC-Test-S2-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 84.1 | informative | informative |
| LCTSC-Test-S2-101: second engine PTV D95, CCC / pb | 0.936 | informative | informative |
| LCTSC-Test-S2-101: second engine PTV D95, CCC / pb, body as water | 1.055 | informative | informative |

## pb_vs_ccc — pass


| Check | Value | Target | Result |
|---|---|---|---|
| water 10 x 10, 5 mm beamlets: gamma 3 %/3 mm pb vs CCC, absolute (%) | 98.99 | ≥ 95.0 | informative |
| water 10 x 10, 10 mm beamlets: gamma 3 %/3 mm pb vs CCC, absolute (%) | 95.63 | ≥ 95.0 | pass |
| pb PDD10 change from 5 to 10 mm beamlets (points) | 0 | ≤ 0.5 | pass |
| CCC PDD10 change from 5 to 10 mm beamlets (points) | 2.67 | informative | informative |
| dose at 10 cm, 4 x 4 over 10 x 10: CCC / pb | 1 | 0.907 (pb) | informative |
| dose at 10 cm, 6 x 6 over 10 x 10: CCC / pb | 1 | 0.947 (pb) | informative |
| isocenter 60 mm toward +x: dose(gantry 90) / dose(gantry 270), CCC | 1.706 | 1.647 ± 5 % (pb), > 1 | pass |

## pb_vs_mc — pass

- note: water_10x10: MC 5.00e+07 primaries
- note: lung_slab: MC 5.00e+07 primaries
- note: bone_slab: MC 5.00e+07 primaries
- note: lung_slab_2x2: MC 5.00e+07 primaries; 5 mm beamlets for CCC
- note: pb kernel f046d6a503757f17 from pencil_6mv.npz (3.0e+07 primaries); the same Mohan 6 MV spectrum as the references

| Check | Value | Target | Result |
|---|---|---|---|
| water_10x10: PDD10 pb vs MC (%) | 67.91 | 68.0 ± 2.0 (MC) | pass |
| water_10x10: d_max pb vs MC (mm) | 16.25 | 13.8 (MC) | informative |
| water_10x10: CAX dose at 50 mm, pb / MC | 1.013 | 1 ± 0.02 | pass |
| water_10x10: CAX dose at 150 mm, pb / MC | 1.012 | 1 ± 0.02 | pass |
| water_10x10: CAX dose at 200 mm, pb / MC | 1.009 | 1 ± 0.02 | pass |
| water_10x10: CAX dose at 250 mm, pb / MC | 0.9992 | 1 ± 0.02 | pass |
| water_10x10: penumbra 80-20 % at 10 cm, pb (mm) | 5.926 | 5.9 ± 2.5 (MC) | pass |
| water_10x10: off-axis ratio at 40 mm, 10 cm depth | 0.9669 | 0.960 ± 0.03 (MC) | pass |
| water_10x10: dose 2 cm outside the field edge at 10 cm (% of CAX) | 4.79 | 5.12 ± 1 (MC) | pass |
| water_10x10: gamma 3 %/3 mm pass rate (%) | 99.71 | ≥ 95.0 | pass |
| lung_slab: correction factor at 20 mm, pb vs MC | 1.001 | 0.983 ± 0.030 (MC) | pass |
| lung_slab: correction factor at 50 mm, pb vs MC | 1.013 | 1.002 ± 0.030 (MC) | pass |
| lung_slab: correction factor at 80 mm, pb vs MC | 1.082 | 1.063 ± 0.032 (MC) | pass |
| lung_slab: correction factor at 130 mm, pb vs MC | 1.232 | 1.201 ± 0.036 (MC) | pass |
| lung_slab: correction factor at 200 mm, pb vs MC | 1.259 | 1.245 ± 0.037 (MC) | pass |
| lung_slab: correction factor at 250 mm, pb vs MC | 1.269 | 1.246 ± 0.037 (MC) | pass |
| bone_slab: correction factor at 20 mm, pb vs MC | 1 | 1.002 ± 0.030 (MC) | pass |
| bone_slab: correction factor at 45 mm, pb vs MC | 0.9664 | 0.981 ± 0.029 (MC) | pass |
| bone_slab: correction factor at 80 mm, pb vs MC | 0.9146 | 0.941 ± 0.028 (MC) | pass |
| bone_slab: correction factor at 150 mm, pb vs MC | 0.9065 | 0.919 ± 0.028 (MC) | pass |
| bone_slab: correction factor at 200 mm, pb vs MC | 0.9038 | 0.904 ± 0.027 (MC) | pass |
| bone_slab: correction factor at 250 mm, pb vs MC | 0.9024 | 0.900 ± 0.027 (MC) | pass |
| 4x4 over 10x10, dose at 10 cm, pb vs MC | 0.9064 | 0.895 ± 0.018 (MC) | pass |
| 4x4 over 10x10, dose at 10 cm, CCC vs MC | 1 | 0.895 (MC) | informative |
| 20x20 over 10x10, dose at 10 cm, pb vs MC | 1.064 | 1.058 ± 0.021 (MC) | pass |
| 20x20 over 10x10, dose at 10 cm, CCC vs MC | 1 | 1.058 (MC) | informative |
| 2x2 in lung: dose at 50 mm (in the lung) over 20 mm, pb / MC | 0.986 | 1 ± 0.03 | pass |
| 2x2 in lung: dose at 50 mm (in the lung) over 20 mm, ccc / MC | 1.013 | informative | informative |
| 2x2 in lung: dose at 80 mm (in the lung) over 20 mm, pb / MC | 1.014 | 1 ± 0.03 | pass |
| 2x2 in lung: dose at 80 mm (in the lung) over 20 mm, ccc / MC | 0.92 | informative | informative |
| 2x2 in lung: dose at 100 mm (in the lung) over 20 mm, pb / MC | 1.02 | 1 ± 0.03 | pass |
| 2x2 in lung: dose at 100 mm (in the lung) over 20 mm, ccc / MC | 0.921 | informative | informative |
| 2x2 in lung: dose at 150 mm (beyond the lung) over 20 mm, pb / MC | 0.999 | 1 ± 0.03 | pass |
| 2x2 in lung: dose at 150 mm (beyond the lung) over 20 mm, ccc / MC | 1.103 | informative | informative |

## photon_heterogeneity_slabs — info


| Check | Value | Target | Result |
|---|---|---|---|
| lung_slab: dose / water-equivalent expectation at 150 mm | 0.9878 | 1 ± 0.05 (effective path length + inverse square) | informative |
| lung_slab: dose / water-equivalent expectation at 200 mm | 0.9993 | 1 ± 0.05 (effective path length + inverse square) | informative |
| lung_slab: dose / water-equivalent expectation at 250 mm | 1.007 | 1 ± 0.05 (effective path length + inverse square) | informative |
| bone_slab: dose / water-equivalent expectation at 150 mm | 0.9769 | 1 ± 0.05 (effective path length + inverse square) | informative |
| bone_slab: dose / water-equivalent expectation at 200 mm | 0.9764 | 1 ± 0.05 (effective path length + inverse square) | informative |
| bone_slab: dose / water-equivalent expectation at 250 mm | 0.9953 | 1 ± 0.05 (effective path length + inverse square) | informative |

## photon_output_vs_field — info


| Check | Value | Target | Result |
|---|---|---|---|
| output factor 4x4 vs 10x10 | 1 | 0.904 measured (phantom scatter only here) | informative |
| output factor 20x20 vs 10x10 | 1 | 1.067 measured (phantom scatter only here) | informative |
| output factor 30x30 vs 10x10 | 1 | 1.102 measured (phantom scatter only here) | informative |

## photon_output_vs_field_pb — info


| Check | Value | Target | Result |
|---|---|---|---|
| output factor 4x4 vs 10x10 | 0.984 | 0.904 measured (phantom scatter only here) | informative |
| output factor 20x20 vs 10x10 | 1.017 | 1.067 measured (phantom scatter only here) | informative |
| output factor 30x30 vs 10x10 | 1.028 | 1.102 measured (phantom scatter only here) | informative |

## photon_pdd_10x10 — pass


| Check | Value | Target | Result |
|---|---|---|---|
| PDD10 (%) | 65.63 | 66.1 ± 1.5 | pass |
| d_max (mm) | 16.25 | 12.0–25.0 | pass |
| PDD20/PDD10 | 0.5516 | 0.58 ± 0.02 | informative |
| dose at d_max per MU (Gy) | 0.01 | 0.010 ± 0.0005 (calibration definition) | pass |

## photon_pdd_10x10_pb — pass


| Check | Value | Target | Result |
|---|---|---|---|
| PDD10 (%) | 67.45 | 66.1 ± 1.5 | informative |
| d_max (mm) | 16.25 | 12.0–25.0 | pass |
| PDD20/PDD10 | 0.5741 | 0.58 ± 0.02 | informative |
| dose at d_max per MU (Gy) | 0.009987 | 0.010 ± 0.0005 (calibration definition) | pass |

## photon_profile_10x10 — pass


| Check | Value | Target | Result |
|---|---|---|---|
| flatness (%) | 0.5666 | ≤ 3.0 | pass |
| symmetry (%) | 0.9457 | ≤ 2.0 | pass |
| penumbra 80–20 % (mm) | 5.321 | 7.0 ± 3.0 | informative |

## photon_profile_10x10_pb — pass


| Check | Value | Target | Result |
|---|---|---|---|
| flatness (%) | 1.684 | ≤ 3.0 | pass |
| symmetry (%) | 2.059e-05 | ≤ 2.0 | pass |
| penumbra 80–20 % (mm) | 5.926 | 7.0 ± 3.0 | informative |

## photon_vs_mc — fail

- note: [shipped] water_10x10: MC 5.00e+07 primaries, relative uncertainty 1.5 % on the axis at 10 cm
- note: [shipped] lung_slab: MC 5.00e+07 primaries, relative uncertainty 1.6 % on the axis at 10 cm
- note: [shipped] bone_slab: MC 5.00e+07 primaries, relative uncertainty 1.5 % on the axis at 10 cm
- note: [full] water_10x10: MC 5.00e+07 primaries, relative uncertainty 1.5 % on the axis at 10 cm
- note: [full] lung_slab: MC 5.00e+07 primaries, relative uncertainty 1.6 % on the axis at 10 cm
- note: [full] bone_slab: MC 5.00e+07 primaries, relative uncertainty 1.5 % on the axis at 10 cm
- note: the Monte Carlo beam carries the spectrum of the CCC kernels (Mohan 6 MV, mean 1.90 MeV; kernel fluence mean 1.89 MeV), so the comparison is transport in the phantom

| Check | Value | Target | Result |
|---|---|---|---|
| [shipped] water_10x10: PDD10 CCC vs MC (%) | 68.07 | 68.0 ± 2.0 (MC) | pass |
| [shipped] water_10x10: d_max CCC vs MC (mm) | 21.25 | 13.8 (MC) | informative |
| [shipped] water_10x10: CAX dose at 50 mm, CCC / MC | 1.01 | 1 ± 0.02 | pass |
| [shipped] water_10x10: CAX dose at 150 mm, CCC / MC | 0.9791 | 1 ± 0.02 | FAIL |
| [shipped] water_10x10: CAX dose at 200 mm, CCC / MC | 0.9537 | 1 ± 0.02 | FAIL |
| [shipped] water_10x10: CAX dose at 250 mm, CCC / MC | 0.9312 | 1 ± 0.02 | FAIL |
| [shipped] water_10x10: penumbra 80-20 % at 10 cm, CCC (mm) | 5.835 | 5.9 ± 2.5 (MC) | pass |
| [shipped] water_10x10: off-axis ratio at 40 mm, 10 cm depth | 0.9767 | 0.960 ± 0.03 (MC) | pass |
| [shipped] water_10x10: gamma 3 %/3 mm pass rate (%) | 98 | ≥ 95.0 | pass |
| [shipped] lung_slab: correction factor at 20 mm, CCC vs MC | 0.998 | 0.983 ± 0.030 (MC) | pass |
| [shipped] lung_slab: correction factor at 50 mm, CCC vs MC | 1.008 | 1.002 ± 0.030 (MC) | pass |
| [shipped] lung_slab: correction factor at 80 mm, CCC vs MC | 1.008 | 1.063 ± 0.032 (MC) | FAIL |
| [shipped] lung_slab: correction factor at 130 mm, CCC vs MC | 1.215 | 1.201 ± 0.036 (MC) | pass |
| [shipped] lung_slab: correction factor at 200 mm, CCC vs MC | 1.294 | 1.245 ± 0.037 (MC) | FAIL |
| [shipped] lung_slab: correction factor at 250 mm, CCC vs MC | 1.293 | 1.246 ± 0.037 (MC) | FAIL |
| [shipped] bone_slab: correction factor at 20 mm, CCC vs MC | 0.9999 | 1.002 ± 0.030 (MC) | pass |
| [shipped] bone_slab: correction factor at 45 mm, CCC vs MC | 0.9891 | 0.981 ± 0.029 (MC) | pass |
| [shipped] bone_slab: correction factor at 80 mm, CCC vs MC | 0.9291 | 0.941 ± 0.028 (MC) | pass |
| [shipped] bone_slab: correction factor at 150 mm, CCC vs MC | 0.8949 | 0.919 ± 0.028 (MC) | pass |
| [shipped] bone_slab: correction factor at 200 mm, CCC vs MC | 0.9037 | 0.904 ± 0.027 (MC) | pass |
| [shipped] bone_slab: correction factor at 250 mm, CCC vs MC | 0.9019 | 0.900 ± 0.027 (MC) | pass |
| [full] water_10x10: PDD10 CCC vs MC (%) | 71.42 | 68.0 ± 2.0 (MC) | FAIL |
| [full] water_10x10: d_max CCC vs MC (mm) | 21.25 | 13.8 (MC) | informative |
| [full] water_10x10: CAX dose at 50 mm, CCC / MC | 0.9901 | 1 ± 0.02 | pass |
| [full] water_10x10: CAX dose at 150 mm, CCC / MC | 1.052 | 1 ± 0.02 | FAIL |
| [full] water_10x10: CAX dose at 200 mm, CCC / MC | 1.1 | 1 ± 0.02 | FAIL |
| [full] water_10x10: CAX dose at 250 mm, CCC / MC | 1.124 | 1 ± 0.02 | FAIL |
| [full] water_10x10: penumbra 80-20 % at 10 cm, CCC (mm) | 6.609 | 5.9 ± 2.5 (MC) | pass |
| [full] water_10x10: off-axis ratio at 40 mm, 10 cm depth | 0.9688 | 0.960 ± 0.03 (MC) | pass |
| [full] water_10x10: gamma 3 %/3 mm pass rate (%) | 78.32 | ≥ 95.0 | FAIL |
| [full] lung_slab: correction factor at 20 mm, CCC vs MC | 0.9955 | 0.983 ± 0.030 (MC) | pass |
| [full] lung_slab: correction factor at 50 mm, CCC vs MC | 1.005 | 1.002 ± 0.030 (MC) | pass |
| [full] lung_slab: correction factor at 80 mm, CCC vs MC | 1.053 | 1.063 ± 0.032 (MC) | pass |
| [full] lung_slab: correction factor at 130 mm, CCC vs MC | 1.164 | 1.201 ± 0.036 (MC) | FAIL |
| [full] lung_slab: correction factor at 200 mm, CCC vs MC | 1.184 | 1.245 ± 0.037 (MC) | FAIL |
| [full] lung_slab: correction factor at 250 mm, CCC vs MC | 1.193 | 1.246 ± 0.037 (MC) | FAIL |
| [full] bone_slab: correction factor at 20 mm, CCC vs MC | 1.003 | 1.002 ± 0.030 (MC) | pass |
| [full] bone_slab: correction factor at 45 mm, CCC vs MC | 0.9989 | 0.981 ± 0.029 (MC) | pass |
| [full] bone_slab: correction factor at 80 mm, CCC vs MC | 0.9453 | 0.941 ± 0.028 (MC) | pass |
| [full] bone_slab: correction factor at 150 mm, CCC vs MC | 0.9274 | 0.919 ± 0.028 (MC) | pass |
| [full] bone_slab: correction factor at 200 mm, CCC vs MC | 0.9307 | 0.904 ± 0.027 (MC) | pass |
| [full] bone_slab: correction factor at 250 mm, CCC vs MC | 0.9215 | 0.900 ± 0.027 (MC) | pass |

## photon_vs_pyradplan — info

- note: water_10x10: pyRadPlan 0.5.0, pyRadPlan photon pencil beam (SVD kernels), machine Generic, 81 bixels of 10.0 mm (its bixels are centred on the axis, so the field is 9 x 9 cm at the isocenter and 10 x 10 cm at the 10 cm normalisation depth; the ~1 % scatter difference is inside the tolerance); CCC scatter 'shipped'
- note: lung_slab: pyRadPlan 0.5.0, pyRadPlan photon pencil beam (SVD kernels), machine Generic, 81 bixels of 10.0 mm (its bixels are centred on the axis, so the field is 9 x 9 cm at the isocenter and 10 x 10 cm at the 10 cm normalisation depth; the ~1 % scatter difference is inside the tolerance); CCC scatter 'shipped'
- note: bone_slab: pyRadPlan 0.5.0, pyRadPlan photon pencil beam (SVD kernels), machine Generic, 81 bixels of 10.0 mm (its bixels are centred on the axis, so the field is 9 x 9 cm at the isocenter and 10 x 10 cm at the 10 cm normalisation depth; the ~1 % scatter difference is inside the tolerance); CCC scatter 'shipped'
- note: informative: pyRadPlan's generic photon machine is a different beam from the kernels' spectrum (its water PDD10 is about 3.5 points below the Monte Carlo reference's), so the Monte Carlo case, not this one, judges the CCC engine

| Check | Value | Target | Result |
|---|---|---|---|
| water_10x10: PDD10 CCC vs pyRadPlan (%) | 68.26 | 64.6 ± 3.0 (pyRadPlan pencil beam) | informative |
| water_10x10: CAX dose at 50 mm, CCC / pyRadPlan | 0.9814 | 1 ± 0.03 | informative |
| water_10x10: CAX dose at 150 mm, CCC / pyRadPlan | 0.963 | 1 ± 0.03 | informative |
| water_10x10: CAX dose at 200 mm, CCC / pyRadPlan | 0.8951 | 1 ± 0.03 | informative |
| water_10x10: CAX dose at 250 mm, CCC / pyRadPlan | 0.9033 | 1 ± 0.03 | informative |
| lung_slab: CAX dose at 50 mm, CCC / pyRadPlan | 1.112 | 1 ± 0.03 | informative |
| lung_slab: CAX dose at 150 mm, CCC / pyRadPlan | 1.091 | 1 ± 0.03 | informative |
| lung_slab: CAX dose at 200 mm, CCC / pyRadPlan | 1.131 | 1 ± 0.03 | informative |
| lung_slab: CAX dose at 250 mm, CCC / pyRadPlan | 1.051 | 1 ± 0.03 | informative |
| bone_slab: CAX dose at 50 mm, CCC / pyRadPlan | 0.9861 | 1 ± 0.03 | informative |
| bone_slab: CAX dose at 150 mm, CCC / pyRadPlan | 0.9094 | 1 ± 0.03 | informative |
| bone_slab: CAX dose at 200 mm, CCC / pyRadPlan | 0.8782 | 1 ± 0.03 | informative |
| bone_slab: CAX dose at 250 mm, CCC / pyRadPlan | 0.8889 | 1 ± 0.03 | informative |

## proton_bragg_peak — pass

- note: MCsquare through radiarch's driver, water-only calibration, 400000 primaries per spot, seed fixed

| Check | Value | Target | Result |
|---|---|---|---|
| distal 80-20 % fall-off at 100 MeV (mm) | 1.832 | 2.1 ± 1.0 (Bortfeld straggling + BDL energy spread 0.67 %) | pass |
| IDD peak-to-entrance at 100 MeV | 4.698 | 3-5 (informative) | informative |
| entrance core sigma x at 100 MeV (mm) | 4.957 | 4.92 ± 0.50 (BDL SpotSize1x propagated 410 mm to the isocenter) | pass |
| entrance core sigma y at 100 MeV (mm) | 5.607 | 5.52 ± 0.55 (BDL SpotSize1y propagated 410 mm to the isocenter) | pass |
| lateral sigma x at 0.8 R80 (62 mm) for 100 MeV (mm) | 6.905 | informative (multiple Coulomb scattering grows it to several mm) | informative |
| distal 80-20 % fall-off at 150 MeV (mm) | 3.338 | 4.0 ± 1.2 (Bortfeld straggling + BDL energy spread 0.63 %) | pass |
| IDD peak-to-entrance at 150 MeV | 4.388 | 3-5 (informative) | informative |
| entrance core sigma x at 150 MeV (mm) | 3.578 | 3.53 ± 0.50 (BDL SpotSize1x propagated 410 mm to the isocenter) | pass |
| entrance core sigma y at 150 MeV (mm) | 3.808 | 3.82 ± 0.50 (BDL SpotSize1y propagated 410 mm to the isocenter) | pass |
| lateral sigma x at 0.8 R80 (127 mm) for 150 MeV (mm) | 6.991 | informative (multiple Coulomb scattering grows it to several mm) | informative |
| distal 80-20 % fall-off at 200 MeV (mm) | 4.529 | 5.5 ± 1.6 (Bortfeld straggling + BDL energy spread 0.44 %) | pass |
| IDD peak-to-entrance at 200 MeV | 4.082 | 3-5 (informative) | informative |
| entrance core sigma x at 200 MeV (mm) | 2.653 | 2.61 ± 0.50 (BDL SpotSize1x propagated 410 mm to the isocenter) | pass |
| entrance core sigma y at 200 MeV (mm) | 2.806 | 2.82 ± 0.50 (BDL SpotSize1y propagated 410 mm to the isocenter) | pass |
| lateral sigma x at 0.8 R80 (209 mm) for 200 MeV (mm) | 7.73 | informative (multiple Coulomb scattering grows it to several mm) | informative |
| distal 80-20 % fall-off at 225 MeV (mm) | 4.965 | 5.7 ± 1.7 (Bortfeld straggling + BDL energy spread 0.27 %) | pass |
| IDD peak-to-entrance at 225 MeV | 3.897 | 3-5 (informative) | informative |
| entrance core sigma x at 225 MeV (mm) | 2.935 | 3.10 ± 0.50 (BDL SpotSize1x propagated 410 mm to the isocenter) | pass |
| entrance core sigma y at 225 MeV (mm) | 3.079 | 3.14 ± 0.50 (BDL SpotSize1y propagated 410 mm to the isocenter) | pass |
| lateral sigma x at 0.8 R80 (255 mm) for 225 MeV (mm) | 8.544 | informative (multiple Coulomb scattering grows it to several mm) | informative |

## proton_range_water — pass

- note: radiarch's MCsquare driver (R14) with the water-only calibration; seed fixed, all threads

| Check | Value | Target | Result |
|---|---|---|---|
| R80 at 100 MeV (mm) | 77.55 | 77.2 ± 1.8 | pass |
| R80 at 150 MeV (mm) | 158.7 | 157.7 ± 2.6 | pass |
| R80 at 200 MeV (mm) | 261 | 259.6 ± 3.6 | pass |
| R80 at 225 MeV (mm) | 319.1 | 317.4 ± 4.2 | pass |

## tg119_planning — pass

- note: fluence-level plans (open-field beamlets, CCC shipped-scatter Dij, L-BFGS-B); TG-119 institutional results are deliverable plans, so the comparison with their means is informative; the goals are graded

| Check | Value | Target | Result |
|---|---|---|---|
| c_shape_easy: OuterTarget D95 (Gy) | 50.1 | >= 50.0 (or >= 49.78: institutional mean 50.11 ± 2 SD) | pass |
| c_shape_easy: OuterTarget D10 (Gy) | 51.25 | <= 55.0 (or <= 61.42: institutional mean 57.02 ± 2 SD) | pass |
| c_shape_easy: Core D5 (Gy) | 24.55 | <= 25.0 | pass |
| c_shape_hard: OuterTarget D95 (Gy) | 50.1 | >= 50.0 (or >= 49.78: institutional mean 50.11 ± 2 SD) | pass |
| c_shape_hard: OuterTarget D10 (Gy) | 53.86 | <= 55.0 (or <= 61.42: institutional mean 57.02 ± 2 SD) | pass |
| c_shape_hard: Core D5 (Gy) | 10.19 | <= 10.0 (or <= 22.44: institutional mean 16.3 ± 2 SD) | pass |
| prostate: PTV D95 (Gy) | 75.75 | >= 75.6 (or >= 75.24: institutional mean 75.66 ± 2 SD) | pass |
| prostate: PTV D5 (Gy) | 78.82 | <= 83.0 (or <= 84.55: institutional mean 81.43 ± 2 SD) | pass |
| prostate: Rectum D30 (Gy) | 62.9 | <= 70.0 (or <= 71.30: institutional mean 65.36 ± 2 SD) | pass |
| prostate: Rectum D10 (Gy) | 70.75 | <= 75.0 (or <= 76.03: institutional mean 73.03 ± 2 SD) | pass |
| prostate: Urinary bladder D30 (Gy) | 41.12 | <= 70.0 | pass |
| prostate: Urinary bladder D10 (Gy) | 63.75 | <= 75.0 (or <= 78.99: institutional mean 62.69 ± 2 SD) | pass |
| head_neck: PTV D90 (Gy) | 50.1 | >= 50.0 (or >= 49.12: institutional mean 50.28 ± 2 SD) | pass |
| head_neck: PTV D99 (Gy) | 48.01 | >= 46.5 (or >= 46.00: institutional mean 47.04 ± 2 SD) | pass |
| head_neck: PTV D20 (Gy) | 50.69 | <= 55.0 | pass |
| head_neck: Cord Dmax (Gy) | 36.08 | <= 40.0 (or <= 42.41: institutional mean 37.41 ± 2 SD) | pass |
| head_neck: Lt Parotid D50 (Gy) | 15.64 | <= 20.0 (or <= 21.66: institutional mean 17.98 ± 2 SD) | pass |
| head_neck: Rt Parotid D50 (Gy) | 18.93 | <= 20.0 (or <= 21.66: institutional mean 17.98 ± 2 SD) | pass |
| multi_target: Center D99 (Gy) | 50.1 | >= 50.0 (or >= 46.31: institutional mean 49.55 ± 2 SD) | pass |
| multi_target: Center D10 (Gy) | 53.29 | <= 53.0 (or <= 58.01: institutional mean 54.55 ± 2 SD) | pass |
| multi_target: Superior D99 (Gy) | 28.43 | >= 25.0 (or >= 23.46: institutional mean 25.16 ± 2 SD) | pass |
| multi_target: Superior D10 (Gy) | 30.73 | <= 35.0 (or <= 40.20: institutional mean 34.12 ± 2 SD) | pass |
| multi_target: Inferiorr D99 (Gy) | 17.04 | >= 12.5 (or >= 10.37: institutional mean 14.07 ± 2 SD) | pass |
| multi_target: Inferiorr D10 (Gy) | 19.39 | <= 25.0 (or <= 29.62: institutional mean 24.18 ± 2 SD) | pass |
