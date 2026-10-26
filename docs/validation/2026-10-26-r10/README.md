# Validation record R10, 2026-10-26: guide for the reviewing physicist

Radiarch is a research treatment-planning system. These documents record how its planning protocols reproduce the
plans the validation harness makes, and how they plan a batch of patients unattended. **They are research
evidence, not a clinical commissioning: radiarch is not for clinical use, and signing records a review of research
evidence, not a clinical release.**

R10 adds a Python SDK, an auto-planning service, planning protocols (a site's plan as data: prescription, structure
derivations, planning goals, beams or arcs, machine, engine, the evaluation template), and a command line that plans
one patient or a list of cases. ADR 0017 (`docs/adr/0017-sdk-and-planning-protocols.md`) gives the decisions. The
two cases of this record ran from commit `92ce40d`, one case per process: `20261026-150400` and `20261026-152231`.
No engine changed in R10; the engines' records are R8's (`../2026-10-23-r8/`, with its correction of 2026-10-24).

## What to review and sign

| Document | Contents | Signed by |
|---|---|---|
| [`2026-10-26-pb-v1.1.1-92ce40d.md`](2026-10-26-pb-v1.1.1-92ce40d.md) | The shipped lung protocol against the harness case it encodes (every shared setting, then its plans against the recorded harness plans) and the lung SBRT protocol over six LCTSC thoraces through `radiarch batch` | medical physicist and project lead |

`run-summary.md` lists every check of the two runs in one table, and `results.json` holds their full numbers.

## What R10 adds, and why it matters for review

1. **The harness's planning became a service, unchanged.** The goal-driven loop the validation cases planned with
   (a goal that fails gets three times its weight and an organ's limit 10 % less dose, the plan renormalised to the
   target's coverage goal each round) moved into `services/autoplan.py` without a change in logic; the cases call
   the service. The plans in the R7 to R9 records are therefore the service's plans.
2. **A protocol reproduces its harness case exactly** (`protocol_lung_vmat`, 44 pass). The shipped
   `lung-60gy-30fx-vmat` protocol states, as data, what the R8 case `lung_vmat_lctsc` plans in code: all 16 shared
   settings are equal (prescription, CTV and PTV margins, the two rings' limits and weights, the coverage and organ
   goals with their maximum-dose terms, the two arcs, beamlet size, iterations, rounds, machine, jaw margin,
   template). Run on the case's two patients with its synthetic tumour, every RTOG 0617 goal value equals the
   recorded harness run's (the R8 record's correction folder), to the reported precision.
3. **A protocol plans a batch unattended** (`protocol_batch_lctsc`, 79 pass). `radiarch batch` planned all six
   LCTSC thoraces on disk with the `lung-sbrt-54gy-3fx-vmat` protocol (four of them never planned by the harness),
   each with a synthetic 12 mm peripheral tumour in the right lung: all six planned and deliverable, PTV D95 54.1 Gy
   after normalisation, the lung SBRT template's priority-1 goals met.
4. **A protocol's plan is deliverable as written.** The harness normalised a plan by scaling its dose array; the
   service scales the plan's metersets by the same factor and stores that plan and its dose, so the exported plan
   is the plan evaluated.
5. **A fault found during R10.** Exported RT Plans had stated the course's metersets in DICOM's per-fraction fields
   (a 30-fraction plan said 30 times its MU per fraction); found by a protocol test, fixed in `3a98b85` before this
   run (ADR 0012's correction). The dose records were not affected.

## Questions we would most like answered

1. **Protocols as data.** Is the protocol's content (prescription, derivations, planning goals separate from the
   evaluation template, beams or arcs, the loop's settings) what a department would want to fix in a research
   protocol, and what is missing (couch angles, a per-patient arc side, field-in-field rules)?
2. **The planning loop.** Three times the weight and 10 % less dose for a failed organ goal, renormalisation to
   coverage each round, three fluence rounds and three meterset rounds: is this a reasonable stand-in for a planner's
   iterations in a research system, or should a multi-criteria method (R11) replace it before plans are compared
   with clinical ones?
3. **Batch planning.** Which outputs would you want from a batch beyond the goals per case (DVH bands across the
   cohort, plan complexity, delivery time)?

## How to sign

Either reply to the covering email with your comments and a statement that you reviewed the named document at
commit `92ce40d`, which we then record in its signature table with the date and a reference to your email; or print
its signature section, sign and date it, and return a scan. Comments that lead to changes produce a new run and new
documents; a signature always refers to one commit.

## How to reproduce (optional)

```bash
git clone https://github.com/passlab/radiarch && cd radiarch && git checkout 92ce40d
python3 -m venv .venv && .venv/bin/pip install -e "./src[dev,validation]"     # Python 3.12 or later
.venv/bin/python -m radiarch.validation.run --cases protocol_lung_vmat
.venv/bin/python -m radiarch.validation.run --cases protocol_batch_lctsc
.venv/bin/python -m radiarch.validation.report --results validation/results/<first run> --also validation/results/<second run> --engines pb
# or the command line itself:
radiarch protocols
radiarch batch --protocol lung-sbrt-54gy-3fx-vmat --cases cases.csv --out results
```

The cases read LCTSC from a data directory outside the repository, `RADIARCH_VALIDATION_DATA` (default
`../data/public`); without it the lung protocol's settings are still checked and the batch case is skipped.
