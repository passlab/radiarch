# Rerun of the R8 record's VMAT cases, 2026-11-07: closed leaf pairs parked under an X jaw

**What changed.** From commit `b11713b` on, the sequencer parks closed leaf pairs 10 mm behind the X1 jaw (behind X2
when the leaves cannot reach X1). A static segment parks every closed pair there. An arc parks only a pair that no
control point opens, for the whole arc; a pair open in some sectors still waits where its sweep leaves it. Before, a
closed pair stayed where the sequencer closed it. With the leaf model of `412a105`, a closed pair inside the jaws'
opening passes dose through its tips' gap. `LEAF_MODEL_VERSION` is 2, so cached sequences and arcs are made again.
The three VMAT cases plan through apertures, so they are rerun. Their numbers in the rerun of 2026-11-05
(`../2026-11-05-leaf-model-412a105/`) are superseded by these runs.

**These runs.** Three runs, one case per process, from a clean checkout of commit `b11713b` on the 96-core server, in
the radiarch image built from `55ab566` with the checkout mounted over its code, each capped at 6 BLAS threads:
`20261107-021808-b11713b` (`lung_sbrt_vmat`), `20261107-035324-b11713b` (`lung_vmat_lctsc`) and
`20261107-030602-b11713b` (`hn_sib_vmat`). `run-summary.md` lists every check, and `results.json` holds the full
numbers.

**What the parking changes.**

- Every graded check passes, as before: `lung_sbrt_vmat` 32, `lung_vmat_lctsc` 10, `hn_sib_vmat` 12.
- `lung_sbrt_vmat` and `hn_sib_vmat` are unchanged: every value equals the rerun of 2026-11-05.
- In `lung_vmat_lctsc`, only the second patient's (LCTSC-Test-S2-101) values move, by at most 0.19. The first
  patient's are unchanged.

| Check | 2026-11-05 (412a105) | Parked (b11713b) | Target | Result |
|---|---|---|---|---|
| LCTSC-Test-S2-101: PTV V60Gy[%] >= 95.0 | 95.62 | 95.43 | >= 95.0 | pass → pass |
| LCTSC-Test-S2-101: PTV D0.03cc[Gy] <= 72.0 | 65.25 | 65.22 | <= 72.0 | informative |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 37.0 | 14.01 | 13.99 | <= 37.0 | pass → pass |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5 | 15.65 | 15.6 | <= 50.5 | pass → pass |
| LCTSC-Test-S2-101: Esophagus Dmean[Gy] <= 34.0 | 3.24 | 3.25 | <= 34.0 | informative |
| LCTSC-Test-S2-101: second engine (CCC) gamma 3 %/3 mm against pb (%) | 86.1 | 86.0 | informative | informative |

The engines' open fields, their Monte Carlo comparisons and the fluence-level plans have no apertures and stand as
recorded.

## How to reproduce (optional)

```bash
git clone https://github.com/passlab/radiarch && cd radiarch && git checkout b11713b
python3 -m venv .venv && .venv/bin/pip install -e "./src[dev,validation]"     # Python 3.12 or later
.venv/bin/python -m radiarch.validation.run --cases lung_sbrt_vmat
.venv/bin/python -m radiarch.validation.run --cases lung_vmat_lctsc
.venv/bin/python -m radiarch.validation.run --cases hn_sib_vmat
```

The cases read their CT and structures from `RADIARCH_VALIDATION_DATA`, outside the repository.
