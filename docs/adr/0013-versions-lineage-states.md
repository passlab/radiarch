# ADR 0013 — Versions, lineage, attribution and states

Date: 2026-10-21. Status: accepted. Roadmap R12 ("Plan states and lineage").

## Context

Radiarch's results were already content-addressed and cross-referenced:
every dose names its geometry and beam model, every sequence its
optimization, every export what it wrote. What was missing was the view
SMIS needs of them (F1.8: a regenerated dose is a derived version with
lineage; F2.5: every output attributed to a capability, a version, a
dataset) and the one rule the clinic needs (an approved plan does not
change under its feet), without radiarch taking a decision that belongs to
the record system (F5.4: approval transitions stay in smis-ois).

## Decisions

1. **Versions are the stored results; the lineage is read, not written.**
   `services/lineage.py` builds the version view from the existing stores:
   a node per result (geometry, beam model, influence, dose, optimization,
   sequence, bao, evaluation, rt_export, legacy plan) with its parents
   taken from the references the result already carries (an aperture beam
   model and a segment dose also name their sequence through the cache
   key the aperture service gave them). No new table of results, no
   duplicated ids; a result that is deleted is a `missing` node in the
   graphs that referenced it.
2. **Attribution from what the results know.** `Attribution` carries the
   capability (radiarch at its package version), the engine and its
   version, the machine model, the HU model, the modality, and the dataset
   (patient, study, CT series, frame of reference, structure set, imported
   plan). A version inherits its dataset from its geometry. The RT export
   manifest carries the same attribution, and every DICOM object radiarch
   writes names the engine and the machine in its private block next to
   the intended-use statement (what the write gateway's stamp check wants).
3. **States are recorded, never decided.** A version is `draft`,
   `approved`, `superseded` or `retired`; the transitions are draft →
   approved | retired, approved → superseded | retired, superseded →
   retired. An approval must name the authority that decided it and the
   actor who did, with a reference into that system; an approval whose
   authority is radiarch is refused. Transitions live in one JSON file
   under the artifact directory and every one is audited.
4. **Approved versions are immutable, and so is everything they derive
   from.** A version that was ever approved (superseded or retired later or
   not) locks itself and its whole ancestry: the delete routes of every
   store answer 409. Caches are content-addressed, so re-running the same
   inputs reuses the approved version rather than replacing it.
5. **The SMIS transformation record is a view too.**
   `GET /lineage/{kind}/{id}/derivation?dataset_id=&version=` renders a
   version as the manifest schema's `derivation` member: a `computation`
   by the tool radiarch, parameters that name the engine, machine, HU
   model, parents and roots, and for an export the DICOM series it wrote.
   The record validates against the SMIS manifest schema (the test runs
   the schema when it is on the machine).
6. **A capability declaration.** `GET /lineage/capability` states what
   radiarch is to a registry: a tool, what it reads and writes, what it
   never does (route a plan to a treatment queue, grant an approval,
   re-identify), how it labels objects, its engines with versions and
   availability, machines, HU models, goal templates and the state rule.

## Consequences

- Nothing changes for callers who ignore states; everything stays a draft
  and deletable. The clinic's record system records approvals through the
  state route once F5.4 exists; until then the tests and the fixture
  builder do.
- `descendants` scans every store; it is a maintenance view, not a hot
  path. The lock set is recomputed per request from the approved versions'
  graphs; with hundreds of versions this is milliseconds.
- Not done: an approval that pins the engine binary's digest (the
  attribution names the version; the container digest comes with F3.3's
  computation request), lineage across radiarch instances, and the audit
  trail's own immutability (JSONL, as before).
