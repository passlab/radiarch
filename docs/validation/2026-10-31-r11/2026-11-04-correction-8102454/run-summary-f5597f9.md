# Radiarch validation run 20261104-000104 (f5597f9)

RESEARCH USE ONLY. NOT FOR CLINICAL USE. Radiarch is a research treatment-planning system; its plans, doses and evaluations must not be used to treat patients.

| Case | Status | Time (s) | Checks |
|---|---|---|---|
| mco_protocol_lung | **pass** | 19387.5 | 22 pass, 0 fail, 61 informative |

## mco_protocol_lung — pass


| Check | Value | Target | Result |
|---|---|---|---|
| demo-lung-imrt: deliverable | True | True | pass |
| demo-lung-imrt-mco: deliverable | True | True | pass |
| PTV V60Gy[%] >= 95.0: MCO plan | 95.1 | >= 95.0 | pass |
| PTV V60Gy[%] >= 95.0: MCO against the reweighting plan | 95.10 vs 95.38 | informative | informative |
| PTV D0.03cc[Gy] <= 72.0: MCO plan | 80.03 | <= 72.0 | informative |
| PTV D0.03cc[Gy] <= 72.0: MCO against the reweighting plan | 80.03 vs 69.46 | informative | informative |
| Lungs-GTV V20Gy[%] <= 37.0: MCO plan | 20.97 | <= 37.0 | pass |
| Lungs-GTV V20Gy[%] <= 37.0: MCO against the reweighting plan | 20.97 vs 19.82 | informative | informative |
| Lungs-GTV Dmean[Gy] <= 20.0: MCO plan | 12.51 | <= 20.0 | pass |
| Lungs-GTV Dmean[Gy] <= 20.0: MCO against the reweighting plan | 12.51 vs 11.04 | informative | informative |
| SpinalCord D0.03cc[Gy] <= 50.5: MCO plan | 7.57 | <= 50.5 | pass |
| SpinalCord D0.03cc[Gy] <= 50.5: MCO against the reweighting plan | 7.57 vs 35.67 | informative | informative |
| Esophagus Dmean[Gy] <= 34.0: MCO plan | 1.81 | <= 34.0 | informative |
| Esophagus Dmean[Gy] <= 34.0: MCO against the reweighting plan | 1.81 vs 9.64 | informative | informative |
| Heart V60Gy[%] <= 33.0: MCO plan | 3.05 | <= 33.0 | informative |
| Heart V60Gy[%] <= 33.0: MCO against the reweighting plan | 3.05 vs 0.15 | informative | informative |
| Heart V45Gy[%] <= 66.0: MCO plan | 6.43 | <= 66.0 | informative |
| Heart V45Gy[%] <= 66.0: MCO against the reweighting plan | 6.43 vs 1.25 | informative | informative |
| Heart V40Gy[%] <= 100.0: MCO plan | 7.69 | <= 100.0 | informative |
| Heart V40Gy[%] <= 100.0: MCO against the reweighting plan | 7.69 vs 2.34 | informative | informative |
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
| deliverable (seven static fields): UniformRMS(PTV) navigated → deliverable (Gy) | 0.48 → 9.82 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): MeanDose(Lungs-PTV) navigated → deliverable (Gy) | 10.45 → 10.69 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): MeanDose(Heart) navigated → deliverable (Gy) | 7.53 → 12.09 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): MeanDose(Esophagus) navigated → deliverable (Gy) | 1.10 → 1.81 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): EUDMax(SpinalCord) navigated → deliverable (Gy) | 2.68 → 4.74 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): PTV D95%[Gy] >= 60 navigated → deliverable (Gy) | 59.10 → 60.12 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): SpinalCord Dmax[Gy] <= 45 navigated → deliverable (Gy) | 3.93 → 7.84 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): Esophagus Dmean[Gy] <= 34 navigated → deliverable (Gy) | 1.10 → 1.81 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): Heart D33%[Gy] <= 60 navigated → deliverable (Gy) | 4.77 → 11.71 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): Lungs-PTV D37%[Gy] <= 20 navigated → deliverable (Gy) | 1.33 → 3.15 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): flagged rows of the deviation table | 6 | informative | informative |
| deliverable (seven static fields): normalisation of the deliverable plan within 15 % of 1 | 1.111 | 0.85 to 1.15 | pass |
| deliverable (seven static fields): meterset rounds | 1 | informative | informative |
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
| deliverable (two arcs): UniformRMS(PTV) navigated → deliverable (Gy) | 0.55 → 9.91 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): MeanDose(Lungs-PTV) navigated → deliverable (Gy) | 9.65 → 10.13 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): MeanDose(Heart) navigated → deliverable (Gy) | 9.91 → 15.88 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): MeanDose(Esophagus) navigated → deliverable (Gy) | 5.29 → 11.26 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): EUDMax(SpinalCord) navigated → deliverable (Gy) | 7.74 → 18.19 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): PTV D95%[Gy] >= 60 navigated → deliverable (Gy) | 59.33 → 60.12 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): SpinalCord Dmax[Gy] <= 45 navigated → deliverable (Gy) | 10.64 → 27.76 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): Esophagus Dmean[Gy] <= 34 navigated → deliverable (Gy) | 5.29 → 11.26 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): Heart D33%[Gy] <= 60 navigated → deliverable (Gy) | 10.51 → 18.27 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): Lungs-PTV D37%[Gy] <= 20 navigated → deliverable (Gy) | 5.34 → 8.71 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): flagged rows of the deviation table | 8 | informative | informative |
| deliverable (two arcs): normalisation of the deliverable plan within 15 % of 1 | 1.108 | 0.85 to 1.15 | pass |
| deliverable (two arcs): meterset rounds | 1 | informative | informative |
| PTV V60Gy[%] >= 95.0: MCO plan (two arcs) | 95.25 | >= 95.0 | pass |
| PTV D0.03cc[Gy] <= 72.0: MCO plan (two arcs) | 79.9 | <= 72.0 | informative |
| Lungs-GTV V20Gy[%] <= 37.0: MCO plan (two arcs) | 17.76 | <= 37.0 | pass |
| Lungs-GTV Dmean[Gy] <= 20.0: MCO plan (two arcs) | 11.96 | <= 20.0 | pass |
| SpinalCord D0.03cc[Gy] <= 50.5: MCO plan (two arcs) | 26.88 | <= 50.5 | pass |
| Esophagus Dmean[Gy] <= 34.0: MCO plan (two arcs) | 11.26 | <= 34.0 | informative |
| Heart V60Gy[%] <= 33.0: MCO plan (two arcs) | 0.61 | <= 33.0 | informative |
| Heart V45Gy[%] <= 66.0: MCO plan (two arcs) | 2.81 | <= 66.0 | informative |
| Heart V40Gy[%] <= 100.0: MCO plan (two arcs) | 4.44 | <= 100.0 | informative |
