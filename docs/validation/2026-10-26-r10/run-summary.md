# Radiarch validation run 20261026-150400-92ce40d + 20261026-152231-92ce40d

RESEARCH USE ONLY. NOT FOR CLINICAL USE. Radiarch is a research treatment-planning system; its plans, doses and evaluations must not be used to treat patients.

The two cases ran one per process from commit 92ce40d: `protocol_lung_vmat` (20261026-150400), `protocol_batch_lctsc` (20261026-152231).

| Case | Status | Time (s) | Checks |
|---|---|---|---|
| protocol_lung_vmat | **pass** | 1075.5 | 44 pass, 0 fail, 10 informative |
| protocol_batch_lctsc | **pass** | 1108.6 | 79 pass, 0 fail, 36 informative |

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
| LCTSC-Test-S1-101: PTV V60Gy[%] >= 95.0 (protocol) | 95.66 | >= 95.0 | pass |
| LCTSC-Test-S1-101: PTV V60Gy[%] >= 95.0: protocol against the recorded harness run | 95.66 | 95.66 ± 0.96 | pass |
| LCTSC-Test-S1-101: PTV D0.03cc[Gy] <= 72.0 (protocol) | 65.9 | <= 72.0 | informative |
| LCTSC-Test-S1-101: PTV D0.03cc[Gy] <= 72.0: protocol against the recorded harness run | 65.9 | 65.9 ± 0.66 | pass |
| LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 37.0 (protocol) | 13.72 | <= 37.0 | pass |
| LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 37.0: protocol against the recorded harness run | 13.72 | 13.72 ± 0.14 | pass |
| LCTSC-Test-S1-101: Lungs-GTV Dmean[Gy] <= 20.0 (protocol) | 7.85 | <= 20.0 | pass |
| LCTSC-Test-S1-101: Lungs-GTV Dmean[Gy] <= 20.0: protocol against the recorded harness run | 7.85 | 7.85 ± 0.08 | pass |
| LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 50.5 (protocol) | 17.89 | <= 50.5 | pass |
| LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 50.5: protocol against the recorded harness run | 17.89 | 17.89 ± 0.18 | pass |
| LCTSC-Test-S1-101: Esophagus Dmean[Gy] <= 34.0 (protocol) | 2.72 | <= 34.0 | informative |
| LCTSC-Test-S1-101: Esophagus Dmean[Gy] <= 34.0: protocol against the recorded harness run | 2.72 | 2.72 ± 0.05 | pass |
| LCTSC-Test-S1-101: Heart V60Gy[%] <= 33.0 (protocol) | 0 | <= 33.0 | informative |
| LCTSC-Test-S1-101: Heart V60Gy[%] <= 33.0: protocol against the recorded harness run | 0 | 0.0 ± 0.05 | pass |
| LCTSC-Test-S1-101: Heart V45Gy[%] <= 66.0 (protocol) | 0 | <= 66.0 | informative |
| LCTSC-Test-S1-101: Heart V45Gy[%] <= 66.0: protocol against the recorded harness run | 0 | 0.0 ± 0.05 | pass |
| LCTSC-Test-S1-101: Heart V40Gy[%] <= 100.0 (protocol) | 0 | <= 100.0 | informative |
| LCTSC-Test-S1-101: Heart V40Gy[%] <= 100.0: protocol against the recorded harness run | 0 | 0.0 ± 0.05 | pass |
| LCTSC-Test-S2-101: protocol run deliverable | True | True | pass |
| LCTSC-Test-S2-101: PTV V60Gy[%] >= 95.0 (protocol) | 95.74 | >= 95.0 | pass |
| LCTSC-Test-S2-101: PTV V60Gy[%] >= 95.0: protocol against the recorded harness run | 95.74 | 95.74 ± 0.96 | pass |
| LCTSC-Test-S2-101: PTV D0.03cc[Gy] <= 72.0 (protocol) | 66.87 | <= 72.0 | informative |
| LCTSC-Test-S2-101: PTV D0.03cc[Gy] <= 72.0: protocol against the recorded harness run | 66.87 | 66.87 ± 0.67 | pass |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 37.0 (protocol) | 13.18 | <= 37.0 | pass |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 37.0: protocol against the recorded harness run | 13.18 | 13.18 ± 0.13 | pass |
| LCTSC-Test-S2-101: Lungs-GTV Dmean[Gy] <= 20.0 (protocol) | 8.28 | <= 20.0 | pass |
| LCTSC-Test-S2-101: Lungs-GTV Dmean[Gy] <= 20.0: protocol against the recorded harness run | 8.28 | 8.28 ± 0.08 | pass |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5 (protocol) | 20.19 | <= 50.5 | pass |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5: protocol against the recorded harness run | 20.19 | 20.19 ± 0.20 | pass |
| LCTSC-Test-S2-101: Esophagus Dmean[Gy] <= 34.0 (protocol) | 3.24 | <= 34.0 | informative |
| LCTSC-Test-S2-101: Esophagus Dmean[Gy] <= 34.0: protocol against the recorded harness run | 3.24 | 3.24 ± 0.05 | pass |
| LCTSC-Test-S2-101: Heart V60Gy[%] <= 33.0 (protocol) | 0 | <= 33.0 | informative |
| LCTSC-Test-S2-101: Heart V60Gy[%] <= 33.0: protocol against the recorded harness run | 0 | 0.0 ± 0.05 | pass |
| LCTSC-Test-S2-101: Heart V45Gy[%] <= 66.0 (protocol) | 0.11 | <= 66.0 | informative |
| LCTSC-Test-S2-101: Heart V45Gy[%] <= 66.0: protocol against the recorded harness run | 0.11 | 0.11 ± 0.05 | pass |
| LCTSC-Test-S2-101: Heart V40Gy[%] <= 100.0 (protocol) | 0.31 | <= 100.0 | informative |
| LCTSC-Test-S2-101: Heart V40Gy[%] <= 100.0: protocol against the recorded harness run | 0.31 | 0.31 ± 0.05 | pass |

## protocol_batch_lctsc — pass


| Check | Value | Target | Result |
|---|---|---|---|
| radiarch batch over 6 LCTSC thoraces: cases planned | 6 | = 6 | pass |
| LCTSC-Test-S1-101: deliverable | True | True | pass |
| LCTSC-Test-S1-101: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S1-101: planning goal SpinalCord Dmax <= 21.9 | 11.36 | <= 21.9 | informative |
| LCTSC-Test-S1-101: planning goal Esophagus Dmax <= 25.2 | 2.58 | <= 25.2 | informative |
| LCTSC-Test-S1-101: planning goal Heart Dmax <= 30.0 | 17.14 | <= 30.0 | informative |
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
| LCTSC-Test-S1-102: deliverable | True | True | pass |
| LCTSC-Test-S1-102: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S1-102: planning goal SpinalCord Dmax <= 21.9 | 11.66 | <= 21.9 | informative |
| LCTSC-Test-S1-102: planning goal Esophagus Dmax <= 25.2 | 3.91 | <= 25.2 | informative |
| LCTSC-Test-S1-102: planning goal Heart Dmax <= 30.0 | 20.35 | <= 30.0 | informative |
| LCTSC-Test-S1-102: PTV V100%[%] >= 95.0 | 95.27 | >= 95.0 | pass |
| LCTSC-Test-S1-102: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S1-102: PTV D0.03cc[%] <= 140.0 | 115.5 | <= 140.0 | informative |
| LCTSC-Test-S1-102: Lungs-GTV V20Gy[%] <= 10.0 | 3.11 | <= 10.0 | informative |
| LCTSC-Test-S1-102: SpinalCord D0.03cc[Gy] <= 21.9 | 11.6 | <= 21.9 | pass |
| LCTSC-Test-S1-102: SpinalCord D0.35cc[Gy] <= 18.0 | 10.87 | <= 18.0 | pass |
| LCTSC-Test-S1-102: SpinalCord D1.2cc[Gy] <= 12.3 | 9.08 | <= 12.3 | pass |
| LCTSC-Test-S1-102: Esophagus D0.03cc[Gy] <= 25.2 | 3.89 | <= 25.2 | pass |
| LCTSC-Test-S1-102: Esophagus D5cc[Gy] <= 17.7 | 1.61 | <= 17.7 | pass |
| LCTSC-Test-S1-102: Heart D0.03cc[Gy] <= 30.0 | 20.28 | <= 30.0 | pass |
| LCTSC-Test-S1-102: Heart D15cc[Gy] <= 24.0 | 10.87 | <= 24.0 | pass |
| LCTSC-Test-S1-102: Lungs D1500cc[Gy] <= 11.6 | 0.63 | <= 11.6 | pass |
| LCTSC-Test-S1-102: Lungs D1000cc[Gy] <= 12.4 | 1.28 | <= 12.4 | pass |
| LCTSC-Test-S1-102: Lungs V12.5Gy[cc] <= 1000.0 | 227.2 | <= 1000.0 | informative |
| LCTSC-Test-S2-101: deliverable | True | True | pass |
| LCTSC-Test-S2-101: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S2-101: planning goal SpinalCord Dmax <= 21.9 | 10.07 | <= 21.9 | informative |
| LCTSC-Test-S2-101: planning goal Esophagus Dmax <= 25.2 | 6.42 | <= 25.2 | informative |
| LCTSC-Test-S2-101: planning goal Heart Dmax <= 30.0 | 17.69 | <= 30.0 | informative |
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
| LCTSC-Test-S2-102: deliverable | True | True | pass |
| LCTSC-Test-S2-102: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S2-102: planning goal SpinalCord Dmax <= 21.9 | 10.75 | <= 21.9 | informative |
| LCTSC-Test-S2-102: planning goal Esophagus Dmax <= 25.2 | 3.06 | <= 25.2 | informative |
| LCTSC-Test-S2-102: planning goal Heart Dmax <= 30.0 | 11.4 | <= 30.0 | informative |
| LCTSC-Test-S2-102: PTV V100%[%] >= 95.0 | 95.2 | >= 95.0 | pass |
| LCTSC-Test-S2-102: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S2-102: PTV D0.03cc[%] <= 140.0 | 118.1 | <= 140.0 | informative |
| LCTSC-Test-S2-102: Lungs-GTV V20Gy[%] <= 10.0 | 1.87 | <= 10.0 | informative |
| LCTSC-Test-S2-102: SpinalCord D0.03cc[Gy] <= 21.9 | 10.69 | <= 21.9 | pass |
| LCTSC-Test-S2-102: SpinalCord D0.35cc[Gy] <= 18.0 | 10.04 | <= 18.0 | pass |
| LCTSC-Test-S2-102: SpinalCord D1.2cc[Gy] <= 12.3 | 9.26 | <= 12.3 | pass |
| LCTSC-Test-S2-102: Esophagus D0.03cc[Gy] <= 25.2 | 3.05 | <= 25.2 | pass |
| LCTSC-Test-S2-102: Esophagus D5cc[Gy] <= 17.7 | 1.84 | <= 17.7 | pass |
| LCTSC-Test-S2-102: Heart D0.03cc[Gy] <= 30.0 | 11.38 | <= 30.0 | pass |
| LCTSC-Test-S2-102: Heart D15cc[Gy] <= 24.0 | 6.95 | <= 24.0 | pass |
| LCTSC-Test-S2-102: Lungs D1500cc[Gy] <= 11.6 | 0.91 | <= 11.6 | pass |
| LCTSC-Test-S2-102: Lungs D1000cc[Gy] <= 12.4 | 1.99 | <= 12.4 | pass |
| LCTSC-Test-S2-102: Lungs V12.5Gy[cc] <= 1000.0 | 217.7 | <= 1000.0 | informative |
| LCTSC-Test-S3-101: deliverable | True | True | pass |
| LCTSC-Test-S3-101: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S3-101: planning goal SpinalCord Dmax <= 21.9 | 3.87 | <= 21.9 | informative |
| LCTSC-Test-S3-101: planning goal Esophagus Dmax <= 25.2 | 3.63 | <= 25.2 | informative |
| LCTSC-Test-S3-101: planning goal Heart Dmax <= 30.0 | 19.07 | <= 30.0 | informative |
| LCTSC-Test-S3-101: PTV V100%[%] >= 95.0 | 95.29 | >= 95.0 | pass |
| LCTSC-Test-S3-101: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S3-101: PTV D0.03cc[%] <= 140.0 | 114.8 | <= 140.0 | informative |
| LCTSC-Test-S3-101: Lungs-GTV V20Gy[%] <= 10.0 | 3.92 | <= 10.0 | informative |
| LCTSC-Test-S3-101: SpinalCord D0.03cc[Gy] <= 21.9 | 3.45 | <= 21.9 | pass |
| LCTSC-Test-S3-101: SpinalCord D0.35cc[Gy] <= 18.0 | 3.06 | <= 18.0 | pass |
| LCTSC-Test-S3-101: SpinalCord D1.2cc[Gy] <= 12.3 | 2.68 | <= 12.3 | pass |
| LCTSC-Test-S3-101: Esophagus D0.03cc[Gy] <= 25.2 | 3.28 | <= 25.2 | pass |
| LCTSC-Test-S3-101: Esophagus D5cc[Gy] <= 17.7 | 1.92 | <= 17.7 | pass |
| LCTSC-Test-S3-101: Heart D0.03cc[Gy] <= 30.0 | 18.96 | <= 30.0 | pass |
| LCTSC-Test-S3-101: Heart D15cc[Gy] <= 24.0 | 9.08 | <= 24.0 | pass |
| LCTSC-Test-S3-101: Lungs D1500cc[Gy] <= 11.6 | 0.25 | <= 11.6 | pass |
| LCTSC-Test-S3-101: Lungs D1000cc[Gy] <= 12.4 | 0.62 | <= 12.4 | pass |
| LCTSC-Test-S3-101: Lungs V12.5Gy[cc] <= 1000.0 | 185.9 | <= 1000.0 | informative |
| LCTSC-Test-S3-102: deliverable | True | True | pass |
| LCTSC-Test-S3-102: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S3-102: planning goal SpinalCord Dmax <= 21.9 | 11.08 | <= 21.9 | informative |
| LCTSC-Test-S3-102: planning goal Esophagus Dmax <= 25.2 | 5.73 | <= 25.2 | informative |
| LCTSC-Test-S3-102: planning goal Heart Dmax <= 30.0 | 19.55 | <= 30.0 | informative |
| LCTSC-Test-S3-102: PTV V100%[%] >= 95.0 | 95.51 | >= 95.0 | pass |
| LCTSC-Test-S3-102: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S3-102: PTV D0.03cc[%] <= 140.0 | 113.5 | <= 140.0 | informative |
| LCTSC-Test-S3-102: Lungs-GTV V20Gy[%] <= 10.0 | 2.59 | <= 10.0 | informative |
| LCTSC-Test-S3-102: SpinalCord D0.03cc[Gy] <= 21.9 | 11 | <= 21.9 | pass |
| LCTSC-Test-S3-102: SpinalCord D0.35cc[Gy] <= 18.0 | 10.03 | <= 18.0 | pass |
| LCTSC-Test-S3-102: SpinalCord D1.2cc[Gy] <= 12.3 | 8.21 | <= 12.3 | pass |
| LCTSC-Test-S3-102: Esophagus D0.03cc[Gy] <= 25.2 | 5.59 | <= 25.2 | pass |
| LCTSC-Test-S3-102: Esophagus D5cc[Gy] <= 17.7 | 3.06 | <= 17.7 | pass |
| LCTSC-Test-S3-102: Heart D0.03cc[Gy] <= 30.0 | 19.2 | <= 30.0 | pass |
| LCTSC-Test-S3-102: Heart D15cc[Gy] <= 24.0 | 8.22 | <= 24.0 | pass |
| LCTSC-Test-S3-102: Lungs D1500cc[Gy] <= 11.6 | 0.5 | <= 11.6 | pass |
| LCTSC-Test-S3-102: Lungs D1000cc[Gy] <= 12.4 | 1.22 | <= 12.4 | pass |
| LCTSC-Test-S3-102: Lungs V12.5Gy[cc] <= 1000.0 | 232.7 | <= 1000.0 | informative |
