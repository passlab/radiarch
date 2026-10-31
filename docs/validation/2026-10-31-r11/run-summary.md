# Radiarch validation run 20261031-012024-b4085b0 + 20261031-015552-b4085b0 + 20261031-131756-b4085b0

RESEARCH USE ONLY. NOT FOR CLINICAL USE. Radiarch is a research treatment-planning system; its plans, doses and evaluations must not be used to treat patients.

The three cases ran one per process from commit b4085b0: `mco_front_tg119` (20261031-012024) and `mco_robust_proton` (20261031-015552) on a 20-core workstation, Python 3.14.3; `mco_protocol_lung` (20261031-131756) on a 96-core server, Python 3.12.13.

| Case | Status | Time (s) | Checks |
|---|---|---|---|
| mco_front_tg119 | **pass** | 3294.7 | 7 pass, 0 fail, 31 informative |
| mco_robust_proton | **pass** | 2125.7 | 11 pass, 0 fail, 26 informative |
| mco_protocol_lung | **pass** | 28948.9 | 20 pass, 0 fail, 59 informative |

## mco_front_tg119 — pass

- note: the deliverable plan's dose is recomputed by the engine from its sequenced apertures; TG-119's institutional results are deliverable plans too

| Check | Value | Target | Result |
|---|---|---|---|
| c_shape_hard: the error bound never grows as plans are added | 0.659 → 0.651 → 0.647 → 0.644 → 0.643 → 0.643 → 0.642 | non-increasing | pass |
| c_shape_hard: plans whose solve converged | 0 of 9 | informative | informative |
| c_shape_hard: plans dominated by another plan | 0 | informative | informative |
| c_shape_hard: hard constraint OuterTarget Dmin >= 25.0 Gy in every plan | 24.98 | >= 25.0 (tolerance 0.1) | pass |
| c_shape_hard: hard constraint OuterTarget Dmax <= 60.0 Gy in every plan | 60.07 | <= 60.0 (tolerance 0.1) | pass |
| c_shape_hard: error bound with 3 plans | 0.6592 | tolerance 0.01 | informative |
| c_shape_hard: error bound with 4 plans | 0.6511 | tolerance 0.01 | informative |
| c_shape_hard: error bound with 5 plans | 0.647 | tolerance 0.01 | informative |
| c_shape_hard: error bound with 6 plans | 0.6442 | tolerance 0.01 | informative |
| c_shape_hard: error bound with 7 plans | 0.6428 | tolerance 0.01 | informative |
| c_shape_hard: error bound with 8 plans | 0.6427 | tolerance 0.01 | informative |
| c_shape_hard: error bound with 9 plans | 0.6425 | tolerance 0.01 | informative |
| plan 0 (anchor) | RMSUnder(OuterTarget) 0.00, EUDMax(Core) 16.56 | the front | informative |
| plan 1 (anchor) | RMSUnder(OuterTarget) 11.15, EUDMax(Core) 2.23 | the front | informative |
| plan 2 (balance) | RMSUnder(OuterTarget) 1.32, EUDMax(Core) 4.62 | the front | informative |
| plan 3 (sandwich) | RMSUnder(OuterTarget) 4.78, EUDMax(Core) 2.47 | the front | informative |
| plan 4 (sandwich) | RMSUnder(OuterTarget) 2.65, EUDMax(Core) 3.42 | the front | informative |
| plan 5 (sandwich) | RMSUnder(OuterTarget) 1.84, EUDMax(Core) 4.03 | the front | informative |
| plan 6 (sandwich) | RMSUnder(OuterTarget) 1.54, EUDMax(Core) 4.33 | the front | informative |
| plan 7 (sandwich) | RMSUnder(OuterTarget) 1.69, EUDMax(Core) 4.17 | the front | informative |
| plan 8 (sandwich) | RMSUnder(OuterTarget) 1.58, EUDMax(Core) 4.28 | the front | informative |
| automatic navigation: levels | 2 | informative | informative |
| navigated: OuterTarget D95%[Gy] >= 50.0 | 50 | >= 50.0 | informative |
| navigated: OuterTarget D10%[Gy] <= 55.0 | 58.39 | <= 55.0 | informative |
| navigated: Core D5%[Gy] <= 10.0 | 9.14 | <= 10.0 | informative |
| deliverable (static fields): deliverable | True | True | pass |
| deliverable (static fields): RMSUnder(OuterTarget) navigated → deliverable (Gy) | 0.97 → 0.83 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (static fields): EUDMax(Core) navigated → deliverable (Gy) | 7.66 → 5.28 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (static fields): OuterTarget D95%[Gy] >= 50 navigated → deliverable (Gy) | 50.00 → 50.10 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (static fields): OuterTarget D10%[Gy] <= 55 navigated → deliverable (Gy) | 58.39 → 60.89 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (static fields): Core D5%[Gy] <= 10 navigated → deliverable (Gy) | 9.14 → 6.16 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (static fields): flagged rows of the deviation table | 1 | informative | informative |
| deliverable: OuterTarget D95 (Gy) | 50.1 | >= 50.0 (or >= 49.78: institutional mean 50.11 ± 2 SD) | pass |
| deliverable against the recorded reweighting plan: OuterTarget D95 (Gy) | 50.10 vs 50.1 | informative | informative |
| deliverable: OuterTarget D10 (Gy) | 60.89 | <= 55.0 (or <= 61.42: institutional mean 57.02 ± 2 SD) | pass |
| deliverable against the recorded reweighting plan: OuterTarget D10 (Gy) | 60.89 vs 53.86 | informative | informative |
| deliverable: Core D5 (Gy) | 6.16 | <= 10.0 (or <= 22.44: institutional mean 16.3 ± 2 SD) | pass |
| deliverable against the recorded reweighting plan: Core D5 (Gy) | 6.16 vs 10.19 | informative | informative |

## mco_robust_proton — pass


| Check | Value | Target | Result |
|---|---|---|---|
| robust set: the error bound never grows as plans are added | 0.150 → 0.106 → 0.081 → 0.077 → 0.071 | non-increasing | pass |
| robust set: plans whose solve converged | 7 of 7 | informative | informative |
| robust set: plans dominated by another plan | 0 | informative | informative |
| robust set: each converged plan is the best of the set in its own worst-scenario sum | 0 | <= 0.01 | pass |
| robust set: hard constraint CTV Dmin >= 1.7 Gy in every plan and all 5 scenarios | 1.682 | >= 1.7 (tolerance 0.02) | pass |
| robust set: error bound with 3 plans | 0.1498 | tolerance 0.02 | informative |
| robust set: error bound with 4 plans | 0.1064 | tolerance 0.02 | informative |
| robust set: error bound with 5 plans | 0.0808 | tolerance 0.02 | informative |
| robust set: error bound with 6 plans | 0.0767 | tolerance 0.02 | informative |
| robust set: error bound with 7 plans | 0.0708 | tolerance 0.02 | informative |
| nominal set: the error bound never grows as plans are added | 0.086 → 0.062 → 0.026 → 0.023 → 0.020 | non-increasing | pass |
| nominal set: plans whose solve converged | 7 of 7 | informative | informative |
| nominal set: plans dominated by another plan | 0 | informative | informative |
| nominal set: each converged plan is the best of the set in its own weighted sum | 0 | <= 0.01 | pass |
| nominal set: hard constraint CTV Dmin >= 1.7 Gy in every plan | 1.691 | >= 1.7 (tolerance 0.02) | pass |
| nominal set: error bound with 3 plans | 0.0861 | tolerance 0.02 | informative |
| nominal set: error bound with 4 plans | 0.0617 | tolerance 0.02 | informative |
| nominal set: error bound with 5 plans | 0.026 | tolerance 0.02 | informative |
| nominal set: error bound with 6 plans | 0.0235 | tolerance 0.02 | informative |
| nominal set: error bound with 7 plans | 0.0201 | tolerance 0.02 | informative |
| robust set: scenarios | nominal, range_up, range_down, shift_left, shift_right | nominal first | pass |
| robust set: every worst case at least its nominal value | 0 | = 0 | pass |
| robust set: the robust gap within the error bound | 0.06966 | <= 0.070822 | pass |
| nominal plans that meet the hard constraints in every scenario | 0 of 7 | informative | informative |
| converged robust plans protect their worst scenario better than any nominal plan | nothing to compare | <= 0 | informative |
| balance plans, UniformRMS(CTV): robust worst case vs nominal plan's worst case (Gy) | 0.196 vs 0.184 | informative | informative |
| balance plans, MeanDose(OAR): robust worst case vs nominal plan's worst case (Gy) | 0.081 vs 0.090 | informative | informative |
| navigated state: worst cases within the linear bound | 0.332 ≤ 0.379, 0.112 ≤ 0.112 | value <= bound | pass |
| navigated: CTV D95%[Gy] >= 1.9 | nominal 1.934, worst 1.900 | >= 1.9 | informative |
| navigated: OAR Dmean[Gy] <= 0.5 | nominal 0.066, worst 0.112 | <= 0.5 | informative |
| navigated: every goal met in every scenario | True | informative | informative |
| deliverable (spots): deliverable | True | True | pass |
| deliverable (spots): UniformRMS(CTV) navigated → deliverable (Gy) | 0.33 → 0.16 | flagged when worse by more than 0.04 Gy or 1.0 % volume | informative |
| deliverable (spots): MeanDose(OAR) navigated → deliverable (Gy) | 0.11 → 0.07 | flagged when worse by more than 0.04 Gy or 1.0 % volume | informative |
| deliverable (spots): CTV D95%[Gy] >= 1.9 navigated → deliverable (Gy) | 1.90 → 1.79 | flagged when worse by more than 0.04 Gy or 1.0 % volume | informative |
| deliverable (spots): OAR Dmean[Gy] <= 0.5 navigated → deliverable (Gy) | 0.11 → 0.07 | flagged when worse by more than 0.04 Gy or 1.0 % volume | informative |
| deliverable (spots): flagged rows of the deviation table | 1 | informative | informative |

## mco_protocol_lung — pass


| Check | Value | Target | Result |
|---|---|---|---|
| demo-lung-imrt: deliverable | True | True | pass |
| demo-lung-imrt-mco: deliverable | True | True | pass |
| PTV V60Gy[%] >= 95.0: MCO plan | 95.17 | >= 95.0 | pass |
| PTV V60Gy[%] >= 95.0: MCO against the reweighting plan | 95.17 vs 95.38 | informative | informative |
| PTV D0.03cc[Gy] <= 72.0: MCO plan | 85.8 | <= 72.0 | informative |
| PTV D0.03cc[Gy] <= 72.0: MCO against the reweighting plan | 85.80 vs 69.46 | informative | informative |
| Lungs-GTV V20Gy[%] <= 37.0: MCO plan | 18.92 | <= 37.0 | pass |
| Lungs-GTV V20Gy[%] <= 37.0: MCO against the reweighting plan | 18.92 vs 19.82 | informative | informative |
| Lungs-GTV Dmean[Gy] <= 20.0: MCO plan | 11.86 | <= 20.0 | pass |
| Lungs-GTV Dmean[Gy] <= 20.0: MCO against the reweighting plan | 11.86 vs 11.04 | informative | informative |
| SpinalCord D0.03cc[Gy] <= 50.5: MCO plan | 4.87 | <= 50.5 | pass |
| SpinalCord D0.03cc[Gy] <= 50.5: MCO against the reweighting plan | 4.87 vs 35.67 | informative | informative |
| Esophagus Dmean[Gy] <= 34.0: MCO plan | 1.1 | <= 34.0 | informative |
| Esophagus Dmean[Gy] <= 34.0: MCO against the reweighting plan | 1.10 vs 9.64 | informative | informative |
| Heart V60Gy[%] <= 33.0: MCO plan | 3.72 | <= 33.0 | informative |
| Heart V60Gy[%] <= 33.0: MCO against the reweighting plan | 3.72 vs 0.15 | informative | informative |
| Heart V45Gy[%] <= 66.0: MCO plan | 4.59 | <= 66.0 | informative |
| Heart V45Gy[%] <= 66.0: MCO against the reweighting plan | 4.59 vs 1.25 | informative | informative |
| Heart V40Gy[%] <= 100.0: MCO plan | 4.88 | <= 100.0 | informative |
| Heart V40Gy[%] <= 100.0: MCO against the reweighting plan | 4.88 vs 2.34 | informative | informative |
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
| deliverable (seven static fields): UniformRMS(PTV) navigated → deliverable (Gy) | 0.48 → 11.18 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): MeanDose(Lungs-PTV) navigated → deliverable (Gy) | 10.45 → 9.92 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): MeanDose(Heart) navigated → deliverable (Gy) | 7.53 → 6.04 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): MeanDose(Esophagus) navigated → deliverable (Gy) | 1.10 → 1.10 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): EUDMax(SpinalCord) navigated → deliverable (Gy) | 2.68 → 3.19 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): PTV D95%[Gy] >= 60 navigated → deliverable (Gy) | 59.10 → 60.12 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): SpinalCord Dmax[Gy] <= 45 navigated → deliverable (Gy) | 3.93 → 5.13 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): Esophagus Dmean[Gy] <= 34 navigated → deliverable (Gy) | 1.10 → 1.10 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): Heart D33%[Gy] <= 60 navigated → deliverable (Gy) | 4.77 → 2.34 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): Lungs-PTV D37%[Gy] <= 20 navigated → deliverable (Gy) | 1.33 → 1.22 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): flagged rows of the deviation table | 2 | informative | informative |
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
| deliverable (two arcs): UniformRMS(PTV) navigated → deliverable (Gy) | 0.55 → 24.20 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): MeanDose(Lungs-PTV) navigated → deliverable (Gy) | 9.65 → 10.88 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): MeanDose(Heart) navigated → deliverable (Gy) | 9.91 → 4.88 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): MeanDose(Esophagus) navigated → deliverable (Gy) | 5.29 → 2.03 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): EUDMax(SpinalCord) navigated → deliverable (Gy) | 7.74 → 23.94 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): PTV D95%[Gy] >= 60 navigated → deliverable (Gy) | 59.33 → 60.12 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): SpinalCord Dmax[Gy] <= 45 navigated → deliverable (Gy) | 10.64 → 41.79 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): Esophagus Dmean[Gy] <= 34 navigated → deliverable (Gy) | 5.29 → 2.03 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): Heart D33%[Gy] <= 60 navigated → deliverable (Gy) | 10.51 → 3.18 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): Lungs-PTV D37%[Gy] <= 20 navigated → deliverable (Gy) | 5.34 → 2.34 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): flagged rows of the deviation table | 4 | informative | informative |
| PTV V60Gy[%] >= 95.0: MCO plan (two arcs) | 95.05 | >= 95.0 | pass |
| PTV D0.03cc[Gy] <= 72.0: MCO plan (two arcs) | 149.2 | <= 72.0 | informative |
| Lungs-GTV V20Gy[%] <= 37.0: MCO plan (two arcs) | 18.02 | <= 37.0 | pass |
| Lungs-GTV Dmean[Gy] <= 20.0: MCO plan (two arcs) | 13.12 | <= 20.0 | pass |
| SpinalCord D0.03cc[Gy] <= 50.5: MCO plan (two arcs) | 38.91 | <= 50.5 | pass |
| Esophagus Dmean[Gy] <= 34.0: MCO plan (two arcs) | 2.03 | <= 34.0 | informative |
| Heart V60Gy[%] <= 33.0: MCO plan (two arcs) | 0.42 | <= 33.0 | informative |
| Heart V45Gy[%] <= 66.0: MCO plan (two arcs) | 1.23 | <= 66.0 | informative |
| Heart V40Gy[%] <= 100.0: MCO plan (two arcs) | 1.7 | <= 100.0 | informative |
