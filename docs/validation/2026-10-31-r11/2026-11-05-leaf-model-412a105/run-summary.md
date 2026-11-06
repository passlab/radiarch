# Radiarch validation run 20261105-223821-412a105 + 20261106-034544-412a105

RESEARCH USE ONLY. NOT FOR CLINICAL USE. Radiarch is a research treatment-planning system; its plans, doses and evaluations must not be used to treat patients.

The cases ran one per process from commit 412a105: `mco_front_tg119` (20261105-223821), `mco_protocol_lung` (20261106-034544).

| Case | Status | Time (s) | Checks |
|---|---|---|---|
| mco_front_tg119 | **pass** | 4720.3 | 8 pass, 0 fail, 32 informative |
| mco_protocol_lung | **pass** | 23163.9 | 22 pass, 0 fail, 61 informative |

## mco_front_tg119 — pass

- note: the deliverable plan's dose is recomputed by the engine from its sequenced apertures; TG-119's institutional results are deliverable plans too

| Check | Value | Target | Result |
|---|---|---|---|
| c_shape_hard: the error bound never grows as plans are added | 0.659 → 0.653 → 0.649 → 0.646 → 0.645 → 0.644 → 0.644 | non-increasing | pass |
| c_shape_hard: plans whose solve converged | 0 of 9 | informative | informative |
| c_shape_hard: plans dominated by another plan | 0 | informative | informative |
| c_shape_hard: hard constraint OuterTarget Dmin >= 25.0 Gy in every plan | 24.98 | >= 25.0 (tolerance 0.1) | pass |
| c_shape_hard: hard constraint OuterTarget Dmax <= 60.0 Gy in every plan | 60.1 | <= 60.0 (tolerance 0.1) | pass |
| c_shape_hard: error bound with 3 plans | 0.6593 | tolerance 0.01 | informative |
| c_shape_hard: error bound with 4 plans | 0.6526 | tolerance 0.01 | informative |
| c_shape_hard: error bound with 5 plans | 0.6491 | tolerance 0.01 | informative |
| c_shape_hard: error bound with 6 plans | 0.6464 | tolerance 0.01 | informative |
| c_shape_hard: error bound with 7 plans | 0.6449 | tolerance 0.01 | informative |
| c_shape_hard: error bound with 8 plans | 0.6445 | tolerance 0.01 | informative |
| c_shape_hard: error bound with 9 plans | 0.6443 | tolerance 0.01 | informative |
| plan 0 (anchor) | RMSUnder(OuterTarget) 0.00, EUDMax(Core) 16.15 | the front | informative |
| plan 1 (anchor) | RMSUnder(OuterTarget) 11.24, EUDMax(Core) 2.23 | the front | informative |
| plan 2 (balance) | RMSUnder(OuterTarget) 1.42, EUDMax(Core) 4.53 | the front | informative |
| plan 3 (sandwich) | RMSUnder(OuterTarget) 4.83, EUDMax(Core) 2.46 | the front | informative |
| plan 4 (sandwich) | RMSUnder(OuterTarget) 2.72, EUDMax(Core) 3.37 | the front | informative |
| plan 5 (sandwich) | RMSUnder(OuterTarget) 1.88, EUDMax(Core) 4.00 | the front | informative |
| plan 6 (sandwich) | RMSUnder(OuterTarget) 1.52, EUDMax(Core) 4.35 | the front | informative |
| plan 7 (sandwich) | RMSUnder(OuterTarget) 1.69, EUDMax(Core) 4.17 | the front | informative |
| plan 8 (sandwich) | RMSUnder(OuterTarget) 1.58, EUDMax(Core) 4.27 | the front | informative |
| automatic navigation: levels | 2 | informative | informative |
| navigated: OuterTarget D95%[Gy] >= 50.0 | 50 | >= 50.0 | informative |
| navigated: OuterTarget D10%[Gy] <= 55.0 | 57.86 | <= 55.0 | informative |
| navigated: Core D5%[Gy] <= 10.0 | 10 | <= 10.0 | informative |
| deliverable (static fields): deliverable | True | True | pass |
| deliverable (static fields): RMSUnder(OuterTarget) navigated → deliverable (Gy) | 1.00 → 0.55 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (static fields): EUDMax(Core) navigated → deliverable (Gy) | 8.38 → 19.08 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (static fields): OuterTarget D95%[Gy] >= 50 navigated → deliverable (Gy) | 50.00 → 50.10 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (static fields): OuterTarget D10%[Gy] <= 55 navigated → deliverable (Gy) | 57.86 → 56.04 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (static fields): Core D5%[Gy] <= 10 navigated → deliverable (Gy) | 10.00 → 22.40 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (static fields): flagged rows of the deviation table | 2 | informative | informative |
| deliverable (static fields): normalisation of the deliverable plan within 15 % of 1 | 1.028 | 0.85 to 1.15 | pass |
| deliverable (static fields): meterset rounds | 3 | informative | informative |
| deliverable: OuterTarget D95 (Gy) | 50.1 | >= 50.0 (or >= 49.78: institutional mean 50.11 ± 2 SD) | pass |
| deliverable against the recorded reweighting plan: OuterTarget D95 (Gy) | 50.10 vs 50.1 | informative | informative |
| deliverable: OuterTarget D10 (Gy) | 56.04 | <= 55.0 (or <= 61.42: institutional mean 57.02 ± 2 SD) | pass |
| deliverable against the recorded reweighting plan: OuterTarget D10 (Gy) | 56.04 vs 53.86 | informative | informative |
| deliverable: Core D5 (Gy) | 22.4 | <= 10.0 (or <= 22.44: institutional mean 16.3 ± 2 SD) | pass |
| deliverable against the recorded reweighting plan: Core D5 (Gy) | 22.40 vs 10.19 | informative | informative |

## mco_protocol_lung — pass


| Check | Value | Target | Result |
|---|---|---|---|
| demo-lung-imrt: deliverable | True | True | pass |
| demo-lung-imrt-mco: deliverable | True | True | pass |
| PTV V60Gy[%] >= 95.0: MCO plan | 95.27 | >= 95.0 | pass |
| PTV V60Gy[%] >= 95.0: MCO against the reweighting plan | 95.27 vs 95.25 | informative | informative |
| PTV D0.03cc[Gy] <= 72.0: MCO plan | 69.66 | <= 72.0 | informative |
| PTV D0.03cc[Gy] <= 72.0: MCO against the reweighting plan | 69.66 vs 68.54 | informative | informative |
| Lungs-GTV V20Gy[%] <= 37.0: MCO plan | 20.91 | <= 37.0 | pass |
| Lungs-GTV V20Gy[%] <= 37.0: MCO against the reweighting plan | 20.91 vs 20.11 | informative | informative |
| Lungs-GTV Dmean[Gy] <= 20.0: MCO plan | 12.38 | <= 20.0 | pass |
| Lungs-GTV Dmean[Gy] <= 20.0: MCO against the reweighting plan | 12.38 vs 11.25 | informative | informative |
| SpinalCord D0.03cc[Gy] <= 50.5: MCO plan | 5.56 | <= 50.5 | pass |
| SpinalCord D0.03cc[Gy] <= 50.5: MCO against the reweighting plan | 5.56 vs 35.19 | informative | informative |
| Esophagus Dmean[Gy] <= 34.0: MCO plan | 1.59 | <= 34.0 | informative |
| Esophagus Dmean[Gy] <= 34.0: MCO against the reweighting plan | 1.59 vs 9.85 | informative | informative |
| Heart V60Gy[%] <= 33.0: MCO plan | 3.64 | <= 33.0 | informative |
| Heart V60Gy[%] <= 33.0: MCO against the reweighting plan | 3.64 vs 0.12 | informative | informative |
| Heart V45Gy[%] <= 66.0: MCO plan | 5.25 | <= 66.0 | informative |
| Heart V45Gy[%] <= 66.0: MCO against the reweighting plan | 5.25 vs 1.34 | informative | informative |
| Heart V40Gy[%] <= 100.0: MCO plan | 5.69 | <= 100.0 | informative |
| Heart V40Gy[%] <= 100.0: MCO against the reweighting plan | 5.69 vs 2.42 | informative | informative |
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
| deliverable (seven static fields): UniformRMS(PTV) navigated → deliverable (Gy) | 0.48 → 5.81 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): MeanDose(Lungs-PTV) navigated → deliverable (Gy) | 10.45 → 10.64 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): MeanDose(Heart) navigated → deliverable (Gy) | 7.53 → 10.14 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): MeanDose(Esophagus) navigated → deliverable (Gy) | 1.10 → 1.59 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): EUDMax(SpinalCord) navigated → deliverable (Gy) | 2.68 → 3.77 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): PTV D95%[Gy] >= 60 navigated → deliverable (Gy) | 59.10 → 60.12 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): SpinalCord Dmax[Gy] <= 45 navigated → deliverable (Gy) | 3.93 → 5.62 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): Esophagus Dmean[Gy] <= 34 navigated → deliverable (Gy) | 1.10 → 1.59 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): Heart D33%[Gy] <= 60 navigated → deliverable (Gy) | 4.77 → 8.40 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): Lungs-PTV D37%[Gy] <= 20 navigated → deliverable (Gy) | 1.33 → 2.45 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): flagged rows of the deviation table | 6 | informative | informative |
| deliverable (seven static fields): normalisation of the deliverable plan within 15 % of 1 | 0.9673 | 0.85 to 1.15 | pass |
| deliverable (seven static fields): meterset rounds | 2 | informative | informative |
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
| deliverable (two arcs): UniformRMS(PTV) navigated → deliverable (Gy) | 0.55 → 6.60 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): MeanDose(Lungs-PTV) navigated → deliverable (Gy) | 9.65 → 12.39 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): MeanDose(Heart) navigated → deliverable (Gy) | 9.91 → 16.19 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): MeanDose(Esophagus) navigated → deliverable (Gy) | 5.29 → 11.76 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): EUDMax(SpinalCord) navigated → deliverable (Gy) | 7.74 → 23.30 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): PTV D95%[Gy] >= 60 navigated → deliverable (Gy) | 59.33 → 60.12 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): SpinalCord Dmax[Gy] <= 45 navigated → deliverable (Gy) | 10.64 → 32.39 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): Esophagus Dmean[Gy] <= 34 navigated → deliverable (Gy) | 5.29 → 11.76 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): Heart D33%[Gy] <= 60 navigated → deliverable (Gy) | 10.51 → 18.23 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): Lungs-PTV D37%[Gy] <= 20 navigated → deliverable (Gy) | 5.34 → 9.69 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): flagged rows of the deviation table | 9 | informative | informative |
| deliverable (two arcs): normalisation of the deliverable plan within 15 % of 1 | 1.003 | 0.85 to 1.15 | pass |
| deliverable (two arcs): meterset rounds | 2 | informative | informative |
| PTV V60Gy[%] >= 95.0: MCO plan (two arcs) | 95.24 | >= 95.0 | pass |
| PTV D0.03cc[Gy] <= 72.0: MCO plan (two arcs) | 72.32 | <= 72.0 | informative |
| Lungs-GTV V20Gy[%] <= 37.0: MCO plan (two arcs) | 21.64 | <= 37.0 | pass |
| Lungs-GTV Dmean[Gy] <= 20.0: MCO plan (two arcs) | 14.18 | <= 20.0 | pass |
| SpinalCord D0.03cc[Gy] <= 50.5: MCO plan (two arcs) | 32.32 | <= 50.5 | pass |
| Esophagus Dmean[Gy] <= 34.0: MCO plan (two arcs) | 11.76 | <= 34.0 | informative |
| Heart V60Gy[%] <= 33.0: MCO plan (two arcs) | 0.68 | <= 33.0 | informative |
| Heart V45Gy[%] <= 66.0: MCO plan (two arcs) | 3.29 | <= 66.0 | informative |
| Heart V40Gy[%] <= 100.0: MCO plan (two arcs) | 5.28 | <= 100.0 | informative |
