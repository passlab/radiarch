# ADR 0007 — DICOM RT in: plan, dose and registration readers; dose from an RT Plan

Date: 2026-10-21. Status: accepted. Roadmap R2.

## Context

Everything radiarch computed so far started from a beam set radiarch chose.
Recalculating the dose of an existing plan, comparing the dosimetric impact of
two plans and planning a reference site all start from plans and doses that
exist as DICOM RT objects. The
vendored OpenTPS readers are not usable for this: its photon plan read path
refers to an unbound variable, it keeps no MLC positions, and it is going away
with R15.

## Decision

`src/radiarch/dicom/` reads RT objects with pydicom into radiarch's own models:

- **RT Plan → `PhotonPlan`.** One segment per control-point interval; the
  interval's meterset is its share of the cumulative meterset weight times the
  beam meterset from the fraction group. A step-and-shoot interval takes the
  aperture of its start control point; an interval over which the leaves move
  takes the mean of its two ends. A beam whose gantry angle is constant is one
  `PhotonBeam`; an **arc is discretized into one `PhotonBeam` per interval at the
  mid-angle**, the representation R8's arc optimizer will share. Attributes
  omitted at later control points keep their last value, as the standard allows.
  Setup beams and zero-meterset beams are skipped; crossed leaves close at
  their mid-point; a plan without jaw positions takes them from the leaf bank.
- **RT Ion Plan → `ProtonPlan`.** Every control point carrying non-zero scan-spot
  weights is an energy layer; spot metersets are their share of the final
  cumulative meterset weight times the beam meterset; range-shifter settings are
  carried per layer. Only `MODULATED` (pencil-beam scanning) beams are accepted.
- **RT Dose → `RTDoseVolume`** on the `(z, y, x)` convention, frames ordered by
  ascending z whatever the file's order, relative or absolute frame offsets,
  axis-aligned only; `resample_dose_to_grid` puts it on a radiarch grid.
- **Spatial and Deformable Spatial Registration** → matrices per source frame
  and displacement grids; consumed by R9.

`services/plan_import.py` stores an imported plan as a beam model in the same
store as built ones, with the plan's own metersets per fluence element in
`plan_weights.npy` and the DICOM provenance on the result. `POST /beam-model/import`
takes an upload or a server path; `POST /dose/recalculate` runs the ordinary dose
pipeline with those metersets as weights. A plan whose frame of reference is not
the geometry's is refused unless the caller opts out: computing on another CT is
registration (R9), not recalculation.

## Evidence

`tests/test_dicom_readers.py` (hand-built plans, doses and registrations, and an
Eclipse RT Dose from the public pancreatic collection) and
`tests/test_plan_import.py`, whose last case imports an RT Ion Plan and shows the
recalculated MCsquare dose equals the engine's dose for the same plan model at a
fixed seed.

## Consequences

- Plans from PACS are staged by upload for now; fetching an RT Plan instance
  over DICOMweb joins the fetcher when the Orthanc adapter grows instance retrieval.
- The hand-built RT objects in `tests/dicom_fixtures.py` are the seed of R6's writers:
  writer output will be read back through these readers.
- `PhotonBeam` gained `energy_mv`; both plan models gained `dicom` provenance;
  `BeamModelResult` gained `plan_weights_uri` and `imported_plan`.
