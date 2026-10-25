# Radiarch validation run 20261025-114942-316b6c6 + 20261025-121624-316b6c6 + 20261025-142024-316b6c6

RESEARCH USE ONLY. NOT FOR CLINICAL USE. Radiarch is a research treatment-planning system; its plans, doses and evaluations must not be used to treat patients.

The three cases ran one per process from commit 316b6c6 (each needs its own memory budget): `registration_4d_lung` (20261025-114942), `replan_pancreas_cbct` (20261025-121624), `lung_4d_itv` (20261025-142024).

| Case | Status | Time (s) | Checks |
|---|---|---|---|
| registration_4d_lung | **fail** | 798.5 | 29 pass, 2 fail, 179 informative |
| replan_pancreas_cbct | **fail** | 1599.5 | 15 pass, 5 fail, 140 informative |
| lung_4d_itv | **pass** | 1618.4 | 22 pass, 0 fail, 8 informative |

## registration_4d_lung — fail


| Check | Value | Target | Result |
|---|---|---|---|
| 101_HM10395: Tumor 50 % → 0 %, rigid only: Dice | 0.671 | informative | informative |
| 101_HM10395: Tumor 50 % → 0 %, rigid only: mean surface distance (mm) | 3.1 | informative | informative |
| 101_HM10395: Tumor 50 % → 0 %, rigid only: HD95 (mm) | 8 | informative | informative |
| 101_HM10395: LN 50 % → 0 %, rigid only: Dice | 0.779 | informative | informative |
| 101_HM10395: LN 50 % → 0 %, rigid only: mean surface distance (mm) | 2.2 | informative | informative |
| 101_HM10395: LN 50 % → 0 %, rigid only: HD95 (mm) | 6.3 | informative | informative |
| 101_HM10395: RLung 50 % → 0 %, rigid only: Dice | 0.914 | informative | informative |
| 101_HM10395: RLung 50 % → 0 %, rigid only: mean surface distance (mm) | 3.3 | informative | informative |
| 101_HM10395: RLung 50 % → 0 %, rigid only: HD95 (mm) | 17 | informative | informative |
| 101_HM10395: LLung 50 % → 0 %, rigid only: Dice | 0.923 | informative | informative |
| 101_HM10395: LLung 50 % → 0 %, rigid only: mean surface distance (mm) | 2.6 | informative | informative |
| 101_HM10395: LLung 50 % → 0 %, rigid only: HD95 (mm) | 10.2 | informative | informative |
| 101_HM10395: Heart 50 % → 0 %, rigid only: Dice | 0.939 | informative | informative |
| 101_HM10395: Heart 50 % → 0 %, rigid only: mean surface distance (mm) | 1.7 | informative | informative |
| 101_HM10395: Heart 50 % → 0 %, rigid only: HD95 (mm) | 6 | informative | informative |
| 101_HM10395: Esophagus 50 % → 0 %, rigid only: Dice | 0.818 | informative | informative |
| 101_HM10395: Esophagus 50 % → 0 %, rigid only: mean surface distance (mm) | 1.2 | informative | informative |
| 101_HM10395: Esophagus 50 % → 0 %, rigid only: HD95 (mm) | 6.4 | informative | informative |
| 101_HM10395: Cord 50 % → 0 %, rigid only: Dice | 0.997 | informative | informative |
| 101_HM10395: Cord 50 % → 0 %, rigid only: mean surface distance (mm) | 0 | informative | informative |
| 101_HM10395: Cord 50 % → 0 %, rigid only: HD95 (mm) | 0 | informative | informative |
| 101_HM10395: markers (MarkerA, MarkerB, MarkerC) 50 % → 0 %, rigid only: mean centroid error (mm, 5.1 before) | 5.34 | informative | informative |
| 101_HM10395: anatomical landmarks (Carina) 50 % → 0 %, rigid only: mean centroid error (mm, 6.0 before) | 6.22 | informative | informative |
| 101_HM10395: Tumor 50 % → 0 %, demons: Dice | 0.864 | >= 0.8 | pass |
| 101_HM10395: Tumor 50 % → 0 %, demons: mean surface distance (mm) | 1.3 | <= 3.0 | pass |
| 101_HM10395: Tumor 50 % → 0 %, demons: HD95 (mm) | 3.5 | informative | informative |
| 101_HM10395: Tumor 50 % → 0 %, demons: Dice above no registration (0.671) | 0.864 | > 0.671 | pass |
| 101_HM10395: LN 50 % → 0 %, demons: Dice | 0.858 | informative | informative |
| 101_HM10395: LN 50 % → 0 %, demons: mean surface distance (mm) | 1.3 | informative | informative |
| 101_HM10395: LN 50 % → 0 %, demons: HD95 (mm) | 4 | informative | informative |
| 101_HM10395: RLung 50 % → 0 %, demons: Dice | 0.977 | >= 0.9 | pass |
| 101_HM10395: RLung 50 % → 0 %, demons: mean surface distance (mm) | 0.9 | <= 3.0 | pass |
| 101_HM10395: RLung 50 % → 0 %, demons: HD95 (mm) | 2 | informative | informative |
| 101_HM10395: LLung 50 % → 0 %, demons: Dice | 0.978 | >= 0.9 | pass |
| 101_HM10395: LLung 50 % → 0 %, demons: mean surface distance (mm) | 0.9 | <= 3.0 | pass |
| 101_HM10395: LLung 50 % → 0 %, demons: HD95 (mm) | 2 | informative | informative |
| 101_HM10395: Heart 50 % → 0 %, demons: Dice | 0.905 | informative | informative |
| 101_HM10395: Heart 50 % → 0 %, demons: mean surface distance (mm) | 2.6 | informative | informative |
| 101_HM10395: Heart 50 % → 0 %, demons: HD95 (mm) | 6.3 | informative | informative |
| 101_HM10395: Esophagus 50 % → 0 %, demons: Dice | 0.832 | informative | informative |
| 101_HM10395: Esophagus 50 % → 0 %, demons: mean surface distance (mm) | 0.9 | informative | informative |
| 101_HM10395: Esophagus 50 % → 0 %, demons: HD95 (mm) | 2.8 | informative | informative |
| 101_HM10395: Cord 50 % → 0 %, demons: Dice | 0.985 | informative | informative |
| 101_HM10395: Cord 50 % → 0 %, demons: mean surface distance (mm) | 0.1 | informative | informative |
| 101_HM10395: Cord 50 % → 0 %, demons: HD95 (mm) | 2 | informative | informative |
| 101_HM10395: markers (MarkerA, MarkerB, MarkerC) 50 % → 0 %, demons: mean centroid error (mm, 5.1 before) | 1.12 | <= 2.0 | pass |
| 101_HM10395: anatomical landmarks (Carina) 50 % → 0 %, demons: mean centroid error (mm, 6.0 before) | 2.51 | informative | informative |
| 101_HM10395: demons: body voxels where the field folds (%) | 0 | 0 | pass |
| 101_HM10395: Tumor 50 % → 0 %, bspline: Dice | 0.863 | informative | informative |
| 101_HM10395: Tumor 50 % → 0 %, bspline: mean surface distance (mm) | 1.3 | informative | informative |
| 101_HM10395: Tumor 50 % → 0 %, bspline: HD95 (mm) | 3.5 | informative | informative |
| 101_HM10395: LN 50 % → 0 %, bspline: Dice | 0.857 | informative | informative |
| 101_HM10395: LN 50 % → 0 %, bspline: mean surface distance (mm) | 1.4 | informative | informative |
| 101_HM10395: LN 50 % → 0 %, bspline: HD95 (mm) | 4 | informative | informative |
| 101_HM10395: RLung 50 % → 0 %, bspline: Dice | 0.976 | informative | informative |
| 101_HM10395: RLung 50 % → 0 %, bspline: mean surface distance (mm) | 1 | informative | informative |
| 101_HM10395: RLung 50 % → 0 %, bspline: HD95 (mm) | 2.8 | informative | informative |
| 101_HM10395: LLung 50 % → 0 %, bspline: Dice | 0.977 | informative | informative |
| 101_HM10395: LLung 50 % → 0 %, bspline: mean surface distance (mm) | 0.9 | informative | informative |
| 101_HM10395: LLung 50 % → 0 %, bspline: HD95 (mm) | 2 | informative | informative |
| 101_HM10395: Heart 50 % → 0 %, bspline: Dice | 0.903 | informative | informative |
| 101_HM10395: Heart 50 % → 0 %, bspline: mean surface distance (mm) | 2.7 | informative | informative |
| 101_HM10395: Heart 50 % → 0 %, bspline: HD95 (mm) | 8 | informative | informative |
| 101_HM10395: Esophagus 50 % → 0 %, bspline: Dice | 0.779 | informative | informative |
| 101_HM10395: Esophagus 50 % → 0 %, bspline: mean surface distance (mm) | 1.2 | informative | informative |
| 101_HM10395: Esophagus 50 % → 0 %, bspline: HD95 (mm) | 3.5 | informative | informative |
| 101_HM10395: Cord 50 % → 0 %, bspline: Dice | 0.979 | informative | informative |
| 101_HM10395: Cord 50 % → 0 %, bspline: mean surface distance (mm) | 0.2 | informative | informative |
| 101_HM10395: Cord 50 % → 0 %, bspline: HD95 (mm) | 2 | informative | informative |
| 101_HM10395: markers (MarkerA, MarkerB, MarkerC) 50 % → 0 %, bspline: mean centroid error (mm, 5.1 before) | 0.98 | informative | informative |
| 101_HM10395: anatomical landmarks (Carina) 50 % → 0 %, bspline: mean centroid error (mm, 6.0 before) | 2.34 | informative | informative |
| 101_HM10395: bspline: body voxels where the field folds (%) | 0 | informative | informative |
| 103_HM10395: Tumor 50 % → 0 %, rigid only: Dice | 0.754 | informative | informative |
| 103_HM10395: Tumor 50 % → 0 %, rigid only: mean surface distance (mm) | 2.7 | informative | informative |
| 103_HM10395: Tumor 50 % → 0 %, rigid only: HD95 (mm) | 7.2 | informative | informative |
| 103_HM10395: LN 50 % → 0 %, rigid only: Dice | 0.679 | informative | informative |
| 103_HM10395: LN 50 % → 0 %, rigid only: mean surface distance (mm) | 1.9 | informative | informative |
| 103_HM10395: LN 50 % → 0 %, rigid only: HD95 (mm) | 6 | informative | informative |
| 103_HM10395: RLung 50 % → 0 %, rigid only: Dice | 0.893 | informative | informative |
| 103_HM10395: RLung 50 % → 0 %, rigid only: mean surface distance (mm) | 3.5 | informative | informative |
| 103_HM10395: RLung 50 % → 0 %, rigid only: HD95 (mm) | 18.5 | informative | informative |
| 103_HM10395: LLung 50 % → 0 %, rigid only: Dice | 0.887 | informative | informative |
| 103_HM10395: LLung 50 % → 0 %, rigid only: mean surface distance (mm) | 4.3 | informative | informative |
| 103_HM10395: LLung 50 % → 0 %, rigid only: HD95 (mm) | 18.2 | informative | informative |
| 103_HM10395: Heart 50 % → 0 %, rigid only: Dice | 0.848 | informative | informative |
| 103_HM10395: Heart 50 % → 0 %, rigid only: mean surface distance (mm) | 4.8 | informative | informative |
| 103_HM10395: Heart 50 % → 0 %, rigid only: HD95 (mm) | 11.7 | informative | informative |
| 103_HM10395: Esophagus 50 % → 0 %, rigid only: Dice | 0.81 | informative | informative |
| 103_HM10395: Esophagus 50 % → 0 %, rigid only: mean surface distance (mm) | 1.2 | informative | informative |
| 103_HM10395: Esophagus 50 % → 0 %, rigid only: HD95 (mm) | 5.7 | informative | informative |
| 103_HM10395: Cord 50 % → 0 %, rigid only: Dice | 0.979 | informative | informative |
| 103_HM10395: Cord 50 % → 0 %, rigid only: mean surface distance (mm) | 0.2 | informative | informative |
| 103_HM10395: Cord 50 % → 0 %, rigid only: HD95 (mm) | 2 | informative | informative |
| 103_HM10395: markers (MarkerA, MarkerB) 50 % → 0 %, rigid only: mean centroid error (mm, 7.5 before) | 7.68 | informative | informative |
| 103_HM10395: anatomical landmarks (Carina) 50 % → 0 %, rigid only: mean centroid error (mm, 12.0 before) | 12.21 | informative | informative |
| 103_HM10395: Tumor 50 % → 0 %, demons: Dice | 0.826 | >= 0.8 | pass |
| 103_HM10395: Tumor 50 % → 0 %, demons: mean surface distance (mm) | 1.9 | <= 3.0 | pass |
| 103_HM10395: Tumor 50 % → 0 %, demons: HD95 (mm) | 4.9 | informative | informative |
| 103_HM10395: Tumor 50 % → 0 %, demons: Dice above no registration (0.754) | 0.826 | > 0.754 | pass |
| 103_HM10395: LN 50 % → 0 %, demons: Dice | 0.772 | informative | informative |
| 103_HM10395: LN 50 % → 0 %, demons: mean surface distance (mm) | 1.4 | informative | informative |
| 103_HM10395: LN 50 % → 0 %, demons: HD95 (mm) | 4 | informative | informative |
| 103_HM10395: RLung 50 % → 0 %, demons: Dice | 0.954 | >= 0.9 | pass |
| 103_HM10395: RLung 50 % → 0 %, demons: mean surface distance (mm) | 1.6 | <= 3.0 | pass |
| 103_HM10395: RLung 50 % → 0 %, demons: HD95 (mm) | 4 | informative | informative |
| 103_HM10395: LLung 50 % → 0 %, demons: Dice | 0.958 | >= 0.9 | pass |
| 103_HM10395: LLung 50 % → 0 %, demons: mean surface distance (mm) | 2.1 | <= 3.0 | pass |
| 103_HM10395: LLung 50 % → 0 %, demons: HD95 (mm) | 4.5 | informative | informative |
| 103_HM10395: Heart 50 % → 0 %, demons: Dice | 0.936 | informative | informative |
| 103_HM10395: Heart 50 % → 0 %, demons: mean surface distance (mm) | 2.1 | informative | informative |
| 103_HM10395: Heart 50 % → 0 %, demons: HD95 (mm) | 6.3 | informative | informative |
| 103_HM10395: Esophagus 50 % → 0 %, demons: Dice | 0.795 | informative | informative |
| 103_HM10395: Esophagus 50 % → 0 %, demons: mean surface distance (mm) | 1.3 | informative | informative |
| 103_HM10395: Esophagus 50 % → 0 %, demons: HD95 (mm) | 4.5 | informative | informative |
| 103_HM10395: Cord 50 % → 0 %, demons: Dice | 0.955 | informative | informative |
| 103_HM10395: Cord 50 % → 0 %, demons: mean surface distance (mm) | 0.4 | informative | informative |
| 103_HM10395: Cord 50 % → 0 %, demons: HD95 (mm) | 2 | informative | informative |
| 103_HM10395: markers (MarkerA, MarkerB) 50 % → 0 %, demons: mean centroid error (mm, 7.5 before) | 1.33 | <= 2.0 | pass |
| 103_HM10395: anatomical landmarks (Carina) 50 % → 0 %, demons: mean centroid error (mm, 12.0 before) | 5.1 | informative | informative |
| 103_HM10395: demons: body voxels where the field folds (%) | 0 | 0 | pass |
| 103_HM10395: Tumor 50 % → 0 %, bspline: Dice | 0.817 | informative | informative |
| 103_HM10395: Tumor 50 % → 0 %, bspline: mean surface distance (mm) | 2 | informative | informative |
| 103_HM10395: Tumor 50 % → 0 %, bspline: HD95 (mm) | 4.9 | informative | informative |
| 103_HM10395: LN 50 % → 0 %, bspline: Dice | 0.736 | informative | informative |
| 103_HM10395: LN 50 % → 0 %, bspline: mean surface distance (mm) | 1.5 | informative | informative |
| 103_HM10395: LN 50 % → 0 %, bspline: HD95 (mm) | 4 | informative | informative |
| 103_HM10395: RLung 50 % → 0 %, bspline: Dice | 0.946 | informative | informative |
| 103_HM10395: RLung 50 % → 0 %, bspline: mean surface distance (mm) | 1.8 | informative | informative |
| 103_HM10395: RLung 50 % → 0 %, bspline: HD95 (mm) | 4.5 | informative | informative |
| 103_HM10395: LLung 50 % → 0 %, bspline: Dice | 0.953 | informative | informative |
| 103_HM10395: LLung 50 % → 0 %, bspline: mean surface distance (mm) | 2.2 | informative | informative |
| 103_HM10395: LLung 50 % → 0 %, bspline: HD95 (mm) | 6 | informative | informative |
| 103_HM10395: Heart 50 % → 0 %, bspline: Dice | 0.932 | informative | informative |
| 103_HM10395: Heart 50 % → 0 %, bspline: mean surface distance (mm) | 2.2 | informative | informative |
| 103_HM10395: Heart 50 % → 0 %, bspline: HD95 (mm) | 6 | informative | informative |
| 103_HM10395: Esophagus 50 % → 0 %, bspline: Dice | 0.747 | informative | informative |
| 103_HM10395: Esophagus 50 % → 0 %, bspline: mean surface distance (mm) | 1.6 | informative | informative |
| 103_HM10395: Esophagus 50 % → 0 %, bspline: HD95 (mm) | 4.5 | informative | informative |
| 103_HM10395: Cord 50 % → 0 %, bspline: Dice | 0.966 | informative | informative |
| 103_HM10395: Cord 50 % → 0 %, bspline: mean surface distance (mm) | 0.3 | informative | informative |
| 103_HM10395: Cord 50 % → 0 %, bspline: HD95 (mm) | 2 | informative | informative |
| 103_HM10395: markers (MarkerA, MarkerB) 50 % → 0 %, bspline: mean centroid error (mm, 7.5 before) | 1.66 | informative | informative |
| 103_HM10395: anatomical landmarks (Carina) 50 % → 0 %, bspline: mean centroid error (mm, 12.0 before) | 4.89 | informative | informative |
| 103_HM10395: bspline: body voxels where the field folds (%) | 0 | informative | informative |
| 105_HM10395: Tumor 50 % → 0 %, rigid only: Dice | 0.651 | informative | informative |
| 105_HM10395: Tumor 50 % → 0 %, rigid only: mean surface distance (mm) | 2.4 | informative | informative |
| 105_HM10395: Tumor 50 % → 0 %, rigid only: HD95 (mm) | 6 | informative | informative |
| 105_HM10395: markers (MarkerA, MarkerB) 50 % → 0 %, rigid only: mean centroid error (mm, 8.3 before) | 8.35 | informative | informative |
| 105_HM10395: anatomical landmarks (Carina) 50 % → 0 %, rigid only: mean centroid error (mm, 6.3 before) | 6.42 | informative | informative |
| 105_HM10395: Tumor 50 % → 0 %, demons: Dice | 0.833 | >= 0.8 | pass |
| 105_HM10395: Tumor 50 % → 0 %, demons: mean surface distance (mm) | 1.3 | <= 3.0 | pass |
| 105_HM10395: Tumor 50 % → 0 %, demons: HD95 (mm) | 3.5 | informative | informative |
| 105_HM10395: Tumor 50 % → 0 %, demons: Dice above no registration (0.651) | 0.833 | > 0.651 | pass |
| 105_HM10395: markers (MarkerA, MarkerB) 50 % → 0 %, demons: mean centroid error (mm, 8.3 before) | 1.09 | <= 2.0 | pass |
| 105_HM10395: anatomical landmarks (Carina) 50 % → 0 %, demons: mean centroid error (mm, 6.3 before) | 2.25 | informative | informative |
| 105_HM10395: demons: body voxels where the field folds (%) | 0 | 0 | pass |
| 105_HM10395: Tumor 50 % → 0 %, bspline: Dice | 0.805 | informative | informative |
| 105_HM10395: Tumor 50 % → 0 %, bspline: mean surface distance (mm) | 1.4 | informative | informative |
| 105_HM10395: Tumor 50 % → 0 %, bspline: HD95 (mm) | 3.5 | informative | informative |
| 105_HM10395: markers (MarkerA, MarkerB) 50 % → 0 %, bspline: mean centroid error (mm, 8.3 before) | 2.44 | informative | informative |
| 105_HM10395: anatomical landmarks (Carina) 50 % → 0 %, bspline: mean centroid error (mm, 6.3 before) | 2.02 | informative | informative |
| 105_HM10395: bspline: body voxels where the field folds (%) | 0 | informative | informative |
| 111_HM10395: Tumor 50 % → 0 %, rigid only: Dice | 0.789 | informative | informative |
| 111_HM10395: Tumor 50 % → 0 %, rigid only: mean surface distance (mm) | 2.5 | informative | informative |
| 111_HM10395: Tumor 50 % → 0 %, rigid only: HD95 (mm) | 9.2 | informative | informative |
| 111_HM10395: LN 50 % → 0 %, rigid only: Dice | 0.026 | informative | informative |
| 111_HM10395: LN 50 % → 0 %, rigid only: mean surface distance (mm) | 7.5 | informative | informative |
| 111_HM10395: LN 50 % → 0 %, rigid only: HD95 (mm) | 12.6 | informative | informative |
| 111_HM10395: anatomical landmarks (Carina) 50 % → 0 %, rigid only: mean centroid error (mm, 10.3 before) | 10.43 | informative | informative |
| 111_HM10395: Tumor 50 % → 0 %, demons: Dice | 0.767 | >= 0.8 | FAIL |
| 111_HM10395: Tumor 50 % → 0 %, demons: mean surface distance (mm) | 2.8 | <= 3.0 | pass |
| 111_HM10395: Tumor 50 % → 0 %, demons: HD95 (mm) | 9 | informative | informative |
| 111_HM10395: Tumor 50 % → 0 %, demons: Dice above no registration (0.789) | 0.767 | > 0.789 | FAIL |
| 111_HM10395: LN 50 % → 0 %, demons: Dice | 0.404 | informative | informative |
| 111_HM10395: LN 50 % → 0 %, demons: mean surface distance (mm) | 2.8 | informative | informative |
| 111_HM10395: LN 50 % → 0 %, demons: HD95 (mm) | 6.3 | informative | informative |
| 111_HM10395: anatomical landmarks (Carina) 50 % → 0 %, demons: mean centroid error (mm, 10.3 before) | 2.55 | informative | informative |
| 111_HM10395: demons: body voxels where the field folds (%) | 0 | 0 | pass |
| 111_HM10395: Tumor 50 % → 0 %, bspline: Dice | 0.751 | informative | informative |
| 111_HM10395: Tumor 50 % → 0 %, bspline: mean surface distance (mm) | 3.1 | informative | informative |
| 111_HM10395: Tumor 50 % → 0 %, bspline: HD95 (mm) | 10 | informative | informative |
| 111_HM10395: LN 50 % → 0 %, bspline: Dice | 0.442 | informative | informative |
| 111_HM10395: LN 50 % → 0 %, bspline: mean surface distance (mm) | 2.6 | informative | informative |
| 111_HM10395: LN 50 % → 0 %, bspline: HD95 (mm) | 6.3 | informative | informative |
| 111_HM10395: anatomical landmarks (Carina) 50 % → 0 %, bspline: mean centroid error (mm, 10.3 before) | 2.23 | informative | informative |
| 111_HM10395: bspline: body voxels where the field folds (%) | 0 | informative | informative |
| 114_HM10395: Tumor 50 % → 0 %, rigid only: Dice | 0.775 | informative | informative |
| 114_HM10395: Tumor 50 % → 0 %, rigid only: mean surface distance (mm) | 3.5 | informative | informative |
| 114_HM10395: Tumor 50 % → 0 %, rigid only: HD95 (mm) | 11.7 | informative | informative |
| 114_HM10395: LN 50 % → 0 %, rigid only: Dice | 0.752 | informative | informative |
| 114_HM10395: LN 50 % → 0 %, rigid only: mean surface distance (mm) | 1.4 | informative | informative |
| 114_HM10395: LN 50 % → 0 %, rigid only: HD95 (mm) | 4 | informative | informative |
| 114_HM10395: anatomical landmarks (Carina) 50 % → 0 %, rigid only: mean centroid error (mm, 2.5 before) | 2.76 | informative | informative |
| 114_HM10395: Tumor 50 % → 0 %, demons: Dice | 0.837 | >= 0.8 | pass |
| 114_HM10395: Tumor 50 % → 0 %, demons: mean surface distance (mm) | 2.3 | <= 3.0 | pass |
| 114_HM10395: Tumor 50 % → 0 %, demons: HD95 (mm) | 6.3 | informative | informative |
| 114_HM10395: Tumor 50 % → 0 %, demons: Dice above no registration (0.775) | 0.837 | > 0.775 | pass |
| 114_HM10395: LN 50 % → 0 %, demons: Dice | 0.738 | informative | informative |
| 114_HM10395: LN 50 % → 0 %, demons: mean surface distance (mm) | 1.5 | informative | informative |
| 114_HM10395: LN 50 % → 0 %, demons: HD95 (mm) | 4 | informative | informative |
| 114_HM10395: anatomical landmarks (Carina) 50 % → 0 %, demons: mean centroid error (mm, 2.5 before) | 2.6 | informative | informative |
| 114_HM10395: demons: body voxels where the field folds (%) | 0 | 0 | pass |
| 114_HM10395: Tumor 50 % → 0 %, bspline: Dice | 0.834 | informative | informative |
| 114_HM10395: Tumor 50 % → 0 %, bspline: mean surface distance (mm) | 2.3 | informative | informative |
| 114_HM10395: Tumor 50 % → 0 %, bspline: HD95 (mm) | 6.6 | informative | informative |
| 114_HM10395: LN 50 % → 0 %, bspline: Dice | 0.716 | informative | informative |
| 114_HM10395: LN 50 % → 0 %, bspline: mean surface distance (mm) | 1.7 | informative | informative |
| 114_HM10395: LN 50 % → 0 %, bspline: HD95 (mm) | 4.5 | informative | informative |
| 114_HM10395: anatomical landmarks (Carina) 50 % → 0 %, bspline: mean centroid error (mm, 2.5 before) | 3.48 | informative | informative |
| 114_HM10395: bspline: body voxels where the field folds (%) | 0 | informative | informative |

## replan_pancreas_cbct — fail


| Check | Value | Target | Result |
|---|---|---|---|
| Pancreas-CT-CB_001 Aligned CB07 20120728: Stomach_duo planning → cone-beam, rigid only: Dice | 0.525 | informative | informative |
| Pancreas-CT-CB_001 Aligned CB07 20120728: Stomach_duo planning → cone-beam, rigid only: mean surface distance (mm) | 8.6 | informative | informative |
| Pancreas-CT-CB_001 Aligned CB07 20120728: Bowel_sm planning → cone-beam, rigid only: Dice | 0.263 | informative | informative |
| Pancreas-CT-CB_001 Aligned CB07 20120728: Bowel_sm planning → cone-beam, rigid only: mean surface distance (mm) | 13 | informative | informative |
| Pancreas-CT-CB_001 Aligned CB07 20120728: Stomach_duo planning → cone-beam, bspline: Dice | 0.636 | informative | informative |
| Pancreas-CT-CB_001 Aligned CB07 20120728: Stomach_duo planning → cone-beam, bspline: mean surface distance (mm) | 6.5 | informative | informative |
| Pancreas-CT-CB_001 Aligned CB07 20120728: Stomach_duo D0.03cc (Gy) of the day (cone-beam contour, mapped dose) | 70.74 | informative | informative |
| Pancreas-CT-CB_001 Aligned CB07 20120728: Bowel_sm planning → cone-beam, bspline: Dice | 0.336 | informative | informative |
| Pancreas-CT-CB_001 Aligned CB07 20120728: Bowel_sm planning → cone-beam, bspline: mean surface distance (mm) | 11.8 | informative | informative |
| Pancreas-CT-CB_001 Aligned CB07 20120728: Bowel_sm D0.03cc (Gy) of the day (cone-beam contour, mapped dose) | 40.15 | informative | informative |
| Pancreas-CT-CB_001 Aligned CB07 20120728: bspline: body voxels where the field folds (%) | 0 | 0 | pass |
| Pancreas-CT-CB_001 Aligned CB07 20120728: Stomach_duo planning → cone-beam, demons: Dice | 0.062 | informative | informative |
| Pancreas-CT-CB_001 Aligned CB07 20120728: Stomach_duo planning → cone-beam, demons: mean surface distance (mm) | 23.6 | informative | informative |
| Pancreas-CT-CB_001 Aligned CB07 20120728: Bowel_sm planning → cone-beam, demons: Dice | 0.062 | informative | informative |
| Pancreas-CT-CB_001 Aligned CB07 20120728: Bowel_sm planning → cone-beam, demons: mean surface distance (mm) | 24.9 | informative | informative |
| Pancreas-CT-CB_001 Aligned CB07 20120728: Stomach_duo Dice, bspline above rigid only (0.525) | 0.636 | > 0.525 | pass |
| Pancreas-CT-CB_001 Aligned resampled CB02 20120719: Stomach_duo planning → cone-beam, rigid only: Dice | 0.569 | informative | informative |
| Pancreas-CT-CB_001 Aligned resampled CB02 20120719: Stomach_duo planning → cone-beam, rigid only: mean surface distance (mm) | 6.2 | informative | informative |
| Pancreas-CT-CB_001 Aligned resampled CB02 20120719: Bowel_sm planning → cone-beam, rigid only: Dice | 0.415 | informative | informative |
| Pancreas-CT-CB_001 Aligned resampled CB02 20120719: Bowel_sm planning → cone-beam, rigid only: mean surface distance (mm) | 16.4 | informative | informative |
| Pancreas-CT-CB_001 Aligned resampled CB02 20120719: Stomach_duo planning → cone-beam, bspline: Dice | 0.656 | informative | informative |
| Pancreas-CT-CB_001 Aligned resampled CB02 20120719: Stomach_duo planning → cone-beam, bspline: mean surface distance (mm) | 4.9 | informative | informative |
| Pancreas-CT-CB_001 Aligned resampled CB02 20120719: Stomach_duo D0.03cc (Gy) of the day (cone-beam contour, mapped dose) | 70.16 | informative | informative |
| Pancreas-CT-CB_001 Aligned resampled CB02 20120719: Bowel_sm planning → cone-beam, bspline: Dice | 0.396 | informative | informative |
| Pancreas-CT-CB_001 Aligned resampled CB02 20120719: Bowel_sm planning → cone-beam, bspline: mean surface distance (mm) | 16.9 | informative | informative |
| Pancreas-CT-CB_001 Aligned resampled CB02 20120719: Bowel_sm D0.03cc (Gy) of the day (cone-beam contour, mapped dose) | 61.27 | informative | informative |
| Pancreas-CT-CB_001 Aligned resampled CB02 20120719: bspline: body voxels where the field folds (%) | 0 | 0 | pass |
| Pancreas-CT-CB_001 Aligned resampled CB02 20120719: Stomach_duo planning → cone-beam, demons: Dice | 0.106 | informative | informative |
| Pancreas-CT-CB_001 Aligned resampled CB02 20120719: Stomach_duo planning → cone-beam, demons: mean surface distance (mm) | 13.8 | informative | informative |
| Pancreas-CT-CB_001 Aligned resampled CB02 20120719: Bowel_sm planning → cone-beam, demons: Dice | 0.121 | informative | informative |
| Pancreas-CT-CB_001 Aligned resampled CB02 20120719: Bowel_sm planning → cone-beam, demons: mean surface distance (mm) | 17.7 | informative | informative |
| Pancreas-CT-CB_001 Aligned resampled CB02 20120719: Stomach_duo Dice, bspline above rigid only (0.569) | 0.656 | > 0.569 | pass |
| Pancreas-CT-CB_002 Aligned CBCT01 20120608: Stomach_duo planning → cone-beam, rigid only: Dice | 0.524 | informative | informative |
| Pancreas-CT-CB_002 Aligned CBCT01 20120608: Stomach_duo planning → cone-beam, rigid only: mean surface distance (mm) | 10 | informative | informative |
| Pancreas-CT-CB_002 Aligned CBCT01 20120608: Bowel_sm planning → cone-beam, rigid only: Dice | 0.6 | informative | informative |
| Pancreas-CT-CB_002 Aligned CBCT01 20120608: Bowel_sm planning → cone-beam, rigid only: mean surface distance (mm) | 4.2 | informative | informative |
| Pancreas-CT-CB_002 Aligned CBCT01 20120608: Stomach_duo planning → cone-beam, bspline: Dice | 0.622 | informative | informative |
| Pancreas-CT-CB_002 Aligned CBCT01 20120608: Stomach_duo planning → cone-beam, bspline: mean surface distance (mm) | 8.6 | informative | informative |
| Pancreas-CT-CB_002 Aligned CBCT01 20120608: Stomach_duo D0.03cc (Gy) of the day (cone-beam contour, mapped dose) | 35.2 | informative | informative |
| Pancreas-CT-CB_002 Aligned CBCT01 20120608: Bowel_sm planning → cone-beam, bspline: Dice | 0.5 | informative | informative |
| Pancreas-CT-CB_002 Aligned CBCT01 20120608: Bowel_sm planning → cone-beam, bspline: mean surface distance (mm) | 5.8 | informative | informative |
| Pancreas-CT-CB_002 Aligned CBCT01 20120608: Bowel_sm D0.03cc (Gy) of the day (cone-beam contour, mapped dose) | 37.91 | informative | informative |
| Pancreas-CT-CB_002 Aligned CBCT01 20120608: bspline: body voxels where the field folds (%) | 0 | 0 | pass |
| Pancreas-CT-CB_002 Aligned CBCT01 20120608: Stomach_duo planning → cone-beam, demons: Dice | 0.608 | informative | informative |
| Pancreas-CT-CB_002 Aligned CBCT01 20120608: Stomach_duo planning → cone-beam, demons: mean surface distance (mm) | 8.3 | informative | informative |
| Pancreas-CT-CB_002 Aligned CBCT01 20120608: Bowel_sm planning → cone-beam, demons: Dice | 0.491 | informative | informative |
| Pancreas-CT-CB_002 Aligned CBCT01 20120608: Bowel_sm planning → cone-beam, demons: mean surface distance (mm) | 5 | informative | informative |
| Pancreas-CT-CB_002 Aligned CBCT01 20120608: Stomach_duo Dice, bspline above rigid only (0.524) | 0.622 | > 0.524 | pass |
| Pancreas-CT-CB_002 Aligned CT 20120614: Stomach_duo planning → cone-beam, rigid only: Dice | 0.782 | informative | informative |
| Pancreas-CT-CB_002 Aligned CT 20120614: Stomach_duo planning → cone-beam, rigid only: mean surface distance (mm) | 4.8 | informative | informative |
| Pancreas-CT-CB_002 Aligned CT 20120614: Bowel_sm planning → cone-beam, rigid only: Dice | 0.452 | informative | informative |
| Pancreas-CT-CB_002 Aligned CT 20120614: Bowel_sm planning → cone-beam, rigid only: mean surface distance (mm) | 11.5 | informative | informative |
| Pancreas-CT-CB_002 Aligned CT 20120614: Stomach_duo planning → cone-beam, bspline: Dice | 0.799 | informative | informative |
| Pancreas-CT-CB_002 Aligned CT 20120614: Stomach_duo planning → cone-beam, bspline: mean surface distance (mm) | 4.6 | informative | informative |
| Pancreas-CT-CB_002 Aligned CT 20120614: Stomach_duo D0.03cc (Gy) of the day (cone-beam contour, mapped dose) | 32.07 | informative | informative |
| Pancreas-CT-CB_002 Aligned CT 20120614: Bowel_sm planning → cone-beam, bspline: Dice | 0.443 | informative | informative |
| Pancreas-CT-CB_002 Aligned CT 20120614: Bowel_sm planning → cone-beam, bspline: mean surface distance (mm) | 10.5 | informative | informative |
| Pancreas-CT-CB_002 Aligned CT 20120614: Bowel_sm D0.03cc (Gy) of the day (cone-beam contour, mapped dose) | 37.6 | informative | informative |
| Pancreas-CT-CB_002 Aligned CT 20120614: bspline: body voxels where the field folds (%) | 0 | 0 | pass |
| Pancreas-CT-CB_002 Aligned CT 20120614: Stomach_duo planning → cone-beam, demons: Dice | 0.735 | informative | informative |
| Pancreas-CT-CB_002 Aligned CT 20120614: Stomach_duo planning → cone-beam, demons: mean surface distance (mm) | 5.8 | informative | informative |
| Pancreas-CT-CB_002 Aligned CT 20120614: Bowel_sm planning → cone-beam, demons: Dice | 0.345 | informative | informative |
| Pancreas-CT-CB_002 Aligned CT 20120614: Bowel_sm planning → cone-beam, demons: mean surface distance (mm) | 12.5 | informative | informative |
| Pancreas-CT-CB_002 Aligned CT 20120614: Stomach_duo Dice, bspline above rigid only (0.782) | 0.799 | > 0.782 | pass |
| Pancreas-CT-CB_003 Aligned CT 20120211: Stomach_duo planning → cone-beam, rigid only: Dice | 0.821 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120211: Stomach_duo planning → cone-beam, rigid only: mean surface distance (mm) | 3.1 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120211: Bowel_sm planning → cone-beam, rigid only: Dice | 0.552 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120211: Bowel_sm planning → cone-beam, rigid only: mean surface distance (mm) | 4.5 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120211: Stomach_duo planning → cone-beam, bspline: Dice | 0.724 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120211: Stomach_duo planning → cone-beam, bspline: mean surface distance (mm) | 4.8 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120211: Stomach_duo D0.03cc (Gy) of the day (cone-beam contour, mapped dose) | 61.18 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120211: Bowel_sm planning → cone-beam, bspline: Dice | 0.512 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120211: Bowel_sm planning → cone-beam, bspline: mean surface distance (mm) | 5.1 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120211: Bowel_sm D0.03cc (Gy) of the day (cone-beam contour, mapped dose) | 38.84 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120211: bspline: body voxels where the field folds (%) | 0 | 0 | pass |
| Pancreas-CT-CB_003 Aligned CT 20120211: Stomach_duo planning → cone-beam, demons: Dice | 0.711 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120211: Stomach_duo planning → cone-beam, demons: mean surface distance (mm) | 5.1 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120211: Bowel_sm planning → cone-beam, demons: Dice | 0.48 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120211: Bowel_sm planning → cone-beam, demons: mean surface distance (mm) | 6.5 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120211: Stomach_duo Dice, bspline above rigid only (0.821) | 0.724 | > 0.821 | FAIL |
| Pancreas-CT-CB_003 Aligned CT 20120218: Stomach_duo planning → cone-beam, rigid only: Dice | 0.72 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120218: Stomach_duo planning → cone-beam, rigid only: mean surface distance (mm) | 4.5 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120218: Bowel_sm planning → cone-beam, rigid only: Dice | 0.484 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120218: Bowel_sm planning → cone-beam, rigid only: mean surface distance (mm) | 5.7 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120218: Stomach_duo planning → cone-beam, bspline: Dice | 0.585 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120218: Stomach_duo planning → cone-beam, bspline: mean surface distance (mm) | 6.7 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120218: Stomach_duo D0.03cc (Gy) of the day (cone-beam contour, mapped dose) | 63.13 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120218: Bowel_sm planning → cone-beam, bspline: Dice | 0.429 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120218: Bowel_sm planning → cone-beam, bspline: mean surface distance (mm) | 7.1 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120218: Bowel_sm D0.03cc (Gy) of the day (cone-beam contour, mapped dose) | 42.1 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120218: bspline: body voxels where the field folds (%) | 0 | 0 | pass |
| Pancreas-CT-CB_003 Aligned CT 20120218: Stomach_duo planning → cone-beam, demons: Dice | 0.743 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120218: Stomach_duo planning → cone-beam, demons: mean surface distance (mm) | 3.8 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120218: Bowel_sm planning → cone-beam, demons: Dice | 0.439 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120218: Bowel_sm planning → cone-beam, demons: mean surface distance (mm) | 11 | informative | informative |
| Pancreas-CT-CB_003 Aligned CT 20120218: Stomach_duo Dice, bspline above rigid only (0.720) | 0.585 | > 0.720 | FAIL |
| Pancreas-CT-CB_004 Aligned CT - test1 20120129: Stomach_duo planning → cone-beam, rigid only: Dice | 0.544 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120129: Stomach_duo planning → cone-beam, rigid only: mean surface distance (mm) | 7.1 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120129: Bowel_sm planning → cone-beam, rigid only: Dice | 0.48 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120129: Bowel_sm planning → cone-beam, rigid only: mean surface distance (mm) | 6.2 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120129: Stomach_duo planning → cone-beam, bspline: Dice | 0.398 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120129: Stomach_duo planning → cone-beam, bspline: mean surface distance (mm) | 10 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120129: Stomach_duo D0.03cc (Gy) of the day (cone-beam contour, mapped dose) | 78.55 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120129: Bowel_sm planning → cone-beam, bspline: Dice | 0.417 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120129: Bowel_sm planning → cone-beam, bspline: mean surface distance (mm) | 7.3 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120129: Bowel_sm D0.03cc (Gy) of the day (cone-beam contour, mapped dose) | 79.01 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120129: bspline: body voxels where the field folds (%) | 0 | 0 | pass |
| Pancreas-CT-CB_004 Aligned CT - test1 20120129: Stomach_duo planning → cone-beam, demons: Dice | 0.63 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120129: Stomach_duo planning → cone-beam, demons: mean surface distance (mm) | 5.7 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120129: Bowel_sm planning → cone-beam, demons: Dice | 0.392 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120129: Bowel_sm planning → cone-beam, demons: mean surface distance (mm) | 7.7 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120129: Stomach_duo Dice, bspline above rigid only (0.544) | 0.398 | > 0.544 | FAIL |
| Pancreas-CT-CB_004 Aligned CT - test1 20120206: Stomach_duo planning → cone-beam, rigid only: Dice | 0.641 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120206: Stomach_duo planning → cone-beam, rigid only: mean surface distance (mm) | 5.7 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120206: Bowel_sm planning → cone-beam, rigid only: Dice | 0.528 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120206: Bowel_sm planning → cone-beam, rigid only: mean surface distance (mm) | 6.8 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120206: Stomach_duo planning → cone-beam, bspline: Dice | 0.61 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120206: Stomach_duo planning → cone-beam, bspline: mean surface distance (mm) | 6 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120206: Stomach_duo D0.03cc (Gy) of the day (cone-beam contour, mapped dose) | 75.47 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120206: Bowel_sm planning → cone-beam, bspline: Dice | 0.383 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120206: Bowel_sm planning → cone-beam, bspline: mean surface distance (mm) | 9.4 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120206: Bowel_sm D0.03cc (Gy) of the day (cone-beam contour, mapped dose) | 80.06 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120206: bspline: body voxels where the field folds (%) | 0 | 0 | pass |
| Pancreas-CT-CB_004 Aligned CT - test1 20120206: Stomach_duo planning → cone-beam, demons: Dice | 0.603 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120206: Stomach_duo planning → cone-beam, demons: mean surface distance (mm) | 6.3 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120206: Bowel_sm planning → cone-beam, demons: Dice | 0.345 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120206: Bowel_sm planning → cone-beam, demons: mean surface distance (mm) | 9.6 | informative | informative |
| Pancreas-CT-CB_004 Aligned CT - test1 20120206: Stomach_duo Dice, bspline above rigid only (0.641) | 0.61 | > 0.641 | FAIL |
| Pancreas-CT-CB_005 Aligned CT - test1 20121230: Stomach_duo planning → cone-beam, rigid only: Dice | 0.69 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20121230: Stomach_duo planning → cone-beam, rigid only: mean surface distance (mm) | 5.7 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20121230: Bowel_sm planning → cone-beam, rigid only: Dice | 0.446 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20121230: Bowel_sm planning → cone-beam, rigid only: mean surface distance (mm) | 8.1 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20121230: Stomach_duo planning → cone-beam, bspline: Dice | 0.712 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20121230: Stomach_duo planning → cone-beam, bspline: mean surface distance (mm) | 5.1 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20121230: Stomach_duo D0.03cc (Gy) of the day (cone-beam contour, mapped dose) | 94.98 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20121230: Bowel_sm planning → cone-beam, bspline: Dice | 0.344 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20121230: Bowel_sm planning → cone-beam, bspline: mean surface distance (mm) | 8.7 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20121230: Bowel_sm D0.03cc (Gy) of the day (cone-beam contour, mapped dose) | 85.1 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20121230: bspline: body voxels where the field folds (%) | 0 | 0 | pass |
| Pancreas-CT-CB_005 Aligned CT - test1 20121230: Stomach_duo planning → cone-beam, demons: Dice | 0.603 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20121230: Stomach_duo planning → cone-beam, demons: mean surface distance (mm) | 7.4 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20121230: Bowel_sm planning → cone-beam, demons: Dice | 0.179 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20121230: Bowel_sm planning → cone-beam, demons: mean surface distance (mm) | 17.3 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20121230: Stomach_duo Dice, bspline above rigid only (0.690) | 0.712 | > 0.690 | pass |
| Pancreas-CT-CB_005 Aligned CT - test1 20130107: Stomach_duo planning → cone-beam, rigid only: Dice | 0.607 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20130107: Stomach_duo planning → cone-beam, rigid only: mean surface distance (mm) | 7.4 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20130107: Bowel_sm planning → cone-beam, rigid only: Dice | 0.432 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20130107: Bowel_sm planning → cone-beam, rigid only: mean surface distance (mm) | 12.7 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20130107: Stomach_duo planning → cone-beam, bspline: Dice | 0.604 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20130107: Stomach_duo planning → cone-beam, bspline: mean surface distance (mm) | 7 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20130107: Stomach_duo D0.03cc (Gy) of the day (cone-beam contour, mapped dose) | 91.41 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20130107: Bowel_sm planning → cone-beam, bspline: Dice | 0.168 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20130107: Bowel_sm planning → cone-beam, bspline: mean surface distance (mm) | 14.8 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20130107: Bowel_sm D0.03cc (Gy) of the day (cone-beam contour, mapped dose) | 93.89 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20130107: bspline: body voxels where the field folds (%) | 0 | 0 | pass |
| Pancreas-CT-CB_005 Aligned CT - test1 20130107: Stomach_duo planning → cone-beam, demons: Dice | 0.516 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20130107: Stomach_duo planning → cone-beam, demons: mean surface distance (mm) | 9.1 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20130107: Bowel_sm planning → cone-beam, demons: Dice | 0.329 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20130107: Bowel_sm planning → cone-beam, demons: mean surface distance (mm) | 19.1 | informative | informative |
| Pancreas-CT-CB_005 Aligned CT - test1 20130107: Stomach_duo Dice, bspline above rigid only (0.607) | 0.604 | > 0.607 | FAIL |

## lung_4d_itv — pass


| Check | Value | Target | Result |
|---|---|---|---|
| 101_HM10395: ITV over 10 phases / reference tumour (volume) | 1.49 | informative | informative |
| 101_HM10395: planned PTV D95 (Gy) | 60.12 | informative | informative |
| 101_HM10395: phase 0 %: its tumour D95 (Gy) | 60.48 | >= 57.0 | pass |
| 101_HM10395: phase 10 %: its tumour D95 (Gy) | 60.6 | >= 57.0 | pass |
| 101_HM10395: phase 20 %: its tumour D95 (Gy) | 60.53 | >= 57.0 | pass |
| 101_HM10395: phase 30 %: its tumour D95 (Gy) | 60.58 | >= 57.0 | pass |
| 101_HM10395: phase 40 %: its tumour D95 (Gy) | 60.37 | >= 57.0 | pass |
| 101_HM10395: phase 50 %: its tumour D95 (Gy) | 60.32 | >= 57.0 | pass |
| 101_HM10395: phase 60 %: its tumour D95 (Gy) | 60.38 | >= 57.0 | pass |
| 101_HM10395: phase 70 %: its tumour D95 (Gy) | 60.27 | >= 57.0 | pass |
| 101_HM10395: phase 80 %: its tumour D95 (Gy) | 60.34 | >= 57.0 | pass |
| 101_HM10395: phase 90 %: its tumour D95 (Gy) | 60.33 | >= 57.0 | pass |
| 101_HM10395: accumulated over 10 phases: reference tumour D95 (Gy) | 60.97 | >= 57.0 | pass |
| 101_HM10395: Lungs V20Gy (%), accumulated / planned | 10.26 | informative | informative |
| 101_HM10395: SpinalCord Dmax (Gy), accumulated / planned | 23.73 | informative | informative |
| 103_HM10395: ITV over 10 phases / reference tumour (volume) | 1.47 | informative | informative |
| 103_HM10395: planned PTV D95 (Gy) | 60.12 | informative | informative |
| 103_HM10395: phase 0 %: its tumour D95 (Gy) | 61.14 | >= 57.0 | pass |
| 103_HM10395: phase 10 %: its tumour D95 (Gy) | 61.05 | >= 57.0 | pass |
| 103_HM10395: phase 20 %: its tumour D95 (Gy) | 60.73 | >= 57.0 | pass |
| 103_HM10395: phase 30 %: its tumour D95 (Gy) | 60.42 | >= 57.0 | pass |
| 103_HM10395: phase 40 %: its tumour D95 (Gy) | 60.13 | >= 57.0 | pass |
| 103_HM10395: phase 50 %: its tumour D95 (Gy) | 60.08 | >= 57.0 | pass |
| 103_HM10395: phase 60 %: its tumour D95 (Gy) | 59.9 | >= 57.0 | pass |
| 103_HM10395: phase 70 %: its tumour D95 (Gy) | 60.1 | >= 57.0 | pass |
| 103_HM10395: phase 80 %: its tumour D95 (Gy) | 60.64 | >= 57.0 | pass |
| 103_HM10395: phase 90 %: its tumour D95 (Gy) | 61.01 | >= 57.0 | pass |
| 103_HM10395: accumulated over 10 phases: reference tumour D95 (Gy) | 61.09 | >= 57.0 | pass |
| 103_HM10395: Lungs V20Gy (%), accumulated / planned | 17.68 | informative | informative |
| 103_HM10395: SpinalCord Dmax (Gy), accumulated / planned | 35.95 | informative | informative |
