# Radiarch validation run 20261110-191147-f3a83c7 + 20261110-191603-f3a83c7

RESEARCH USE ONLY. NOT FOR CLINICAL USE. Radiarch is a research treatment-planning system; its plans, doses and evaluations must not be used to treat patients.

The cases ran one per process from commit f3a83c7: `protocol_batch_lctsc` (20261110-191147), `protocol_lung_vmat` (20261110-191603).

| Case | Status | Time (s) | Checks |
|---|---|---|---|
| protocol_batch_lctsc | **pass** | 1958.2 | 79 pass, 0 fail, 36 informative |
| protocol_lung_vmat | **fail** | 2213.8 | 38 pass, 6 fail, 10 informative |

## protocol_batch_lctsc — pass


| Check | Value | Target | Result |
|---|---|---|---|
| radiarch batch over 6 LCTSC thoraces: cases planned | 6 | = 6 | pass |
| LCTSC-Test-S1-101: deliverable | True | True | pass |
| LCTSC-Test-S1-101: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S1-101: planning goal SpinalCord Dmax <= 21.9 | 10.78 | <= 21.9 | informative |
| LCTSC-Test-S1-101: planning goal Esophagus Dmax <= 25.2 | 2.07 | <= 25.2 | informative |
| LCTSC-Test-S1-101: planning goal Heart Dmax <= 30.0 | 16.54 | <= 30.0 | informative |
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
| LCTSC-Test-S1-102: deliverable | True | True | pass |
| LCTSC-Test-S1-102: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S1-102: planning goal SpinalCord Dmax <= 21.9 | 10.76 | <= 21.9 | informative |
| LCTSC-Test-S1-102: planning goal Esophagus Dmax <= 25.2 | 4.09 | <= 25.2 | informative |
| LCTSC-Test-S1-102: planning goal Heart Dmax <= 30.0 | 20.99 | <= 30.0 | informative |
| LCTSC-Test-S1-102: PTV V100%[%] >= 95.0 | 95.44 | >= 95.0 | pass |
| LCTSC-Test-S1-102: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S1-102: PTV D0.03cc[%] <= 140.0 | 115.3 | <= 140.0 | informative |
| LCTSC-Test-S1-102: Lungs-GTV V20Gy[%] <= 10.0 | 3.18 | <= 10.0 | informative |
| LCTSC-Test-S1-102: SpinalCord D0.03cc[Gy] <= 21.9 | 10.28 | <= 21.9 | pass |
| LCTSC-Test-S1-102: SpinalCord D0.35cc[Gy] <= 18.0 | 9.53 | <= 18.0 | pass |
| LCTSC-Test-S1-102: SpinalCord D1.2cc[Gy] <= 12.3 | 7.74 | <= 12.3 | pass |
| LCTSC-Test-S1-102: Esophagus D0.03cc[Gy] <= 25.2 | 4.07 | <= 25.2 | pass |
| LCTSC-Test-S1-102: Esophagus D5cc[Gy] <= 17.7 | 1.93 | <= 17.7 | pass |
| LCTSC-Test-S1-102: Heart D0.03cc[Gy] <= 30.0 | 20.87 | <= 30.0 | pass |
| LCTSC-Test-S1-102: Heart D15cc[Gy] <= 24.0 | 10.65 | <= 24.0 | pass |
| LCTSC-Test-S1-102: Lungs D1500cc[Gy] <= 11.6 | 0.68 | <= 11.6 | pass |
| LCTSC-Test-S1-102: Lungs D1000cc[Gy] <= 12.4 | 1.38 | <= 12.4 | pass |
| LCTSC-Test-S1-102: Lungs V12.5Gy[cc] <= 1000.0 | 227.4 | <= 1000.0 | informative |
| LCTSC-Test-S2-101: deliverable | True | True | pass |
| LCTSC-Test-S2-101: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S2-101: planning goal SpinalCord Dmax <= 21.9 | 9.01 | <= 21.9 | informative |
| LCTSC-Test-S2-101: planning goal Esophagus Dmax <= 25.2 | 5.65 | <= 25.2 | informative |
| LCTSC-Test-S2-101: planning goal Heart Dmax <= 30.0 | 18.48 | <= 30.0 | informative |
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
| LCTSC-Test-S2-102: deliverable | True | True | pass |
| LCTSC-Test-S2-102: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S2-102: planning goal SpinalCord Dmax <= 21.9 | 9.41 | <= 21.9 | informative |
| LCTSC-Test-S2-102: planning goal Esophagus Dmax <= 25.2 | 3.98 | <= 25.2 | informative |
| LCTSC-Test-S2-102: planning goal Heart Dmax <= 30.0 | 9.08 | <= 30.0 | informative |
| LCTSC-Test-S2-102: PTV V100%[%] >= 95.0 | 95.2 | >= 95.0 | pass |
| LCTSC-Test-S2-102: PTV V90%[%] >= 99.0 | 99.84 | >= 99.0 | pass |
| LCTSC-Test-S2-102: PTV D0.03cc[%] <= 140.0 | 118.1 | <= 140.0 | informative |
| LCTSC-Test-S2-102: Lungs-GTV V20Gy[%] <= 10.0 | 2.06 | <= 10.0 | informative |
| LCTSC-Test-S2-102: SpinalCord D0.03cc[Gy] <= 21.9 | 9.35 | <= 21.9 | pass |
| LCTSC-Test-S2-102: SpinalCord D0.35cc[Gy] <= 18.0 | 8.85 | <= 18.0 | pass |
| LCTSC-Test-S2-102: SpinalCord D1.2cc[Gy] <= 12.3 | 8.22 | <= 12.3 | pass |
| LCTSC-Test-S2-102: Esophagus D0.03cc[Gy] <= 25.2 | 3.82 | <= 25.2 | pass |
| LCTSC-Test-S2-102: Esophagus D5cc[Gy] <= 17.7 | 2.22 | <= 17.7 | pass |
| LCTSC-Test-S2-102: Heart D0.03cc[Gy] <= 30.0 | 9.07 | <= 30.0 | pass |
| LCTSC-Test-S2-102: Heart D15cc[Gy] <= 24.0 | 5.92 | <= 24.0 | pass |
| LCTSC-Test-S2-102: Lungs D1500cc[Gy] <= 11.6 | 1.05 | <= 11.6 | pass |
| LCTSC-Test-S2-102: Lungs D1000cc[Gy] <= 12.4 | 2.17 | <= 12.4 | pass |
| LCTSC-Test-S2-102: Lungs V12.5Gy[cc] <= 1000.0 | 237.9 | <= 1000.0 | informative |
| LCTSC-Test-S3-101: deliverable | True | True | pass |
| LCTSC-Test-S3-101: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S3-101: planning goal SpinalCord Dmax <= 21.9 | 6.22 | <= 21.9 | informative |
| LCTSC-Test-S3-101: planning goal Esophagus Dmax <= 25.2 | 3.69 | <= 25.2 | informative |
| LCTSC-Test-S3-101: planning goal Heart Dmax <= 30.0 | 17.91 | <= 30.0 | informative |
| LCTSC-Test-S3-101: PTV V100%[%] >= 95.0 | 95.29 | >= 95.0 | pass |
| LCTSC-Test-S3-101: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S3-101: PTV D0.03cc[%] <= 140.0 | 114.1 | <= 140.0 | informative |
| LCTSC-Test-S3-101: Lungs-GTV V20Gy[%] <= 10.0 | 4.01 | <= 10.0 | informative |
| LCTSC-Test-S3-101: SpinalCord D0.03cc[Gy] <= 21.9 | 5.63 | <= 21.9 | pass |
| LCTSC-Test-S3-101: SpinalCord D0.35cc[Gy] <= 18.0 | 4.37 | <= 18.0 | pass |
| LCTSC-Test-S3-101: SpinalCord D1.2cc[Gy] <= 12.3 | 3.54 | <= 12.3 | pass |
| LCTSC-Test-S3-101: Esophagus D0.03cc[Gy] <= 25.2 | 3.61 | <= 25.2 | pass |
| LCTSC-Test-S3-101: Esophagus D5cc[Gy] <= 17.7 | 2.57 | <= 17.7 | pass |
| LCTSC-Test-S3-101: Heart D0.03cc[Gy] <= 30.0 | 17.72 | <= 30.0 | pass |
| LCTSC-Test-S3-101: Heart D15cc[Gy] <= 24.0 | 8.25 | <= 24.0 | pass |
| LCTSC-Test-S3-101: Lungs D1500cc[Gy] <= 11.6 | 0.27 | <= 11.6 | pass |
| LCTSC-Test-S3-101: Lungs D1000cc[Gy] <= 12.4 | 0.67 | <= 12.4 | pass |
| LCTSC-Test-S3-101: Lungs V12.5Gy[cc] <= 1000.0 | 186.7 | <= 1000.0 | informative |
| LCTSC-Test-S3-102: deliverable | True | True | pass |
| LCTSC-Test-S3-102: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S3-102: planning goal SpinalCord Dmax <= 21.9 | 9.96 | <= 21.9 | informative |
| LCTSC-Test-S3-102: planning goal Esophagus Dmax <= 25.2 | 5.76 | <= 25.2 | informative |
| LCTSC-Test-S3-102: planning goal Heart Dmax <= 30.0 | 19.06 | <= 30.0 | informative |
| LCTSC-Test-S3-102: PTV V100%[%] >= 95.0 | 95.85 | >= 95.0 | pass |
| LCTSC-Test-S3-102: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S3-102: PTV D0.03cc[%] <= 140.0 | 110.7 | <= 140.0 | informative |
| LCTSC-Test-S3-102: Lungs-GTV V20Gy[%] <= 10.0 | 2.58 | <= 10.0 | informative |
| LCTSC-Test-S3-102: SpinalCord D0.03cc[Gy] <= 21.9 | 9.76 | <= 21.9 | pass |
| LCTSC-Test-S3-102: SpinalCord D0.35cc[Gy] <= 18.0 | 8.58 | <= 18.0 | pass |
| LCTSC-Test-S3-102: SpinalCord D1.2cc[Gy] <= 12.3 | 7.02 | <= 12.3 | pass |
| LCTSC-Test-S3-102: Esophagus D0.03cc[Gy] <= 25.2 | 5.43 | <= 25.2 | pass |
| LCTSC-Test-S3-102: Esophagus D5cc[Gy] <= 17.7 | 3.71 | <= 17.7 | pass |
| LCTSC-Test-S3-102: Heart D0.03cc[Gy] <= 30.0 | 18.89 | <= 30.0 | pass |
| LCTSC-Test-S3-102: Heart D15cc[Gy] <= 24.0 | 8.92 | <= 24.0 | pass |
| LCTSC-Test-S3-102: Lungs D1500cc[Gy] <= 11.6 | 0.51 | <= 11.6 | pass |
| LCTSC-Test-S3-102: Lungs D1000cc[Gy] <= 12.4 | 1.29 | <= 12.4 | pass |
| LCTSC-Test-S3-102: Lungs V12.5Gy[cc] <= 1000.0 | 236.3 | <= 1000.0 | informative |

## protocol_lung_vmat — fail


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
| LCTSC-Test-S1-101: PTV V60Gy[%] >= 95.0 (protocol) | 95.94 | >= 95.0 | pass |
| LCTSC-Test-S1-101: PTV V60Gy[%] >= 95.0: protocol against the recorded harness run | 95.94 | 95.6 ± 0.96 | pass |
| LCTSC-Test-S1-101: PTV D0.03cc[Gy] <= 72.0 (protocol) | 64.8 | <= 72.0 | informative |
| LCTSC-Test-S1-101: PTV D0.03cc[Gy] <= 72.0: protocol against the recorded harness run | 64.8 | 65.25 ± 0.65 | pass |
| LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 37.0 (protocol) | 14.4 | <= 37.0 | pass |
| LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 37.0: protocol against the recorded harness run | 14.4 | 14.78 ± 0.15 | FAIL |
| LCTSC-Test-S1-101: Lungs-GTV Dmean[Gy] <= 20.0 (protocol) | 8.2 | <= 20.0 | pass |
| LCTSC-Test-S1-101: Lungs-GTV Dmean[Gy] <= 20.0: protocol against the recorded harness run | 8.2 | 8.37 ± 0.08 | FAIL |
| LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 50.5 (protocol) | 14.85 | <= 50.5 | pass |
| LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 50.5: protocol against the recorded harness run | 14.85 | 14.89 ± 0.15 | pass |
| LCTSC-Test-S1-101: Esophagus Dmean[Gy] <= 34.0 (protocol) | 3.21 | <= 34.0 | informative |
| LCTSC-Test-S1-101: Esophagus Dmean[Gy] <= 34.0: protocol against the recorded harness run | 3.21 | 3.38 ± 0.05 | FAIL |
| LCTSC-Test-S1-101: Heart V60Gy[%] <= 33.0 (protocol) | 0 | <= 33.0 | informative |
| LCTSC-Test-S1-101: Heart V60Gy[%] <= 33.0: protocol against the recorded harness run | 0 | 0.0 ± 0.05 | pass |
| LCTSC-Test-S1-101: Heart V45Gy[%] <= 66.0 (protocol) | 0 | <= 66.0 | informative |
| LCTSC-Test-S1-101: Heart V45Gy[%] <= 66.0: protocol against the recorded harness run | 0 | 0.0 ± 0.05 | pass |
| LCTSC-Test-S1-101: Heart V40Gy[%] <= 100.0 (protocol) | 0 | <= 100.0 | informative |
| LCTSC-Test-S1-101: Heart V40Gy[%] <= 100.0: protocol against the recorded harness run | 0 | 0.0 ± 0.05 | pass |
| LCTSC-Test-S2-101: protocol run deliverable | True | True | pass |
| LCTSC-Test-S2-101: PTV V60Gy[%] >= 95.0 (protocol) | 95.96 | >= 95.0 | pass |
| LCTSC-Test-S2-101: PTV V60Gy[%] >= 95.0: protocol against the recorded harness run | 95.96 | 95.62 ± 0.96 | pass |
| LCTSC-Test-S2-101: PTV D0.03cc[Gy] <= 72.0 (protocol) | 65.39 | <= 72.0 | informative |
| LCTSC-Test-S2-101: PTV D0.03cc[Gy] <= 72.0: protocol against the recorded harness run | 65.39 | 65.25 ± 0.65 | pass |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 37.0 (protocol) | 13.88 | <= 37.0 | pass |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 37.0: protocol against the recorded harness run | 13.88 | 14.01 ± 0.14 | pass |
| LCTSC-Test-S2-101: Lungs-GTV Dmean[Gy] <= 20.0 (protocol) | 8.54 | <= 20.0 | pass |
| LCTSC-Test-S2-101: Lungs-GTV Dmean[Gy] <= 20.0: protocol against the recorded harness run | 8.54 | 8.68 ± 0.09 | FAIL |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5 (protocol) | 16.4 | <= 50.5 | pass |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5: protocol against the recorded harness run | 16.4 | 15.65 ± 0.16 | FAIL |
| LCTSC-Test-S2-101: Esophagus Dmean[Gy] <= 34.0 (protocol) | 3.14 | <= 34.0 | informative |
| LCTSC-Test-S2-101: Esophagus Dmean[Gy] <= 34.0: protocol against the recorded harness run | 3.14 | 3.24 ± 0.05 | FAIL |
| LCTSC-Test-S2-101: Heart V60Gy[%] <= 33.0 (protocol) | 0 | <= 33.0 | informative |
| LCTSC-Test-S2-101: Heart V60Gy[%] <= 33.0: protocol against the recorded harness run | 0 | 0.0 ± 0.05 | pass |
| LCTSC-Test-S2-101: Heart V45Gy[%] <= 66.0 (protocol) | 0.15 | <= 66.0 | informative |
| LCTSC-Test-S2-101: Heart V45Gy[%] <= 66.0: protocol against the recorded harness run | 0.15 | 0.19 ± 0.05 | pass |
| LCTSC-Test-S2-101: Heart V40Gy[%] <= 100.0 (protocol) | 0.38 | <= 100.0 | informative |
| LCTSC-Test-S2-101: Heart V40Gy[%] <= 100.0: protocol against the recorded harness run | 0.38 | 0.42 ± 0.05 | pass |
