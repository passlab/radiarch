# Leaf transmission, rounded leaf ends and tongue-and-groove in aperture doses

Status: design agreed with the project lead, 2026-11-04; built 2026-11-04 (see "As built"); the records rerun
2026-11-05; checked against Monte Carlo 2026-11-06 (see "Against Monte Carlo"); the rounded ends pass a tail beyond
their tips from 2026-11-11 (see "The rounded ends' tail and the pencil beam's edge"). Radiarch is not for clinical use.

## The problem

Every photon dose radiarch computes from MLC apertures treats the leaves as ideal: full dose where they are open,
none through them. Three code paths do this:

- **Step-and-shoot sequencing** (`services/sequencing.py`, `coverage_matrix`). A segment's dose is the open-field
  influence matrix times the fraction of each beamlet inside the aperture.
- **The pencil-beam engine** (`services/dose_engines/pb.py`, `aperture_rectangles`). This path covers the VMAT
  control-point intervals, the final arc dose, and imported plans recomputed through their apertures.
- **CCC** (`PhotonSegment.coverage_beamlets`, `ccc_driver.delivered_beamlet_geometry`). This path recomputes
  delivered plans.

The machine model already holds a leaf transmission (1.5 %) and a jaw transmission (0.2 %). No dose path uses them.

A real MLC adds three effects. The values are representative of a 120-leaf MLC (LoSasso, Chui and Ling 1998, Med
Phys 25:1919):

| Effect | Size | Where it matters |
|---|---|---|
| Leaf transmission | 1.5 to 2 % of the open dose passes through closed leaves | Organs under closed leaves. IMRT and VMAT deliver several times the MU of an open field, so the leakage there is several percent of the prescription. |
| Rounded leaf ends (dosimetric leaf gap, DLG) | An opening acts about 1.5 to 2 mm wider than its nominal gap | Narrow openings. A sliding-window sweep with 10 mm gaps gets about 15 % more dose than the ideal model gives. |
| Tongue-and-groove | A strip about 0.5 mm wide at each boundary between leaf pairs is shadowed when the neighbouring pair is closed there | Underdosed stripes between pairs in summed segments, a few percent of the target dose. |

The plan row names transmission and tongue-and-groove. The rounded leaf ends are added too, because for
sliding-window arcs they are the largest of the three; the project lead agreed on 2026-11-04.

## The design

1. **One aperture model.** `PhotonSegment` gains one method that returns its fluence as rectangles, each with a
   factor:
   - the open parts, with factor 1;
   - the parts under the leaves inside the jaws, with the leaf transmission;
   - the parts under the jaws, with the jaw transmission.

   Each leaf tip moves back by half the DLG. All three dose paths use this method: the sequencing coverage, the
   pencil beam's fluence grid and CCC's coverage cells. Because there is one function, the paths cannot disagree.
2. **Tongue-and-groove.** Take a strip of the tongue-and-groove width centred on the boundary between two adjacent
   leaf pairs. Inside it, the opening is the overlap of the two pairs' openings, and the rest of the strip gets the
   leaf transmission. This is the simplest published model. It gives the stripe in summed segments, and it changes
   nothing when the two pairs are open alike.
3. **The machine model.**
   - `MLCSpec` gains `dosimetric_leaf_gap_mm` and `tongue_and_groove_mm`.
   - The two synthetic machines get representative values (transmission 1.5 %, DLG 1.5 mm, tongue-and-groove
     0.5 mm), with the source in their files.
   - A machine file without the new fields keeps ideal tips and no tongue-and-groove. Its leaf transmission is
     used from now on.
4. **Caches.** An MLC model version goes into the sequencing, VMAT and engine cache keys, so cached doses from the
   ideal model are not reused.

## As built (2026-11-04)

- `LeafModel` (`models/photon_plan.py`) holds the four values; `PhotonMachineSpec.leaf_model()` reads them from the
  machine (`MLCSpec.dosimetric_leaf_gap_mm`, `MLCSpec.tongue_and_groove_mm`, the leaf and jaw transmissions).
- `PhotonPlan.leaf_model` carries them. Sequencing and VMAT set it from the machine, a plan normalised or moved
  for the day keeps it, and an imported photon plan gets the import's machine's (ideal leaves, with a warning, when
  radiarch has no such photon machine). A plan without it, made before or without a machine, keeps ideal leaves.
- `PhotonSegment.fluence_rectangles(model)` is the one aperture model. The sequencing coverage
  (`sequencing.coverage_matrix`, through `aperture_segment`, so the coverage and the plan's segments are the same
  apertures), the pencil beam's fluence (`pb.aperture_rectangles`) and CCC's delivered cells
  (`PhotonSegment.coverage_beamlets`) all use it.
- Details the design left open:
  - Under both the leaves and a jaw the fluence is about the product of the two transmissions (3e-5) and is left
    out, so the fluence stays within the jaws and the leaf openings.
  - A jaws-only field (no MLC rows) is unchanged: the open-field records and R8's Monte Carlo comparisons stay as
    they are.
  - Tongue-and-groove applies between adjacent pairs that a segment lists. Pairs it does not list are closed leaves
    inside the jaws, at the leaf transmission.
  - The sequencing coverage has the open field's beamlets only, so fluence past them (a rounded tip at the field's
    edge, under a jaw) is not in it: the jaw transmission over 0.75 mm.
  - A dose of an aperture plan from its own beamlets (`fluence: beamlets`, the optimizer's columns) keeps ideal
    leaves. The doses through the apertures are the pencil beam's `fluence: apertures` and CCC's delivered dose.
- Caches: `LEAF_MODEL_VERSION` is in the keys of sequences, arcs, MCO deliverable plans and protocol runs. An
  imported plan's key already holds the plan, now with its leaf model. The engines' versions are unchanged: their
  beamlet doses are the same.
- Machines: both synthetic machines get a 1.5 mm leaf gap and 0.5 mm tongue-and-groove; their leaf transmissions
  stay (1.5 % and 0.5 %).
- There are no regression goldens of aperture doses, so none are regenerated.
- Cost, on a sliding-window arc of 10 mm gaps in an 8 x 8 cm field (30 intervals): the pencil beam's segment dose
  matrix gains 13 % more entries in the same time (its 80 mm cutoff already reaches across the field), and the arc's
  dose rises 25 %. CCC's delivered recomputation gets 5.3 times the beamlets, since every cell inside the jaws now
  carries the transmission, and takes about that much longer.

## Tests

- A closed leaf pair inside the jaws gives the leaf transmission of the open dose, plus the DLG leak at the tips.
- A narrow sliding gap gives a dose that scales with the gap plus the DLG.
- Two complementary segments split at a leaf-pair boundary give a summed dose that dips in the tongue-and-groove
  strip by the expected amount.
- The three paths agree on one segment: the integrals of their fluence are equal.

Built as `tests/test_r4_mlc_leaf_model.py`, with a pencil-beam check that closed leaves pass 1.5 % of the open dose
(1.52 % with the scatter of the tips' gap).

## Against Monte Carlo (2026-11-06)

The tests above check the model against itself. The validation case `pb_vs_mc` now also checks it against OpenGATE,
through the Elekta Versa HD's Agility MLC that `opengate.contrib.linacs.elektaversa` models: 80 pairs of 5.1 mm at
isocenter, rounded leaf ends, tongue-and-groove, and the Versa's leaf calibration, which puts the 50 % edge on a
nominal leaf position, as an Elekta planning system states it. The project lead chose this before B1 on 2026-11-05.

- **References** (`validation/mc_reference.py`). Four fields set leaf by leaf between Y jaws at ±50 mm and two
  tungsten blocks standing in for X jaws at ±100 mm (the Versa has none): open; every pair closed on the axis; a
  10 mm gap on every pair; and an irregular field with pairs closed off the axis, 5 and 10 mm gaps and steps between
  pairs. All four share one source cone, so their doses relate directly. Also 1 × 1 and 2 × 2 cm open fields at
  1.25 mm, since VMAT apertures are mostly smaller than the 4 × 4 cm reference.
- **The fit, as a commissioning would do it.** The Agility's leaf transmission and dosimetric leaf gap are the values
  that make the pencil beam give the Monte Carlo dose at 10 cm under the closed field's leaves and across the 10 mm
  gap field, integrated over 100 mm along the leaves as a sweeping gap measures it. They are reported, not graded:
  they describe this MLC model, not radiarch. (The first form fitted the gap's centre dose; see the results.)
- **The check.** The pencil beam with the fitted values and the synthetic machines' 0.5 mm tongue-and-groove is
  graded against the irregular field: gamma 3 %/2 mm at least 95 % (TG-218), the dose under the closed pairs within
  1 % and in the gaps within 3 % of the open field's. The same field with ideal leaves is reported beside it. The
  small fields grade the dose at 10 cm over 10 × 10 cm (3 % and 5 %) and the width at half maximum (1 mm).
- **What it does not check.** The synthetic machines' values (1.5 % and 0.5 % transmission, 1.5 mm gap) are not the
  Agility's; the fit tests the model's form with an MLC's own values. Tongue-and-groove is not fitted: its stripes are
  narrower than the 2.5 mm grid.
- **A fault found on the way.** OpenGATE 10 runs a source's `n` on every thread, so the R7 and R8 references ran 18
  times the primaries they state (9 × 10⁸, not 5 × 10⁷; the pencil kernel 5.4 × 10⁸, not 3 × 10⁷). Their comparisons
  are unaffected, since each relates references made with the same 18 threads. `mc_reference.py` now splits the total
  over the threads and stores the dose per simulated primary, and the harness scales the older references to match.
- **A second fault: one process does not scale.** One OpenGATE process stops gaining speed beyond about a dozen
  threads: on the 48-core compute server, 81 000 primaries per second on 4 threads, 149 000 on 12, 132 000 on 80. The
  2 × 2 cm reference took 3.4 hours that way. The others ran as 62 chunks of 2 × 10⁸ primaries, 16 processes of 5
  threads at a time (1.6 million per second together), each chunk with its own seed, merged by `mc_reference.py
  --merge` (the dose weighted by primaries, the uncertainties in quadrature). Primaries: 2 × 10⁹ for the open, gap
  and irregular fields, 4 × 10⁹ for the closed field, 1.6 and 2.4 × 10⁹ for the 2 × 2 and 1 × 1 cm fields.

### Results (2026-11-06)

The pencil beam against the new references, in the record run `20261106-163934-727654c`
(`docs/validation/2026-10-23-r8/2026-11-06-mc-leaf-model-727654c/`; CCC's informative field-size rows left out). The
working tree before the commit gave the same values:

| Check | Pencil beam | Monte Carlo | Tolerance | |
|---|---|---|---|---|
| 1 × 1 over 10 × 10, dose at 10 cm | 0.719 | 0.764 | 5 % | fails (−5.9 %) |
| 2 × 2 over 10 × 10, dose at 10 cm | 0.844 | 0.839 | 3 % | passes |
| Width at half maximum at 10 cm, 1 × 1 and 2 × 2 (mm) | 11.37, 22.16 | 11.52, 22.41 | 1 mm | pass |
| Irregular field, gamma 3 %/2 mm, depth 20–200 mm | 100.0 % | | ≥ 95 % | passes |
| Under the pairs closed at 20 mm (% of open) | 1.82 | 1.81 | 1 | passes |
| 10 mm gap at 20 mm (% of open) | 80.06 | 81.17 | 3 | passes |
| 5 mm gap at −30 mm (% of open) | 53.26 | 50.06 | 3 | fails (+3.2) |

- **The Agility in the OpenGATE model:** leaf transmission 0.196 %, dosimetric leaf gap 1.01 mm. The closed field
  alone, integrated over its tips' line, gives 0.96 mm. Touching rounded ends leak a line on the axis that peaks at
  16 % of the open dose.
- **Ideal leaves**, for comparison: gamma 99.1 %, the closed pairs 1.62 %, the gaps 77.69 % and 46.89 %. The leaf model
  brings the low dose and the 10 mm gap to the Monte Carlo and overshoots the 5 mm gap.
- **The fit's form changed after the first results.** Fitted to the 10 mm gap's centre dose, as first built, the leaf
  gap came out 1.30 mm and the 5 mm gap failed by 5.2 points. The centre dose of a 10 mm gap grows by only 1.6 % of
  the open dose per millimetre of gap, so the pencil beam's 0.3-point error there moved the fit by 0.3 mm. The
  integral grows by the open dose times the gap's growth, as a sweeping-gap measurement does; it gives 1.01 mm,
  which the closed field confirms. The project lead chose the integral on 2026-11-06. No tolerance changed.
- **Two findings.**
  1. The pencil beam is 5.9 % low on a 1 × 1 cm field, though within 0.6 % at 2 × 2 cm. The field-size references
     shape x with the leaves, since the Versa has no X jaws; their pencil-beam plans use jaws, without the leaf model.
  2. One leaf gap cannot serve both gap widths: the irregular field's 5 mm gap matches the Monte Carlo with 0.6 mm,
     its 10 mm gap with about 1.6 mm.

  Both are the pencil beam on openings of a centimetre and less. Planning systems with a single leaf gap share the
  second, which is why their leaf gap is often tuned on clinical VMAT plans. Both are fixed from `pb` 1.2.0 (below).

## The rounded ends' tail and the pencil beam's edge (2026-11-11)

The two findings, diagnosed on the same references and fixed together. The change is `pb` 1.2.0 and
`LEAF_MODEL_VERSION` 4.

**Why the 1 × 1 cm field was low.** `pb` 1.1 blurred every field edge with a Gaussian of 4 mm FWHM, fitted to the
10 × 10 cm field's penumbra. A symmetric blur moves fluence from inside an edge to outside it. A 1 cm field's edges
are close to its centre, so the blur took 5.9 % from it. Without the blur, the pencil beam gives the 1 × 1 cm field
0.764 against the Monte Carlo's 0.764. The kernel's components play no part: 4 and 8 give the same.

**What the edge looks like.** Against the Monte Carlo, an unblurred pencil beam matches inside a field. Outside each
edge, the Monte Carlo has a tail: up to 6–9 % of the axis dose just past the edge, falling off over about 10 mm. The
leaf tips have the most; the jaws have less. The 4 mm blur imitated the tail by taking dose from inside the field.

**Why the 5 mm gap was high.** The leaf model moved each tip back by half the leaf gap, so all the extra fluence sat
at the opening's edge. In a 5 mm gap, that edge is close to the centre. The Monte Carlo's rounded ends pass the same
amount as a tail spread over millimetres under the leaf, and less of it reaches a narrow gap's centre. The irregular
field showed it. Over ideal leaves, the Monte Carlo's excess was about 3.3 points in both gaps. The moved tips gave
6.4 points to the 5 mm gap and 2.4 to the 10 mm gap.

**The comparison was half a voxel off.** An independent review of the first build found it. The references' voxels
sit half a voxel to the side of the harness's phantoms: an even count of voxels against an odd one, centred on the
axis. Resampled onto the phantom, each Monte Carlo value is therefore the mean of two voxels across the beam, while
the pencil beam was taken at the voxel's centre. At an edge, that softens the Monte Carlo by about 0.6 mm (80–20 %).
The 4 mm blur, fitted to that edge, absorbed it too. Now the pencil beam is scored on each reference's own voxels,
each the mean of 2 × 2 × 2 points in it, and resampled onto the phantom as the reference is (`cases_r8._pb_dose`).
CCC's comparisons with the same references (`photon_vs_mc`, R7) still have the offset; they are not changed here.

**The model.**
- A rounded end passes half the leaf gap as a tail beyond its tip: `f(s) = min(1, A exp(-s / λ))` of the open
  fluence, on top of the leaf transmission, with integral DLG / 2. `LeafModel.leaf_tip_tail_mm` is λ; 0 keeps the
  moved tip. The tail is a set of rectangles, 0.25 mm wide at the tip and up to λ wide. It stops at 4 λ, where a
  real rounded end is the leaf's full thickness, and its last rectangle holds the rest of the integral. So the
  sequencing coverage, the pencil beam and CCC still share one aperture model.
- In a tongue-and-groove strip between pairs open in different places, each tail reaches the midpoint between the
  tips, so the fluence does not jump as the openings part.
- A closed pair is parked far enough behind an X jaw that its whole tail stays under the jaw.
- The pencil beam's Gaussian edge blur stands for the source size and the collimators' scatter. It goes from 4.0 mm
  FWHM to none: the Monte Carlo's source is a point, and the fit wants no blur. A real machine's commissioning would
  set its own.
- The lung's lateral kernel scaling was fitted with the old edge, so it was refitted on the same two lung slabs. Its
  exponent goes from 0.9 to 0.925. The 2 × 2 cm slab is within 1.9 % at every depth. The 10 × 10 cm slab is within
  2.6 %, as in the R8 record; the exponent does not move it.
- The synthetic machines take the Agility's tail, 2.3 mm, with their own 1.5 mm leaf gap.

**The fit, as a commissioning would do it.** The blur and the tail were fitted together on two fields: the 10 × 10 cm
field's leaf edge at 10 cm (40 to 75 mm from the axis), and the 10 mm gap field across its gap. The fit minimised
the root mean square of both, with the leaf transmission and leaf gap refitted at each point of a grid of blurs from
0 to 2.5 mm and tails from 1 to 3 mm. The minimum was no blur and a tail of about 2.3 mm. In full mode the harness
fits the tail itself at run time: the transmission and gap stay at their first fit during the search and are
refitted at the end. The blur is the engine's default.

The 10 × 10 cm field's graded checks across the beam (the penumbra, the off-axis ratio, the dose 2 cm outside the
edge, its gamma) use the fitted edge, so they are consistency checks. The independent checks are the 1 × 1, 2 × 2,
4 × 4 and 20 × 20 cm fields, the narrow lung field beyond its fit, and the irregular MLC field.

**The comparisons now plan each field as the Monte Carlo collimates it.** x is set by the Agility's leaf tips with the
fitted leaf model, y by the jaws, and the X jaws sit at the edge of the source's cone. Before, the open fields'
pencil-beam plans used jaws on both axes with ideal leaves, so the 4 mm blur also stood in for the leaf tips.

**Results.** The run `20261112-032744` used the working tree before the commit. The Agility fits 0.198 %, a leaf gap of
0.96 mm and a tail of 2.32 mm. All 35 graded checks pass and none fail. The `pb` 1.1 column is the R8 record's run,
with the old comparison:

| Check | `pb` 1.1 (727654c) | `pb` 1.2.0 | Monte Carlo | Tolerance |
|---|---|---|---|---|
| 1 × 1 over 10 × 10, dose at 10 cm | 0.719 (fails) | 0.765 | 0.764 | 5 % |
| 1 × 1, width at half maximum at 10 cm (mm) | 11.37 | 11.77 | 11.52 | 1 mm |
| 2 × 2 over 10 × 10 | 0.844 | 0.848 | 0.839 | 3 % |
| 2 × 2, width at half maximum (mm) | 22.16 | 22.72 | 22.41 | 1 mm |
| 4 × 4 and 20 × 20 over 10 × 10 | 0.906, 1.064 | 0.907, 1.064 | 0.895, 1.058 | 2 % |
| 10 × 10 penumbra 80–20 % at 10 cm (mm) | 5.93 | 6.04 | 5.87 | 2.5 mm |
| 10 × 10, 2 cm outside the edge (% of the axis) | 4.79 | 5.09 | 5.12 | 1 point |
| 2 × 2 in lung, at 50 / 80 / 100 mm over 20 mm | 0.986 / 1.014 / 1.020 | 0.981 / 1.009 / 1.019 | 1 | 3 % |
| Irregular field, gamma 3 %/2 mm | 100.0 % | 100.0 % | | ≥ 95 % |
| Irregular field, under the pairs closed at 20 mm (% of open) | 1.82 | 1.82 | 1.81 | 1 point |
| Irregular field, 10 mm gap (% of open) | 80.06 | 80.60 | 81.17 | 3 points |
| Irregular field, 5 mm gap (% of open) | 53.26 (fails) | 50.87 | 50.06 | 3 points |

Informative: the 10 mm gap field's centre, 80.49 against 80.82 % (80.53 before). Touching closed pairs leak 5.99 % of
the open dose within 10 mm of their tips' line, against the Monte Carlo's 5.90 % (6.36 before).

**One graded check against CCC fails: a recorded finding.** `pb_vs_ccc` compares the pencil beam with CCC on the
10 × 10 cm field in water. With 10 mm beamlets, its gamma 3 %/3 mm is 94.55 % against at least 95 % (95.63 % with
`pb` 1.1). Most failing points are in the field deeper than 9 cm, where CCC's shipped scatter cut-off loses dose (R7
and R8 records). The sharper pencil-beam edge adds the rest, and at that edge the pencil beam follows the Monte Carlo
(gamma 99.3 %). The project lead had it recorded as a finding about CCC; no tolerance changed
(`validation/known_findings.yaml`). In fast mode, as CI's nightly run does it, the check passes at 97.4 %.

**Also changed.** Each beamlet's influence-matrix table now covers the cells as the dose path's fluence grid does. Its
offset from the grid is kept to 0.05 mm: exact for beamlets whose size is a multiple of it, and at most 400 tables
per size. With the sharper edge, the two paths differed by up to 6.5 % at the edge voxels of a 6 cm field; with the
4 mm blur the difference was 1.6 %. A field's influence matrix now equals its dose.

## What changes, and the reruns

Every photon dose made from apertures changes: IMRT and VMAT plans, imported plans recomputed through their
apertures, and MCO deliverable plans. Records with such doses get dated reruns on the compute server:
- R8: the VMAT and SBRT cases, and the CCC recomputation of delivered plans;
- R9: the 4D lung case, whose VMAT plan is recomputed on every phase (added 2026-11-05);
- R10: the protocol plans;
- R11: the deliverable plans, the lung case's after the R11.9 correction and the TG-119 case's static fields (added
  2026-11-05).

The open-field records do not change: R7, and R8's Monte Carlo comparisons on jaw-defined fields. The physicist then reviews the records once, with the MLC model
in.

From `pb` 1.2.0 (2026-11-11) every pencil-beam dose changes as well, open fields included, and every aperture dose
from a machine's leaf model. The same records are rerun, together with R8's pencil-beam cases (`pb_vs_mc`,
`pb_vs_ccc`, `photon_pdd_10x10_pb`, `photon_profile_10x10_pb`, `photon_output_vs_field_pb`, `dij_consistency`).

## Still not modelled

- Head scatter and source occlusion in small apertures (the output factor). The Monte Carlo has a point source, so
  the fitted blur is none; a real machine's commissioning would set its source size.
- A tail beyond the jaws' edges. The Monte Carlo's Y jaws show one about two thirds the size of the leaf tips'.
- Transmission that varies with leaf position (interleaf leakage beyond an average).
- Jaw tracking.
- Leaf position errors.

## Effort

About 0.75 engineer-weeks for the model, the three paths and the tests, then about a day of compute-server time for
the reruns.
