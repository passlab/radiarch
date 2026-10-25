# Validation record R9, 2026-10-25: guide for the reviewing physicist

Radiarch is a research treatment-planning system. These documents record how its
registration, 4D and replanning services compare with clinicians' contours and with the
plans' own goals on public data. **They are research evidence, not a clinical commissioning:
radiarch is not for clinical use, and signing records a review of research evidence, not a
clinical release.**

R9 adds image registration (rigid, then Demons or a B-spline), contour propagation and dose
mapping between images, 4D planning on a respiratory-correlated CT (average-intensity CT, ITV,
the plan on every phase, deformable accumulation), adaptive replanning on a later CT or
cone-beam CT, and DICOM registration objects. ADR 0016
(`docs/adr/0016-registration-and-replanning.md`) gives the decisions and the findings in prose.
The three cases of this record ran from commit `316b6c6`, one case per process (each needs its
own memory budget): `20261025-114942`, `20261025-121624` and `20261025-142024`. The engines'
records are R8's (`../2026-10-23-r8/`, with its correction of 2026-10-24); nothing in R9 changes
an engine.

## What to review and sign

| Document | Contents | Signed by |
|---|---|---|
| [`2026-10-25-services-v0.1.0-316b6c6.md`](2026-10-25-services-v0.1.0-316b6c6.md) | Registration between breathing phases of five 4D-Lung patients against the clinician's contours and fiducial markers (rigid only, Demons, B-spline); the planning CT registered to ten cone-beam CTs of five Pancreatic-CT-CBCT-SEG patients against the cone-beam contours, with the clinical dose mapped onto each day | medical physicist and project lead |
| [`2026-10-25-pb-v1.1.1-316b6c6.md`](2026-10-25-pb-v1.1.1-316b6c6.md) | 4D lung planning with the ITV approach on two 4D-Lung patients: VMAT on the average CT, the plan recomputed on all ten phases with `pb` and accumulated on the 50 % phase | medical physicist and project lead |

`run-summary.md` lists every check of the three runs in one table, and `results.json` holds
their full numbers as the harness wrote them.

## What R9 adds, and why it matters for review

1. **Registration and its quality** (ADR 0016, decisions 1–4). A rigid step (Mattes mutual
   information), then diffeomorphic Demons for images of one calibration or a B-spline with
   normalised correlation for a cone-beam CT; the composite kept as one displacement field. Each
   registration reports, after AAPM TG-132, the similarity before and after, the Jacobian
   determinant and the share of body voxels where the field folds, and landmark errors; radiarch
   reports these and does not accept or reject a registration.
2. **Between breathing phases** (`registration_4d_lung`, 29 pass, 2 fail). Phase 50 % registered
   to 0 % in five patients with 4–11 mm tumour motion, the propagated contours compared with the
   clinician's 0 % contours, graded on Demons against TG-132's tolerances. Demons raises the
   tumour's Dice from 0.65–0.78 to 0.83–0.86 in four patients and brings the fiducial markers
   from 5–8 mm to 1.1–1.3 mm; the lungs reach 0.95–0.98; no field folds. **The two failures are
   one patient (111):** its two tumour contours differ by 11 % in volume (83 and 75 cc), and every
   method lowers the tumour's Dice slightly (0.79 to 0.77). The limits were set from TG-132 before
   this run and were not changed after it. The carina is reported but not graded: it is a
   contoured region, whose centroid moves with the extent drawn, not a point landmark.
3. **4D planning** (`lung_4d_itv`, 22 pass). The ITV as the union of the tumour drawn on all ten
   phases (1.47–1.49 times the tumour), PTV = ITV + 5 mm, two VMAT arcs on the average CT. The plan
   recomputed on each phase gives that phase's own tumour D95 59.9–61.1 Gy (the limit is 57 Gy,
   95 % of 60 Gy), and the dose accumulated through Demons on the 50 % phase gives it 61.0 and
   61.1 Gy.
4. **Cone-beam CT and replanning** (`replan_pancreas_cbct`, 15 pass, 5 fail). The B-spline never
   folds on the ten cone-beam CTs. **It places the stomach-duodenum better than rigid alignment
   in five of the ten** (Dice 0.52 to 0.62–0.66 in two patients) **and worse in the other five**
   (0.82 to 0.72 in one). The organs' gas and filling change from day to day, which an
   intensity-based metric does not follow. The organ doses of the day (the clinical dose mapped
   onto each cone-beam CT and read inside its own contours) are reported, not graded. The
   collection has no RT Plan, so the recomputation of a plan on the day's anatomy is tested in the
   unit tests (a shifted, recalibrated image with a limited field of view), not here.
5. **Faults found during R9.** Derived geometries (PTVs, rings) had been stored with x and z
   swapped since R4; the four affected planning cases are corrected in the R8 record's correction
   folder. The RT Dose writer wrapped round-off below zero to false hot spots in exported doses;
   fixed, with no effect on the records, which grade dose arrays. On the first cone-beam CT the
   B-spline had folded in 44 % of the body: the image is mostly padding outside its field of view;
   the metric is now masked to the body and the B-spline bounded to stay one-to-one.

## Questions we would most like answered

1. **Tolerances.** The registration case grades Demons against TG-132's figures: fiducial markers
   within 2 mm, Dice at least 0.80 for the tumour and 0.90 for the lungs, mean surface distance
   within 3 mm, no folding. Are these the right figures for a research system, given that the
   reference contours carry their own variability (patient 111)?
2. **Cone-beam CT.** The B-spline is safe but not reliably better than rigid alignment on
   abdominal cone-beam CTs. Would you rather radiarch default to rigid alignment for cone-beam
   CTs until a better metric (local correlation, histogram matching, contour guidance) is shown to
   help, or keep the deformable step with its quality figures shown?
3. **Accumulation.** Doses are mapped by pulling each phase's dose back through its registration
   (not energy-conserving where tissue compresses; the Jacobian is reported) and summed with
   equal phase shares. Is that acceptable for research 4D evaluation, and which check of
   accumulation would you want next?
4. **The ITV approach.** Planning on the average CT with PTV = ITV + 5 mm gives every phase's
   tumour its dose in these two patients. Is the average CT the right planning image for a
   research system, or would you want mid-ventilation planning too?

## How to sign

Either reply to the covering email with your comments and a statement that you reviewed the
named documents at commit `316b6c6`, which we then record in the signature table of each
document with the date and a reference to your email; or print the signature section of a
document, sign and date it, and return a scan. Comments that lead to changes produce a new
run and new documents; a signature always refers to one commit.

## How to reproduce (optional)

```bash
git clone https://github.com/passlab/radiarch && cd radiarch && git checkout 316b6c6
python3 -m venv .venv && .venv/bin/pip install -e "./src[dev,validation]"     # Python 3.12 or later
for c in registration_4d_lung replan_pancreas_cbct lung_4d_itv; do       # one process each
  .venv/bin/python -m radiarch.validation.run --cases $c
done
.venv/bin/python -m radiarch.validation.report --results validation/results/<first run> \
  --also validation/results/<second run> validation/results/<third run> --engines pb services
```

`lung_4d_itv` needs about 18 GB of memory at its 3 mm grid. The cases read 4D-Lung and
Pancreatic-CT-CBCT-SEG from a data directory outside the repository, `RADIARCH_VALIDATION_DATA`
(default `../data/public`); without them they are skipped.
