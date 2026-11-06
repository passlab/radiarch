# Radiarch validation run 20261106-001709-55ab566

RESEARCH USE ONLY. NOT FOR CLINICAL USE. Radiarch is a research treatment-planning system; its plans, doses and evaluations must not be used to treat patients.

The cases ran one per process from commit 55ab566: `protocol_batch_lctsc` (20261106-001709).

| Case | Status | Time (s) | Checks |
|---|---|---|---|
| protocol_batch_lctsc | **pass** | 1858.4 | 79 pass, 0 fail, 36 informative |

## protocol_batch_lctsc — pass


| Check | Value | Target | Result |
|---|---|---|---|
| radiarch batch over 6 LCTSC thoraces: cases planned | 6 | = 6 | pass |
| LCTSC-Test-S1-101: deliverable | True | True | pass |
| LCTSC-Test-S1-101: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S1-101: planning goal SpinalCord Dmax <= 21.9 | 10.92 | <= 21.9 | informative |
| LCTSC-Test-S1-101: planning goal Esophagus Dmax <= 25.2 | 2.08 | <= 25.2 | informative |
| LCTSC-Test-S1-101: planning goal Heart Dmax <= 30.0 | 18.04 | <= 30.0 | informative |
| LCTSC-Test-S1-101: PTV V100%[%] >= 95.0 | 95.1 | >= 95.0 | pass |
| LCTSC-Test-S1-101: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S1-101: PTV D0.03cc[%] <= 140.0 | 115.5 | <= 140.0 | informative |
| LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 10.0 | 2.61 | <= 10.0 | informative |
| LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 21.9 | 10.69 | <= 21.9 | pass |
| LCTSC-Test-S1-101: SpinalCord D0.35cc[Gy] <= 18.0 | 8.87 | <= 18.0 | pass |
| LCTSC-Test-S1-101: SpinalCord D1.2cc[Gy] <= 12.3 | 7.85 | <= 12.3 | pass |
| LCTSC-Test-S1-101: Esophagus D0.03cc[Gy] <= 25.2 | 2.07 | <= 25.2 | pass |
| LCTSC-Test-S1-101: Esophagus D5cc[Gy] <= 17.7 | 0.53 | <= 17.7 | pass |
| LCTSC-Test-S1-101: Heart D0.03cc[Gy] <= 30.0 | 17.94 | <= 30.0 | pass |
| LCTSC-Test-S1-101: Heart D15cc[Gy] <= 24.0 | 11.38 | <= 24.0 | pass |
| LCTSC-Test-S1-101: Lungs D1500cc[Gy] <= 11.6 | 0.51 | <= 11.6 | pass |
| LCTSC-Test-S1-101: Lungs D1000cc[Gy] <= 12.4 | 1.11 | <= 12.4 | pass |
| LCTSC-Test-S1-101: Lungs V12.5Gy[cc] <= 1000.0 | 223.1 | <= 1000.0 | informative |
| LCTSC-Test-S1-102: deliverable | True | True | pass |
| LCTSC-Test-S1-102: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S1-102: planning goal SpinalCord Dmax <= 21.9 | 11.18 | <= 21.9 | informative |
| LCTSC-Test-S1-102: planning goal Esophagus Dmax <= 25.2 | 4.53 | <= 25.2 | informative |
| LCTSC-Test-S1-102: planning goal Heart Dmax <= 30.0 | 22.71 | <= 30.0 | informative |
| LCTSC-Test-S1-102: PTV V100%[%] >= 95.0 | 95.27 | >= 95.0 | pass |
| LCTSC-Test-S1-102: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S1-102: PTV D0.03cc[%] <= 140.0 | 115.8 | <= 140.0 | informative |
| LCTSC-Test-S1-102: Lungs-GTV V20Gy[%] <= 10.0 | 3.1 | <= 10.0 | informative |
| LCTSC-Test-S1-102: SpinalCord D0.03cc[Gy] <= 21.9 | 10.97 | <= 21.9 | pass |
| LCTSC-Test-S1-102: SpinalCord D0.35cc[Gy] <= 18.0 | 10.25 | <= 18.0 | pass |
| LCTSC-Test-S1-102: SpinalCord D1.2cc[Gy] <= 12.3 | 8.21 | <= 12.3 | pass |
| LCTSC-Test-S1-102: Esophagus D0.03cc[Gy] <= 25.2 | 4.48 | <= 25.2 | pass |
| LCTSC-Test-S1-102: Esophagus D5cc[Gy] <= 17.7 | 1.66 | <= 17.7 | pass |
| LCTSC-Test-S1-102: Heart D0.03cc[Gy] <= 30.0 | 22.52 | <= 30.0 | pass |
| LCTSC-Test-S1-102: Heart D15cc[Gy] <= 24.0 | 11.07 | <= 24.0 | pass |
| LCTSC-Test-S1-102: Lungs D1500cc[Gy] <= 11.6 | 0.63 | <= 11.6 | pass |
| LCTSC-Test-S1-102: Lungs D1000cc[Gy] <= 12.4 | 1.27 | <= 12.4 | pass |
| LCTSC-Test-S1-102: Lungs V12.5Gy[cc] <= 1000.0 | 224.4 | <= 1000.0 | informative |
| LCTSC-Test-S2-101: deliverable | True | True | pass |
| LCTSC-Test-S2-101: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S2-101: planning goal SpinalCord Dmax <= 21.9 | 10.3 | <= 21.9 | informative |
| LCTSC-Test-S2-101: planning goal Esophagus Dmax <= 25.2 | 7.31 | <= 25.2 | informative |
| LCTSC-Test-S2-101: planning goal Heart Dmax <= 30.0 | 18.79 | <= 30.0 | informative |
| LCTSC-Test-S2-101: PTV V100%[%] >= 95.0 | 95.51 | >= 95.0 | pass |
| LCTSC-Test-S2-101: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S2-101: PTV D0.03cc[%] <= 140.0 | 113.8 | <= 140.0 | informative |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 10.0 | 2.6 | <= 10.0 | informative |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 21.9 | 10.21 | <= 21.9 | pass |
| LCTSC-Test-S2-101: SpinalCord D0.35cc[Gy] <= 18.0 | 9.17 | <= 18.0 | pass |
| LCTSC-Test-S2-101: SpinalCord D1.2cc[Gy] <= 12.3 | 7.7 | <= 12.3 | pass |
| LCTSC-Test-S2-101: Esophagus D0.03cc[Gy] <= 25.2 | 7.14 | <= 25.2 | pass |
| LCTSC-Test-S2-101: Esophagus D5cc[Gy] <= 17.7 | 3.83 | <= 17.7 | pass |
| LCTSC-Test-S2-101: Heart D0.03cc[Gy] <= 30.0 | 18.57 | <= 30.0 | pass |
| LCTSC-Test-S2-101: Heart D15cc[Gy] <= 24.0 | 10.44 | <= 24.0 | pass |
| LCTSC-Test-S2-101: Lungs D1500cc[Gy] <= 11.6 | 0.66 | <= 11.6 | pass |
| LCTSC-Test-S2-101: Lungs D1000cc[Gy] <= 12.4 | 1.24 | <= 12.4 | pass |
| LCTSC-Test-S2-101: Lungs V12.5Gy[cc] <= 1000.0 | 211.7 | <= 1000.0 | informative |
| LCTSC-Test-S2-102: deliverable | True | True | pass |
| LCTSC-Test-S2-102: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S2-102: planning goal SpinalCord Dmax <= 21.9 | 10.68 | <= 21.9 | informative |
| LCTSC-Test-S2-102: planning goal Esophagus Dmax <= 25.2 | 3.48 | <= 25.2 | informative |
| LCTSC-Test-S2-102: planning goal Heart Dmax <= 30.0 | 9.34 | <= 30.0 | informative |
| LCTSC-Test-S2-102: PTV V100%[%] >= 95.0 | 95.36 | >= 95.0 | pass |
| LCTSC-Test-S2-102: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S2-102: PTV D0.03cc[%] <= 140.0 | 119.3 | <= 140.0 | informative |
| LCTSC-Test-S2-102: Lungs-GTV V20Gy[%] <= 10.0 | 1.93 | <= 10.0 | informative |
| LCTSC-Test-S2-102: SpinalCord D0.03cc[Gy] <= 21.9 | 10.53 | <= 21.9 | pass |
| LCTSC-Test-S2-102: SpinalCord D0.35cc[Gy] <= 18.0 | 9.84 | <= 18.0 | pass |
| LCTSC-Test-S2-102: SpinalCord D1.2cc[Gy] <= 12.3 | 9.03 | <= 12.3 | pass |
| LCTSC-Test-S2-102: Esophagus D0.03cc[Gy] <= 25.2 | 3.39 | <= 25.2 | pass |
| LCTSC-Test-S2-102: Esophagus D5cc[Gy] <= 17.7 | 1.97 | <= 17.7 | pass |
| LCTSC-Test-S2-102: Heart D0.03cc[Gy] <= 30.0 | 9.34 | <= 30.0 | pass |
| LCTSC-Test-S2-102: Heart D15cc[Gy] <= 24.0 | 5.73 | <= 24.0 | pass |
| LCTSC-Test-S2-102: Lungs D1500cc[Gy] <= 11.6 | 0.92 | <= 11.6 | pass |
| LCTSC-Test-S2-102: Lungs D1000cc[Gy] <= 12.4 | 1.91 | <= 12.4 | pass |
| LCTSC-Test-S2-102: Lungs V12.5Gy[cc] <= 1000.0 | 235.4 | <= 1000.0 | informative |
| LCTSC-Test-S3-101: deliverable | True | True | pass |
| LCTSC-Test-S3-101: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S3-101: planning goal SpinalCord Dmax <= 21.9 | 7.73 | <= 21.9 | informative |
| LCTSC-Test-S3-101: planning goal Esophagus Dmax <= 25.2 | 3.8 | <= 25.2 | informative |
| LCTSC-Test-S3-101: planning goal Heart Dmax <= 30.0 | 19.31 | <= 30.0 | informative |
| LCTSC-Test-S3-101: PTV V100%[%] >= 95.0 | 95.6 | >= 95.0 | pass |
| LCTSC-Test-S3-101: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S3-101: PTV D0.03cc[%] <= 140.0 | 114.7 | <= 140.0 | informative |
| LCTSC-Test-S3-101: Lungs-GTV V20Gy[%] <= 10.0 | 3.94 | <= 10.0 | informative |
| LCTSC-Test-S3-101: SpinalCord D0.03cc[Gy] <= 21.9 | 6.83 | <= 21.9 | pass |
| LCTSC-Test-S3-101: SpinalCord D0.35cc[Gy] <= 18.0 | 4.87 | <= 18.0 | pass |
| LCTSC-Test-S3-101: SpinalCord D1.2cc[Gy] <= 12.3 | 3.26 | <= 12.3 | pass |
| LCTSC-Test-S3-101: Esophagus D0.03cc[Gy] <= 25.2 | 3.78 | <= 25.2 | pass |
| LCTSC-Test-S3-101: Esophagus D5cc[Gy] <= 17.7 | 2.1 | <= 17.7 | pass |
| LCTSC-Test-S3-101: Heart D0.03cc[Gy] <= 30.0 | 19.11 | <= 30.0 | pass |
| LCTSC-Test-S3-101: Heart D15cc[Gy] <= 24.0 | 8.81 | <= 24.0 | pass |
| LCTSC-Test-S3-101: Lungs D1500cc[Gy] <= 11.6 | 0.26 | <= 11.6 | pass |
| LCTSC-Test-S3-101: Lungs D1000cc[Gy] <= 12.4 | 0.63 | <= 12.4 | pass |
| LCTSC-Test-S3-101: Lungs V12.5Gy[cc] <= 1000.0 | 187.2 | <= 1000.0 | informative |
| LCTSC-Test-S3-102: deliverable | True | True | pass |
| LCTSC-Test-S3-102: PTV D95 (Gy) | 54.11 | >= 54.0 | pass |
| LCTSC-Test-S3-102: planning goal SpinalCord Dmax <= 21.9 | 11.15 | <= 21.9 | informative |
| LCTSC-Test-S3-102: planning goal Esophagus Dmax <= 25.2 | 5.82 | <= 25.2 | informative |
| LCTSC-Test-S3-102: planning goal Heart Dmax <= 30.0 | 20.67 | <= 30.0 | informative |
| LCTSC-Test-S3-102: PTV V100%[%] >= 95.0 | 95.35 | >= 95.0 | pass |
| LCTSC-Test-S3-102: PTV V90%[%] >= 99.0 | 100 | >= 99.0 | pass |
| LCTSC-Test-S3-102: PTV D0.03cc[%] <= 140.0 | 112.2 | <= 140.0 | informative |
| LCTSC-Test-S3-102: Lungs-GTV V20Gy[%] <= 10.0 | 2.52 | <= 10.0 | informative |
| LCTSC-Test-S3-102: SpinalCord D0.03cc[Gy] <= 21.9 | 10.98 | <= 21.9 | pass |
| LCTSC-Test-S3-102: SpinalCord D0.35cc[Gy] <= 18.0 | 9.76 | <= 18.0 | pass |
| LCTSC-Test-S3-102: SpinalCord D1.2cc[Gy] <= 12.3 | 8.03 | <= 12.3 | pass |
| LCTSC-Test-S3-102: Esophagus D0.03cc[Gy] <= 25.2 | 5.37 | <= 25.2 | pass |
| LCTSC-Test-S3-102: Esophagus D5cc[Gy] <= 17.7 | 3.38 | <= 17.7 | pass |
| LCTSC-Test-S3-102: Heart D0.03cc[Gy] <= 30.0 | 20.55 | <= 30.0 | pass |
| LCTSC-Test-S3-102: Heart D15cc[Gy] <= 24.0 | 8.93 | <= 24.0 | pass |
| LCTSC-Test-S3-102: Lungs D1500cc[Gy] <= 11.6 | 0.49 | <= 11.6 | pass |
| LCTSC-Test-S3-102: Lungs D1000cc[Gy] <= 12.4 | 1.24 | <= 12.4 | pass |
| LCTSC-Test-S3-102: Lungs V12.5Gy[cc] <= 1000.0 | 232.5 | <= 1000.0 | informative |
