# Radiarch validation run 20261111-013504-f3a83c7

RESEARCH USE ONLY. NOT FOR CLINICAL USE. Radiarch is a research treatment-planning system; its plans, doses and evaluations must not be used to treat patients.

The cases ran one per process from commit f3a83c7: `mco_protocol_lung` (20261111-013504).

| Case | Status | Time (s) | Checks |
|---|---|---|---|
| mco_protocol_lung | **pass** | 24954.3 | 38 pass, 0 fail, 121 informative |

## mco_protocol_lung — pass


| Check | Value | Target | Result |
|---|---|---|---|
| demo-lung-imrt: deliverable | True | True | pass |
| demo-lung-imrt-mco: deliverable | True | True | pass |
| PTV V60Gy[%] >= 95.0: MCO plan | 95.32 | >= 95.0 | pass |
| PTV V60Gy[%] >= 95.0: MCO against the reweighting plan | 95.32 vs 95.27 | informative | informative |
| PTV D0.03cc[Gy] <= 72.0: MCO plan | 72.02 | <= 72.0 | informative |
| PTV D0.03cc[Gy] <= 72.0: MCO against the reweighting plan | 72.02 vs 68.54 | informative | informative |
| Lungs-GTV V20Gy[%] <= 37.0: MCO plan | 20.99 | <= 37.0 | pass |
| Lungs-GTV V20Gy[%] <= 37.0: MCO against the reweighting plan | 20.99 vs 20.11 | informative | informative |
| Lungs-GTV Dmean[Gy] <= 20.0: MCO plan | 12.56 | <= 20.0 | pass |
| Lungs-GTV Dmean[Gy] <= 20.0: MCO against the reweighting plan | 12.56 vs 11.25 | informative | informative |
| SpinalCord D0.03cc[Gy] <= 50.5: MCO plan | 4.56 | <= 50.5 | pass |
| SpinalCord D0.03cc[Gy] <= 50.5: MCO against the reweighting plan | 4.56 vs 35.19 | informative | informative |
| Esophagus Dmean[Gy] <= 34.0: MCO plan | 1.14 | <= 34.0 | informative |
| Esophagus Dmean[Gy] <= 34.0: MCO against the reweighting plan | 1.14 vs 9.85 | informative | informative |
| Heart V60Gy[%] <= 33.0: MCO plan | 4.23 | <= 33.0 | informative |
| Heart V60Gy[%] <= 33.0: MCO against the reweighting plan | 4.23 vs 0.12 | informative | informative |
| Heart V45Gy[%] <= 66.0: MCO plan | 5.31 | <= 66.0 | informative |
| Heart V45Gy[%] <= 66.0: MCO against the reweighting plan | 5.31 vs 1.34 | informative | informative |
| Heart V40Gy[%] <= 100.0: MCO plan | 6.12 | <= 100.0 | informative |
| Heart V40Gy[%] <= 100.0: MCO against the reweighting plan | 6.12 vs 2.42 | informative | informative |
| Pareto set: the error bound never grows as plans are added | 0.759 → 0.739 → 0.688 → 0.680 → 0.616 → 0.587 → 0.578 → 0.578 → 0.574 → 0.557 → 0.555 | non-increasing | pass |
| Pareto set: plans whose solve converged | 5 of 16 | informative | informative |
| Pareto set: plans dominated by another plan | 0 | informative | informative |
| Pareto set: each converged plan is the best of the set in its own weighted sum | 0 | <= 0.01 | pass |
| Pareto set: hard constraint SpinalCord Dmax <= 45.0 Gy in every plan | 45.04 | <= 45.0 (tolerance 0.1) | pass |
| Pareto set: hard constraint PTV Dmin >= 54.0 Gy in every plan | 53.91 | >= 54.0 (tolerance 0.1) | pass |
| Pareto set: error bound with 6 plans | 0.7595 | tolerance 0.05 | informative |
| Pareto set: error bound with 7 plans | 0.7392 | tolerance 0.05 | informative |
| Pareto set: error bound with 8 plans | 0.6877 | tolerance 0.05 | informative |
| Pareto set: error bound with 9 plans | 0.6801 | tolerance 0.05 | informative |
| Pareto set: error bound with 10 plans | 0.616 | tolerance 0.05 | informative |
| Pareto set: error bound with 11 plans | 0.5872 | tolerance 0.05 | informative |
| Pareto set: error bound with 12 plans | 0.5782 | tolerance 0.05 | informative |
| Pareto set: error bound with 13 plans | 0.5775 | tolerance 0.05 | informative |
| Pareto set: error bound with 14 plans | 0.5742 | tolerance 0.05 | informative |
| Pareto set: error bound with 15 plans | 0.5571 | tolerance 0.05 | informative |
| Pareto set: error bound with 16 plans | 0.5553 | tolerance 0.05 | informative |
| deliverable (seven static fields): deliverable | True | True | pass |
| deliverable (seven static fields): UniformRMS(PTV) navigated → deliverable (Gy) | 0.48 → 5.82 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): MeanDose(Lungs-PTV) navigated → deliverable (Gy) | 10.45 → 10.65 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): MeanDose(Heart) navigated → deliverable (Gy) | 7.53 → 10.20 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): MeanDose(Esophagus) navigated → deliverable (Gy) | 1.10 → 1.60 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): EUDMax(SpinalCord) navigated → deliverable (Gy) | 2.68 → 3.78 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): PTV D95%[Gy] >= 60 navigated → deliverable (Gy) | 59.10 → 60.12 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): SpinalCord Dmax[Gy] <= 45 navigated → deliverable (Gy) | 3.93 → 5.63 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): Esophagus Dmean[Gy] <= 34 navigated → deliverable (Gy) | 1.10 → 1.60 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): Heart D33%[Gy] <= 60 navigated → deliverable (Gy) | 4.77 → 8.51 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): Lungs-PTV D37%[Gy] <= 20 navigated → deliverable (Gy) | 1.33 → 2.45 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): flagged rows of the deviation table | 6 | informative | informative |
| deliverable (seven static fields): normalisation of the deliverable plan within 15 % of 1 | 0.9674 | 0.85 to 1.15 | pass |
| deliverable (seven static fields): meterset rounds | 2 | informative | informative |
| seven static fields: second set: the error bound never grows as plans are added | 0.475 → 0.453 → 0.451 → 0.390 → 0.379 → 0.337 | non-increasing | pass |
| seven static fields: second set: plans whose solve converged | 11 of 11 | informative | informative |
| seven static fields: second set: plans dominated by another plan | 0 | informative | informative |
| seven static fields: second set: each converged plan is the best of the set in its own weighted sum | 0 | <= 0.01 | pass |
| seven static fields: second set: hard constraint SpinalCord Dmax <= 45.0 Gy in every plan | 6.885 | <= 45.0 (tolerance 0.1) | pass |
| seven static fields: second set: hard constraint PTV Dmin >= 54.0 Gy in every plan | 54.01 | >= 54.0 (tolerance 0.1) | pass |
| seven static fields: second set: hard constraint PTV gEUD >= 64.358 Gy in every plan | 64.36 | >= 64.358 (tolerance 0.6436) | pass |
| seven static fields: second set: hard constraint PTV Dmax <= 72.0 Gy in every plan | 72.63 | <= 72.0 (tolerance 0.72) | pass |
| seven static fields: second set: error bound with 6 plans | 0.4746 | tolerance 0.05 | informative |
| seven static fields: second set: error bound with 7 plans | 0.4534 | tolerance 0.05 | informative |
| seven static fields: second set: error bound with 8 plans | 0.4512 | tolerance 0.05 | informative |
| seven static fields: second set: error bound with 9 plans | 0.3904 | tolerance 0.05 | informative |
| seven static fields: second set: error bound with 10 plans | 0.3791 | tolerance 0.05 | informative |
| seven static fields: second set: error bound with 11 plans | 0.3375 | tolerance 0.05 | informative |
| seven static fields: second set | 11 plans on 75 segments | informative | informative |
| seven static fields: plan on the second set: deliverable | True | True | pass |
| seven static fields: plan on the second set: UniformRMS(PTV) navigated → deliverable (Gy) | 5.46 → 4.97 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: MeanDose(Lungs-PTV) navigated → deliverable (Gy) | 10.92 → 10.83 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: MeanDose(Heart) navigated → deliverable (Gy) | 8.20 → 8.13 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: MeanDose(Esophagus) navigated → deliverable (Gy) | 1.15 → 1.14 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: EUDMax(SpinalCord) navigated → deliverable (Gy) | 2.98 → 2.96 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: PTV D95%[Gy] >= 60 navigated → deliverable (Gy) | 60.62 → 60.12 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: SpinalCord Dmax[Gy] <= 45 navigated → deliverable (Gy) | 4.62 → 4.58 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: Esophagus Dmean[Gy] <= 34 navigated → deliverable (Gy) | 1.15 → 1.14 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: Heart D33%[Gy] <= 60 navigated → deliverable (Gy) | 4.18 → 4.14 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: Lungs-PTV D37%[Gy] <= 20 navigated → deliverable (Gy) | 1.27 → 1.26 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: flagged rows of the deviation table | 0 | informative | informative |
| seven static fields: plan on the second set: normalisation of the deliverable plan within 15 % of 1 | 0.9917 | 0.85 to 1.15 | pass |
| seven static fields: UniformRMS(PTV) navigated → deliverable → second navigation → plan (Gy) | 0.48 → 5.82 → 5.46 → 4.97 | informative | informative |
| seven static fields: MeanDose(Lungs-PTV) navigated → deliverable → second navigation → plan (Gy) | 10.45 → 10.65 → 10.92 → 10.83 | informative | informative |
| seven static fields: MeanDose(Heart) navigated → deliverable → second navigation → plan (Gy) | 7.53 → 10.20 → 8.20 → 8.13 | informative | informative |
| seven static fields: MeanDose(Esophagus) navigated → deliverable → second navigation → plan (Gy) | 1.10 → 1.60 → 1.15 → 1.14 | informative | informative |
| seven static fields: EUDMax(SpinalCord) navigated → deliverable → second navigation → plan (Gy) | 2.68 → 3.78 → 2.98 → 2.96 | informative | informative |
| seven static fields: PTV D95%[Gy] >= 60 navigated → deliverable → second navigation → plan (Gy) | 59.10 → 60.12 → 60.62 → 60.12 | informative | informative |
| seven static fields: SpinalCord Dmax[Gy] <= 45 navigated → deliverable → second navigation → plan (Gy) | 3.93 → 5.63 → 4.62 → 4.58 | informative | informative |
| seven static fields: Esophagus Dmean[Gy] <= 34 navigated → deliverable → second navigation → plan (Gy) | 1.10 → 1.60 → 1.15 → 1.14 | informative | informative |
| seven static fields: Heart D33%[Gy] <= 60 navigated → deliverable → second navigation → plan (Gy) | 4.77 → 8.51 → 4.18 → 4.14 | informative | informative |
| seven static fields: Lungs-PTV D37%[Gy] <= 20 navigated → deliverable → second navigation → plan (Gy) | 1.33 → 2.45 → 1.27 → 1.26 | informative | informative |
| demo-lung-imrt-mco-arcs: deliverable | True | True | pass |
| Pareto set on the arcs' sectors: the error bound never grows as plans are added | 0.825 → 0.822 → 0.794 | non-increasing | pass |
| Pareto set on the arcs' sectors: plans whose solve converged | 0 of 8 | informative | informative |
| Pareto set on the arcs' sectors: plans dominated by another plan | 0 | informative | informative |
| Pareto set on the arcs' sectors: hard constraint SpinalCord Dmax <= 45.0 Gy in every plan | 45.01 | <= 45.0 (tolerance 0.1) | pass |
| Pareto set on the arcs' sectors: hard constraint PTV Dmin >= 54.0 Gy in every plan | 53.91 | >= 54.0 (tolerance 0.1) | pass |
| Pareto set on the arcs' sectors: error bound with 6 plans | 0.8246 | tolerance 0.05 | informative |
| Pareto set on the arcs' sectors: error bound with 7 plans | 0.8216 | tolerance 0.05 | informative |
| Pareto set on the arcs' sectors: error bound with 8 plans | 0.7939 | tolerance 0.05 | informative |
| deliverable (two arcs): deliverable | True | True | pass |
| deliverable (two arcs): UniformRMS(PTV) navigated → deliverable (Gy) | 0.55 → 6.28 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): MeanDose(Lungs-PTV) navigated → deliverable (Gy) | 9.65 → 12.80 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): MeanDose(Heart) navigated → deliverable (Gy) | 9.91 → 16.98 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): MeanDose(Esophagus) navigated → deliverable (Gy) | 5.29 → 12.20 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): EUDMax(SpinalCord) navigated → deliverable (Gy) | 7.74 → 24.24 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): PTV D95%[Gy] >= 60 navigated → deliverable (Gy) | 59.33 → 60.12 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): SpinalCord Dmax[Gy] <= 45 navigated → deliverable (Gy) | 10.64 → 35.23 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): Esophagus Dmean[Gy] <= 34 navigated → deliverable (Gy) | 5.29 → 12.20 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): Heart D33%[Gy] <= 60 navigated → deliverable (Gy) | 10.51 → 19.30 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): Lungs-PTV D37%[Gy] <= 20 navigated → deliverable (Gy) | 5.34 → 10.13 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): flagged rows of the deviation table | 9 | informative | informative |
| deliverable (two arcs): normalisation of the deliverable plan within 15 % of 1 | 0.9947 | 0.85 to 1.15 | pass |
| deliverable (two arcs): meterset rounds | 2 | informative | informative |
| two arcs: second set: the error bound never grows as plans are added | 0.993 → 0.956 → 0.943 → 0.931 → 0.892 → 0.891 | non-increasing | pass |
| two arcs: second set: plans whose solve converged | 3 of 11 | informative | informative |
| two arcs: second set: plans dominated by another plan | 0 | informative | informative |
| two arcs: second set: each converged plan is the best of the set in its own weighted sum | 0 | <= 0.01 | pass |
| two arcs: second set: hard constraint SpinalCord Dmax <= 45.0 Gy in every plan | 32.85 | <= 45.0 (tolerance 0.1) | pass |
| two arcs: second set: hard constraint PTV Dmin >= 54.0 Gy in every plan | 54.11 | >= 54.0 (tolerance 0.1) | pass |
| two arcs: second set: hard constraint PTV gEUD >= 64.623 Gy in every plan | 64.62 | >= 64.623 (tolerance 0.6462) | pass |
| two arcs: second set: hard constraint PTV Dmax <= 72.0 Gy in every plan | 72.39 | <= 72.0 (tolerance 0.72) | pass |
| two arcs: second set: error bound with 6 plans | 0.9932 | tolerance 0.05 | informative |
| two arcs: second set: error bound with 7 plans | 0.9556 | tolerance 0.05 | informative |
| two arcs: second set: error bound with 8 plans | 0.9426 | tolerance 0.05 | informative |
| two arcs: second set: error bound with 9 plans | 0.9307 | tolerance 0.05 | informative |
| two arcs: second set: error bound with 10 plans | 0.8924 | tolerance 0.05 | informative |
| two arcs: second set: error bound with 11 plans | 0.8908 | tolerance 0.05 | informative |
| two arcs: second set | 11 plans on 192 arc intervals | informative | informative |
| two arcs: plan on the second set: deliverable | True | True | pass |
| two arcs: plan on the second set: UniformRMS(PTV) navigated → deliverable (Gy) | 6.29 → 6.20 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: MeanDose(Lungs-PTV) navigated → deliverable (Gy) | 11.49 → 11.47 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: MeanDose(Heart) navigated → deliverable (Gy) | 15.02 → 15.00 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: MeanDose(Esophagus) navigated → deliverable (Gy) | 9.73 → 9.71 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: EUDMax(SpinalCord) navigated → deliverable (Gy) | 20.16 → 20.13 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: PTV D95%[Gy] >= 60 navigated → deliverable (Gy) | 60.22 → 60.12 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: SpinalCord Dmax[Gy] <= 45 navigated → deliverable (Gy) | 27.69 → 27.62 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: Esophagus Dmean[Gy] <= 34 navigated → deliverable (Gy) | 9.73 → 9.71 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: Heart D33%[Gy] <= 60 navigated → deliverable (Gy) | 16.55 → 16.52 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: Lungs-PTV D37%[Gy] <= 20 navigated → deliverable (Gy) | 7.41 → 7.40 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: flagged rows of the deviation table | 0 | informative | informative |
| two arcs: plan on the second set: normalisation of the deliverable plan within 15 % of 1 | 0.9984 | 0.85 to 1.15 | pass |
| two arcs: UniformRMS(PTV) navigated → deliverable → second navigation → plan (Gy) | 0.55 → 6.28 → 6.29 → 6.20 | informative | informative |
| two arcs: MeanDose(Lungs-PTV) navigated → deliverable → second navigation → plan (Gy) | 9.65 → 12.80 → 11.49 → 11.47 | informative | informative |
| two arcs: MeanDose(Heart) navigated → deliverable → second navigation → plan (Gy) | 9.91 → 16.98 → 15.02 → 15.00 | informative | informative |
| two arcs: MeanDose(Esophagus) navigated → deliverable → second navigation → plan (Gy) | 5.29 → 12.20 → 9.73 → 9.71 | informative | informative |
| two arcs: EUDMax(SpinalCord) navigated → deliverable → second navigation → plan (Gy) | 7.74 → 24.24 → 20.16 → 20.13 | informative | informative |
| two arcs: PTV D95%[Gy] >= 60 navigated → deliverable → second navigation → plan (Gy) | 59.33 → 60.12 → 60.22 → 60.12 | informative | informative |
| two arcs: SpinalCord Dmax[Gy] <= 45 navigated → deliverable → second navigation → plan (Gy) | 10.64 → 35.23 → 27.69 → 27.62 | informative | informative |
| two arcs: Esophagus Dmean[Gy] <= 34 navigated → deliverable → second navigation → plan (Gy) | 5.29 → 12.20 → 9.73 → 9.71 | informative | informative |
| two arcs: Heart D33%[Gy] <= 60 navigated → deliverable → second navigation → plan (Gy) | 10.51 → 19.30 → 16.55 → 16.52 | informative | informative |
| two arcs: Lungs-PTV D37%[Gy] <= 20 navigated → deliverable → second navigation → plan (Gy) | 5.34 → 10.13 → 7.41 → 7.40 | informative | informative |
| PTV V60Gy[%] >= 95.0: MCO plan (two arcs) | 95.29 | >= 95.0 | pass |
| PTV D0.03cc[Gy] <= 72.0: MCO plan (two arcs) | 72.08 | <= 72.0 | informative |
| Lungs-GTV V20Gy[%] <= 37.0: MCO plan (two arcs) | 20.93 | <= 37.0 | pass |
| Lungs-GTV Dmean[Gy] <= 20.0: MCO plan (two arcs) | 13.26 | <= 20.0 | pass |
| SpinalCord D0.03cc[Gy] <= 50.5: MCO plan (two arcs) | 27.62 | <= 50.5 | pass |
| Esophagus Dmean[Gy] <= 34.0: MCO plan (two arcs) | 9.71 | <= 34.0 | informative |
| Heart V60Gy[%] <= 33.0: MCO plan (two arcs) | 0.46 | <= 33.0 | informative |
| Heart V45Gy[%] <= 66.0: MCO plan (two arcs) | 2.77 | <= 66.0 | informative |
| Heart V40Gy[%] <= 100.0: MCO plan (two arcs) | 4.39 | <= 100.0 | informative |
