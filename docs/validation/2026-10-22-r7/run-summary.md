# Radiarch validation run 20261022-150018 (20fc3bf)

RESEARCH USE ONLY. NOT FOR CLINICAL USE. Radiarch is a research treatment-planning system; its plans, doses and evaluations must not be used to treat patients.

| Case | Status | Time (s) | Checks |
|---|---|---|---|
| dij_consistency | **pass** | 531.3 | 6 pass, 0 fail, 0 informative |
| dvh_crosscheck_pancreatic | **fail** | 258.5 | 47 pass, 3 fail, 19 informative |
| gamma_crosscheck_synthetic | **pass** | 5.6 | 4 pass, 0 fail, 0 informative |
| geometry_volumes_lctsc | **fail** | 127.2 | 29 pass, 1 fail, 0 informative |
| lung_e2e_lctsc | **pass** | 395.5 | 2 pass, 0 fail, 4 informative |
| photon_heterogeneity_slabs | **info** | 123.8 | 0 pass, 0 fail, 6 informative |
| photon_output_vs_field | **info** | 625.2 | 0 pass, 0 fail, 3 informative |
| photon_pdd_10x10 | **pass** | 41.4 | 3 pass, 0 fail, 1 informative |
| photon_profile_10x10 | **pass** | 41.3 | 2 pass, 0 fail, 1 informative |
| photon_vs_mc | **fail** | 14.0 | 26 pass, 14 fail, 2 informative |
| photon_vs_pyradplan | **info** | 0.4 | 0 pass, 0 fail, 13 informative |
| proton_bragg_peak | **pass** | 8.1 | 12 pass, 0 fail, 8 informative |
| proton_range_water | **pass** | 3.6 | 4 pass, 0 fail, 0 informative |
| tg119_planning | **pass** | 2682.8 | 24 pass, 0 fail, 0 informative |

## dij_consistency — pass


| Check | Value | Target | Result |
|---|---|---|---|
| ccc: integral ratio Dij·w / forward | 1 | 1 ± 0.0001 | pass |
| ccc: correlation above 1 % of max | 1 | ≥ 0.9999 | pass |
| ccc: high-dose (≥ 50 % of max) p95 relative error | 1.182e-07 | ≤ 0.001 | pass |
| mcsquare: integral ratio Dij·w / forward | 0.9808 | 1 ± 0.05 | pass |
| mcsquare: correlation above 1 % of max | 0.9978 | ≥ 0.95 | pass |
| mcsquare: high-dose (≥ 50 % of max) p95 relative error | 0.07332 | ≤ 0.15 | pass |

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

## lung_e2e_lctsc — pass

- note: synthetic 2 cm GTV at the right lung's centroid, CTV +5 mm, PTV +5 mm; 7 coplanar open-field beam models, CCC shipped-scatter Dij, L-BFGS-B; goals from the RTOG 0617 template; a research pipeline check, not a plan quality statement

| Check | Value | Target | Result |
|---|---|---|---|
| LCTSC-Test-S1-101: PTV V60Gy[%] >= 95.0 Gy | 97.45 | >= 95.0 | pass |
| LCTSC-Test-S1-101: PTV D0.03cc[Gy] <= 72.0 Gy | 61.94 | <= 72.0 | informative |
| LCTSC-Test-S1-101: PTV D5 / D95 after normalisation (homogeneity) | 1.02 | ≤ 1.15 (informative) | informative |
| LCTSC-Test-S2-101: PTV V60Gy[%] >= 95.0 Gy | 97.98 | >= 95.0 | pass |
| LCTSC-Test-S2-101: PTV D0.03cc[Gy] <= 72.0 Gy | 61.33 | <= 72.0 | informative |
| LCTSC-Test-S2-101: PTV D5 / D95 after normalisation (homogeneity) | 1.012 | ≤ 1.15 (informative) | informative |

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

## photon_pdd_10x10 — pass


| Check | Value | Target | Result |
|---|---|---|---|
| PDD10 (%) | 65.63 | 66.1 ± 1.5 | pass |
| d_max (mm) | 16.25 | 12.0–25.0 | pass |
| PDD20/PDD10 | 0.5516 | 0.58 ± 0.02 | informative |
| dose at d_max per MU (Gy) | 0.01 | 0.010 ± 0.0005 (calibration definition) | pass |

## photon_profile_10x10 — pass


| Check | Value | Target | Result |
|---|---|---|---|
| flatness (%) | 0.5666 | ≤ 3.0 | pass |
| symmetry (%) | 0.9457 | ≤ 2.0 | pass |
| penumbra 80–20 % (mm) | 5.321 | 7.0 ± 3.0 | informative |

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
| distal 80-20 % fall-off at 100 MeV (mm) | 1.833 | 2.1 ± 1.0 (Bortfeld straggling + BDL energy spread 0.67 %) | pass |
| IDD peak-to-entrance at 100 MeV | 4.697 | 3-5 (informative) | informative |
| entrance core sigma x at 100 MeV (mm) | 4.951 | 4.92 ± 0.50 (BDL SpotSize1x propagated 410 mm to the isocenter) | pass |
| entrance core sigma y at 100 MeV (mm) | 5.601 | 5.52 ± 0.55 (BDL SpotSize1y propagated 410 mm to the isocenter) | pass |
| lateral sigma x at 0.8 R80 (62 mm) for 100 MeV (mm) | 6.905 | informative (multiple Coulomb scattering grows it to several mm) | informative |
| distal 80-20 % fall-off at 150 MeV (mm) | 3.339 | 4.0 ± 1.2 (Bortfeld straggling + BDL energy spread 0.63 %) | pass |
| IDD peak-to-entrance at 150 MeV | 4.388 | 3-5 (informative) | informative |
| entrance core sigma x at 150 MeV (mm) | 3.573 | 3.53 ± 0.50 (BDL SpotSize1x propagated 410 mm to the isocenter) | pass |
| entrance core sigma y at 150 MeV (mm) | 3.814 | 3.82 ± 0.50 (BDL SpotSize1y propagated 410 mm to the isocenter) | pass |
| lateral sigma x at 0.8 R80 (127 mm) for 150 MeV (mm) | 6.994 | informative (multiple Coulomb scattering grows it to several mm) | informative |
| distal 80-20 % fall-off at 200 MeV (mm) | 4.531 | 5.5 ± 1.6 (Bortfeld straggling + BDL energy spread 0.44 %) | pass |
| IDD peak-to-entrance at 200 MeV | 4.081 | 3-5 (informative) | informative |
| entrance core sigma x at 200 MeV (mm) | 2.655 | 2.61 ± 0.50 (BDL SpotSize1x propagated 410 mm to the isocenter) | pass |
| entrance core sigma y at 200 MeV (mm) | 2.805 | 2.82 ± 0.50 (BDL SpotSize1y propagated 410 mm to the isocenter) | pass |
| lateral sigma x at 0.8 R80 (209 mm) for 200 MeV (mm) | 7.734 | informative (multiple Coulomb scattering grows it to several mm) | informative |
| distal 80-20 % fall-off at 225 MeV (mm) | 4.968 | 5.7 ± 1.7 (Bortfeld straggling + BDL energy spread 0.27 %) | pass |
| IDD peak-to-entrance at 225 MeV | 3.896 | 3-5 (informative) | informative |
| entrance core sigma x at 225 MeV (mm) | 2.94 | 3.10 ± 0.50 (BDL SpotSize1x propagated 410 mm to the isocenter) | pass |
| entrance core sigma y at 225 MeV (mm) | 3.095 | 3.14 ± 0.50 (BDL SpotSize1y propagated 410 mm to the isocenter) | pass |
| lateral sigma x at 0.8 R80 (255 mm) for 225 MeV (mm) | 8.539 | informative (multiple Coulomb scattering grows it to several mm) | informative |

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
| c_shape_easy: OuterTarget D10 (Gy) | 51.24 | <= 55.0 (or <= 61.42: institutional mean 57.02 ± 2 SD) | pass |
| c_shape_easy: Core D5 (Gy) | 24.55 | <= 25.0 | pass |
| c_shape_hard: OuterTarget D95 (Gy) | 50.1 | >= 50.0 (or >= 49.78: institutional mean 50.11 ± 2 SD) | pass |
| c_shape_hard: OuterTarget D10 (Gy) | 53.85 | <= 55.0 (or <= 61.42: institutional mean 57.02 ± 2 SD) | pass |
| c_shape_hard: Core D5 (Gy) | 10.17 | <= 10.0 (or <= 22.44: institutional mean 16.3 ± 2 SD) | pass |
| prostate: PTV D95 (Gy) | 75.75 | >= 75.6 (or >= 75.24: institutional mean 75.66 ± 2 SD) | pass |
| prostate: PTV D5 (Gy) | 78.59 | <= 83.0 (or <= 84.55: institutional mean 81.43 ± 2 SD) | pass |
| prostate: Rectum D30 (Gy) | 62.56 | <= 70.0 (or <= 71.30: institutional mean 65.36 ± 2 SD) | pass |
| prostate: Rectum D10 (Gy) | 70.57 | <= 75.0 (or <= 76.03: institutional mean 73.03 ± 2 SD) | pass |
| prostate: Urinary bladder D30 (Gy) | 40.75 | <= 70.0 | pass |
| prostate: Urinary bladder D10 (Gy) | 62.41 | <= 75.0 (or <= 78.99: institutional mean 62.69 ± 2 SD) | pass |
| head_neck: PTV D90 (Gy) | 50.1 | >= 50.0 (or >= 49.12: institutional mean 50.28 ± 2 SD) | pass |
| head_neck: PTV D99 (Gy) | 48.03 | >= 46.5 (or >= 46.00: institutional mean 47.04 ± 2 SD) | pass |
| head_neck: PTV D20 (Gy) | 50.69 | <= 55.0 | pass |
| head_neck: Cord Dmax (Gy) | 36.08 | <= 40.0 (or <= 42.41: institutional mean 37.41 ± 2 SD) | pass |
| head_neck: Lt Parotid D50 (Gy) | 15.55 | <= 20.0 (or <= 21.66: institutional mean 17.98 ± 2 SD) | pass |
| head_neck: Rt Parotid D50 (Gy) | 18.96 | <= 20.0 (or <= 21.66: institutional mean 17.98 ± 2 SD) | pass |
| multi_target: Center D99 (Gy) | 50.1 | >= 50.0 (or >= 46.31: institutional mean 49.55 ± 2 SD) | pass |
| multi_target: Center D10 (Gy) | 53.39 | <= 53.0 (or <= 58.01: institutional mean 54.55 ± 2 SD) | pass |
| multi_target: Superior D99 (Gy) | 28.39 | >= 25.0 (or >= 23.46: institutional mean 25.16 ± 2 SD) | pass |
| multi_target: Superior D10 (Gy) | 30.79 | <= 35.0 (or <= 40.20: institutional mean 34.12 ± 2 SD) | pass |
| multi_target: Inferiorr D99 (Gy) | 17.09 | >= 12.5 (or >= 10.37: institutional mean 14.07 ± 2 SD) | pass |
| multi_target: Inferiorr D10 (Gy) | 19.44 | <= 25.0 (or <= 29.62: institutional mean 24.18 ± 2 SD) | pass |
