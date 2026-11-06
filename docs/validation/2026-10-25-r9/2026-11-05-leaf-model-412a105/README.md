# Rerun of the R9 record, 2026-11-05: the 4D lung case with the MLC leaf model

**What changed.** From commit `412a105` on, every photon dose computed from apertures uses the machine's leaf model:
the leaf transmission, a dosimetric leaf gap of 1.5 mm and a tongue-and-groove of 0.5 mm (representative values, not a
commissioned machine's). `docs/reports/mlc-leaf-model.md` gives the model, and the R8 record's rerun
(`../../2026-10-23-r8/2026-11-05-leaf-model-412a105/`) describes it. `lung_4d_itv` plans VMAT arcs on the average CT
and recomputes the plan through its apertures on all ten phases, so it is rerun. Its numbers in the record (`../`,
commit `316b6c6`, run `20261025-142024`) are superseded by this rerun. The registration and replanning cases have no
aperture doses and stand as recorded.

**This run.** `20261105-233837-412a105`, from a clean checkout of commit `412a105` on the 96-core server, in the
radiarch image built from `55ab566` with the checkout mounted over its code, capped at 6 BLAS threads.
`run-summary.md` lists every check, and `results.json` holds the full numbers.

**The baseline.** To separate the leaf model from the commits since the record, the case also ran from `55ab566`, the
commit before the leaf model, in the same image and the same way: run `20261106-020417-55ab566`, in
`baseline-55ab566/`. The baseline reproduces the record: no value moves by more than 0.41 (Gy or percentage points).

**What the leaf model changes.**

- All 22 graded checks pass, in the baseline and with the leaf model. No check changes status.
- The tumour's D95 on each phase rises by up to 0.18 Gy for `101_HM10395` and by 0.31 to 0.42 Gy for `103_HM10395`.
  The accumulated D95 on the reference phase rises from 60.90 to 60.96 Gy and from 61.12 to 61.54 Gy.
- The lungs' V20Gy rises. Accumulated over the phases, it goes from 10.35 to 11.20 % and from 17.35 to 19.49 %. On
  the average CT, it goes from 11.01 to 11.90 % and from 18.37 to 20.64 %. The second patient's rise, about
  2 percentage points, is twice the conventional lung case's in the R8 rerun.
- The spinal cord's maximum rises, accumulated from 24.14 to 24.74 Gy and from 36.34 to 37.51 Gy. On the average CT,
  it goes from 24.62 to 25.16 Gy and from 36.31 to 37.45 Gy. Both are informative.

## Checks whose value changed by 1 or more (Gy or %) with the leaf model

| Case | Check | Baseline (55ab566) | Leaf model (412a105) | Target | Result |
|---|---|---|---|---|---|
| lung_4d_itv | 103_HM10395: Lungs V20Gy (%), accumulated / planned | 17.35 | 19.49 | informative | informative → informative |
| lung_4d_itv | 103_HM10395: SpinalCord Dmax (Gy), accumulated / planned | 36.34 | 37.51 | informative | informative → informative |

## How to reproduce (optional)

```bash
git clone https://github.com/passlab/radiarch && cd radiarch && git checkout 412a105    # 55ab566 for the baseline
python3 -m venv .venv && .venv/bin/pip install -e "./src[dev,validation]"     # Python 3.12 or later
.venv/bin/python -m radiarch.validation.run --cases lung_4d_itv    # about 18 GB of memory at its 3 mm grid
```

The case reads the 4D-Lung patients from `RADIARCH_VALIDATION_DATA`, outside the repository.
