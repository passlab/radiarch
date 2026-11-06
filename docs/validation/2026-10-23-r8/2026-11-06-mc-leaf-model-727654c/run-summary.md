# Radiarch validation run 20261106-163934 (727654c)

RESEARCH USE ONLY. NOT FOR CLINICAL USE. Radiarch is a research treatment-planning system; its plans, doses and evaluations must not be used to treat patients.

| Case | Status | Time (s) | Checks |
|---|---|---|---|
| pb_vs_mc | **fail** | 76.2 | 33 pass, 2 fail, 15 informative |

## pb_vs_mc — fail

- note: water_10x10: MC 9.00e+08 primaries
- note: lung_slab: MC 9.00e+08 primaries
- note: bone_slab: MC 9.00e+08 primaries
- note: lung_slab_2x2: MC 9.00e+08 primaries; 5 mm beamlets for CCC
- note: MLC fields: MC mlc_open 2.0e+09, mlc_closed 4.0e+09, mlc_gap10 2.0e+09, mlc_shape 2.0e+09 primaries
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
| 1x1 over 10x10, dose at 10 cm, pb vs MC | 0.7192 | 0.764 ± 0.038 (MC) | FAIL |
| 1x1: width at half maximum at 10 cm, pb vs MC (mm) | 11.37 | 11.52 ± 1 (MC) | pass |
| 2x2 over 10x10, dose at 10 cm, pb vs MC | 0.8437 | 0.839 ± 0.025 (MC) | pass |
| 2x2: width at half maximum at 10 cm, pb vs MC (mm) | 22.16 | 22.41 ± 1 (MC) | pass |
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
| Agility MLC (Monte Carlo): leaf transmission fitted at 10 cm (%) | 0.196 | informative | informative |
| Agility MLC (Monte Carlo): dosimetric leaf gap fitted at 10 cm (mm) | 1.01 | informative | informative |
| 10 mm gap on every pair, fitted leaf model: dose at the gap's centre at 10 cm, pb vs MC (% of open) | 80.53 | 80.82 (MC) | informative |
| closed pairs touching on the axis: excess dose within 10 mm of the tips' line, pb vs MC (% of open) | 6.362 | 5.904 (MC) | informative |
| irregular MLC field, leaf model: gamma 3 %/2 mm pass rate, depth 20-200 mm (%) | 100 | ≥ 95.0 | pass |
| irregular MLC field, leaf model: dose under the pairs closed at 20 mm at 10 cm, pb vs MC (% of open) | 1.82 | 1.81 ± 1 (MC) | pass |
| irregular MLC field, leaf model: dose 10 mm gap at 20 mm at 10 cm, pb vs MC (% of open) | 80.06 | 81.17 ± 3 (MC) | pass |
| irregular MLC field, leaf model: dose 5 mm gap at -30 mm at 10 cm, pb vs MC (% of open) | 53.26 | 50.06 ± 3 (MC) | FAIL |
| irregular MLC field, ideal leaves: gamma 3 %/2 mm pass rate, depth 20-200 mm (%) | 99.1 | informative | informative |
| irregular MLC field, ideal leaves: dose under the pairs closed at 20 mm at 10 cm, pb vs MC (% of open) | 1.62 | 1.81 (MC) | informative |
| irregular MLC field, ideal leaves: dose 10 mm gap at 20 mm at 10 cm, pb vs MC (% of open) | 77.69 | 81.17 (MC) | informative |
| irregular MLC field, ideal leaves: dose 5 mm gap at -30 mm at 10 cm, pb vs MC (% of open) | 46.89 | 50.06 (MC) | informative |
