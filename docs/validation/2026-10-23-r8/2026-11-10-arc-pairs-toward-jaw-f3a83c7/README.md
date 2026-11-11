# Rerun of the R8 record's VMAT cases, 2026-11-10: an arc's closed leaf pairs move toward an X jaw

**What changed.** From commit `f3a83c7` on (release 0.3.1), an arc moves a leaf pair that is closed for part of the
arc toward the park position, 10 mm behind an X jaw, for as long as it stays closed. In each run of control points
at which a pair is closed:
- an end next to an open control point stays, since an interval's aperture is the mean of its two control points and
  that end shapes the open interval beside it;
- every other point goes as near the park position as the leaf speed allows in the time each interval takes anyway
  (its gantry time, or its largest leaf move). No interval's minimum time or minimum meterset changes.

Before, such a pair waited inside the field where its sweep left it, and its tips' gap passed dose (the leaf model of
`412a105` includes it). A pair that no control point opens still waits under the jaw for the whole arc, as from
`b11713b`. `LEAF_MODEL_VERSION` is 3, so cached arcs are made again. The three VMAT cases are rerun. Their numbers in
the rerun of 2026-11-07 (`../2026-11-07-parked-leaf-pairs-b11713b/`) are superseded by these runs.

**These runs.** Three runs, one case per process, from a clean checkout of commit `f3a83c7` on the 96-core server, in
the radiarch image built from `e486b71` with the checkout mounted over its code, each capped at 6 BLAS threads:
`20261110-190036-f3a83c7` (`lung_sbrt_vmat`), `20261110-203936-f3a83c7` (`lung_vmat_lctsc`) and
`20261110-194944-f3a83c7` (`hn_sib_vmat`). `run-summary.md` lists every check, and `results.json` holds the full
numbers.

## What the move changes

- Every graded check passes, as before: `lung_sbrt_vmat` 32, `lung_vmat_lctsc` 10, `hn_sib_vmat` 12.
- All three cases move, both patients of each, since most arcs close some pairs for part of the arc. The moves are
  small, at most 1.6 (Gy, percentage points or percent of the prescription).
- **Lung, 60 Gy in 30 (`lung_vmat_lctsc`).** Both patients' coverage rises, and their lungs' and oesophagus's doses
  fall a little. The second patient's cord maximum rises by 0.8 Gy, far below its limit.

| Check | LCTSC-Test-S1-101: b11713b | f3a83c7 | LCTSC-Test-S2-101: b11713b | f3a83c7 | Target |
|---|---|---|---|---|---|
| PTV V60Gy (%) | 95.6 | 95.94 | 95.43 | 95.96 | >= 95.0 |
| PTV D0.03cc (Gy) | 65.25 | 64.8 | 65.22 | 65.39 | <= 72.0 (informative) |
| Lungs-GTV V20Gy (%) | 14.78 | 14.4 | 13.99 | 13.88 | <= 37.0 |
| Lungs-GTV Dmean (Gy) | 8.37 | 8.2 | 8.68 | 8.54 | <= 20.0 |
| SpinalCord D0.03cc (Gy) | 14.89 | 14.85 | 15.6 | 16.4 | <= 50.5 |
| Esophagus Dmean (Gy) | 3.38 | 3.21 | 3.25 | 3.14 | <= 34.0 (informative) |
| Paddick conformity index | 0.898 | 0.919 | 0.897 | 0.91 | informative |
| Second engine (CCC) gamma 3 %/3 mm against pb (%) | 82.1 | 82.3 | 86.0 | 85.7 | informative |

- **Lung SBRT (`lung_sbrt_vmat`).** The first patient's PTV V100% rises from 95.44 to 95.78 %. The second patient's
  cord maximum falls from 9.21 to 8.70 Gy. That patient's D2cm (the maximum 2 cm from the PTV, in % of the
  prescription) rises from 50.04 to 51.65. This passes as RTOG 0915's minor deviation (at most 59.74), where before it
  met the protocol's limit (below 51.39). The first patient's D2cm was already a minor deviation (54.41, now 54.31).
- **Head and neck, 70/56 Gy (`hn_sib_vmat`).** The first patient's parotid mean rises from 31.11 to 32.04 Gy
  (informative; neither run meets 26 Gy). The second patient's brainstem maximum falls from 44.17 to 43.30 Gy and its
  mandible maximum from 57.96 to 57.08 Gy.

Every check that moved by 0.3 or more:

| Case | Check | b11713b | f3a83c7 | Target | Result |
|---|---|---|---|---|---|
| lung_sbrt_vmat | LCTSC-Test-S1-101: PTV V100%[%] >= 95.0 | 95.44 | 95.78 | >= 95.0 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S1-101: Lungs V12.5Gy[cc] <= 1000.0 | 229.9 | 228.18 | <= 1000.0 | informative |
| lung_sbrt_vmat | LCTSC-Test-S2-101: PTV D0.03cc[%] <= 140.0 | 112.97 | 113.76 | <= 140.0 | informative |
| lung_sbrt_vmat | LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 21.9 | 9.21 | 8.7 | <= 21.9 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S2-101: SpinalCord D0.35cc[Gy] <= 18.0 | 8.4 | 7.94 | <= 18.0 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S2-101: Lungs V12.5Gy[cc] <= 1000.0 | 219.65 | 217.75 | <= 1000.0 | informative |
| lung_sbrt_vmat | LCTSC-Test-S2-101: D2cm (PTV 16.3 cc) | 50.041 | 51.646 | < 51.3882 (minor ≤ 59.7352) | pass → pass (minor) |
| lung_sbrt_vmat | LCTSC-Test-S2-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 93.0 | 92.5 | informative | informative |
| lung_vmat_lctsc | LCTSC-Test-S1-101: PTV V60Gy[%] >= 95.0 | 95.6 | 95.94 | >= 95.0 | pass → pass |
| lung_vmat_lctsc | LCTSC-Test-S1-101: PTV D0.03cc[Gy] <= 72.0 | 65.25 | 64.8 | <= 72.0 | informative |
| lung_vmat_lctsc | LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 37.0 | 14.78 | 14.4 | <= 37.0 | pass → pass |
| lung_vmat_lctsc | LCTSC-Test-S2-101: PTV V60Gy[%] >= 95.0 | 95.43 | 95.96 | >= 95.0 | pass → pass |
| lung_vmat_lctsc | LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5 | 15.6 | 16.4 | <= 50.5 | pass → pass |
| hn_sib_vmat | 0522c0001: PTV_High D0.03cc[%] <= 110.0 | 112.78 | 112.46 | <= 110.0 | informative |
| hn_sib_vmat | 0522c0001: Parotid Dmean[Gy] <= 26.0 | 31.11 | 32.04 | <= 26.0 | informative |
| hn_sib_vmat | 0522c0002: Brainstem D0.03cc[Gy] <= 54.0 | 44.17 | 43.3 | <= 54.0 | pass → pass |
| hn_sib_vmat | 0522c0002: Brainstem_PRV D0.03cc[Gy] <= 60.0 | 51.95 | 51.65 | <= 60.0 | informative |
| hn_sib_vmat | 0522c0002: Parotid Dmean[Gy] <= 26.0 | 22.75 | 23.4 | <= 26.0 | informative |
| hn_sib_vmat | 0522c0002: Glnd_Submand Dmean[Gy] <= 39.0 | 54.69 | 54.01 | <= 39.0 | informative |
| hn_sib_vmat | 0522c0002: Mandible D0.03cc[Gy] <= 70.0 | 57.96 | 57.08 | <= 70.0 | informative |
| hn_sib_vmat | 0522c0002: hottest point outside the elective volume (% of 70 Gy) | 96.7 | 96.1 | informative | informative |

## How much leak the move removes

Measured on the four arcs of the R11 record's 4 mm lung case from this commit (its deliverable plan's two meterset
rounds, two arcs each; machine `synthetic-120`, leaf gap 1.5 mm, 25 mm/s), the same way as on 2026-11-08. Each arc
was built again from its sector fluence, with the move and without it. The build with the move equals the stored arc.
Both builds were measured with the stored metersets, so the difference is the move alone. The script is not in the
repository.

| Arc | MU per fraction | Closed pairs inside the field, share of the pair metersets: without → with | Their tips' leak, share of the arc's open fluence: without → with |
|---|---|---|---|
| Round 1, ARC1 | 954.0 | 21.4 → 14.5 % | 2.39 → 1.62 % |
| Round 1, ARC2 | 907.3 | 32.6 → 23.2 % | 5.13 → 3.66 % |
| Round 2, ARC1 | 1517.3 | 41.4 → 31.9 % | 7.16 → 5.52 % |
| Round 2, ARC2 | 1374.0 | 41.5 → 30.5 % | 8.05 → 5.92 % |

- The move removes 23 to 32 % of the leak, as estimated on 2026-11-08 ("about a quarter"). Most closed runs are too
  short for a leaf to reach the jaw and come back.
- The leak is a geometric estimate: each leaking pair's 1.5 mm gap against the arc's whole open area, weighted by
  meterset, with leaf transmission left out of both.
- Delivery time is unchanged (222.7 to 271.7 s per arc), and no interval falls below its minimum meterset.

The engines' open fields, their Monte Carlo comparisons and the fluence-level plans have no apertures and stand as
recorded.

## How to reproduce (optional)

```bash
git clone https://github.com/passlab/radiarch && cd radiarch && git checkout f3a83c7
python3 -m venv .venv && .venv/bin/pip install -e "./src[dev,validation]"     # Python 3.12 or later
.venv/bin/python -m radiarch.validation.run --cases lung_sbrt_vmat
.venv/bin/python -m radiarch.validation.run --cases lung_vmat_lctsc
.venv/bin/python -m radiarch.validation.run --cases hn_sib_vmat
```

The cases read their CT and structures from `RADIARCH_VALIDATION_DATA`, outside the repository.
