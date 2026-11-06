# Leaf transmission, rounded leaf ends and tongue-and-groove in aperture doses

Status: design agreed with the project lead, 2026-11-04; built 2026-11-04 (see "As built"); the records' reruns
are next. Radiarch is not for clinical use.

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

## Still not modelled

- Head scatter and source occlusion in small apertures (the output factor).
- Transmission that varies with leaf position (interleaf leakage beyond an average).
- Jaw tracking.
- Leaf position errors.

## Effort

About 0.75 engineer-weeks for the model, the three paths and the tests, then about a day of compute-server time for
the reruns.
