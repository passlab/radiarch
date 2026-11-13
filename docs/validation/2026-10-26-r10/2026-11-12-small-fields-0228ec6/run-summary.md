# Radiarch validation run 20261112-140015-0228ec6 + 20261112-232403-9357fdc

RESEARCH USE ONLY. NOT FOR CLINICAL USE. Radiarch is a research treatment-planning system; its plans, doses and evaluations must not be used to treat patients.

The cases ran one per process: `protocol_batch_lctsc` (20261112-140015, commit 0228ec6), `protocol_lung_vmat` (20261112-232403, commit 9357fdc).

| Case | Status | Time (s) | Checks |
|---|---|---|---|
| protocol_batch_lctsc | **pass** | 2018.9 | 79 pass, 0 fail, 36 informative |
| protocol_lung_vmat | **pass** | 2219.1 | 44 pass, 0 fail, 10 informative |

## protocol_batch_lctsc — pass


| Check | Value | Target | Result |
|---|---|---|---|
| radiarch batch over 6 LCTSC thoraces: cases planned | 6 | = 6 | pass |
| LCTSC-Test-S1-101: deliverable | True | True | pass |
| LCTSC-Test-S1-101: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S1-101: planning goal SpinalCord Dmax <= 21.9 | 9.57 | <= 21.9 | informative |
| LCTSC-Test-S1-101: planning goal Esophagus Dmax <= 25.2 | 2.3 | <= 25.2 | informative |
| LCTSC-Test-S1-101: planning goal Heart Dmax <= 30.0 | 11.59 | <= 30.0 | informative |
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
| LCTSC-Test-S1-102: deliverable | True | True | pass |
| LCTSC-Test-S1-102: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S1-102: planning goal SpinalCord Dmax <= 21.9 | 10.94 | <= 21.9 | informative |
| LCTSC-Test-S1-102: planning goal Esophagus Dmax <= 25.2 | 6.57 | <= 25.2 | informative |
| LCTSC-Test-S1-102: planning goal Heart Dmax <= 30.0 | 15.03 | <= 30.0 | informative |
| LCTSC-Test-S1-102: PTV V100%[%] >= 95.0 | 95.61 | >= 95.0 | pass |
| LCTSC-Test-S1-102: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S1-102: PTV D0.03cc[%] <= 140.0 | 116.1 | <= 140.0 | informative |
| LCTSC-Test-S1-102: Lungs-GTV V20Gy[%] <= 10.0 | 3.15 | <= 10.0 | informative |
| LCTSC-Test-S1-102: SpinalCord D0.03cc[Gy] <= 21.9 | 10.72 | <= 21.9 | pass |
| LCTSC-Test-S1-102: SpinalCord D0.35cc[Gy] <= 18.0 | 10.21 | <= 18.0 | pass |
| LCTSC-Test-S1-102: SpinalCord D1.2cc[Gy] <= 12.3 | 9.41 | <= 12.3 | pass |
| LCTSC-Test-S1-102: Esophagus D0.03cc[Gy] <= 25.2 | 6.4 | <= 25.2 | pass |
| LCTSC-Test-S1-102: Esophagus D5cc[Gy] <= 17.7 | 1.68 | <= 17.7 | pass |
| LCTSC-Test-S1-102: Heart D0.03cc[Gy] <= 30.0 | 14.94 | <= 30.0 | pass |
| LCTSC-Test-S1-102: Heart D15cc[Gy] <= 24.0 | 9.01 | <= 24.0 | pass |
| LCTSC-Test-S1-102: Lungs D1500cc[Gy] <= 11.6 | 0.63 | <= 11.6 | pass |
| LCTSC-Test-S1-102: Lungs D1000cc[Gy] <= 12.4 | 1.22 | <= 12.4 | pass |
| LCTSC-Test-S1-102: Lungs V12.5Gy[cc] <= 1000.0 | 240.1 | <= 1000.0 | informative |
| LCTSC-Test-S2-101: deliverable | True | True | pass |
| LCTSC-Test-S2-101: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S2-101: planning goal SpinalCord Dmax <= 21.9 | 8.68 | <= 21.9 | informative |
| LCTSC-Test-S2-101: planning goal Esophagus Dmax <= 25.2 | 5.53 | <= 25.2 | informative |
| LCTSC-Test-S2-101: planning goal Heart Dmax <= 30.0 | 17.8 | <= 30.0 | informative |
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
| LCTSC-Test-S2-102: deliverable | True | True | pass |
| LCTSC-Test-S2-102: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S2-102: planning goal SpinalCord Dmax <= 21.9 | 10.68 | <= 21.9 | informative |
| LCTSC-Test-S2-102: planning goal Esophagus Dmax <= 25.2 | 2.94 | <= 25.2 | informative |
| LCTSC-Test-S2-102: planning goal Heart Dmax <= 30.0 | 8.78 | <= 30.0 | informative |
| LCTSC-Test-S2-102: PTV V100%[%] >= 95.0 | 95.84 | >= 95.0 | pass |
| LCTSC-Test-S2-102: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S2-102: PTV D0.03cc[%] <= 140.0 | 119.3 | <= 140.0 | informative |
| LCTSC-Test-S2-102: Lungs-GTV V20Gy[%] <= 10.0 | 2.04 | <= 10.0 | informative |
| LCTSC-Test-S2-102: SpinalCord D0.03cc[Gy] <= 21.9 | 10.49 | <= 21.9 | pass |
| LCTSC-Test-S2-102: SpinalCord D0.35cc[Gy] <= 18.0 | 9.65 | <= 18.0 | pass |
| LCTSC-Test-S2-102: SpinalCord D1.2cc[Gy] <= 12.3 | 8.93 | <= 12.3 | pass |
| LCTSC-Test-S2-102: Esophagus D0.03cc[Gy] <= 25.2 | 2.93 | <= 25.2 | pass |
| LCTSC-Test-S2-102: Esophagus D5cc[Gy] <= 17.7 | 1.95 | <= 17.7 | pass |
| LCTSC-Test-S2-102: Heart D0.03cc[Gy] <= 30.0 | 8.75 | <= 30.0 | pass |
| LCTSC-Test-S2-102: Heart D15cc[Gy] <= 24.0 | 6.12 | <= 24.0 | pass |
| LCTSC-Test-S2-102: Lungs D1500cc[Gy] <= 11.6 | 0.99 | <= 11.6 | pass |
| LCTSC-Test-S2-102: Lungs D1000cc[Gy] <= 12.4 | 2.2 | <= 12.4 | pass |
| LCTSC-Test-S2-102: Lungs V12.5Gy[cc] <= 1000.0 | 251.4 | <= 1000.0 | informative |
| LCTSC-Test-S3-101: deliverable | True | True | pass |
| LCTSC-Test-S3-101: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S3-101: planning goal SpinalCord Dmax <= 21.9 | 8.9 | <= 21.9 | informative |
| LCTSC-Test-S3-101: planning goal Esophagus Dmax <= 25.2 | 4.46 | <= 25.2 | informative |
| LCTSC-Test-S3-101: planning goal Heart Dmax <= 30.0 | 15.57 | <= 30.0 | informative |
| LCTSC-Test-S3-101: PTV V100%[%] >= 95.0 | 95.29 | >= 95.0 | pass |
| LCTSC-Test-S3-101: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S3-101: PTV D0.03cc[%] <= 140.0 | 115.2 | <= 140.0 | informative |
| LCTSC-Test-S3-101: Lungs-GTV V20Gy[%] <= 10.0 | 4.09 | <= 10.0 | informative |
| LCTSC-Test-S3-101: SpinalCord D0.03cc[Gy] <= 21.9 | 8.47 | <= 21.9 | pass |
| LCTSC-Test-S3-101: SpinalCord D0.35cc[Gy] <= 18.0 | 7.72 | <= 18.0 | pass |
| LCTSC-Test-S3-101: SpinalCord D1.2cc[Gy] <= 12.3 | 6.36 | <= 12.3 | pass |
| LCTSC-Test-S3-101: Esophagus D0.03cc[Gy] <= 25.2 | 4.37 | <= 25.2 | pass |
| LCTSC-Test-S3-101: Esophagus D5cc[Gy] <= 17.7 | 2.15 | <= 17.7 | pass |
| LCTSC-Test-S3-101: Heart D0.03cc[Gy] <= 30.0 | 15.34 | <= 30.0 | pass |
| LCTSC-Test-S3-101: Heart D15cc[Gy] <= 24.0 | 8.88 | <= 24.0 | pass |
| LCTSC-Test-S3-101: Lungs D1500cc[Gy] <= 11.6 | 0.28 | <= 11.6 | pass |
| LCTSC-Test-S3-101: Lungs D1000cc[Gy] <= 12.4 | 0.68 | <= 12.4 | pass |
| LCTSC-Test-S3-101: Lungs V12.5Gy[cc] <= 1000.0 | 187.2 | <= 1000.0 | informative |
| LCTSC-Test-S3-102: deliverable | True | True | pass |
| LCTSC-Test-S3-102: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S3-102: planning goal SpinalCord Dmax <= 21.9 | 11.08 | <= 21.9 | informative |
| LCTSC-Test-S3-102: planning goal Esophagus Dmax <= 25.2 | 6.03 | <= 25.2 | informative |
| LCTSC-Test-S3-102: planning goal Heart Dmax <= 30.0 | 17.48 | <= 30.0 | informative |
| LCTSC-Test-S3-102: PTV V100%[%] >= 95.0 | 95.68 | >= 95.0 | pass |
| LCTSC-Test-S3-102: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S3-102: PTV D0.03cc[%] <= 140.0 | 112.4 | <= 140.0 | informative |
| LCTSC-Test-S3-102: Lungs-GTV V20Gy[%] <= 10.0 | 2.68 | <= 10.0 | informative |
| LCTSC-Test-S3-102: SpinalCord D0.03cc[Gy] <= 21.9 | 10.49 | <= 21.9 | pass |
| LCTSC-Test-S3-102: SpinalCord D0.35cc[Gy] <= 18.0 | 9.75 | <= 18.0 | pass |
| LCTSC-Test-S3-102: SpinalCord D1.2cc[Gy] <= 12.3 | 8.8 | <= 12.3 | pass |
| LCTSC-Test-S3-102: Esophagus D0.03cc[Gy] <= 25.2 | 5.82 | <= 25.2 | pass |
| LCTSC-Test-S3-102: Esophagus D5cc[Gy] <= 17.7 | 3.4 | <= 17.7 | pass |
| LCTSC-Test-S3-102: Heart D0.03cc[Gy] <= 30.0 | 17.29 | <= 30.0 | pass |
| LCTSC-Test-S3-102: Heart D15cc[Gy] <= 24.0 | 9.71 | <= 24.0 | pass |
| LCTSC-Test-S3-102: Lungs D1500cc[Gy] <= 11.6 | 0.51 | <= 11.6 | pass |
| LCTSC-Test-S3-102: Lungs D1000cc[Gy] <= 12.4 | 1.21 | <= 12.4 | pass |
| LCTSC-Test-S3-102: Lungs V12.5Gy[cc] <= 1000.0 | 235.1 | <= 1000.0 | informative |

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
| LCTSC-Test-S1-101: PTV D0.03cc[Gy] <= 72.0 (protocol) | 66.16 | <= 72.0 | informative |
| LCTSC-Test-S1-101: PTV D0.03cc[Gy] <= 72.0: protocol against the recorded harness run | 66.16 | 66.16 ± 0.66 | pass |
| LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 37.0 (protocol) | 14.96 | <= 37.0 | pass |
| LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 37.0: protocol against the recorded harness run | 14.96 | 14.96 ± 0.15 | pass |
| LCTSC-Test-S1-101: Lungs-GTV Dmean[Gy] <= 20.0 (protocol) | 8.07 | <= 20.0 | pass |
| LCTSC-Test-S1-101: Lungs-GTV Dmean[Gy] <= 20.0: protocol against the recorded harness run | 8.07 | 8.07 ± 0.08 | pass |
| LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 50.5 (protocol) | 17.59 | <= 50.5 | pass |
| LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 50.5: protocol against the recorded harness run | 17.59 | 17.59 ± 0.18 | pass |
| LCTSC-Test-S1-101: Esophagus Dmean[Gy] <= 34.0 (protocol) | 2.48 | <= 34.0 | informative |
| LCTSC-Test-S1-101: Esophagus Dmean[Gy] <= 34.0: protocol against the recorded harness run | 2.48 | 2.48 ± 0.05 | pass |
| LCTSC-Test-S1-101: Heart V60Gy[%] <= 33.0 (protocol) | 0 | <= 33.0 | informative |
| LCTSC-Test-S1-101: Heart V60Gy[%] <= 33.0: protocol against the recorded harness run | 0 | 0.0 ± 0.05 | pass |
| LCTSC-Test-S1-101: Heart V45Gy[%] <= 66.0 (protocol) | 0 | <= 66.0 | informative |
| LCTSC-Test-S1-101: Heart V45Gy[%] <= 66.0: protocol against the recorded harness run | 0 | 0.0 ± 0.05 | pass |
| LCTSC-Test-S1-101: Heart V40Gy[%] <= 100.0 (protocol) | 0 | <= 100.0 | informative |
| LCTSC-Test-S1-101: Heart V40Gy[%] <= 100.0: protocol against the recorded harness run | 0 | 0.0 ± 0.05 | pass |
| LCTSC-Test-S2-101: protocol run deliverable | True | True | pass |
| LCTSC-Test-S2-101: PTV V60Gy[%] >= 95.0 (protocol) | 95.58 | >= 95.0 | pass |
| LCTSC-Test-S2-101: PTV V60Gy[%] >= 95.0: protocol against the recorded harness run | 95.58 | 95.58 ± 0.96 | pass |
| LCTSC-Test-S2-101: PTV D0.03cc[Gy] <= 72.0 (protocol) | 65.34 | <= 72.0 | informative |
| LCTSC-Test-S2-101: PTV D0.03cc[Gy] <= 72.0: protocol against the recorded harness run | 65.34 | 65.34 ± 0.65 | pass |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 37.0 (protocol) | 13.72 | <= 37.0 | pass |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 37.0: protocol against the recorded harness run | 13.72 | 13.72 ± 0.14 | pass |
| LCTSC-Test-S2-101: Lungs-GTV Dmean[Gy] <= 20.0 (protocol) | 8.39 | <= 20.0 | pass |
| LCTSC-Test-S2-101: Lungs-GTV Dmean[Gy] <= 20.0: protocol against the recorded harness run | 8.39 | 8.39 ± 0.08 | pass |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5 (protocol) | 18.85 | <= 50.5 | pass |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5: protocol against the recorded harness run | 18.85 | 18.85 ± 0.19 | pass |
| LCTSC-Test-S2-101: Esophagus Dmean[Gy] <= 34.0 (protocol) | 3.38 | <= 34.0 | informative |
| LCTSC-Test-S2-101: Esophagus Dmean[Gy] <= 34.0: protocol against the recorded harness run | 3.38 | 3.38 ± 0.05 | pass |
| LCTSC-Test-S2-101: Heart V60Gy[%] <= 33.0 (protocol) | 0 | <= 33.0 | informative |
| LCTSC-Test-S2-101: Heart V60Gy[%] <= 33.0: protocol against the recorded harness run | 0 | 0.0 ± 0.05 | pass |
| LCTSC-Test-S2-101: Heart V45Gy[%] <= 66.0 (protocol) | 0.14 | <= 66.0 | informative |
| LCTSC-Test-S2-101: Heart V45Gy[%] <= 66.0: protocol against the recorded harness run | 0.14 | 0.14 ± 0.05 | pass |
| LCTSC-Test-S2-101: Heart V40Gy[%] <= 100.0 (protocol) | 0.38 | <= 100.0 | informative |
| LCTSC-Test-S2-101: Heart V40Gy[%] <= 100.0: protocol against the recorded harness run | 0.38 | 0.38 ± 0.05 | pass |
