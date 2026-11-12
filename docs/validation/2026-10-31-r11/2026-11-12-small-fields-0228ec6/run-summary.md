# Radiarch validation run 20261112-144407-0228ec6 + 20261112-185958-0228ec6

RESEARCH USE ONLY. NOT FOR CLINICAL USE. Radiarch is a research treatment-planning system; its plans, doses and evaluations must not be used to treat patients.

The cases ran one per process from commit 0228ec6: `mco_front_tg119` (20261112-144407), `mco_protocol_lung` (20261112-185958).

| Case | Status | Time (s) | Checks |
|---|---|---|---|
| mco_front_tg119 | **fail** | 4650.3 | 18 pass, 1 fail, 52 informative |
| mco_protocol_lung | **pass** | 20001.2 | 38 pass, 0 fail, 121 informative |

## mco_front_tg119 — fail

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
| deliverable (static fields): OuterTarget D10%[Gy] <= 55 navigated → deliverable (Gy) | 57.86 → 56.02 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (static fields): Core D5%[Gy] <= 10 navigated → deliverable (Gy) | 10.00 → 22.45 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (static fields): flagged rows of the deviation table | 2 | informative | informative |
| deliverable (static fields): normalisation of the deliverable plan within 15 % of 1 | 1.028 | 0.85 to 1.15 | pass |
| deliverable (static fields): meterset rounds | 3 | informative | informative |
| deliverable: OuterTarget D95 (Gy) | 50.1 | >= 50.0 (or >= 49.78: institutional mean 50.11 ± 2 SD) | pass |
| deliverable against the recorded reweighting plan: OuterTarget D95 (Gy) | 50.10 vs 50.1 | informative | informative |
| deliverable: OuterTarget D10 (Gy) | 56.02 | <= 55.0 (or <= 61.42: institutional mean 57.02 ± 2 SD) | pass |
| deliverable against the recorded reweighting plan: OuterTarget D10 (Gy) | 56.02 vs 53.86 | informative | informative |
| deliverable: Core D5 (Gy) | 22.45 | <= 10.0 (or <= 22.44: institutional mean 16.3 ± 2 SD) | FAIL |
| deliverable against the recorded reweighting plan: Core D5 (Gy) | 22.45 vs 10.19 | informative | informative |
| static fields: second set: the error bound never grows as plans are added | 0.127 → 0.112 → 0.030 | non-increasing | pass |
| static fields: second set: plans whose solve converged | 5 of 5 | informative | informative |
| static fields: second set: plans dominated by another plan | 0 | informative | informative |
| static fields: second set: each converged plan is the best of the set in its own weighted sum | 0 | <= 0.01 | pass |
| static fields: second set: hard constraint OuterTarget Dmin >= 25.0 Gy in every plan | 39.1 | >= 25.0 (tolerance 0.1) | pass |
| static fields: second set: hard constraint OuterTarget Dmax <= 60.0 Gy in every plan | 60.1 | <= 60.0 (tolerance 0.1) | pass |
| static fields: second set: hard constraint OuterTarget gEUD >= 53.286 Gy in every plan | 52.83 | >= 53.286 (tolerance 0.5329) | pass |
| static fields: second set: hard constraint OuterTarget Dmax <= 60.0 Gy in every plan | 60.1 | <= 60.0 (tolerance 0.6) | pass |
| static fields: second set: error bound with 3 plans | 0.1271 | tolerance 0.05 | informative |
| static fields: second set: error bound with 4 plans | 0.1124 | tolerance 0.05 | informative |
| static fields: second set: error bound with 5 plans | 0.03 | tolerance 0.05 | informative |
| static fields: second set | 5 plans on 71 segments | informative | informative |
| static fields: plan on the second set: deliverable | True | True | pass |
| static fields: plan on the second set: RMSUnder(OuterTarget) navigated → deliverable (Gy) | 0.54 → 0.53 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| static fields: plan on the second set: EUDMax(Core) navigated → deliverable (Gy) | 16.32 → 16.35 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| static fields: plan on the second set: OuterTarget D95%[Gy] >= 50 navigated → deliverable (Gy) | 50.00 → 50.10 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| static fields: plan on the second set: OuterTarget D10%[Gy] <= 55 navigated → deliverable (Gy) | 58.23 → 58.35 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| static fields: plan on the second set: Core D5%[Gy] <= 10 navigated → deliverable (Gy) | 19.10 → 19.14 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| static fields: plan on the second set: flagged rows of the deviation table | 0 | informative | informative |
| static fields: plan on the second set: normalisation of the deliverable plan within 15 % of 1 | 1.002 | 0.85 to 1.15 | pass |
| static fields: RMSUnder(OuterTarget) navigated → deliverable → second navigation → plan (Gy) | 1.00 → 0.55 → 0.54 → 0.53 | informative | informative |
| static fields: EUDMax(Core) navigated → deliverable → second navigation → plan (Gy) | 8.38 → 19.08 → 16.32 → 16.35 | informative | informative |
| static fields: OuterTarget D95%[Gy] >= 50 navigated → deliverable → second navigation → plan (Gy) | 50.00 → 50.10 → 50.00 → 50.10 | informative | informative |
| static fields: OuterTarget D10%[Gy] <= 55 navigated → deliverable → second navigation → plan (Gy) | 57.86 → 56.02 → 58.23 → 58.35 | informative | informative |
| static fields: Core D5%[Gy] <= 10 navigated → deliverable → second navigation → plan (Gy) | 10.00 → 22.45 → 19.10 → 19.14 | informative | informative |
| plan on the second set: OuterTarget D95 (Gy) | 50.1 | >= 50.0 (or >= 49.78: institutional mean 50.11 ± 2 SD) | pass |
| plan on the second set against the recorded reweighting plan: OuterTarget D95 (Gy) | 50.10 vs 50.1 | informative | informative |
| plan on the second set: OuterTarget D10 (Gy) | 58.35 | <= 55.0 (or <= 61.42: institutional mean 57.02 ± 2 SD) | pass |
| plan on the second set against the recorded reweighting plan: OuterTarget D10 (Gy) | 58.35 vs 53.86 | informative | informative |
| plan on the second set: Core D5 (Gy) | 19.14 | <= 10.0 (or <= 22.44: institutional mean 16.3 ± 2 SD) | pass |
| plan on the second set against the recorded reweighting plan: Core D5 (Gy) | 19.14 vs 10.19 | informative | informative |

## mco_protocol_lung — pass


| Check | Value | Target | Result |
|---|---|---|---|
| demo-lung-imrt: deliverable | True | True | pass |
| demo-lung-imrt-mco: deliverable | True | True | pass |
| PTV V60Gy[%] >= 95.0: MCO plan | 95.33 | >= 95.0 | pass |
| PTV V60Gy[%] >= 95.0: MCO against the reweighting plan | 95.33 vs 95.28 | informative | informative |
| PTV D0.03cc[Gy] <= 72.0: MCO plan | 71.35 | <= 72.0 | informative |
| PTV D0.03cc[Gy] <= 72.0: MCO against the reweighting plan | 71.35 vs 69.80 | informative | informative |
| Lungs-GTV V20Gy[%] <= 37.0: MCO plan | 20.91 | <= 37.0 | pass |
| Lungs-GTV V20Gy[%] <= 37.0: MCO against the reweighting plan | 20.91 vs 20.09 | informative | informative |
| Lungs-GTV Dmean[Gy] <= 20.0: MCO plan | 12.13 | <= 20.0 | pass |
| Lungs-GTV Dmean[Gy] <= 20.0: MCO against the reweighting plan | 12.13 vs 11.24 | informative | informative |
| SpinalCord D0.03cc[Gy] <= 50.5: MCO plan | 21.38 | <= 50.5 | pass |
| SpinalCord D0.03cc[Gy] <= 50.5: MCO against the reweighting plan | 21.38 vs 33.03 | informative | informative |
| Esophagus Dmean[Gy] <= 34.0: MCO plan | 3.25 | <= 34.0 | informative |
| Esophagus Dmean[Gy] <= 34.0: MCO against the reweighting plan | 3.25 vs 9.93 | informative | informative |
| Heart V60Gy[%] <= 33.0: MCO plan | 0.33 | <= 33.0 | informative |
| Heart V60Gy[%] <= 33.0: MCO against the reweighting plan | 0.33 vs 0.18 | informative | informative |
| Heart V45Gy[%] <= 66.0: MCO plan | 2.98 | <= 66.0 | informative |
| Heart V45Gy[%] <= 66.0: MCO against the reweighting plan | 2.98 vs 1.26 | informative | informative |
| Heart V40Gy[%] <= 100.0: MCO plan | 3.92 | <= 100.0 | informative |
| Heart V40Gy[%] <= 100.0: MCO against the reweighting plan | 3.92 vs 2.43 | informative | informative |
| Pareto set: the error bound never grows as plans are added | 0.760 → 0.740 → 0.693 → 0.669 → 0.621 → 0.611 → 0.598 → 0.583 → 0.582 → 0.568 → 0.560 | non-increasing | pass |
| Pareto set: plans whose solve converged | 5 of 16 | informative | informative |
| Pareto set: plans dominated by another plan | 0 | informative | informative |
| Pareto set: each converged plan is the best of the set in its own weighted sum | 0 | <= 0.01 | pass |
| Pareto set: hard constraint SpinalCord Dmax <= 45.0 Gy in every plan | 45.04 | <= 45.0 (tolerance 0.1) | pass |
| Pareto set: hard constraint PTV Dmin >= 54.0 Gy in every plan | 53.92 | >= 54.0 (tolerance 0.1) | pass |
| Pareto set: error bound with 6 plans | 0.7597 | tolerance 0.05 | informative |
| Pareto set: error bound with 7 plans | 0.7402 | tolerance 0.05 | informative |
| Pareto set: error bound with 8 plans | 0.6935 | tolerance 0.05 | informative |
| Pareto set: error bound with 9 plans | 0.6694 | tolerance 0.05 | informative |
| Pareto set: error bound with 10 plans | 0.6208 | tolerance 0.05 | informative |
| Pareto set: error bound with 11 plans | 0.6108 | tolerance 0.05 | informative |
| Pareto set: error bound with 12 plans | 0.5982 | tolerance 0.05 | informative |
| Pareto set: error bound with 13 plans | 0.5828 | tolerance 0.05 | informative |
| Pareto set: error bound with 14 plans | 0.5821 | tolerance 0.05 | informative |
| Pareto set: error bound with 15 plans | 0.5679 | tolerance 0.05 | informative |
| Pareto set: error bound with 16 plans | 0.5604 | tolerance 0.05 | informative |
| deliverable (seven static fields): deliverable | True | True | pass |
| deliverable (seven static fields): UniformRMS(PTV) navigated → deliverable (Gy) | 0.67 → 5.88 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): MeanDose(Lungs-PTV) navigated → deliverable (Gy) | 10.39 → 10.91 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): MeanDose(Heart) navigated → deliverable (Gy) | 8.71 → 19.32 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): MeanDose(Esophagus) navigated → deliverable (Gy) | 3.98 → 9.10 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): EUDMax(SpinalCord) navigated → deliverable (Gy) | 13.24 → 17.22 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): PTV D95%[Gy] >= 60 navigated → deliverable (Gy) | 59.09 → 60.12 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): SpinalCord Dmax[Gy] <= 45 navigated → deliverable (Gy) | 18.73 → 24.93 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): Esophagus Dmean[Gy] <= 34 navigated → deliverable (Gy) | 3.98 → 9.10 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): Heart D33%[Gy] <= 60 navigated → deliverable (Gy) | 9.45 → 25.45 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): Lungs-PTV D37%[Gy] <= 20 navigated → deliverable (Gy) | 3.33 → 8.30 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): flagged rows of the deviation table | 8 | informative | informative |
| deliverable (seven static fields): normalisation of the deliverable plan within 15 % of 1 | 0.9851 | 0.85 to 1.15 | pass |
| deliverable (seven static fields): meterset rounds | 2 | informative | informative |
| seven static fields: second set: the error bound never grows as plans are added | 0.462 → 0.443 → 0.437 → 0.409 → 0.390 → 0.389 | non-increasing | pass |
| seven static fields: second set: plans whose solve converged | 11 of 11 | informative | informative |
| seven static fields: second set: plans dominated by another plan | 0 | informative | informative |
| seven static fields: second set: each converged plan is the best of the set in its own weighted sum | 0 | <= 0.01 | pass |
| seven static fields: second set: hard constraint SpinalCord Dmax <= 45.0 Gy in every plan | 41.1 | <= 45.0 (tolerance 0.1) | pass |
| seven static fields: second set: hard constraint PTV Dmin >= 54.0 Gy in every plan | 54.01 | >= 54.0 (tolerance 0.1) | pass |
| seven static fields: second set: hard constraint PTV gEUD >= 64.394 Gy in every plan | 64.39 | >= 64.394 (tolerance 0.6439) | pass |
| seven static fields: second set: hard constraint PTV Dmax <= 72.0 Gy in every plan | 72.72 | <= 72.0 (tolerance 0.72) | pass |
| seven static fields: second set: error bound with 6 plans | 0.4624 | tolerance 0.05 | informative |
| seven static fields: second set: error bound with 7 plans | 0.4426 | tolerance 0.05 | informative |
| seven static fields: second set: error bound with 8 plans | 0.4368 | tolerance 0.05 | informative |
| seven static fields: second set: error bound with 9 plans | 0.4095 | tolerance 0.05 | informative |
| seven static fields: second set: error bound with 10 plans | 0.3895 | tolerance 0.05 | informative |
| seven static fields: second set: error bound with 11 plans | 0.3893 | tolerance 0.05 | informative |
| seven static fields: second set | 11 plans on 70 segments | informative | informative |
| seven static fields: plan on the second set: deliverable | True | True | pass |
| seven static fields: plan on the second set: UniformRMS(PTV) navigated → deliverable (Gy) | 5.56 → 4.96 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: MeanDose(Lungs-PTV) navigated → deliverable (Gy) | 10.49 → 10.38 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: MeanDose(Heart) navigated → deliverable (Gy) | 11.49 → 11.37 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: MeanDose(Esophagus) navigated → deliverable (Gy) | 3.28 → 3.25 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: EUDMax(SpinalCord) navigated → deliverable (Gy) | 15.01 → 14.86 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: PTV D95%[Gy] >= 60 navigated → deliverable (Gy) | 60.75 → 60.12 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: SpinalCord Dmax[Gy] <= 45 navigated → deliverable (Gy) | 21.78 → 21.55 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: Esophagus Dmean[Gy] <= 34 navigated → deliverable (Gy) | 3.28 → 3.25 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: Heart D33%[Gy] <= 60 navigated → deliverable (Gy) | 14.75 → 14.59 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: Lungs-PTV D37%[Gy] <= 20 navigated → deliverable (Gy) | 2.58 → 2.56 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: flagged rows of the deviation table | 0 | informative | informative |
| seven static fields: plan on the second set: normalisation of the deliverable plan within 15 % of 1 | 0.9896 | 0.85 to 1.15 | pass |
| seven static fields: UniformRMS(PTV) navigated → deliverable → second navigation → plan (Gy) | 0.67 → 5.88 → 5.56 → 4.96 | informative | informative |
| seven static fields: MeanDose(Lungs-PTV) navigated → deliverable → second navigation → plan (Gy) | 10.39 → 10.91 → 10.49 → 10.38 | informative | informative |
| seven static fields: MeanDose(Heart) navigated → deliverable → second navigation → plan (Gy) | 8.71 → 19.32 → 11.49 → 11.37 | informative | informative |
| seven static fields: MeanDose(Esophagus) navigated → deliverable → second navigation → plan (Gy) | 3.98 → 9.10 → 3.28 → 3.25 | informative | informative |
| seven static fields: EUDMax(SpinalCord) navigated → deliverable → second navigation → plan (Gy) | 13.24 → 17.22 → 15.01 → 14.86 | informative | informative |
| seven static fields: PTV D95%[Gy] >= 60 navigated → deliverable → second navigation → plan (Gy) | 59.09 → 60.12 → 60.75 → 60.12 | informative | informative |
| seven static fields: SpinalCord Dmax[Gy] <= 45 navigated → deliverable → second navigation → plan (Gy) | 18.73 → 24.93 → 21.78 → 21.55 | informative | informative |
| seven static fields: Esophagus Dmean[Gy] <= 34 navigated → deliverable → second navigation → plan (Gy) | 3.98 → 9.10 → 3.28 → 3.25 | informative | informative |
| seven static fields: Heart D33%[Gy] <= 60 navigated → deliverable → second navigation → plan (Gy) | 9.45 → 25.45 → 14.75 → 14.59 | informative | informative |
| seven static fields: Lungs-PTV D37%[Gy] <= 20 navigated → deliverable → second navigation → plan (Gy) | 3.33 → 8.30 → 2.58 → 2.56 | informative | informative |
| demo-lung-imrt-mco-arcs: deliverable | True | True | pass |
| Pareto set on the arcs' sectors: the error bound never grows as plans are added | 0.821 → 0.816 → 0.764 | non-increasing | pass |
| Pareto set on the arcs' sectors: plans whose solve converged | 0 of 8 | informative | informative |
| Pareto set on the arcs' sectors: plans dominated by another plan | 0 | informative | informative |
| Pareto set on the arcs' sectors: hard constraint SpinalCord Dmax <= 45.0 Gy in every plan | 44.99 | <= 45.0 (tolerance 0.1) | pass |
| Pareto set on the arcs' sectors: hard constraint PTV Dmin >= 54.0 Gy in every plan | 53.9 | >= 54.0 (tolerance 0.1) | pass |
| Pareto set on the arcs' sectors: error bound with 6 plans | 0.8209 | tolerance 0.05 | informative |
| Pareto set on the arcs' sectors: error bound with 7 plans | 0.8162 | tolerance 0.05 | informative |
| Pareto set on the arcs' sectors: error bound with 8 plans | 0.7637 | tolerance 0.05 | informative |
| deliverable (two arcs): deliverable | True | True | pass |
| deliverable (two arcs): UniformRMS(PTV) navigated → deliverable (Gy) | 0.52 → 6.13 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): MeanDose(Lungs-PTV) navigated → deliverable (Gy) | 10.28 → 14.09 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): MeanDose(Heart) navigated → deliverable (Gy) | 13.23 → 19.13 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): MeanDose(Esophagus) navigated → deliverable (Gy) | 7.36 → 13.19 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): EUDMax(SpinalCord) navigated → deliverable (Gy) | 12.34 → 28.41 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): PTV D95%[Gy] >= 60 navigated → deliverable (Gy) | 59.41 → 60.12 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): SpinalCord Dmax[Gy] <= 45 navigated → deliverable (Gy) | 18.40 → 42.45 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): Esophagus Dmean[Gy] <= 34 navigated → deliverable (Gy) | 7.36 → 13.19 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): Heart D33%[Gy] <= 60 navigated → deliverable (Gy) | 14.72 → 22.21 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): Lungs-PTV D37%[Gy] <= 20 navigated → deliverable (Gy) | 7.04 → 12.08 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): flagged rows of the deviation table | 9 | informative | informative |
| deliverable (two arcs): normalisation of the deliverable plan within 15 % of 1 | 0.9972 | 0.85 to 1.15 | pass |
| deliverable (two arcs): meterset rounds | 2 | informative | informative |
| two arcs: second set: the error bound never grows as plans are added | 1.031 → 0.969 → 0.960 → 0.954 → 0.925 → 0.854 | non-increasing | pass |
| two arcs: second set: plans whose solve converged | 1 of 11 | informative | informative |
| two arcs: second set: plans dominated by another plan | 0 | informative | informative |
| two arcs: second set: each converged plan is the best of the set in its own weighted sum | 0 | <= 0.01 | pass |
| two arcs: second set: hard constraint SpinalCord Dmax <= 45.0 Gy in every plan | 39.49 | <= 45.0 (tolerance 0.1) | pass |
| two arcs: second set: hard constraint PTV Dmin >= 54.0 Gy in every plan | 54.12 | >= 54.0 (tolerance 0.1) | pass |
| two arcs: second set: hard constraint PTV gEUD >= 64.503 Gy in every plan | 64.5 | >= 64.503 (tolerance 0.645) | pass |
| two arcs: second set: hard constraint PTV Dmax <= 72.0 Gy in every plan | 72.47 | <= 72.0 (tolerance 0.72) | pass |
| two arcs: second set: error bound with 6 plans | 1.031 | tolerance 0.05 | informative |
| two arcs: second set: error bound with 7 plans | 0.9694 | tolerance 0.05 | informative |
| two arcs: second set: error bound with 8 plans | 0.9598 | tolerance 0.05 | informative |
| two arcs: second set: error bound with 9 plans | 0.954 | tolerance 0.05 | informative |
| two arcs: second set: error bound with 10 plans | 0.925 | tolerance 0.05 | informative |
| two arcs: second set: error bound with 11 plans | 0.8545 | tolerance 0.05 | informative |
| two arcs: second set | 11 plans on 192 arc intervals | informative | informative |
| two arcs: plan on the second set: deliverable | True | True | pass |
| two arcs: plan on the second set: UniformRMS(PTV) navigated → deliverable (Gy) | 6.27 → 6.38 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: MeanDose(Lungs-PTV) navigated → deliverable (Gy) | 12.88 → 12.90 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: MeanDose(Heart) navigated → deliverable (Gy) | 16.45 → 16.49 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: MeanDose(Esophagus) navigated → deliverable (Gy) | 10.95 → 10.97 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: EUDMax(SpinalCord) navigated → deliverable (Gy) | 22.65 → 22.69 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: PTV D95%[Gy] >= 60 navigated → deliverable (Gy) | 60.00 → 60.12 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: SpinalCord Dmax[Gy] <= 45 navigated → deliverable (Gy) | 33.16 → 33.19 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: Esophagus Dmean[Gy] <= 34 navigated → deliverable (Gy) | 10.95 → 10.97 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: Heart D33%[Gy] <= 60 navigated → deliverable (Gy) | 18.20 → 18.25 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: Lungs-PTV D37%[Gy] <= 20 navigated → deliverable (Gy) | 8.24 → 8.26 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: flagged rows of the deviation table | 0 | informative | informative |
| two arcs: plan on the second set: normalisation of the deliverable plan within 15 % of 1 | 1.002 | 0.85 to 1.15 | pass |
| two arcs: UniformRMS(PTV) navigated → deliverable → second navigation → plan (Gy) | 0.52 → 6.13 → 6.27 → 6.38 | informative | informative |
| two arcs: MeanDose(Lungs-PTV) navigated → deliverable → second navigation → plan (Gy) | 10.28 → 14.09 → 12.88 → 12.90 | informative | informative |
| two arcs: MeanDose(Heart) navigated → deliverable → second navigation → plan (Gy) | 13.23 → 19.13 → 16.45 → 16.49 | informative | informative |
| two arcs: MeanDose(Esophagus) navigated → deliverable → second navigation → plan (Gy) | 7.36 → 13.19 → 10.95 → 10.97 | informative | informative |
| two arcs: EUDMax(SpinalCord) navigated → deliverable → second navigation → plan (Gy) | 12.34 → 28.41 → 22.65 → 22.69 | informative | informative |
| two arcs: PTV D95%[Gy] >= 60 navigated → deliverable → second navigation → plan (Gy) | 59.41 → 60.12 → 60.00 → 60.12 | informative | informative |
| two arcs: SpinalCord Dmax[Gy] <= 45 navigated → deliverable → second navigation → plan (Gy) | 18.40 → 42.45 → 33.16 → 33.19 | informative | informative |
| two arcs: Esophagus Dmean[Gy] <= 34 navigated → deliverable → second navigation → plan (Gy) | 7.36 → 13.19 → 10.95 → 10.97 | informative | informative |
| two arcs: Heart D33%[Gy] <= 60 navigated → deliverable → second navigation → plan (Gy) | 14.72 → 22.21 → 18.20 → 18.25 | informative | informative |
| two arcs: Lungs-PTV D37%[Gy] <= 20 navigated → deliverable → second navigation → plan (Gy) | 7.04 → 12.08 → 8.24 → 8.26 | informative | informative |
| PTV V60Gy[%] >= 95.0: MCO plan (two arcs) | 95.39 | >= 95.0 | pass |
| PTV D0.03cc[Gy] <= 72.0: MCO plan (two arcs) | 72.46 | <= 72.0 | informative |
| Lungs-GTV V20Gy[%] <= 37.0: MCO plan (two arcs) | 22.29 | <= 37.0 | pass |
| Lungs-GTV Dmean[Gy] <= 20.0: MCO plan (two arcs) | 14.65 | <= 20.0 | pass |
| SpinalCord D0.03cc[Gy] <= 50.5: MCO plan (two arcs) | 32.26 | <= 50.5 | pass |
| Esophagus Dmean[Gy] <= 34.0: MCO plan (two arcs) | 10.97 | <= 34.0 | informative |
| Heart V60Gy[%] <= 33.0: MCO plan (two arcs) | 0.67 | <= 33.0 | informative |
| Heart V45Gy[%] <= 66.0: MCO plan (two arcs) | 2.76 | <= 66.0 | informative |
| Heart V40Gy[%] <= 100.0: MCO plan (two arcs) | 5.13 | <= 100.0 | informative |
