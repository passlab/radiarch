# Rerun of the R9 record's 4D case, 2026-11-10: an arc's closed leaf pairs move toward an X jaw

**What changed.** From commit `f3a83c7` on (release 0.3.1), an arc moves a leaf pair that is closed for part of the
arc toward the park position, 10 mm behind an X jaw, for as long as it stays closed. The R8 record's rerun of the same
day (`../../2026-10-23-r8/2026-11-10-arc-pairs-toward-jaw-f3a83c7/`) describes the change and measures the leak it
removes. `lung_4d_itv` plans two VMAT arcs and recomputes them through their apertures on every phase, so it is
rerun. Its numbers in the rerun of 2026-11-07 (`../2026-11-07-parked-leaf-pairs-b11713b/`) are superseded by this
run.

**This run.** `20261111-035627-f3a83c7`, from a clean checkout of commit `f3a83c7` on the 96-core server, in the
radiarch image built from `e486b71` with the checkout mounted over its code, capped at 6 BLAS threads. It took
8107.6 s (8016.6 s before). `run-summary.md` lists every check, and `results.json` holds the full numbers.

## What the move changes

- All 22 graded checks pass, as before.
- The tumour's D95 on each phase moves by at most 0.07 Gy. Its accumulated D95 falls by 0.03 and 0.07 Gy, and stays
  above 60.9 Gy against the 57 Gy limit.
- The ITV and the planned PTV D95 are unchanged.
- As in the R8 record's 60 Gy lung case, the lungs' dose falls a little and the cord maximum rises a little. The
  table gives both values of each informative check: accumulated over the ten phases, and planned on the average CT.

| Check | 101_HM10395: b11713b | f3a83c7 | 103_HM10395: b11713b | f3a83c7 |
|---|---|---|---|---|
| Lungs V20Gy (%), accumulated | 11.2 | 11.19 | 19.49 | 19.22 |
| Lungs V20Gy (%), planned on the average CT | 11.90 | 11.84 | 20.64 | 20.32 |
| SpinalCord Dmax (Gy), accumulated | 24.74 | 25.14 | 37.51 | 37.98 |
| SpinalCord Dmax (Gy), planned on the average CT | 25.16 | 25.63 | 37.45 | 37.93 |

The graded checks that moved by 0.04 Gy or more:

| Check | b11713b | f3a83c7 | Target | Result |
|---|---|---|---|---|
| 101_HM10395: phase 20 %: its tumour D95 (Gy) | 60.56 | 60.51 | >= 57.0 | pass → pass |
| 101_HM10395: phase 30 %: its tumour D95 (Gy) | 60.59 | 60.53 | >= 57.0 | pass → pass |
| 101_HM10395: phase 60 %: its tumour D95 (Gy) | 60.41 | 60.37 | >= 57.0 | pass → pass |
| 101_HM10395: phase 80 %: its tumour D95 (Gy) | 60.36 | 60.29 | >= 57.0 | pass → pass |
| 103_HM10395: accumulated over 10 phases: reference tumour D95 (Gy) | 61.54 | 61.47 | >= 57.0 | pass → pass |

The registration and replanning cases have no aperture doses and stand as recorded.

## How to reproduce (optional)

```bash
git clone https://github.com/passlab/radiarch && cd radiarch && git checkout f3a83c7
python3 -m venv .venv && .venv/bin/pip install -e "./src[dev,validation]"     # Python 3.12 or later
.venv/bin/python -m radiarch.validation.run --cases lung_4d_itv
```

The case reads the 4D CTs from `RADIARCH_VALIDATION_DATA`, outside the repository.
