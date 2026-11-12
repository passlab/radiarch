# Validation records: the reviewing physicist's way in

State: 2026-11-12.

Radiarch is a research treatment-planning system. The records in this folder are research evidence, not a clinical
commissioning: **radiarch is not for clinical use, and signing records a review of research evidence, not a clinical
release.**

Five records wait for a physicist's review: R7 to R11. The goal templates wait for a check against their sources.
This page is the way in. It says what to read and in what order, which run holds each case's current numbers, every
graded check that fails in those runs, the limitations the records state, and how to sign. Each record's own
`README.md` is its full guide, with its questions to the reviewer.

## 1. Suggested order

1. **R7, questions 1 and 2** ([`2026-10-22-r7/`](2026-10-22-r7/README.md)): the Monte Carlo reference and the
   tolerances. Every later record grades against them, so an answer here changes the most.
2. **R8** ([`2026-10-23-r8/`](2026-10-23-r8/README.md)): the pencil-beam engine `pb`, the MLC leaf model
   ([`../reports/mlc-leaf-model.md`](../reports/mlc-leaf-model.md)), VMAT and SBRT. Most photon plans of R9 to R11 are
   dosed by `pb`.
3. **The goal templates** (section 5). They grade the patient plans in R8 to R11.
4. **R9** ([`2026-10-25-r9/`](2026-10-25-r9/README.md)): registration, 4D planning and replanning.
5. **R10** ([`2026-10-26-r10/`](2026-10-26-r10/README.md)): planning protocols and batch planning.
6. **R11** ([`2026-10-31-r11/`](2026-10-31-r11/README.md)): multi-criteria optimization.

R13 ([`2026-10-28-r13/`](2026-10-28-r13/README.md)) is the hand check of the RT objects in viewers. It needs no
physicist; its 3D Slicer part waits for the project lead.

## 2. What to sign, and where each case's current numbers are

Each record's documents come from one run at one commit. Later changes reran some cases; each rerun is a dated folder
inside the record, and the record's `README.md` says which cases it supersedes. The table gives the current run of
every case. Reruns not named here were steps on the way; each still explains what its change did.

| Record | Documents to sign (commit) | Cases read from a later run (folder, commit) | Signed by |
|---|---|---|---|
| R7 | CCC 1.0.0, MCsquare 0.3.0 and services 0.1.0 (`20fc3bf`) | `lung_e2e_lctsc`: R8's `2026-10-24-correction-d458e46` (`d458e46`), with CCC 1.1.0 | physicist and project lead; services: project lead |
| R8 | `pb` 1.1.1, CCC 1.1.0, MCsquare 0.3.0 and services 0.1.0 (`52ed834`) | `lung_e2e_lctsc`: `2026-10-24-correction-d458e46` (`d458e46`). `pb_vs_mc`, `pb_vs_ccc`, `photon_pdd_10x10_pb`, `photon_profile_10x10_pb`, `photon_output_vs_field_pb`, `dij_consistency`, `lung_sbrt_vmat`, `lung_vmat_lctsc`, `hn_sib_vmat`: `2026-11-12-small-fields-0228ec6` (`0228ec6`) | physicist and project lead; services: project lead |
| R9 | services 0.1.0 and `pb` 1.1.1 (`316b6c6`) | `lung_4d_itv`: `2026-11-12-small-fields-0228ec6` (`0228ec6`) | physicist and project lead |
| R10 | `pb` 1.1.1 (`92ce40d`) | `protocol_batch_lctsc`: `2026-11-12-small-fields-0228ec6` (`0228ec6`). `protocol_lung_vmat`: the same folder (`0228ec6`; it runs again from the next commit, which names the R8 rerun from `0228ec6` as its record) | physicist and project lead |
| R11 | MCO 0.2.0 (`b4085b0`) | TG-119 and the lung case: `2026-11-12-small-fields-0228ec6` (`0228ec6`). The proton case: none | physicist and project lead |

The reruns of 2026-11-05 (`*-leaf-model-412a105`) each compare their cases with a baseline from the commit before
the MLC leaf model. Read them for what the leaf model changed.

## 3. Graded checks that fail in the current runs

Every other graded check of the current runs passes. R10's batch passes every graded check. Its lung protocol fails
9 comparisons with the harness case's run of 2026-11-10, which the change moved; it runs again from the commit that
names the new run as its record (the R10 folder `2026-11-12-small-fields-0228ec6` says why).

| Record and case | Check | Value | Target | Reading | Where |
|---|---|---|---|---|---|
| R7 and R8, `photon_vs_mc` (14 checks over two settings; values from R8) | CCC against Monte Carlo, shipped scatter cut-off: dose on the axis beyond 15 cm in water; the lung slab's correction factor at 80, 200 and 250 mm | water 0.979, 0.954, 0.931 at 150, 200, 250 mm | 1 ± 0.02 | CCC with generic kernels falls off too fast at depth and is about 5 % off in and behind lung. A stated limitation; `pb` is the engine fitted to the references | ADR 0014 "Findings"; ADR 0015; R7 question 3; R8 question 3 |
| (the same case) | CCC without the cut-off: PDD10, dose beyond 15 cm, gamma, the lung slab's factors | PDD10 71.4 %; 1.05 to 1.12 at depth; gamma 78 % | PDD10 68.0 ± 2.0 %; 1 ± 0.02; ≥ 95 % | the setting is shown to say why the cut-off ships | R8 CCC document |
| R7 and R8, `dvh_crosscheck_pancreatic` (3) | single-voxel maxima against dicompyler-core | 3.5 to 4.6 % apart | ± 3 % | the two rasterizers assign the boundary voxels differently; the means agree within 2.3 % | ADR 0014 "Findings" |
| R7 and R8, `geometry_volumes_lctsc` (1) | LCTSC-Test-S2-102 oesophagus volume against the contour polygons | 39.7 cc | 37.8 cc ± 5 % | 5.0 % above, at the edge of the tolerance | ADR 0014 "Findings" |
| R8, `pb_vs_ccc` (1) | water 10 × 10 cm, 10 mm beamlets: gamma 3 %/3 mm of `pb` against CCC | 94.55 % | ≥ 95 % | most failing points lie deeper than 9 cm, where CCC's shipped scatter cut-off loses dose; `pb`'s sharper edge adds the rest, and there `pb` follows the Monte Carlo. A recorded finding (`src/radiarch/validation/known_findings.yaml`) | R8 rerun `2026-11-12-small-fields-0228ec6`; `../reports/mlc-leaf-model.md` |
| R9, `registration_4d_lung` (2) | patient 111_HM10395, tumour from the 50 % to the 0 % phase, Demons: Dice; and Dice above no registration | 0.767 | ≥ 0.80; > 0.789 | this patient's reference contours vary between phases | R9 question 1 |
| R9, `replan_pancreas_cbct` (5) | B-spline places the stomach-duodenum better than rigid alignment alone, on cone-beam CTs | worse in 5 of 10 pairs (0.821 → 0.724 at worst) | better than rigid | an intensity metric cannot follow day-to-day gas and filling; the B-spline never folds | ADR 0016; R9 question 2 |
| R11, `mco_front_tg119` (1) | the deliverable plan made from the first Pareto set: Core D5 | 22.45 Gy | ≤ 10.0, or ≤ 22.44 (the institutions' mean plus two SD) | the first set's known loss from fluence to apertures (`../reports/mco-deliverable-options.md`); the leaf ends' tail adds 0.05 Gy. The plan on the second set passes (19.14 Gy). Direct aperture optimization is the cure | R11 rerun `2026-11-12-small-fields-0228ec6`; R11 question 3 |

## 4. Limitations the records state

None of these is a failed check. Each is in its record, and some are open items in `docs/impl-plan.md`.

- **The Monte Carlo references** are a point source of the Mohan 6 MV spectrum through the jaws and the MLC, with no
  flattening filter or head scatter (R7 question 1). They ran 18 times the primaries they state; every comparison is
  a ratio, so no value changes.
- **`pb`'s lateral scaling in lung** is fitted to the two Monte Carlo lung slabs it is graded against. Those checks
  are consistency checks, not independent ones (R8 question 2).
- **CCC's scatter cut-off** gives small fields the 10 × 10 cm dose at depth, and organs a few centimetres outside the
  field get no dose (R8 question 3).
- **One SBRT patient's D2cm** is RTOG 0915's minor deviation: 57.37 % against 51.27 % (at most 59.58 % is minor), from
  `0228ec6`. The other patient's is within its limit (50.05 % against 51.39 %).
- **Dose accumulation** pulls each phase's dose back through its registration. It does not conserve energy where
  tissue compresses; the Jacobian is reported (R9 question 3).
- **TG-119 under MCO:** the plan made on the second set gives the core D5 19.14 Gy. That is within the institutional
  limit of 22.44 Gy but above TG-119's goal of 10 Gy (R11's rerun of 2026-11-12).
- **The arcs' second Pareto set** converges in 1 of its 11 plans (error bound 0.85, from `0228ec6`). Every plan meets
  the set's limits, none is dominated, and the plan made on the set is deliverable. The R11 rerun of 2026-11-10
  explains why.

## 5. The goal templates

The templates in `src/radiarch/goals/` grade the patient plans. Each names its source in its `source` field. Each row is a
structure, a metric, a limit and a priority, with a note. Please check every row against its source.

| Template | Rows | Source | Checked against the source | Comments |
|---|---|---|---|---|
| `rtog-0617.json` | 10 | RTOG 0617, section 6, the 60 Gy arm | | |
| `quantec.json` | 32 | QUANTEC: Marks et al. 2010, Table 1, and the organ papers | | |
| `tg101-sbrt-3fx.json` | 26 | AAPM TG-101, Table 3, 3 fractions | | |
| `tg101-sbrt-5fx.json` | 25 | AAPM TG-101, Table 3, 5 fractions | | |
| `sbrt-lung-54gy-3fx.json` | 30 | RTOG 0618 and 0915 target goals; TG-101 limits | | |
| `sbrt-lung-50gy-5fx.json` | 29 | RTOG 0813 starting level; TG-101 limits | | |
| `nccn-head-neck.json` | 19 | NCCN head and neck guidelines; RTOG 1016 | | |
| `pentec-pediatric.json` | 11 | PENTEC reports; marked provisional in the file | | |

## 6. The answers that would change the next work most

- **R7, question 1:** is the Monte Carlo reference acceptable? `pb`'s kernel and the leaf model's fit rest on it.
- **R8, question 3:** should `pb` be the default engine for plan doses, with CCC as the check?
- **R8, question 2:** which independent lung reference should come next?
- **R9, question 2:** should cone-beam CTs default to rigid alignment?
- **R11, question 3:** must the deliverable plan meet every goal the navigated plan met?

## 7. How to sign

Each record's `README.md` gives the two ways: reply to the covering email, or sign and scan a document's signature
section. A signature always refers to one commit. A record's current numbers come from several runs, so the statement
names each run reviewed: the record's documents at their commit, and each later folder at its commit (section 2).
For example:

> I reviewed, as research evidence and not as a clinical commissioning, the R8 record's documents at commit
> `52ed834` and its later runs `2026-10-24-correction-d458e46` (`d458e46`) and `2026-11-12-small-fields-0228ec6`
> (`0228ec6`). My comments follow.

The project lead records the statement in each document's signature table, with the date and a reference to the
email. For the goal templates, fill in section 5's table or name the templates checked in the email. Comments that
lead to changes produce a new run and new documents.
