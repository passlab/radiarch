# Radiarch validation run 20261107-022804-b11713b + 20261107-023423-b11713b

RESEARCH USE ONLY. NOT FOR CLINICAL USE. Radiarch is a research treatment-planning system; its plans, doses and evaluations must not be used to treat patients.

The cases ran one per process from commit b11713b: `protocol_batch_lctsc` (20261107-022804), `protocol_lung_vmat` (20261107-023423).

| Case | Status | Time (s) | Checks |
|---|---|---|---|
| protocol_batch_lctsc | **pass** | 1919.3 | 79 pass, 0 fail, 36 informative |
| protocol_lung_vmat | **pass** | 2298.0 | 44 pass, 0 fail, 10 informative |

## protocol_batch_lctsc — pass


| Check | Value | Target | Result |
|---|---|---|---|
| radiarch batch over 6 LCTSC thoraces: cases planned | 6 | = 6 | pass |
| LCTSC-Test-S1-101: deliverable | True | True | pass |
| LCTSC-Test-S1-101: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S1-101: planning goal SpinalCord Dmax <= 21.9 | 10.72 | <= 21.9 | informative |
| LCTSC-Test-S1-101: planning goal Esophagus Dmax <= 25.2 | 2.19 | <= 25.2 | informative |
| LCTSC-Test-S1-101: planning goal Heart Dmax <= 30.0 | 16.83 | <= 30.0 | informative |
| LCTSC-Test-S1-101: PTV V100%[%] >= 95.0 | 95.44 | >= 95.0 | pass |
| LCTSC-Test-S1-101: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S1-101: PTV D0.03cc[%] <= 140.0 | 115.3 | <= 140.0 | informative |
| LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 10.0 | 2.69 | <= 10.0 | informative |
| LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 21.9 | 10.29 | <= 21.9 | pass |
| LCTSC-Test-S1-101: SpinalCord D0.35cc[Gy] <= 18.0 | 9.21 | <= 18.0 | pass |
| LCTSC-Test-S1-101: SpinalCord D1.2cc[Gy] <= 12.3 | 8.1 | <= 12.3 | pass |
| LCTSC-Test-S1-101: Esophagus D0.03cc[Gy] <= 25.2 | 2.13 | <= 25.2 | pass |
| LCTSC-Test-S1-101: Esophagus D5cc[Gy] <= 17.7 | 0.68 | <= 17.7 | pass |
| LCTSC-Test-S1-101: Heart D0.03cc[Gy] <= 30.0 | 16.69 | <= 30.0 | pass |
| LCTSC-Test-S1-101: Heart D15cc[Gy] <= 24.0 | 10.74 | <= 24.0 | pass |
| LCTSC-Test-S1-101: Lungs D1500cc[Gy] <= 11.6 | 0.55 | <= 11.6 | pass |
| LCTSC-Test-S1-101: Lungs D1000cc[Gy] <= 12.4 | 1.2 | <= 12.4 | pass |
| LCTSC-Test-S1-101: Lungs V12.5Gy[cc] <= 1000.0 | 229.9 | <= 1000.0 | informative |
| LCTSC-Test-S1-102: deliverable | True | True | pass |
| LCTSC-Test-S1-102: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S1-102: planning goal SpinalCord Dmax <= 21.9 | 10.1 | <= 21.9 | informative |
| LCTSC-Test-S1-102: planning goal Esophagus Dmax <= 25.2 | 4.44 | <= 25.2 | informative |
| LCTSC-Test-S1-102: planning goal Heart Dmax <= 30.0 | 20.9 | <= 30.0 | informative |
| LCTSC-Test-S1-102: PTV V100%[%] >= 95.0 | 95.44 | >= 95.0 | pass |
| LCTSC-Test-S1-102: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S1-102: PTV D0.03cc[%] <= 140.0 | 115 | <= 140.0 | informative |
| LCTSC-Test-S1-102: Lungs-GTV V20Gy[%] <= 10.0 | 3.18 | <= 10.0 | informative |
| LCTSC-Test-S1-102: SpinalCord D0.03cc[Gy] <= 21.9 | 9.74 | <= 21.9 | pass |
| LCTSC-Test-S1-102: SpinalCord D0.35cc[Gy] <= 18.0 | 9.1 | <= 18.0 | pass |
| LCTSC-Test-S1-102: SpinalCord D1.2cc[Gy] <= 12.3 | 7.49 | <= 12.3 | pass |
| LCTSC-Test-S1-102: Esophagus D0.03cc[Gy] <= 25.2 | 4.28 | <= 25.2 | pass |
| LCTSC-Test-S1-102: Esophagus D5cc[Gy] <= 17.7 | 2.09 | <= 17.7 | pass |
| LCTSC-Test-S1-102: Heart D0.03cc[Gy] <= 30.0 | 20.77 | <= 30.0 | pass |
| LCTSC-Test-S1-102: Heart D15cc[Gy] <= 24.0 | 10.35 | <= 24.0 | pass |
| LCTSC-Test-S1-102: Lungs D1500cc[Gy] <= 11.6 | 0.69 | <= 11.6 | pass |
| LCTSC-Test-S1-102: Lungs D1000cc[Gy] <= 12.4 | 1.43 | <= 12.4 | pass |
| LCTSC-Test-S1-102: Lungs V12.5Gy[cc] <= 1000.0 | 225.6 | <= 1000.0 | informative |
| LCTSC-Test-S2-101: deliverable | True | True | pass |
| LCTSC-Test-S2-101: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S2-101: planning goal SpinalCord Dmax <= 21.9 | 9.32 | <= 21.9 | informative |
| LCTSC-Test-S2-101: planning goal Esophagus Dmax <= 25.2 | 5.62 | <= 25.2 | informative |
| LCTSC-Test-S2-101: planning goal Heart Dmax <= 30.0 | 18.58 | <= 30.0 | informative |
| LCTSC-Test-S2-101: PTV V100%[%] >= 95.0 | 95.35 | >= 95.0 | pass |
| LCTSC-Test-S2-101: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S2-101: PTV D0.03cc[%] <= 140.0 | 113 | <= 140.0 | informative |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 10.0 | 2.79 | <= 10.0 | informative |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 21.9 | 9.21 | <= 21.9 | pass |
| LCTSC-Test-S2-101: SpinalCord D0.35cc[Gy] <= 18.0 | 8.4 | <= 18.0 | pass |
| LCTSC-Test-S2-101: SpinalCord D1.2cc[Gy] <= 12.3 | 7.2 | <= 12.3 | pass |
| LCTSC-Test-S2-101: Esophagus D0.03cc[Gy] <= 25.2 | 5.43 | <= 25.2 | pass |
| LCTSC-Test-S2-101: Esophagus D5cc[Gy] <= 17.7 | 3.4 | <= 17.7 | pass |
| LCTSC-Test-S2-101: Heart D0.03cc[Gy] <= 30.0 | 18.14 | <= 30.0 | pass |
| LCTSC-Test-S2-101: Heart D15cc[Gy] <= 24.0 | 10.59 | <= 24.0 | pass |
| LCTSC-Test-S2-101: Lungs D1500cc[Gy] <= 11.6 | 0.68 | <= 11.6 | pass |
| LCTSC-Test-S2-101: Lungs D1000cc[Gy] <= 12.4 | 1.34 | <= 12.4 | pass |
| LCTSC-Test-S2-101: Lungs V12.5Gy[cc] <= 1000.0 | 219.7 | <= 1000.0 | informative |
| LCTSC-Test-S2-102: deliverable | True | True | pass |
| LCTSC-Test-S2-102: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S2-102: planning goal SpinalCord Dmax <= 21.9 | 9.25 | <= 21.9 | informative |
| LCTSC-Test-S2-102: planning goal Esophagus Dmax <= 25.2 | 4 | <= 25.2 | informative |
| LCTSC-Test-S2-102: planning goal Heart Dmax <= 30.0 | 9.05 | <= 30.0 | informative |
| LCTSC-Test-S2-102: PTV V100%[%] >= 95.0 | 95.04 | >= 95.0 | pass |
| LCTSC-Test-S2-102: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S2-102: PTV D0.03cc[%] <= 140.0 | 117.2 | <= 140.0 | informative |
| LCTSC-Test-S2-102: Lungs-GTV V20Gy[%] <= 10.0 | 2.08 | <= 10.0 | informative |
| LCTSC-Test-S2-102: SpinalCord D0.03cc[Gy] <= 21.9 | 9.2 | <= 21.9 | pass |
| LCTSC-Test-S2-102: SpinalCord D0.35cc[Gy] <= 18.0 | 8.72 | <= 18.0 | pass |
| LCTSC-Test-S2-102: SpinalCord D1.2cc[Gy] <= 12.3 | 8.11 | <= 12.3 | pass |
| LCTSC-Test-S2-102: Esophagus D0.03cc[Gy] <= 25.2 | 3.85 | <= 25.2 | pass |
| LCTSC-Test-S2-102: Esophagus D5cc[Gy] <= 17.7 | 2.16 | <= 17.7 | pass |
| LCTSC-Test-S2-102: Heart D0.03cc[Gy] <= 30.0 | 9.04 | <= 30.0 | pass |
| LCTSC-Test-S2-102: Heart D15cc[Gy] <= 24.0 | 6.01 | <= 24.0 | pass |
| LCTSC-Test-S2-102: Lungs D1500cc[Gy] <= 11.6 | 1.06 | <= 11.6 | pass |
| LCTSC-Test-S2-102: Lungs D1000cc[Gy] <= 12.4 | 2.24 | <= 12.4 | pass |
| LCTSC-Test-S2-102: Lungs V12.5Gy[cc] <= 1000.0 | 237.5 | <= 1000.0 | informative |
| LCTSC-Test-S3-101: deliverable | True | True | pass |
| LCTSC-Test-S3-101: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S3-101: planning goal SpinalCord Dmax <= 21.9 | 6.2 | <= 21.9 | informative |
| LCTSC-Test-S3-101: planning goal Esophagus Dmax <= 25.2 | 3.69 | <= 25.2 | informative |
| LCTSC-Test-S3-101: planning goal Heart Dmax <= 30.0 | 17.93 | <= 30.0 | informative |
| LCTSC-Test-S3-101: PTV V100%[%] >= 95.0 | 95.45 | >= 95.0 | pass |
| LCTSC-Test-S3-101: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S3-101: PTV D0.03cc[%] <= 140.0 | 114.6 | <= 140.0 | informative |
| LCTSC-Test-S3-101: Lungs-GTV V20Gy[%] <= 10.0 | 4.07 | <= 10.0 | informative |
| LCTSC-Test-S3-101: SpinalCord D0.03cc[Gy] <= 21.9 | 5.61 | <= 21.9 | pass |
| LCTSC-Test-S3-101: SpinalCord D0.35cc[Gy] <= 18.0 | 4.36 | <= 18.0 | pass |
| LCTSC-Test-S3-101: SpinalCord D1.2cc[Gy] <= 12.3 | 3.56 | <= 12.3 | pass |
| LCTSC-Test-S3-101: Esophagus D0.03cc[Gy] <= 25.2 | 3.61 | <= 25.2 | pass |
| LCTSC-Test-S3-101: Esophagus D5cc[Gy] <= 17.7 | 2.59 | <= 17.7 | pass |
| LCTSC-Test-S3-101: Heart D0.03cc[Gy] <= 30.0 | 17.72 | <= 30.0 | pass |
| LCTSC-Test-S3-101: Heart D15cc[Gy] <= 24.0 | 8.21 | <= 24.0 | pass |
| LCTSC-Test-S3-101: Lungs D1500cc[Gy] <= 11.6 | 0.27 | <= 11.6 | pass |
| LCTSC-Test-S3-101: Lungs D1000cc[Gy] <= 12.4 | 0.69 | <= 12.4 | pass |
| LCTSC-Test-S3-101: Lungs V12.5Gy[cc] <= 1000.0 | 187.7 | <= 1000.0 | informative |
| LCTSC-Test-S3-102: deliverable | True | True | pass |
| LCTSC-Test-S3-102: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S3-102: planning goal SpinalCord Dmax <= 21.9 | 9.93 | <= 21.9 | informative |
| LCTSC-Test-S3-102: planning goal Esophagus Dmax <= 25.2 | 5.68 | <= 25.2 | informative |
| LCTSC-Test-S3-102: planning goal Heart Dmax <= 30.0 | 19.02 | <= 30.0 | informative |
| LCTSC-Test-S3-102: PTV V100%[%] >= 95.0 | 95.35 | >= 95.0 | pass |
| LCTSC-Test-S3-102: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S3-102: PTV D0.03cc[%] <= 140.0 | 110.2 | <= 140.0 | informative |
| LCTSC-Test-S3-102: Lungs-GTV V20Gy[%] <= 10.0 | 2.58 | <= 10.0 | informative |
| LCTSC-Test-S3-102: SpinalCord D0.03cc[Gy] <= 21.9 | 9.76 | <= 21.9 | pass |
| LCTSC-Test-S3-102: SpinalCord D0.35cc[Gy] <= 18.0 | 8.47 | <= 18.0 | pass |
| LCTSC-Test-S3-102: SpinalCord D1.2cc[Gy] <= 12.3 | 6.94 | <= 12.3 | pass |
| LCTSC-Test-S3-102: Esophagus D0.03cc[Gy] <= 25.2 | 5.32 | <= 25.2 | pass |
| LCTSC-Test-S3-102: Esophagus D5cc[Gy] <= 17.7 | 3.64 | <= 17.7 | pass |
| LCTSC-Test-S3-102: Heart D0.03cc[Gy] <= 30.0 | 18.78 | <= 30.0 | pass |
| LCTSC-Test-S3-102: Heart D15cc[Gy] <= 24.0 | 8.94 | <= 24.0 | pass |
| LCTSC-Test-S3-102: Lungs D1500cc[Gy] <= 11.6 | 0.51 | <= 11.6 | pass |
| LCTSC-Test-S3-102: Lungs D1000cc[Gy] <= 12.4 | 1.3 | <= 12.4 | pass |
| LCTSC-Test-S3-102: Lungs V12.5Gy[cc] <= 1000.0 | 236.4 | <= 1000.0 | informative |

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
| LCTSC-Test-S2-101: PTV V60Gy[%] >= 95.0 (protocol) | 95.43 | >= 95.0 | pass |
| LCTSC-Test-S2-101: PTV V60Gy[%] >= 95.0: protocol against the recorded harness run | 95.43 | 95.62 ± 0.96 | pass |
| LCTSC-Test-S2-101: PTV D0.03cc[Gy] <= 72.0 (protocol) | 65.22 | <= 72.0 | informative |
| LCTSC-Test-S2-101: PTV D0.03cc[Gy] <= 72.0: protocol against the recorded harness run | 65.22 | 65.25 ± 0.65 | pass |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 37.0 (protocol) | 13.99 | <= 37.0 | pass |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 37.0: protocol against the recorded harness run | 13.99 | 14.01 ± 0.14 | pass |
| LCTSC-Test-S2-101: Lungs-GTV Dmean[Gy] <= 20.0 (protocol) | 8.68 | <= 20.0 | pass |
| LCTSC-Test-S2-101: Lungs-GTV Dmean[Gy] <= 20.0: protocol against the recorded harness run | 8.68 | 8.68 ± 0.09 | pass |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5 (protocol) | 15.6 | <= 50.5 | pass |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5: protocol against the recorded harness run | 15.6 | 15.65 ± 0.16 | pass |
| LCTSC-Test-S2-101: Esophagus Dmean[Gy] <= 34.0 (protocol) | 3.25 | <= 34.0 | informative |
| LCTSC-Test-S2-101: Esophagus Dmean[Gy] <= 34.0: protocol against the recorded harness run | 3.25 | 3.24 ± 0.05 | pass |
| LCTSC-Test-S2-101: Heart V60Gy[%] <= 33.0 (protocol) | 0 | <= 33.0 | informative |
| LCTSC-Test-S2-101: Heart V60Gy[%] <= 33.0: protocol against the recorded harness run | 0 | 0.0 ± 0.05 | pass |
| LCTSC-Test-S2-101: Heart V45Gy[%] <= 66.0 (protocol) | 0.19 | <= 66.0 | informative |
| LCTSC-Test-S2-101: Heart V45Gy[%] <= 66.0: protocol against the recorded harness run | 0.19 | 0.19 ± 0.05 | pass |
| LCTSC-Test-S2-101: Heart V40Gy[%] <= 100.0 (protocol) | 0.42 | <= 100.0 | informative |
| LCTSC-Test-S2-101: Heart V40Gy[%] <= 100.0: protocol against the recorded harness run | 0.42 | 0.42 ± 0.05 | pass |
