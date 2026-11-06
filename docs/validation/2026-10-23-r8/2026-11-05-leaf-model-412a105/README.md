# Rerun of the R8 record, 2026-11-05: the VMAT cases with the MLC leaf model

**What changed.** Until commit `412a105`, a dose computed from apertures treated the leaves as ideal: nothing passed
through a closed leaf, a leaf tip stopped the beam at its nominal position, and adjacent leaves had no tongue-and-groove.
From `412a105` on, every aperture dose (sequencing, the pencil beam's segment and arc doses, CCC's recomputation of the
delivered arcs) uses the machine's leaf model: the leaf transmission (1.5 % for the default machine), a dosimetric leaf
gap of 1.5 mm and a tongue-and-groove of 0.5 mm. These are representative values, not a commissioned machine's.
`docs/reports/mlc-leaf-model.md` gives the model and its tests. The three VMAT cases below plan through apertures. Their
numbers in the 2026-10-24 correction (`../2026-10-24-correction-d458e46/`, run `20261024-152201-d458e46`) are superseded
by this run. The rest of the R8 record stands as recorded: the engines' open fields and their Monte Carlo comparisons
have no MLC rows, and `lung_e2e_lctsc` and the TG-119 case grade fluence-level plans.

**This run.** Three runs, one case per process, from a clean checkout of commit `412a105` on the 96-core server:
`20261105-175915-412a105` (`lung_sbrt_vmat`), `20261105-231816-412a105` (`lung_vmat_lctsc`) and
`20261105-223352-412a105` (`hn_sib_vmat`). They ran in the radiarch image built from `55ab566` with the checkout
mounted over its code. No dependency changed between the two commits, and the image runs the CCC engine, which needs a
newer C library than the server had that morning. A reboot of the server cut the first runs of `lung_vmat_lctsc` and
`hn_sib_vmat`. They were rerun from the same checkout, and the runs here are complete. `run-summary.md` lists every
check, and `results.json` holds the full numbers.

**The baseline.** The commits between the correction (`d458e46`) and the leaf model also change the planning: R9 to
R11.9 brought solver corrections, among other changes. To separate the leaf model from them, the same three cases ran
from `55ab566`, the commit before the leaf model, in the same image and the same way: runs `20261105-235948-55ab566`,
`20261106-004016-55ab566` and `20261106-005331-55ab566`, in `baseline-55ab566/`. The comparisons below are against
this baseline, so every difference is the leaf model's. The cases ran side by side, each capped at 6 BLAS threads, so
their times are not comparable with the record's.

**What the leaf model changes.**

- Every graded check passes, in the baseline and with the leaf model. No check changes status.
- More dose reaches the tissue around the target, through the closed leaves and the wider leaf tips. In the SBRT case,
  R50 (the volume of half the prescription dose over the PTV's volume) rises from 2.22 to 2.39 and from 2.23 to 2.45.
  The lungs' V12.5Gy rises by 7 and 8 cc, and the lung V20 by about 0.1 and 0.2 percentage points.
- In the conventionally fractionated lung case, the lung V20 rises by 1.1 and 0.9 percentage points, the lung mean
  dose by about 0.5 Gy and the oesophagus mean by 0.6 and 0.2 Gy. The Paddick conformity index falls from 0.912 to
  0.898 and from 0.906 to 0.897.
- Organ maxima move both ways, by up to 2 Gy. The metersets are re-optimized on the new segment doses, so the plan
  spends them differently. In the head-and-neck case, one patient's brainstem maximum rises from 42.5 to 44.3 Gy
  (limit 54 Gy); the other's falls from 44.6 to 44.2 Gy. The parotid and submandibular means rise by 0.4 to 1.3 Gy.
  They are informative; the submandibular means and one parotid mean are above their goals, as before.
- The second engine agrees as before. CCC's PTV D95 over the pencil beam's moves by at most 0.002 (0.008 with the body
  as water), and the gamma pass rate (3 %/3 mm) by at most 1 point.
- CCC's recomputation of the delivered arcs now has about five times as many beamlets: the leaf-transmission cells
  under the closed leaves. `lung_vmat_lctsc` took 7116 s against the baseline's 3246 s.

## Checks whose value changed by 1 or more (Gy, %, cc or index points) with the leaf model

| Case | Check | Baseline (55ab566) | Leaf model (412a105) | Target | Result |
|---|---|---|---|---|---|
| lung_sbrt_vmat | LCTSC-Test-S1-101: Heart D0.03cc[Gy] <= 30.0 | 17.94 | 16.69 | <= 30.0 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S1-101: Lungs V12.5Gy[cc] <= 1000.0 | 223.1 | 229.9 | <= 1000.0 | informative → informative |
| lung_sbrt_vmat | LCTSC-Test-S1-101: D2cm (PTV 16.0 cc) | 53.189 | 54.407 | < 51.2655 (minor ≤ 59.5818) | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 21.9 | 10.21 | 9.21 | <= 21.9 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S2-101: Esophagus D0.03cc[Gy] <= 25.2 | 7.14 | 5.43 | <= 25.2 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S2-101: Lungs V12.5Gy[cc] <= 1000.0 | 211.65 | 219.65 | <= 1000.0 | informative → informative |
| lung_vmat_lctsc | LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 37.0 | 13.67 | 14.78 | <= 37.0 | pass → pass |
| lung_vmat_lctsc | LCTSC-Test-S1-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 83.1 | 82.1 | informative | informative → informative |
| lung_vmat_lctsc | LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5 | 16.77 | 15.65 | <= 50.5 | pass → pass |
| hn_sib_vmat | 0522c0001: Brainstem D0.03cc[Gy] <= 54.0 | 42.54 | 44.3 | <= 54.0 | pass → pass |
| hn_sib_vmat | 0522c0002: Brainstem_PRV D0.03cc[Gy] <= 60.0 | 53.94 | 51.95 | <= 60.0 | informative → informative |
| hn_sib_vmat | 0522c0002: Glnd_Submand Dmean[Gy] <= 39.0 | 53.4 | 54.69 | <= 39.0 | informative → informative |
| hn_sib_vmat | 0522c0002: hottest point outside the elective volume (% of 70 Gy) | 98.1 | 96.7 | informative | informative → informative |

## Before the leaf model: the baseline against the correction

These changes come from the commits between `d458e46` and `55ab566`, not from the leaf model. They are listed so the
numbers here can be traced to the correction's. Every check passed in both.

| Case | Check | Correction (d458e46) | Baseline (55ab566) | Target | Result |
|---|---|---|---|---|---|
| lung_sbrt_vmat | LCTSC-Test-S1-101: PTV D0.03cc[%] <= 140.0 | 117.95 | 115.52 | <= 140.0 | informative → informative |
| lung_sbrt_vmat | LCTSC-Test-S1-101: Lungs V12.5Gy[cc] <= 1000.0 | 229.85 | 223.1 | <= 1000.0 | informative → informative |
| lung_sbrt_vmat | LCTSC-Test-S1-101: D2cm (PTV 16.0 cc) | 55.899 | 53.189 | < 51.2655 (minor ≤ 59.5818) | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S2-101: PTV D0.03cc[%] <= 140.0 | 115.2 | 113.82 | <= 140.0 | informative → informative |
| lung_sbrt_vmat | LCTSC-Test-S2-101: Esophagus D5cc[Gy] <= 17.7 | 1.77 | 3.83 | <= 17.7 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S2-101: Heart D0.03cc[Gy] <= 30.0 | 17.5 | 18.57 | <= 30.0 | pass → pass |
| lung_sbrt_vmat | LCTSC-Test-S2-101: D2cm (PTV 16.3 cc) | 49.277 | 51.036 | < 51.3882 (minor ≤ 59.7352) | pass → pass |
| lung_vmat_lctsc | LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 50.5 | 17.89 | 15.2 | <= 50.5 | pass → pass |
| lung_vmat_lctsc | LCTSC-Test-S2-101: PTV D0.03cc[Gy] <= 72.0 | 66.87 | 65.79 | <= 72.0 | informative → informative |
| lung_vmat_lctsc | LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5 | 20.19 | 16.77 | <= 50.5 | pass → pass |
| hn_sib_vmat | 0522c0001: Brainstem_PRV D0.03cc[Gy] <= 60.0 | 48.64 | 51.89 | <= 60.0 | informative → informative |
| hn_sib_vmat | 0522c0002: Brainstem D0.03cc[Gy] <= 54.0 | 41.05 | 44.64 | <= 54.0 | pass → pass |
| hn_sib_vmat | 0522c0002: Brainstem_PRV D0.03cc[Gy] <= 60.0 | 50.97 | 53.94 | <= 60.0 | informative → informative |

The SBRT case's CCC/pb ratio of PTV D95 also moved here, before the leaf model: from 0.997 to 0.987 and from 0.988 to
0.977.

## How to reproduce (optional)

```bash
git clone https://github.com/passlab/radiarch && cd radiarch && git checkout 412a105    # 55ab566 for the baseline
python3 -m venv .venv && .venv/bin/pip install -e "./src[dev,validation]"     # Python 3.12 or later
.venv/bin/python -m radiarch.validation.run --cases lung_sbrt_vmat
.venv/bin/python -m radiarch.validation.run --cases lung_vmat_lctsc    # about 2 hours on 6 threads; CCC needs glibc 2.38
.venv/bin/python -m radiarch.validation.run --cases hn_sib_vmat
```

The cases read the LCTSC and PDDCA patients from `RADIARCH_VALIDATION_DATA`, outside the repository.
