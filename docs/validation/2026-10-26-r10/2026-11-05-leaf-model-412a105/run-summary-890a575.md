# Radiarch validation run 20261106-034538-890a575

RESEARCH USE ONLY. NOT FOR CLINICAL USE. Radiarch is a research treatment-planning system; its plans, doses and evaluations must not be used to treat patients.

The cases ran one per process from commit 890a575: `protocol_lung_vmat` (20261106-034538).

| Case | Status | Time (s) | Checks |
|---|---|---|---|
| protocol_lung_vmat | **pass** | 2121.2 | 44 pass, 0 fail, 10 informative |

## protocol_lung_vmat — pass


| Check | Value | Target | Result |
|---|---|---|---|
| protocol lung-60gy-30fx-vmat encodes lung_vmat_lctsc: prescription (Gy, fractions) | [60.0, 30] | [60.0, 30] | pass |
| protocol lung-60gy-30fx-vmat encodes lung_vmat_lctsc: CTV margin (mm) | 5.0 | 5.0 | pass |
| protocol lung-60gy-30fx-vmat encodes lung_vmat_lctsc: PTV margin (mm) | 5.0 | 5.0 | pass |
| protocol lung-60gy-30fx-vmat encodes lung_vmat_lctsc: PTV from | "CTV" | "CTV" | pass |
| protocol lung-60gy-30fx-vmat encodes lung_vmat_lctsc: far ring outer edge (mm) | 45.0 | 45.0 | pass |
| protocol lung-60gy-30fx-vmat encodes lung_vmat_lctsc: near ring limit (Gy, weight) | [54.0, 100.0] | [54.0, 100.0] | pass |
| protocol lung-60gy-30fx-vmat encodes lung_vmat_lctsc: far ring limit (Gy, weight) | [30.0, 200.0] | [30.0, 200.0] | pass |
| protocol lung-60gy-30fx-vmat encodes lung_vmat_lctsc: coverage goal | [">=", 60.0] | [">=", 60.0] | pass |
| protocol lung-60gy-30fx-vmat encodes lung_vmat_lctsc: arcs | [{"arc_id": "ARC1", "start_deg": 181.0, "stop_deg": 179.0, "direction": "CW", "sectors": 12, "control_point_spacing_deg": 4.0, "couch_deg": 0.0, "collimator_deg": 15.0}, {"arc_id": "ARC2", "start_deg": 179.0, "stop_deg": 181.0, "direction": "CC", "sectors": 12, "control_point_spacing_deg": 4.0, "couch_deg": 0.0, "collimator_deg": -15.0}] | [{"arc_id": "ARC1", "start_deg": 181.0, "stop_deg": 179.0, "direction": "CW", "sectors": 12, "control_point_spacing_deg": 4.0, "couch_deg": 0.0, "collimator_deg": 15.0}, {"arc_id": "ARC2", "start_deg": 179.0, "stop_deg": 181.0, "direction": "CC", "sectors": 12, "control_point_spacing_deg": 4.0, "couch_deg": 0.0, "collimator_deg": -15.0}] | pass |
| protocol lung-60gy-30fx-vmat encodes lung_vmat_lctsc: beamlet (mm), iterations, rounds | [5.0, 150, 3] | [5.0, 150, 3] | pass |
| protocol lung-60gy-30fx-vmat encodes lung_vmat_lctsc: machine, jaw margin (mm) | ["synthetic-120", 10.0] | ["synthetic-120", 10.0] | pass |
| protocol lung-60gy-30fx-vmat encodes lung_vmat_lctsc: evaluation template | "rtog-0617" | "rtog-0617" | pass |
| protocol lung-60gy-30fx-vmat encodes lung_vmat_lctsc: SpinalCord Dmax goal (Gy, maximum term) | [45.0, true] | [45.0, true] | pass |
| protocol lung-60gy-30fx-vmat encodes lung_vmat_lctsc: Esophagus Dmean goal (Gy, maximum term) | [34.0, true] | [34.0, true] | pass |
| protocol lung-60gy-30fx-vmat encodes lung_vmat_lctsc: Heart D33 goal (Gy, maximum term) | [60.0, true] | [60.0, true] | pass |
| protocol lung-60gy-30fx-vmat encodes lung_vmat_lctsc: Lungs-PTV D37 goal (Gy, maximum term) | [20.0, false] | [20.0, false] | pass |
| LCTSC-Test-S1-101: protocol run deliverable | True | True | pass |
| LCTSC-Test-S1-101: PTV V60Gy[%] >= 95.0 (protocol) | 95.6 | >= 95.0 | pass |
| LCTSC-Test-S1-101: PTV V60Gy[%] >= 95.0: protocol against the recorded harness run | 95.6 | 95.6 ± 0.96 | pass |
| LCTSC-Test-S1-101: PTV D0.03cc[Gy] <= 72.0 (protocol) | 65.25 | <= 72.0 | informative |
| LCTSC-Test-S1-101: PTV D0.03cc[Gy] <= 72.0: protocol against the recorded harness run | 65.25 | 65.25 ± 0.65 | pass |
| LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 37.0 (protocol) | 14.78 | <= 37.0 | pass |
| LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 37.0: protocol against the recorded harness run | 14.78 | 14.78 ± 0.15 | pass |
| LCTSC-Test-S1-101: Lungs-GTV Dmean[Gy] <= 20.0 (protocol) | 8.37 | <= 20.0 | pass |
| LCTSC-Test-S1-101: Lungs-GTV Dmean[Gy] <= 20.0: protocol against the recorded harness run | 8.37 | 8.37 ± 0.08 | pass |
| LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 50.5 (protocol) | 14.89 | <= 50.5 | pass |
| LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 50.5: protocol against the recorded harness run | 14.89 | 14.89 ± 0.15 | pass |
| LCTSC-Test-S1-101: Esophagus Dmean[Gy] <= 34.0 (protocol) | 3.38 | <= 34.0 | informative |
| LCTSC-Test-S1-101: Esophagus Dmean[Gy] <= 34.0: protocol against the recorded harness run | 3.38 | 3.38 ± 0.05 | pass |
| LCTSC-Test-S1-101: Heart V60Gy[%] <= 33.0 (protocol) | 0 | <= 33.0 | informative |
| LCTSC-Test-S1-101: Heart V60Gy[%] <= 33.0: protocol against the recorded harness run | 0 | 0.0 ± 0.05 | pass |
| LCTSC-Test-S1-101: Heart V45Gy[%] <= 66.0 (protocol) | 0 | <= 66.0 | informative |
| LCTSC-Test-S1-101: Heart V45Gy[%] <= 66.0: protocol against the recorded harness run | 0 | 0.0 ± 0.05 | pass |
| LCTSC-Test-S1-101: Heart V40Gy[%] <= 100.0 (protocol) | 0 | <= 100.0 | informative |
| LCTSC-Test-S1-101: Heart V40Gy[%] <= 100.0: protocol against the recorded harness run | 0 | 0.0 ± 0.05 | pass |
| LCTSC-Test-S2-101: protocol run deliverable | True | True | pass |
| LCTSC-Test-S2-101: PTV V60Gy[%] >= 95.0 (protocol) | 95.62 | >= 95.0 | pass |
| LCTSC-Test-S2-101: PTV V60Gy[%] >= 95.0: protocol against the recorded harness run | 95.62 | 95.62 ± 0.96 | pass |
| LCTSC-Test-S2-101: PTV D0.03cc[Gy] <= 72.0 (protocol) | 65.25 | <= 72.0 | informative |
| LCTSC-Test-S2-101: PTV D0.03cc[Gy] <= 72.0: protocol against the recorded harness run | 65.25 | 65.25 ± 0.65 | pass |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 37.0 (protocol) | 14.01 | <= 37.0 | pass |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 37.0: protocol against the recorded harness run | 14.01 | 14.01 ± 0.14 | pass |
| LCTSC-Test-S2-101: Lungs-GTV Dmean[Gy] <= 20.0 (protocol) | 8.68 | <= 20.0 | pass |
| LCTSC-Test-S2-101: Lungs-GTV Dmean[Gy] <= 20.0: protocol against the recorded harness run | 8.68 | 8.68 ± 0.09 | pass |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5 (protocol) | 15.65 | <= 50.5 | pass |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5: protocol against the recorded harness run | 15.65 | 15.65 ± 0.16 | pass |
| LCTSC-Test-S2-101: Esophagus Dmean[Gy] <= 34.0 (protocol) | 3.24 | <= 34.0 | informative |
| LCTSC-Test-S2-101: Esophagus Dmean[Gy] <= 34.0: protocol against the recorded harness run | 3.24 | 3.24 ± 0.05 | pass |
| LCTSC-Test-S2-101: Heart V60Gy[%] <= 33.0 (protocol) | 0 | <= 33.0 | informative |
| LCTSC-Test-S2-101: Heart V60Gy[%] <= 33.0: protocol against the recorded harness run | 0 | 0.0 ± 0.05 | pass |
| LCTSC-Test-S2-101: Heart V45Gy[%] <= 66.0 (protocol) | 0.19 | <= 66.0 | informative |
| LCTSC-Test-S2-101: Heart V45Gy[%] <= 66.0: protocol against the recorded harness run | 0.19 | 0.19 ± 0.05 | pass |
| LCTSC-Test-S2-101: Heart V40Gy[%] <= 100.0 (protocol) | 0.42 | <= 100.0 | informative |
| LCTSC-Test-S2-101: Heart V40Gy[%] <= 100.0: protocol against the recorded harness run | 0.42 | 0.42 ± 0.05 | pass |
