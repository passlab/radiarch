# Radiarch validation run 20261112-133523-0228ec6 + 20261112-132750-0228ec6 + 20261112-132735-0228ec6 + 20261112-132636-0228ec6 + 20261112-132643-0228ec6 + 20261112-133125-0228ec6 + 20261112-135033-0228ec6 + 20261112-152611-0228ec6 + 20261112-143759-0228ec6

RESEARCH USE ONLY. NOT FOR CLINICAL USE. Radiarch is a research treatment-planning system; its plans, doses and evaluations must not be used to treat patients.

The cases ran one per process from commit 0228ec6: `pb_vs_mc` (20261112-133523), `pb_vs_ccc` (20261112-132750), `photon_pdd_10x10_pb` (20261112-132735), `photon_profile_10x10_pb` (20261112-132636), `photon_output_vs_field_pb` (20261112-132643), `dij_consistency` (20261112-133125), `lung_sbrt_vmat` (20261112-135033), `lung_vmat_lctsc` (20261112-152611), `hn_sib_vmat` (20261112-143759).

| Case | Status | Time (s) | Checks |
|---|---|---|---|
| pb_vs_mc | **pass** | 529.7 | 35 pass, 0 fail, 16 informative |
| pb_vs_ccc | **fail** | 75.8 | 2 pass, 1 fail, 4 informative |
| photon_pdd_10x10_pb | **pass** | 3.1 | 2 pass, 0 fail, 2 informative |
| photon_profile_10x10_pb | **pass** | 1.7 | 2 pass, 0 fail, 1 informative |
| photon_output_vs_field_pb | **info** | 8.1 | 0 pass, 0 fail, 3 informative |
| dij_consistency | **pass** | 289.8 | 9 pass, 0 fail, 0 informative |
| lung_sbrt_vmat | **pass** | 1437.7 | 32 pass, 0 fail, 12 informative |
| lung_vmat_lctsc | **pass** | 7175.9 | 10 pass, 0 fail, 20 informative |
| hn_sib_vmat | **pass** | 4283.7 | 12 pass, 0 fail, 14 informative |

## pb_vs_mc — pass

- note: water_10x10: MC 9.00e+08 primaries
- note: lung_slab: MC 9.00e+08 primaries
- note: bone_slab: MC 9.00e+08 primaries
- note: lung_slab_2x2: MC 9.00e+08 primaries; 5 mm beamlets for CCC
- note: MLC fields: MC mlc_open 2.0e+09, mlc_closed 4.0e+09, mlc_gap10 2.0e+09, mlc_shape 2.0e+09 primaries
- note: pb kernel f046d6a503757f17 from pencil_6mv.npz (5.4e+08 primaries); the same Mohan 6 MV spectrum as the references

| Check | Value | Target | Result |
|---|---|---|---|
| water_10x10: PDD10 pb vs MC (%) | 67.83 | 68.0 ± 2.0 (MC) | pass |
| water_10x10: d_max pb vs MC (mm) | 16.25 | 13.8 (MC) | informative |
| water_10x10: CAX dose at 50 mm, pb / MC | 1.013 | 1 ± 0.02 | pass |
| water_10x10: CAX dose at 150 mm, pb / MC | 1.012 | 1 ± 0.02 | pass |
| water_10x10: CAX dose at 200 mm, pb / MC | 1.009 | 1 ± 0.02 | pass |
| water_10x10: CAX dose at 250 mm, pb / MC | 0.9996 | 1 ± 0.02 | pass |
| water_10x10: penumbra 80-20 % at 10 cm, pb (mm) | 6.035 | 5.9 ± 2.5 (MC) | pass |
| water_10x10: off-axis ratio at 40 mm, 10 cm depth | 0.9677 | 0.960 ± 0.03 (MC) | pass |
| water_10x10: dose 2 cm outside the field edge at 10 cm (% of CAX) | 5.09 | 5.12 ± 1 (MC) | pass |
| water_10x10: gamma 3 %/3 mm pass rate (%) | 99.29 | ≥ 95.0 | pass |
| lung_slab: correction factor at 20 mm, pb vs MC | 1.001 | 0.983 ± 0.030 (MC) | pass |
| lung_slab: correction factor at 50 mm, pb vs MC | 1.011 | 1.002 ± 0.030 (MC) | pass |
| lung_slab: correction factor at 80 mm, pb vs MC | 1.079 | 1.063 ± 0.032 (MC) | pass |
| lung_slab: correction factor at 130 mm, pb vs MC | 1.232 | 1.201 ± 0.036 (MC) | pass |
| lung_slab: correction factor at 200 mm, pb vs MC | 1.259 | 1.245 ± 0.037 (MC) | pass |
| lung_slab: correction factor at 250 mm, pb vs MC | 1.269 | 1.246 ± 0.037 (MC) | pass |
| bone_slab: correction factor at 20 mm, pb vs MC | 1 | 1.002 ± 0.030 (MC) | pass |
| bone_slab: correction factor at 45 mm, pb vs MC | 0.9665 | 0.981 ± 0.029 (MC) | pass |
| bone_slab: correction factor at 80 mm, pb vs MC | 0.9147 | 0.941 ± 0.028 (MC) | pass |
| bone_slab: correction factor at 150 mm, pb vs MC | 0.9066 | 0.919 ± 0.028 (MC) | pass |
| bone_slab: correction factor at 200 mm, pb vs MC | 0.9038 | 0.904 ± 0.027 (MC) | pass |
| bone_slab: correction factor at 250 mm, pb vs MC | 0.9025 | 0.900 ± 0.027 (MC) | pass |
| 1x1 over 10x10, dose at 10 cm, pb vs MC | 0.7647 | 0.764 ± 0.038 (MC) | pass |
| 1x1: width at half maximum at 10 cm, pb vs MC (mm) | 11.77 | 11.52 ± 1 (MC) | pass |
| 2x2 over 10x10, dose at 10 cm, pb vs MC | 0.8478 | 0.839 ± 0.025 (MC) | pass |
| 2x2: width at half maximum at 10 cm, pb vs MC (mm) | 22.72 | 22.41 ± 1 (MC) | pass |
| 4x4 over 10x10, dose at 10 cm, pb vs MC | 0.9069 | 0.895 ± 0.018 (MC) | pass |
| 4x4 over 10x10, dose at 10 cm, CCC vs MC | 1 | 0.895 (MC) | informative |
| 20x20 over 10x10, dose at 10 cm, pb vs MC | 1.064 | 1.058 ± 0.021 (MC) | pass |
| 20x20 over 10x10, dose at 10 cm, CCC vs MC | 1 | 1.058 (MC) | informative |
| 2x2 in lung: dose at 50 mm (in the lung) over 20 mm, pb / MC | 0.981 | 1 ± 0.03 | pass |
| 2x2 in lung: dose at 50 mm (in the lung) over 20 mm, ccc / MC | 1.013 | informative | informative |
| 2x2 in lung: dose at 80 mm (in the lung) over 20 mm, pb / MC | 1.009 | 1 ± 0.03 | pass |
| 2x2 in lung: dose at 80 mm (in the lung) over 20 mm, ccc / MC | 0.92 | informative | informative |
| 2x2 in lung: dose at 100 mm (in the lung) over 20 mm, pb / MC | 1.019 | 1 ± 0.03 | pass |
| 2x2 in lung: dose at 100 mm (in the lung) over 20 mm, ccc / MC | 0.921 | informative | informative |
| 2x2 in lung: dose at 150 mm (beyond the lung) over 20 mm, pb / MC | 1 | 1 ± 0.03 | pass |
| 2x2 in lung: dose at 150 mm (beyond the lung) over 20 mm, ccc / MC | 1.103 | informative | informative |
| Agility MLC (Monte Carlo): leaf transmission fitted at 10 cm (%) | 0.198 | informative | informative |
| Agility MLC (Monte Carlo): dosimetric leaf gap fitted at 10 cm (mm) | 0.96 | informative | informative |
| Agility MLC (Monte Carlo): tip tail fitted at 10 cm (mm) | 2.32 | informative | informative |
| 10 mm gap on every pair, fitted leaf model: dose at the gap's centre at 10 cm, pb vs MC (% of open) | 80.49 | 80.82 (MC) | informative |
| closed pairs touching on the axis: excess dose within 10 mm of the tips' line, pb vs MC (% of open) | 5.994 | 5.904 (MC) | informative |
| irregular MLC field, leaf model: gamma 3 %/2 mm pass rate, depth 20-200 mm (%) | 100 | ≥ 95.0 | pass |
| irregular MLC field, leaf model: dose under the pairs closed at 20 mm at 10 cm, pb vs MC (% of open) | 1.82 | 1.81 ± 1 (MC) | pass |
| irregular MLC field, leaf model: dose 10 mm gap at 20 mm at 10 cm, pb vs MC (% of open) | 80.6 | 81.17 ± 3 (MC) | pass |
| irregular MLC field, leaf model: dose 5 mm gap at -30 mm at 10 cm, pb vs MC (% of open) | 50.87 | 50.06 ± 3 (MC) | pass |
| irregular MLC field, ideal leaves: gamma 3 %/2 mm pass rate, depth 20-200 mm (%) | 99.9 | informative | informative |
| irregular MLC field, ideal leaves: dose under the pairs closed at 20 mm at 10 cm, pb vs MC (% of open) | 1.62 | 1.81 (MC) | informative |
| irregular MLC field, ideal leaves: dose 10 mm gap at 20 mm at 10 cm, pb vs MC (% of open) | 79.97 | 81.17 (MC) | informative |
| irregular MLC field, ideal leaves: dose 5 mm gap at -30 mm at 10 cm, pb vs MC (% of open) | 47.03 | 50.06 (MC) | informative |

## pb_vs_ccc — fail


| Check | Value | Target | Result |
|---|---|---|---|
| water 10 x 10, 5 mm beamlets: gamma 3 %/3 mm pb vs CCC, absolute (%) | 97.63 | ≥ 95.0 | informative |
| water 10 x 10, 10 mm beamlets: gamma 3 %/3 mm pb vs CCC, absolute (%) | 94.55 | ≥ 95.0 | FAIL |
| pb PDD10 change from 5 to 10 mm beamlets (points) | 0 | ≤ 0.5 | pass |
| CCC PDD10 change from 5 to 10 mm beamlets (points) | 2.67 | informative | informative |
| dose at 10 cm, 4 x 4 over 10 x 10: CCC / pb | 1 | 0.907 (pb) | informative |
| dose at 10 cm, 6 x 6 over 10 x 10: CCC / pb | 1 | 0.947 (pb) | informative |
| isocenter 60 mm toward +x: dose(gantry 90) / dose(gantry 270), CCC | 1.706 | 1.647 ± 5 % (pb), > 1 | pass |

## photon_pdd_10x10_pb — pass


| Check | Value | Target | Result |
|---|---|---|---|
| PDD10 (%) | 67.46 | 66.1 ± 1.5 | informative |
| d_max (mm) | 16.25 | 12.0–25.0 | pass |
| PDD20/PDD10 | 0.5741 | 0.58 ± 0.02 | informative |
| dose at d_max per MU (Gy) | 0.009987 | 0.010 ± 0.0005 (calibration definition) | pass |

## photon_profile_10x10_pb — pass


| Check | Value | Target | Result |
|---|---|---|---|
| flatness (%) | 1.673 | ≤ 3.0 | pass |
| symmetry (%) | 2.059e-05 | ≤ 2.0 | pass |
| penumbra 80–20 % (mm) | 4.312 | 7.0 ± 3.0 | informative |

## photon_output_vs_field_pb — info


| Check | Value | Target | Result |
|---|---|---|---|
| output factor 4x4 vs 10x10 | 0.9841 | 0.904 measured (phantom scatter only here) | informative |
| output factor 20x20 vs 10x10 | 1.017 | 1.067 measured (phantom scatter only here) | informative |
| output factor 30x30 vs 10x10 | 1.028 | 1.102 measured (phantom scatter only here) | informative |

## dij_consistency — pass


| Check | Value | Target | Result |
|---|---|---|---|
| ccc: integral ratio Dij·w / forward | 1 | 1 ± 0.0001 | pass |
| ccc: correlation above 1 % of max | 1 | ≥ 0.9999 | pass |
| ccc: high-dose (≥ 50 % of max) p95 relative error | 1.183e-07 | ≤ 0.001 | pass |
| mcsquare: integral ratio Dij·w / forward | 0.9775 | 1 ± 0.05 | pass |
| mcsquare: correlation above 1 % of max | 0.9946 | ≥ 0.95 | pass |
| mcsquare: high-dose (≥ 50 % of max) p95 relative error | 0.116 | ≤ 0.15 | pass |
| pb: integral ratio Dij·w / forward | 0.998 | 1 ± 0.03 | pass |
| pb: correlation above 1 % of max | 0.9999 | ≥ 0.999 | pass |
| pb: high-dose (≥ 50 % of max) p95 relative error | 0.009552 | ≤ 0.02 | pass |

## lung_sbrt_vmat — pass

- note: synthetic peripheral GTV in the right lung (radius 12 mm), PTV +5 mm, rings for the SBRT dose fall-off; FMO of the arcs' sector beams with the pb Dij, arcs by sweeping each sector's fluence, control-point doses recomputed and metersets re-optimized (R8); a research pipeline check, not a plan quality statement

| Check | Value | Target | Result |
|---|---|---|---|
| LCTSC-Test-S1-101: PTV V100%[%] >= 95.0 | 96.11 | >= 95.0 | pass |
| LCTSC-Test-S1-101: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S1-101: PTV D0.03cc[%] <= 140.0 | 115.5 | <= 140.0 | informative |
| LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 10.0 | 2.79 | <= 10.0 | informative |
| LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 21.9 | 9.5 | <= 21.9 | pass |
| LCTSC-Test-S1-101: SpinalCord D0.35cc[Gy] <= 18.0 | 8.84 | <= 18.0 | pass |
| LCTSC-Test-S1-101: SpinalCord D1.2cc[Gy] <= 12.3 | 8.19 | <= 12.3 | pass |
| LCTSC-Test-S1-101: Esophagus D0.03cc[Gy] <= 25.2 | 1.96 | <= 25.2 | pass |
| LCTSC-Test-S1-101: Esophagus D5cc[Gy] <= 17.7 | 0.84 | <= 17.7 | pass |
| LCTSC-Test-S1-101: Heart D0.03cc[Gy] <= 30.0 | 11.57 | <= 30.0 | pass |
| LCTSC-Test-S1-101: Heart D15cc[Gy] <= 24.0 | 8.48 | <= 24.0 | pass |
| LCTSC-Test-S1-101: Lungs D1500cc[Gy] <= 11.6 | 0.57 | <= 11.6 | pass |
| LCTSC-Test-S1-101: Lungs D1000cc[Gy] <= 12.4 | 1.17 | <= 12.4 | pass |
| LCTSC-Test-S1-101: Lungs V12.5Gy[cc] <= 1000.0 | 244.3 | <= 1000.0 | informative |
| LCTSC-Test-S1-101: R100 (PTV 16.0 cc) | 0.966 | < 1.2 (minor ≤ 1.5) | pass |
| LCTSC-Test-S1-101: R50 (PTV 16.0 cc) | 2.664 | < 4.63673 (minor ≤ 5.70509) | pass |
| LCTSC-Test-S1-101: D2cm (PTV 16.0 cc) | 57.37 | < 51.2655 (minor ≤ 59.5818) | pass |
| LCTSC-Test-S1-101: LungV20 (PTV 16.0 cc) | 2.789 | < 10 (minor ≤ 15) | pass |
| LCTSC-Test-S1-101: arcs deliverable at the machine's limits | True | True | pass |
| LCTSC-Test-S1-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 83.7 | informative | informative |
| LCTSC-Test-S1-101: second engine PTV D95, CCC / pb | 1.004 | informative | informative |
| LCTSC-Test-S1-101: second engine PTV D95, CCC / pb, body as water | 1.033 | informative | informative |
| LCTSC-Test-S2-101: PTV V100%[%] >= 95.0 | 95.35 | >= 95.0 | pass |
| LCTSC-Test-S2-101: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S2-101: PTV D0.03cc[%] <= 140.0 | 112.5 | <= 140.0 | informative |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 10.0 | 2.77 | <= 10.0 | informative |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 21.9 | 8.48 | <= 21.9 | pass |
| LCTSC-Test-S2-101: SpinalCord D0.35cc[Gy] <= 18.0 | 7.57 | <= 18.0 | pass |
| LCTSC-Test-S2-101: SpinalCord D1.2cc[Gy] <= 12.3 | 6.21 | <= 12.3 | pass |
| LCTSC-Test-S2-101: Esophagus D0.03cc[Gy] <= 25.2 | 5.41 | <= 25.2 | pass |
| LCTSC-Test-S2-101: Esophagus D5cc[Gy] <= 17.7 | 2.22 | <= 17.7 | pass |
| LCTSC-Test-S2-101: Heart D0.03cc[Gy] <= 30.0 | 17.6 | <= 30.0 | pass |
| LCTSC-Test-S2-101: Heart D15cc[Gy] <= 24.0 | 10.36 | <= 24.0 | pass |
| LCTSC-Test-S2-101: Lungs D1500cc[Gy] <= 11.6 | 0.62 | <= 11.6 | pass |
| LCTSC-Test-S2-101: Lungs D1000cc[Gy] <= 12.4 | 1.13 | <= 12.4 | pass |
| LCTSC-Test-S2-101: Lungs V12.5Gy[cc] <= 1000.0 | 213.2 | <= 1000.0 | informative |
| LCTSC-Test-S2-101: R100 (PTV 16.3 cc) | 0.96 | < 1.2 (minor ≤ 1.5) | pass |
| LCTSC-Test-S2-101: R50 (PTV 16.3 cc) | 2.424 | < 4.63059 (minor ≤ 5.69589) | pass |
| LCTSC-Test-S2-101: D2cm (PTV 16.3 cc) | 50.05 | < 51.3882 (minor ≤ 59.7352) | pass |
| LCTSC-Test-S2-101: LungV20 (PTV 16.3 cc) | 2.773 | < 10 (minor ≤ 15) | pass |
| LCTSC-Test-S2-101: arcs deliverable at the machine's limits | True | True | pass |
| LCTSC-Test-S2-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 89.9 | informative | informative |
| LCTSC-Test-S2-101: second engine PTV D95, CCC / pb | 0.946 | informative | informative |
| LCTSC-Test-S2-101: second engine PTV D95, CCC / pb, body as water | 1.039 | informative | informative |

## lung_vmat_lctsc — pass

- note: synthetic 2 cm GTV at the right lung's centroid, CTV +5 mm, PTV +5 mm (the R7 lung case), 60 Gy in 30 fractions; FMO of the arcs' sector beams with the pb Dij, arcs by sweeping each sector's fluence, control-point doses recomputed and metersets re-optimized (R8); a research pipeline check, not a plan quality statement

| Check | Value | Target | Result |
|---|---|---|---|
| LCTSC-Test-S1-101: PTV V60Gy[%] >= 95.0 | 95.66 | >= 95.0 | pass |
| LCTSC-Test-S1-101: PTV D0.03cc[Gy] <= 72.0 | 66.16 | <= 72.0 | informative |
| LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 37.0 | 14.96 | <= 37.0 | pass |
| LCTSC-Test-S1-101: Lungs-GTV Dmean[Gy] <= 20.0 | 8.07 | <= 20.0 | pass |
| LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 50.5 | 17.59 | <= 50.5 | pass |
| LCTSC-Test-S1-101: Esophagus Dmean[Gy] <= 34.0 | 2.48 | <= 34.0 | informative |
| LCTSC-Test-S1-101: Heart V60Gy[%] <= 33.0 | 0 | <= 33.0 | informative |
| LCTSC-Test-S1-101: Heart V45Gy[%] <= 66.0 | 0 | <= 66.0 | informative |
| LCTSC-Test-S1-101: Heart V40Gy[%] <= 100.0 | 0 | <= 100.0 | informative |
| LCTSC-Test-S1-101: PTV D5 / D95 (homogeneity) | 1.064 | ≤ 1.15 (informative) | informative |
| LCTSC-Test-S1-101: Paddick conformity index | 0.905 | informative | informative |
| LCTSC-Test-S1-101: arcs deliverable at the machine's limits | True | True | pass |
| LCTSC-Test-S1-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 77.6 | informative | informative |
| LCTSC-Test-S1-101: second engine PTV D95, CCC / pb | 0.877 | informative | informative |
| LCTSC-Test-S1-101: second engine PTV D95, CCC / pb, body as water | 1.05 | informative | informative |
| LCTSC-Test-S2-101: PTV V60Gy[%] >= 95.0 | 95.58 | >= 95.0 | pass |
| LCTSC-Test-S2-101: PTV D0.03cc[Gy] <= 72.0 | 65.34 | <= 72.0 | informative |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 37.0 | 13.72 | <= 37.0 | pass |
| LCTSC-Test-S2-101: Lungs-GTV Dmean[Gy] <= 20.0 | 8.39 | <= 20.0 | pass |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5 | 18.85 | <= 50.5 | pass |
| LCTSC-Test-S2-101: Esophagus Dmean[Gy] <= 34.0 | 3.38 | <= 34.0 | informative |
| LCTSC-Test-S2-101: Heart V60Gy[%] <= 33.0 | 0 | <= 33.0 | informative |
| LCTSC-Test-S2-101: Heart V45Gy[%] <= 66.0 | 0.14 | <= 66.0 | informative |
| LCTSC-Test-S2-101: Heart V40Gy[%] <= 100.0 | 0.38 | <= 100.0 | informative |
| LCTSC-Test-S2-101: PTV D5 / D95 (homogeneity) | 1.06 | ≤ 1.15 (informative) | informative |
| LCTSC-Test-S2-101: Paddick conformity index | 0.916 | informative | informative |
| LCTSC-Test-S2-101: arcs deliverable at the machine's limits | True | True | pass |
| LCTSC-Test-S2-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 79.6 | informative | informative |
| LCTSC-Test-S2-101: second engine PTV D95, CCC / pb | 0.921 | informative | informative |
| LCTSC-Test-S2-101: second engine PTV D95, CCC / pb, body as water | 1.052 | informative | informative |

## hn_sib_vmat — pass

- note: synthetic oropharynx-like GTV between the parotids, PTV70 +8 mm, PTV56 +25 mm outside PTV70 + 3 mm and the brainstem + 5 mm; two full arcs from the fluence of their sector beams (pb Dij), 70/56 Gy in 35 fractions; NCCN head-and-neck template; a research pipeline check, not a plan quality statement

| Check | Value | Target | Result |
|---|---|---|---|
| 0522c0001: PTV_High D95%[%] >= 95.0 | 100.2 | >= 95.0 | pass |
| 0522c0001: PTV_High D0.03cc[%] <= 110.0 | 114.9 | <= 110.0 | informative |
| 0522c0001: Brainstem D0.03cc[Gy] <= 54.0 | 48.46 | <= 54.0 | pass |
| 0522c0001: Brainstem_PRV D0.03cc[Gy] <= 60.0 | 53.26 | <= 60.0 | informative |
| 0522c0001: OpticChiasm D0.03cc[Gy] <= 54.0 | 1.02 | <= 54.0 | pass |
| 0522c0001: OpticNrv D0.03cc[Gy] <= 54.0 | 0.95 | <= 54.0 | pass |
| 0522c0001: Parotid Dmean[Gy] <= 26.0 | 29.19 | <= 26.0 | informative |
| 0522c0001: Glnd_Submand Dmean[Gy] <= 39.0 | 64.02 | <= 39.0 | informative |
| 0522c0001: Mandible D0.03cc[Gy] <= 70.0 | 65.18 | <= 70.0 | informative |
| 0522c0001: PTV56 D95%[Gy] >= 56.0 | 59.75 | >= 56.0 | pass |
| 0522c0001: PTV70 D5 / D95 (homogeneity) | 1.107 | ≤ 1.10 (informative) | informative |
| 0522c0001: hottest point outside the elective volume (% of 70 Gy) | 101.5 | informative | informative |
| 0522c0001: arcs deliverable at the machine's limits | True | True | pass |
| 0522c0002: PTV_High D95%[%] >= 95.0 | 100.2 | >= 95.0 | pass |
| 0522c0002: PTV_High D0.03cc[%] <= 110.0 | 109.7 | <= 110.0 | informative |
| 0522c0002: Brainstem D0.03cc[Gy] <= 54.0 | 38.57 | <= 54.0 | pass |
| 0522c0002: Brainstem_PRV D0.03cc[Gy] <= 60.0 | 48.58 | <= 60.0 | informative |
| 0522c0002: OpticChiasm D0.03cc[Gy] <= 54.0 | 0.81 | <= 54.0 | pass |
| 0522c0002: OpticNrv D0.03cc[Gy] <= 54.0 | 0.78 | <= 54.0 | pass |
| 0522c0002: Parotid Dmean[Gy] <= 26.0 | 22.34 | <= 26.0 | informative |
| 0522c0002: Glnd_Submand Dmean[Gy] <= 39.0 | 54.65 | <= 39.0 | informative |
| 0522c0002: Mandible D0.03cc[Gy] <= 70.0 | 61.66 | <= 70.0 | informative |
| 0522c0002: PTV56 D95%[Gy] >= 56.0 | 59.71 | >= 56.0 | pass |
| 0522c0002: PTV70 D5 / D95 (homogeneity) | 1.083 | ≤ 1.10 (informative) | informative |
| 0522c0002: hottest point outside the elective volume (% of 70 Gy) | 98.4 | informative | informative |
| 0522c0002: arcs deliverable at the machine's limits | True | True | pass |
