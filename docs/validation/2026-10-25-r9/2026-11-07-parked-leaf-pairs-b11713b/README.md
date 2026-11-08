# Rerun of the R9 record's 4D case, 2026-11-07: closed leaf pairs parked under an X jaw

**What changed.** From commit `b11713b` on, the sequencer parks closed leaf pairs 10 mm behind an X jaw: every
closed pair of a static segment, and an arc's pair that no control point opens, for the whole arc. The R8 record's
rerun of the same day (`../../2026-10-23-r8/2026-11-07-parked-leaf-pairs-b11713b/`) describes the change.
`lung_4d_itv` plans VMAT arcs and recomputes them through their apertures on every phase, so it is rerun.

**This run.** `20261107-040941-b11713b`, from a clean checkout of commit `b11713b` on the 96-core server, in the
radiarch image built from `55ab566` with the checkout mounted over its code, capped at 6 BLAS threads.
`run-summary.md` lists every check, and `results.json` holds the full numbers.

**What the parking changes.** Nothing: all 22 graded checks pass, and every value equals the rerun of 2026-11-05
(`../2026-11-05-leaf-model-412a105/`, commit `412a105`), to the reported precision. The parking changed no dose this
case reports; which pairs it moved was not examined. The rerun of 2026-11-05 stands, and this run confirms it at
`b11713b`. The registration and replanning cases have no aperture doses and stand as recorded.

## How to reproduce (optional)

```bash
git clone https://github.com/passlab/radiarch && cd radiarch && git checkout b11713b
python3 -m venv .venv && .venv/bin/pip install -e "./src[dev,validation]"     # Python 3.12 or later
.venv/bin/python -m radiarch.validation.run --cases lung_4d_itv
```

The case reads the 4D CTs from `RADIARCH_VALIDATION_DATA`, outside the repository.
