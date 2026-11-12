# Rerun of the R9 record's 4D case, 2026-11-12: the leaf ends' tail, and no edge blur

**What changed.** From commit `0228ec6` on (`pb` 1.2.0, `LEAF_MODEL_VERSION` 4), a rounded leaf end passes half the
leaf gap as a tail beyond its tip, and the pencil beam no longer blurs a field's edge. The R8 record's rerun of the
same day (`../../2026-10-23-r8/2026-11-12-small-fields-0228ec6/`) describes the change and its checks against Monte
Carlo. `lung_4d_itv` plans two VMAT arcs with the pencil beam and recomputes them through their apertures on every
phase, so it is rerun. Its numbers in the rerun of 2026-11-10 (`../2026-11-10-arc-pairs-toward-jaw-f3a83c7/`) are
superseded by this run.

**This run.** `20261112-154604-0228ec6`, from a clean checkout of commit `0228ec6` on the 96-core server, in the
radiarch image built from `48c0cc4` with the checkout mounted over its code, capped at 6 BLAS threads. It took
8368.2 s (8107.6 s before). `run-summary.md` lists every check, and `results.json` holds the full numbers.

## What the change does

- All 22 graded checks pass, as before.
- The tumour's D95 on each phase falls by up to 0.39 Gy and stays above 60.0 Gy against the 57 Gy limit. Its
  accumulated D95 rises a little: 60.93 → 60.98 and 61.47 → 61.67 Gy.
- The lungs' V20Gy falls by 0.3 and 0.4 percentage points, and the cord maximum by 0.35 and 0.10 Gy (both
  informative, accumulated over the ten phases).

| Check | 101_HM10395: f3a83c7 | 0228ec6 | 103_HM10395: f3a83c7 | 0228ec6 |
|---|---|---|---|---|
| Tumour D95, accumulated over 10 phases (Gy) | 60.93 | 60.98 | 61.47 | 61.67 |
| Lowest tumour D95 on one phase (Gy) | 60.26 | 60.05 | 60.37 | 60.12 |
| Lungs V20Gy (%), accumulated | 11.19 | 10.9 | 19.22 | 18.82 |
| SpinalCord Dmax (Gy), accumulated | 25.14 | 24.79 | 37.98 | 37.88 |

The registration and replanning cases have no pencil-beam doses and no apertures, and stand as recorded.

## How to reproduce (optional)

```bash
git clone https://github.com/passlab/radiarch && cd radiarch && git checkout 0228ec6
python3 -m venv .venv && .venv/bin/pip install -e "./src[dev,validation]"     # Python 3.12 or later
.venv/bin/python -m radiarch.validation.run --cases lung_4d_itv
```

The case reads the 4D CTs from `RADIARCH_VALIDATION_DATA`, outside the repository.
