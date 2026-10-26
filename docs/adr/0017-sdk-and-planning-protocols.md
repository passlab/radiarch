# ADR 0017 — Scripting SDK, auto-planning and planning protocols

Date: 2026-10-26. Status: accepted. Roadmap R10 ("Scripting SDK and planning protocols").

## Context

Through R9, radiarch was driven by its REST API, one service at a time, and its best plans were made by the
validation harness, whose planning loop lived in the validation cases' code. R10 asks for automation without a
user interface: a Python SDK that mirrors the domain, planning protocols that drive end-to-end auto-planning,
wrappers for workflow engines, and batch planning. Commercial systems offer the same through their scripting
interfaces and knowledge- or template-based auto-planning (the evaluation report, rows "Scripting API" and
"Auto-planning").

## Decisions

1. **The SDK is a client of the REST API, and of nothing else.** `radiarch.sdk.Radiarch` talks to a server over
   HTTP, or to the app in the same process (`Radiarch.local()`, through the web framework's test client), with the
   same code. It adds no planning logic: its objects wrap the services' own result models and call their routes.
   Whatever a script does, a server would have done the same way, with the same audit and lineage.
2. **One job rule for every service.** A long request answers 200 with its result (cached or quick) or 202 with a
   job; `/{service}/jobs/{id}` reports progress and, on success, the id of the result. `Radiarch.submit` follows
   that to the result and raises `RadiarchError` with the service's message on failure.
3. **Domain objects that chain.** `Geometry` → `derive` → `photon_beams` or `arc_sectors` → `BeamModel.optimize` →
   `Optimization.sequence` or `.arcs` → `.dose()`, `.evaluate()`, `.export()`, with `Registration` and
   `ProtocolRun` beside them. Each object reads its result's fields directly, so a script uses the documented
   models rather than a second vocabulary.
4. **The harness's planning loop becomes the service, unchanged.** The goal-driven loops the validation cases
   planned with (static fields in R7, VMAT in R8) move into `services/autoplan.py` without a change in logic, each
   function compared line by line with its original; the cases call the service. The plans in the validation
   records are therefore the service's plans, and a protocol that encodes a case reproduces it.
5. **A protocol is data.** `PlanningProtocol` holds what a site's planning protocol holds: prescription, structure
   aliases (the names centres use, mapped to the protocol's), derivations (margins, rings, booleans), the planning
   goals that drive the loop, extra objectives, static fields or arcs, machine, engine, the loop's settings, and the
   goal template the finished plan is evaluated against. Protocols ship as JSON files beside the goal templates; a
   site writes its own as a file. A protocol run is a job, cached by the geometry and the protocol's content.
6. **A protocol's plan is deliverable as it stands.** The harness normalised a plan by scaling its dose array. The
   service scales the plan's metersets by the same factor and stores that plan and its dose, so the plan written
   out is the plan evaluated. Static fields are sequenced into apertures; VMAT arcs carry their metersets.
7. **The command line and its wrappers.** `radiarch plan` plans one patient and `radiarch batch` a list of cases,
   in process or against a server; a batch records a failed case and goes on, and writes a summary table of goals
   per case. CWL tool descriptions of both ship with the package: CWL is the workflow-language standard most engines
   import, so one description serves them all.

## Findings

- **Exported RT Plans stated the course's metersets as one fraction's.** The protocol test compared an exported
  plan's metersets with its plan's and found the R6 writer copying the course MU into DICOM's per-fraction fields;
  fixed separately (`3a98b85`, ADR 0012's correction).

## Consequences

- `sdk/`, `services/autoplan.py`, `models/protocol.py`, `protocols/*.json`, `api/routes/protocols.py`,
  `tasks/autoplan_tasks.py`, `cli.py`, `cwl/*.cwl`; the `radiarch` console script.
- `protocol_lung_vmat` (the shipped lung protocol against the harness case it encodes: every shared setting, then
  its run against the recorded run) and `protocol_batch_lctsc` (the SBRT protocol through `radiarch batch` over the
  LCTSC thoraces) join the harness (pb document).
- Open: knowledge-based planning (dose prediction from earlier plans), multi-criteria trade-offs (R11), protocol
  versions bound to approvals.
