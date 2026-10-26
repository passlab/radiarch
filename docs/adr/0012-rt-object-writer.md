# ADR 0012 — DICOM RT out: the RT object writer

Date: 2026-10-21. Status: accepted. Roadmap R6 ("RT object writer").

## Context

Radiarch read DICOM RT since R2 (ADR 0007) and wrote one thing: a legacy
RT Dose from the `/plans` workflows, with no plan behind it. A clinic
workflow needs the planning system's whole output as the objects a
real one produces — structure set, plan with control points and MU, dose,
DRRs — and the delivery side needs treatment records per fraction and a
course summary, all storable in Orthanc and readable by OHIF and 3D Slicer.
The R4 aperture plans and the R14/R15 proton plans hold everything those
objects need.

## Decisions

1. **One writer per object on a shared case context** (`dicom/writers/`).
   `CaseContext` carries patient, study, frame of reference and the CT
   series with its slice UIDs; every object of a case is built on it, so
   they agree on identity, and every object carries the intended-use
   statement in its series description and a private block (R0), as the
   legacy exporter did. The geometry record now keeps the CT provenance
   (`CTMetadata`: patient ID, sex, birth date, position, study date and
   description, slice UIDs) so a writer needs only the stores; a geometry
   built before R6 falls back to re-reading the CT under
   `RADIARCH_DATA_ROOT`. A CT without a Frame of Reference UID (the OpenTPS
   phantom) gets a stable one derived from its series UID.
2. **RT Structure Set from masks.** Structures are what the geometry holds —
   masks on its grid, derived structures included — turned into closed
   planar contours per slice (the 0.5 iso-line, Douglas–Peucker at a third
   of a voxel; holes and islands as separate contours). Names are written as
   given; the interpreted type follows the name (PTV/CTV/GTV, EXTERNAL,
   SUPPORT, AVOIDANCE, ORGAN). Round trip through radiarch's reader and
   rasterizer gives the mask back (Dice 1.0 on the tests' blocks).
3. **RT Plan as step-and-shoot; RT Ion Plan per energy layer.** Every photon
   segment is a pair of control points (aperture at a cumulative meterset,
   then the same after its MU), leaves moving at zero meterset; weights are
   in MU and the fraction group's `BeamMeterset` is the beam's MU, so the
   R2 reader returns the same segments. *(Corrected 2026-10-25: DICOM states
   one fraction's metersets, while radiarch's photon plans hold the whole
   course's; the writer divides by the fractions planned and the reader
   multiplies back. Until then exported plans stated the course's MU per
   fraction. A proton plan carries its own fraction count; see
   `writers/common.per_fraction`.)* The MLC is the machine's leaf
   pairs when the plan's rows are among them (unused pairs parked at X1),
   else the pairs the rows define; jaws-only plans get X and Y devices only.
   Proton layers become pairs of ion control points (spot weights, then
   zeros) with range-shifter settings; the virtual SADs come from the BDL.
   A prescription becomes a dose reference (VOLUME on the target ROI when
   the structure set was written, else SITE) with cumulative dose
   coefficients at every control point. `PlanIntent` is RESEARCH and
   `ApprovalStatus` UNAPPROVED: approval is a human act in the record system (an OIS).
4. **RT Dose PLAN and BEAM.** Frames by ascending z on the geometry grid,
   31-bit scaling, `DoseType` EFFECTIVE with the RBE in the comment for
   Gy(RBE). A BEAM dose per beam is an engine run with the other beams'
   elements zeroed through the dose service (cached like any dose), so it
   costs one run per beam and works for every engine; the tests check the
   beam doses sum to the plan dose on the linear engine.
5. **DRRs by ray marching, not SimpleITK.** SimpleITK exposes no ray-cast
   interpolator, so `dicom/drr.py` marches rays from the source through the
   CT box with trilinear sampling and integrates the relative attenuation
   `max(0, 1 + HU/1000)`; the beam frame is the spot placer's (gantry about
   z, couch about y, beam along +y at gantry 0), checked against it in the
   tests. The RT Image plane is the isocenter plane (`RTImageSID = SAD`),
   rows along +x and columns down −y of the receptor; each DRR references
   its plan and beam and the plan's beam references the DRR back.
6. **Treatment records from the plan radiarch wrote.** An RT (Ion) Beams
   Treatment Record per session scales the specified metersets by the
   delivered share (interrupted sessions terminate OPERATOR or MACHINE),
   records every control point, chains to the earlier records of the
   course, and the RT Treatment Summary Record carries fractions planned
   and delivered, dates and the cumulative dose to the dose reference.
   These are what a treatment machine and a record system store; the export
   service writes them on request.
7. **Export service and routes.** `POST /rt/export` resolves the plan from
   an aperture sequence (photons; segment MU and segment dose), a proton
   optimization (weights become spot MU; its dose) or a beam model with its
   own metersets (an imported or basic plan, optionally a dose), writes the
   objects into `{artifact_dir}/rt_exports/{id}/` with a manifest, and
   pushes them with STOW-RS when asked (`RADIARCH_DICOMWEB_URL`, or an
   explicit URL on `/push`). A photon optimization is refused until it is
   sequenced: a fluence is not a plan. `POST /rt/exports/{id}/records`
   writes sessions and the summary against an export.
8. **Validation in CI.** Every object type is validated against the DICOM
   standard's IOD tables with `dicom-validator` (a dev extra, edition
   2026d) in the full suite, and with `dciodvfy` (dicom3tools) in a CI
   step; both run clean. An opt-in test round-trips the objects through
   a DICOMweb server (`RADIARCH_TEST_DICOMWEB_URL`), reading the plan and
   dose back from it; it passed against a research Orthanc. OHIF and 3D Slicer are checked by hand (`docs/impl-plan.md`, R6).

## Consequences

- Writing the BEAM doses exposed an R4 defect: the fluence map binned each
  open-field beamlet onto the leaf pair of its centre only, so with
  beamlets wider than the leaves the apertures were combs and the coverage
  matrix credited half the fluence. Beamlets now cover every pair they
  span; the segment dose and the aperture plan's beamlets agree.
- The legacy `/plans` RT Dose goes through the same writer and references
  a plan UID derived from its file; the workflows gain nothing else.
- `DICOMwebNotifier.store_instances` takes datasets, paths or bytes
  (it used to pass raw bytes to a client that wanted datasets, so the
  legacy push never worked); failures still never fail a plan job.
- Contours are written on the geometry grid; a geometry resampled from its
  CT puts contours between CT slices, which Slicer renders and OHIF matches
  to the nearest image. Writing on the CT grid is a resample away (R9).
- Not written: arcs as single beams (R8 will write VMAT control points),
  compensators, wedges, blocks, bolus, spatial registration, DVH sequences
  in the dose, RT Beams Delivery Instruction and UPS (the record system's).
