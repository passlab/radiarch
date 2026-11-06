# Rerun of `pb_vs_mc`, 2026-11-06: small fields and the MLC leaf model against Monte Carlo

Radiarch is a research treatment-planning system and is not for clinical use. This run is research evidence, not a
clinical commissioning.

**What changed.** Commit `e875b46` adds six Monte Carlo references made with OpenGATE: 1 × 1 and 2 × 2 cm water fields,
and four fields through the Versa's Agility MLC (open, all pairs closed, a 10 mm gap on every pair, and an irregular
shape). `pb_vs_mc` now grades the pencil beam on them:

- the small fields' dose at 10 cm over the 10 × 10 cm field's, and their width at half maximum;
- the leaf model: the leaf transmission and the dosimetric leaf gap are fitted to the closed and gap fields, and the
  fitted model is graded on the irregular field (gamma, the dose under its closed pairs, a 10 mm and a 5 mm gap).

`docs/reports/mlc-leaf-model.md` ("Against Monte Carlo") gives the fields, the fit and the reasons. The 34 checks of
the R8 record's `pb_vs_mc` repeat here with R8's values (to the seventh significant digit, from a different processor
and build).

**This run.** Run `20261106-163934-727654c`, from a clean checkout of commit `727654c` on the 96-core server, in 76
seconds. It ran in the radiarch image built from `55ab566` with the checkout mounted over its code; no dependency
changed between the two commits, and the image runs the CCC engine for the informative rows. `run-summary.md` lists
every check, and `results.json` holds the full numbers. 50 checks: 33 pass, 2 fail, 15 informative.

## The new checks

| Check | Pencil beam | Monte Carlo | Tolerance | Result |
|---|---|---|---|---|
| 1 × 1 over 10 × 10, dose at 10 cm | 0.719 | 0.764 | 5 % | **fails** (−5.9 %) |
| 1 × 1, width at half maximum at 10 cm (mm) | 11.37 | 11.52 | 1 mm | passes |
| 2 × 2 over 10 × 10, dose at 10 cm | 0.844 | 0.839 | 3 % | passes |
| 2 × 2, width at half maximum at 10 cm (mm) | 22.16 | 22.41 | 1 mm | passes |
| Irregular field, gamma 3 %/2 mm, depth 20–200 mm (%) | 100.0 | | ≥ 95 | passes |
| Irregular field, under the pairs closed at 20 mm (% of open) | 1.82 | 1.81 | 1 point | passes |
| Irregular field, 10 mm gap at 20 mm (% of open) | 80.06 | 81.17 | 3 points | passes |
| Irregular field, 5 mm gap at −30 mm (% of open) | 53.26 | 50.06 | 3 points | **fails** (+3.2) |

Informative:

- **The Agility in the OpenGATE model:** leaf transmission 0.196 %, dosimetric leaf gap 1.01 mm. The gap is fitted to
  the 10 mm gap field's dose integrated across the gap, as a sweeping gap measures it.
- At the 10 mm gap field's centre the fitted model gives 80.53 % of the open dose, the Monte Carlo 80.82 %.
- Where the closed pairs' rounded ends touch on the axis, the dose within 10 mm of the tips' line exceeds the
  transmission by 6.36 % of the open dose in the pencil beam and 5.90 % in the Monte Carlo.
- The irregular field with ideal leaves, for comparison: gamma 99.1 %, the closed pairs 1.62 %, the gaps 77.69 % and
  46.89 %.
- CCC's 4 × 4 and 20 × 20 rows read 1, as in the R8 record: CCC's shipped scatter cut-off (an R8 finding).

## The two failures

Both are kept as findings; no tolerance changed.

1. **The 1 × 1 cm field's dose is 5.9 % low** (tolerance 5 %), though its width matches and the 2 × 2 cm field is
   within 0.6 %. The field-size references shape x with the leaves, since the Versa has no X jaws; their pencil-beam
   plans use jaws, without the leaf model.
2. **The irregular field's 5 mm gap is 3.2 points high** (tolerance 3). One leaf gap cannot serve both gap widths:
   the 5 mm gap matches the Monte Carlo with 0.6 mm, the 10 mm gap with about 1.6 mm. Planning systems with a single
   leaf gap share this.

Both are the pencil beam on openings of a centimetre and less.

## Primaries

OpenGATE 10 runs a source's `n` on every thread. The R8 references ran on 18 threads, so they simulated 18 times the
primaries they state; the harness now scales them, and the notes read 9.0 × 10⁸ where R8's read 5 × 10⁷. Every
comparison is a ratio of references made the same way, so no R8 value changes. The pencil kernel's note still states
3.0 × 10⁷ primaries; that run also used 18 threads, so it simulated 5.4 × 10⁸. Its absolute scale does not enter any
dose: the pencil beam is calibrated to 1 cGy per MU at d_max of a 10 × 10 cm field.

The new references state what they simulated: 2 × 10⁹ primaries for the open, gap and irregular fields, 4 × 10⁹ for
the closed field, 1.6 × 10⁹ and 2.4 × 10⁹ for the 2 × 2 and 1 × 1 cm fields.

## What to review

The two failures above, and whether the leaf model is fitted the right way: the gap from the integral across a 10 mm
gap, the transmission from the closed field away from the tips.

## How to reproduce (optional)

```bash
git clone https://github.com/passlab/radiarch && cd radiarch && git checkout 727654c
python3 -m venv .venv && .venv/bin/pip install -e "./src[dev,validation]"     # Python 3.12 or later
.venv/bin/python -m radiarch.validation.run --cases pb_vs_mc    # about a minute and a half; CCC needs glibc 2.38
```

The references are in `src/radiarch/validation/references/mc/`; `python -m radiarch.validation.mc_reference` remakes
them with OpenGATE 10.1.1 (several hours on a 48-core server).
