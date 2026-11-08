# Radiarch validation run 20261107-055230-e03cd6d + 20261107-112735-e03cd6d

RESEARCH USE ONLY. NOT FOR CLINICAL USE. Radiarch is a research treatment-planning system; its plans, doses and evaluations must not be used to treat patients.

The cases ran one per process from commit e03cd6d: `mco_front_tg119` (20261107-055230), `mco_protocol_lung` (20261107-112735).

| Case | Status | Time (s) | Checks |
|---|---|---|---|
| mco_front_tg119 | **pass** | 4682.1 | 19 pass, 0 fail, 52 informative |
| mco_protocol_lung | **fail** | 24787.3 | 36 pass, 2 fail, 121 informative |

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
| deliverable (static fields): RMSUnder(OuterTarget) navigated → deliverable (Gy) | 1.00 → 0.54 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (static fields): EUDMax(Core) navigated → deliverable (Gy) | 8.38 → 19.08 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (static fields): OuterTarget D95%[Gy] >= 50 navigated → deliverable (Gy) | 50.00 → 50.10 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (static fields): OuterTarget D10%[Gy] <= 55 navigated → deliverable (Gy) | 57.86 → 56.05 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (static fields): Core D5%[Gy] <= 10 navigated → deliverable (Gy) | 10.00 → 22.40 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (static fields): flagged rows of the deviation table | 2 | informative | informative |
| deliverable (static fields): normalisation of the deliverable plan within 15 % of 1 | 1.028 | 0.85 to 1.15 | pass |
| deliverable (static fields): meterset rounds | 3 | informative | informative |
| deliverable: OuterTarget D95 (Gy) | 50.1 | >= 50.0 (or >= 49.78: institutional mean 50.11 ± 2 SD) | pass |
| deliverable against the recorded reweighting plan: OuterTarget D95 (Gy) | 50.10 vs 50.1 | informative | informative |
| deliverable: OuterTarget D10 (Gy) | 56.05 | <= 55.0 (or <= 61.42: institutional mean 57.02 ± 2 SD) | pass |
| deliverable against the recorded reweighting plan: OuterTarget D10 (Gy) | 56.05 vs 53.86 | informative | informative |
| deliverable: Core D5 (Gy) | 22.4 | <= 10.0 (or <= 22.44: institutional mean 16.3 ± 2 SD) | pass |
| deliverable against the recorded reweighting plan: Core D5 (Gy) | 22.40 vs 10.19 | informative | informative |
| static fields: second set: the error bound never grows as plans are added | 0.129 → 0.112 → 0.031 | non-increasing | pass |
| static fields: second set: plans whose solve converged | 5 of 5 | informative | informative |
| static fields: second set: plans dominated by another plan | 0 | informative | informative |
| static fields: second set: each converged plan is the best of the set in its own weighted sum | 0 | <= 0.01 | pass |
| static fields: second set: hard constraint OuterTarget Dmin >= 25.0 Gy in every plan | 39.19 | >= 25.0 (tolerance 0.1) | pass |
| static fields: second set: hard constraint OuterTarget Dmax <= 60.0 Gy in every plan | 60.05 | <= 60.0 (tolerance 0.1) | pass |
| static fields: second set: hard constraint OuterTarget gEUD >= 53.309 Gy in every plan | 52.79 | >= 53.309 (tolerance 0.5331) | pass |
| static fields: second set: hard constraint OuterTarget Dmax <= 60.0 Gy in every plan | 60.05 | <= 60.0 (tolerance 0.6) | pass |
| static fields: second set: error bound with 3 plans | 0.1285 | tolerance 0.05 | informative |
| static fields: second set: error bound with 4 plans | 0.1119 | tolerance 0.05 | informative |
| static fields: second set: error bound with 5 plans | 0.031 | tolerance 0.05 | informative |
| static fields: second set | 5 plans on 70 segments | informative | informative |
| static fields: plan on the second set: deliverable | True | True | pass |
| static fields: plan on the second set: RMSUnder(OuterTarget) navigated → deliverable (Gy) | 0.50 → 0.49 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| static fields: plan on the second set: EUDMax(Core) navigated → deliverable (Gy) | 16.44 → 16.47 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| static fields: plan on the second set: OuterTarget D95%[Gy] >= 50 navigated → deliverable (Gy) | 50.00 → 50.10 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| static fields: plan on the second set: OuterTarget D10%[Gy] <= 55 navigated → deliverable (Gy) | 58.28 → 58.40 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| static fields: plan on the second set: Core D5%[Gy] <= 10 navigated → deliverable (Gy) | 19.27 → 19.31 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| static fields: plan on the second set: flagged rows of the deviation table | 0 | informative | informative |
| static fields: plan on the second set: normalisation of the deliverable plan within 15 % of 1 | 1.002 | 0.85 to 1.15 | pass |
| static fields: RMSUnder(OuterTarget) navigated → deliverable → second navigation → plan (Gy) | 1.00 → 0.54 → 0.50 → 0.49 | informative | informative |
| static fields: EUDMax(Core) navigated → deliverable → second navigation → plan (Gy) | 8.38 → 19.08 → 16.44 → 16.47 | informative | informative |
| static fields: OuterTarget D95%[Gy] >= 50 navigated → deliverable → second navigation → plan (Gy) | 50.00 → 50.10 → 50.00 → 50.10 | informative | informative |
| static fields: OuterTarget D10%[Gy] <= 55 navigated → deliverable → second navigation → plan (Gy) | 57.86 → 56.05 → 58.28 → 58.40 | informative | informative |
| static fields: Core D5%[Gy] <= 10 navigated → deliverable → second navigation → plan (Gy) | 10.00 → 22.40 → 19.27 → 19.31 | informative | informative |
| plan on the second set: OuterTarget D95 (Gy) | 50.1 | >= 50.0 (or >= 49.78: institutional mean 50.11 ± 2 SD) | pass |
| plan on the second set against the recorded reweighting plan: OuterTarget D95 (Gy) | 50.10 vs 50.1 | informative | informative |
| plan on the second set: OuterTarget D10 (Gy) | 58.4 | <= 55.0 (or <= 61.42: institutional mean 57.02 ± 2 SD) | pass |
| plan on the second set against the recorded reweighting plan: OuterTarget D10 (Gy) | 58.40 vs 53.86 | informative | informative |
| plan on the second set: Core D5 (Gy) | 19.31 | <= 10.0 (or <= 22.44: institutional mean 16.3 ± 2 SD) | pass |
| plan on the second set against the recorded reweighting plan: Core D5 (Gy) | 19.31 vs 10.19 | informative | informative |

## mco_protocol_lung — fail


| Check | Value | Target | Result |
|---|---|---|---|
| demo-lung-imrt: deliverable | True | True | pass |
| demo-lung-imrt-mco: deliverable | True | True | pass |
| PTV V60Gy[%] >= 95.0: MCO plan | 95.34 | >= 95.0 | pass |
| PTV V60Gy[%] >= 95.0: MCO against the reweighting plan | 95.34 vs 95.27 | informative | informative |
| PTV D0.03cc[Gy] <= 72.0: MCO plan | 72.02 | <= 72.0 | informative |
| PTV D0.03cc[Gy] <= 72.0: MCO against the reweighting plan | 72.02 vs 68.54 | informative | informative |
| Lungs-GTV V20Gy[%] <= 37.0: MCO plan | 20.97 | <= 37.0 | pass |
| Lungs-GTV V20Gy[%] <= 37.0: MCO against the reweighting plan | 20.97 vs 20.11 | informative | informative |
| Lungs-GTV Dmean[Gy] <= 20.0: MCO plan | 12.55 | <= 20.0 | pass |
| Lungs-GTV Dmean[Gy] <= 20.0: MCO against the reweighting plan | 12.55 vs 11.25 | informative | informative |
| SpinalCord D0.03cc[Gy] <= 50.5: MCO plan | 4.57 | <= 50.5 | pass |
| SpinalCord D0.03cc[Gy] <= 50.5: MCO against the reweighting plan | 4.57 vs 35.19 | informative | informative |
| Esophagus Dmean[Gy] <= 34.0: MCO plan | 1.14 | <= 34.0 | informative |
| Esophagus Dmean[Gy] <= 34.0: MCO against the reweighting plan | 1.14 vs 9.85 | informative | informative |
| Heart V60Gy[%] <= 33.0: MCO plan | 4.23 | <= 33.0 | informative |
| Heart V60Gy[%] <= 33.0: MCO against the reweighting plan | 4.23 vs 0.12 | informative | informative |
| Heart V45Gy[%] <= 66.0: MCO plan | 5.31 | <= 66.0 | informative |
| Heart V45Gy[%] <= 66.0: MCO against the reweighting plan | 5.31 vs 1.34 | informative | informative |
| Heart V40Gy[%] <= 100.0: MCO plan | 6.11 | <= 100.0 | informative |
| Heart V40Gy[%] <= 100.0: MCO against the reweighting plan | 6.11 vs 2.42 | informative | informative |
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
| seven static fields: second set: the error bound never grows as plans are added | 0.445 → 0.418 → 0.375 → 0.328 → 0.325 → 0.307 | non-increasing | pass |
| seven static fields: second set: plans whose solve converged | 11 of 11 | informative | informative |
| seven static fields: second set: plans dominated by another plan | 1 | informative | informative |
| seven static fields: second set: each converged plan is the best of the set in its own weighted sum | 0.0538 | <= 0.01 | FAIL |
| seven static fields: second set: hard constraint SpinalCord Dmax <= 45.0 Gy in every plan | 6.898 | <= 45.0 (tolerance 0.1) | pass |
| seven static fields: second set: hard constraint PTV Dmin >= 54.0 Gy in every plan | 53.91 | >= 54.0 (tolerance 0.1) | pass |
| seven static fields: second set: hard constraint PTV gEUD >= 64.358 Gy in every plan | 63.77 | >= 64.358 (tolerance 0.6436) | pass |
| seven static fields: second set: hard constraint PTV Dmax <= 72.0 Gy in every plan | 72.07 | <= 72.0 (tolerance 0.72) | pass |
| seven static fields: second set: error bound with 6 plans | 0.4446 | tolerance 0.05 | informative |
| seven static fields: second set: error bound with 7 plans | 0.4179 | tolerance 0.05 | informative |
| seven static fields: second set: error bound with 8 plans | 0.3755 | tolerance 0.05 | informative |
| seven static fields: second set: error bound with 9 plans | 0.3277 | tolerance 0.05 | informative |
| seven static fields: second set: error bound with 10 plans | 0.3251 | tolerance 0.05 | informative |
| seven static fields: second set: error bound with 11 plans | 0.3072 | tolerance 0.05 | informative |
| seven static fields: second set | 11 plans on 75 segments | informative | informative |
| seven static fields: plan on the second set: deliverable | True | True | pass |
| seven static fields: plan on the second set: UniformRMS(PTV) navigated → deliverable (Gy) | 4.90 → 4.91 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: MeanDose(Lungs-PTV) navigated → deliverable (Gy) | 10.82 → 10.82 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: MeanDose(Heart) navigated → deliverable (Gy) | 8.16 → 8.16 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: MeanDose(Esophagus) navigated → deliverable (Gy) | 1.14 → 1.14 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: EUDMax(SpinalCord) navigated → deliverable (Gy) | 2.96 → 2.96 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: PTV D95%[Gy] >= 60 navigated → deliverable (Gy) | 60.11 → 60.12 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: SpinalCord Dmax[Gy] <= 45 navigated → deliverable (Gy) | 4.58 → 4.58 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: Esophagus Dmean[Gy] <= 34 navigated → deliverable (Gy) | 1.14 → 1.14 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: Heart D33%[Gy] <= 60 navigated → deliverable (Gy) | 4.21 → 4.21 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: Lungs-PTV D37%[Gy] <= 20 navigated → deliverable (Gy) | 1.26 → 1.26 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| seven static fields: plan on the second set: flagged rows of the deviation table | 0 | informative | informative |
| seven static fields: plan on the second set: normalisation of the deliverable plan within 15 % of 1 | 1 | 0.85 to 1.15 | pass |
| seven static fields: UniformRMS(PTV) navigated → deliverable → second navigation → plan (Gy) | 0.48 → 5.82 → 4.90 → 4.91 | informative | informative |
| seven static fields: MeanDose(Lungs-PTV) navigated → deliverable → second navigation → plan (Gy) | 10.45 → 10.65 → 10.82 → 10.82 | informative | informative |
| seven static fields: MeanDose(Heart) navigated → deliverable → second navigation → plan (Gy) | 7.53 → 10.20 → 8.16 → 8.16 | informative | informative |
| seven static fields: MeanDose(Esophagus) navigated → deliverable → second navigation → plan (Gy) | 1.10 → 1.60 → 1.14 → 1.14 | informative | informative |
| seven static fields: EUDMax(SpinalCord) navigated → deliverable → second navigation → plan (Gy) | 2.68 → 3.78 → 2.96 → 2.96 | informative | informative |
| seven static fields: PTV D95%[Gy] >= 60 navigated → deliverable → second navigation → plan (Gy) | 59.10 → 60.12 → 60.11 → 60.12 | informative | informative |
| seven static fields: SpinalCord Dmax[Gy] <= 45 navigated → deliverable → second navigation → plan (Gy) | 3.93 → 5.63 → 4.58 → 4.58 | informative | informative |
| seven static fields: Esophagus Dmean[Gy] <= 34 navigated → deliverable → second navigation → plan (Gy) | 1.10 → 1.60 → 1.14 → 1.14 | informative | informative |
| seven static fields: Heart D33%[Gy] <= 60 navigated → deliverable → second navigation → plan (Gy) | 4.77 → 8.51 → 4.21 → 4.21 | informative | informative |
| seven static fields: Lungs-PTV D37%[Gy] <= 20 navigated → deliverable → second navigation → plan (Gy) | 1.33 → 2.45 → 1.26 → 1.26 | informative | informative |
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
| two arcs: second set: the error bound never grows as plans are added | 1.000 → 0.903 → 0.861 → 0.848 → 0.848 → 0.845 | non-increasing | pass |
| two arcs: second set: plans whose solve converged | 3 of 11 | informative | informative |
| two arcs: second set: plans dominated by another plan | 0 | informative | informative |
| two arcs: second set: each converged plan is the best of the set in its own weighted sum | 0.2033 | <= 0.01 | FAIL |
| two arcs: second set: hard constraint SpinalCord Dmax <= 45.0 Gy in every plan | 33.21 | <= 45.0 (tolerance 0.1) | pass |
| two arcs: second set: hard constraint PTV Dmin >= 54.0 Gy in every plan | 53.98 | >= 54.0 (tolerance 0.1) | pass |
| two arcs: second set: hard constraint PTV gEUD >= 64.82 Gy in every plan | 64.25 | >= 64.82 (tolerance 0.6482) | pass |
| two arcs: second set: hard constraint PTV Dmax <= 72.0 Gy in every plan | 72.03 | <= 72.0 (tolerance 0.72) | pass |
| two arcs: second set: error bound with 6 plans | 1 | tolerance 0.05 | informative |
| two arcs: second set: error bound with 7 plans | 0.9025 | tolerance 0.05 | informative |
| two arcs: second set: error bound with 8 plans | 0.8611 | tolerance 0.05 | informative |
| two arcs: second set: error bound with 9 plans | 0.8482 | tolerance 0.05 | informative |
| two arcs: second set: error bound with 10 plans | 0.8482 | tolerance 0.05 | informative |
| two arcs: second set: error bound with 11 plans | 0.8448 | tolerance 0.05 | informative |
| two arcs: second set | 11 plans on 192 arc intervals | informative | informative |
| two arcs: plan on the second set: deliverable | True | True | pass |
| two arcs: plan on the second set: UniformRMS(PTV) navigated → deliverable (Gy) | 6.17 → 6.29 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: MeanDose(Lungs-PTV) navigated → deliverable (Gy) | 12.08 → 12.11 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: MeanDose(Heart) navigated → deliverable (Gy) | 15.82 → 15.85 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: MeanDose(Esophagus) navigated → deliverable (Gy) | 10.88 → 10.90 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: EUDMax(SpinalCord) navigated → deliverable (Gy) | 21.72 → 21.77 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: PTV D95%[Gy] >= 60 navigated → deliverable (Gy) | 60.00 → 60.12 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: SpinalCord Dmax[Gy] <= 45 navigated → deliverable (Gy) | 29.30 → 29.36 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: Esophagus Dmean[Gy] <= 34 navigated → deliverable (Gy) | 10.88 → 10.90 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: Heart D33%[Gy] <= 60 navigated → deliverable (Gy) | 17.52 → 17.54 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: Lungs-PTV D37%[Gy] <= 20 navigated → deliverable (Gy) | 8.86 → 8.87 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| two arcs: plan on the second set: flagged rows of the deviation table | 0 | informative | informative |
| two arcs: plan on the second set: normalisation of the deliverable plan within 15 % of 1 | 1.002 | 0.85 to 1.15 | pass |
| two arcs: UniformRMS(PTV) navigated → deliverable → second navigation → plan (Gy) | 0.55 → 6.60 → 6.17 → 6.29 | informative | informative |
| two arcs: MeanDose(Lungs-PTV) navigated → deliverable → second navigation → plan (Gy) | 9.65 → 12.39 → 12.08 → 12.11 | informative | informative |
| two arcs: MeanDose(Heart) navigated → deliverable → second navigation → plan (Gy) | 9.91 → 16.19 → 15.82 → 15.85 | informative | informative |
| two arcs: MeanDose(Esophagus) navigated → deliverable → second navigation → plan (Gy) | 5.29 → 11.76 → 10.88 → 10.90 | informative | informative |
| two arcs: EUDMax(SpinalCord) navigated → deliverable → second navigation → plan (Gy) | 7.74 → 23.30 → 21.72 → 21.77 | informative | informative |
| two arcs: PTV D95%[Gy] >= 60 navigated → deliverable → second navigation → plan (Gy) | 59.33 → 60.12 → 60.00 → 60.12 | informative | informative |
| two arcs: SpinalCord Dmax[Gy] <= 45 navigated → deliverable → second navigation → plan (Gy) | 10.64 → 32.39 → 29.30 → 29.36 | informative | informative |
| two arcs: Esophagus Dmean[Gy] <= 34 navigated → deliverable → second navigation → plan (Gy) | 5.29 → 11.76 → 10.88 → 10.90 | informative | informative |
| two arcs: Heart D33%[Gy] <= 60 navigated → deliverable → second navigation → plan (Gy) | 10.51 → 18.23 → 17.52 → 17.54 | informative | informative |
| two arcs: Lungs-PTV D37%[Gy] <= 20 navigated → deliverable → second navigation → plan (Gy) | 5.34 → 9.69 → 8.86 → 8.87 | informative | informative |
| PTV V60Gy[%] >= 95.0: MCO plan (two arcs) | 95.46 | >= 95.0 | pass |
| PTV D0.03cc[Gy] <= 72.0: MCO plan (two arcs) | 72.16 | <= 72.0 | informative |
| Lungs-GTV V20Gy[%] <= 37.0: MCO plan (two arcs) | 21.21 | <= 37.0 | pass |
| Lungs-GTV Dmean[Gy] <= 20.0: MCO plan (two arcs) | 13.88 | <= 20.0 | pass |
| SpinalCord D0.03cc[Gy] <= 50.5: MCO plan (two arcs) | 29.32 | <= 50.5 | pass |
| Esophagus Dmean[Gy] <= 34.0: MCO plan (two arcs) | 10.9 | <= 34.0 | informative |
| Heart V60Gy[%] <= 33.0: MCO plan (two arcs) | 0.66 | <= 33.0 | informative |
| Heart V45Gy[%] <= 66.0: MCO plan (two arcs) | 3.37 | <= 66.0 | informative |
| Heart V40Gy[%] <= 100.0: MCO plan (two arcs) | 5.28 | <= 100.0 | informative |
