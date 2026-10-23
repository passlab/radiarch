# Radiarch documentation

Radiarch is research software, not for clinical use. Start with the design, then the plan.

## Start here

| Document | What it is |
|---|---|
| [`architecture.md`](architecture.md) | Design and architecture as built: principles, components, services, engines, data model, persistence, pipeline, conventions, deployment, limits |
| [`impl-plan.md`](impl-plan.md) | Implementation plan and tasks: the roadmap's status, each item's tasks checked when done, what remains and where it is planned |
| [`impl-log.md`](impl-log.md) | What each roadmap item did, file by file, with its fixes, tests, open points and commits |
| [`demo.md`](demo.md) | A fifteen-minute walk through the services on the bundled phantom |
| [`PRODUCTION.md`](PRODUCTION.md) | Running radiarch in production: workers, limits, the API key, the audit log, storage |

## Decisions

[`adr/`](adr/) holds one record per decision, numbered in order: the CCC engine (0001), the
optimizer and beam-angle search (0002, 0003), evaluation metrics (0004), owning the core (0005),
the MCsquare driver (0006), DICOM RT readers (0007), the core without OpenTPS (0008), robust
protons (0009), machine model and apertures (0010), clinical goals and radiobiology (0011), the
RT object writer (0012), versions and lineage (0013), the validation report (0014), and the
native pencil-beam engine with VMAT and SBRT (0015).

## Reports

| Document | What it is |
|---|---|
| [`reports/tps-evaluation-and-roadmap.md`](reports/tps-evaluation-and-roadmap.md) | Evaluation against a commercial TPS, the engine strategy and the roadmap R0–R15 (2026-10-20; its status is kept in `impl-plan.md`) |
| [`reports/validation-data-and-test-plan.md`](reports/validation-data-and-test-plan.md) | Which data and tests validate the planning services; the R7a harness and the R7 results (2026-10-21/22) |

## Validation records

| Record | What it is |
|---|---|
| [`validation/2026-10-23-r8/`](validation/2026-10-23-r8/) | The R8 record for review: the pencil-beam engine, CCC 1.1.0, the arcs and SBRT; a guide, one document per engine version, the run summary and results of the clean-commit run |
| [`validation/2026-10-22-r7/`](validation/2026-10-22-r7/) | The R7 record for review: a guide for the reviewing physicist, one document per engine version, the run summary and results |
| [`validation/2026-10-21-full-run.md`](validation/2026-10-21-full-run.md) | The first full run of the R7a harness |

## Earlier documents

The documents of the project before the roadmap (February to October 2026: the original plan for
the six services, the phase notes, the project report, the handoff task list) were removed on
2026-10-22. They are in the git history; commit `2f7b506` is the last that has them.
