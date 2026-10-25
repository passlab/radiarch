# ADR 0016 — Registration, contour propagation, dose mapping, 4D planning and replanning

Date: 2026-10-24. Status: accepted. Roadmap R9 ("Registration, 4D, replanning").

## Context

R9 asks radiarch to work across images of one patient: phases of a 4DCT, a
re-planning CT, a cone-beam CT of a treatment day. Each step needs the same
three things: a transform from one image to another, the structures of one
image on the other, and a dose computed on one image on the other. Imported
plans on a CT in another frame of reference (R2) need the same transform.
The roadmap names SimpleITK for the registration; AAPM TG-132 (Brock et al.
2017) for what a registration must report.

This record covers R9.1 to R9.7.

## Decisions

1. **One displacement field per registration, on the fixed grid.** The
   registration maps fixed points to moving points, `T(x) = x + u(x)` (ITK's
   convention), and stores `u` as a three-component NIfTI on the fixed
   geometry's grid. The rigid and deformable parts are composed into that one
   field, so every later use (structures, doses, the CT itself) samples one
   field and nothing re-composes transforms. The rigid part is kept as a 4 × 4
   matrix and six parameters for reading and for a later DICOM Spatial
   Registration object.
2. **Rigid first, then one of two deformable methods.** Rigid: Euler 3D,
   Mattes mutual information (50 bins, 25 % random sampling with a fixed
   seed), regular-step gradient descent over a pyramid. It starts from the
   identity when both CTs share a frame of reference (4DCT phases), else from
   the volume centres or the body's centres of mass. Deformable:
   diffeomorphic Demons for images of the same modality and calibration (CT to
   CT, phase to phase), B-spline with normalised correlation (L-BFGS-B) for
   CT to cone-beam CT: correlation is invariant to a linear HU scale and
   offset, which is most of a cone-beam CT's calibration difference. Mutual
   information was tried and rejected for the B-spline: ITK's Mattes metric
   keeps a derivative buffer of bins² × parameters per work unit, over 8 GB
   for a thorax's ~11 000 parameters on 20 threads (3.4 GB and 51 s even on
   the test phantom, against 0.3 GB and 3 s); the joint-histogram metric did
   not move the B-spline at all. Cupping and scatter, which are not linear,
   may need histogram matching or a local metric when the cone-beam cases
   come (R9.5). `none` gives rigid only.
   The metric looks only at the fixed image's body (HU > −500) and 10 mm
   around it, and the B-spline coefficients are bounded to 0.4 of the
   control-point spacing, a sufficient condition for a one-to-one cubic
   B-spline (Choi and Lee 2000) and the registration's regularisation. The
   B-spline metric samples 10 % of the masked voxels by default
   (`bspline_sampling`).
3. **A working grid per image, over its own extent.** Both CTs are clipped to
   a HU window (−1000…1500 by default) and resampled to an isotropic working
   spacing (3 mm by default) over each image's own extent. A cone-beam CT's
   short field of view stays short: points outside an image drop out of the
   metric instead of being compared with air.
4. **Quality is reported, not judged.** After TG-132: inside the fixed body
   (HU > −500), the mean absolute HU difference and the normalised
   cross-correlation for the initial, the rigid and the final transform; the
   Jacobian determinant of `T` (minimum, maximum, mean and the fraction of
   body voxels where it is not positive, i.e. where the field folds); the
   largest displacement; landmark errors between structure centroids (before,
   after the rigid step, after). Landmarks are given as structure pairs, which
   suits 4DCT marker contours and clinician-contoured fiducials. The service
   returns these numbers and does not accept or reject a registration; that is
   a reviewer's decision.
5. **Propagated structures make a derived geometry.** Propagation pulls each
   moving mask back through `T`, keeps the voxels above a partial-volume level
   (0.5), and adds them to a new geometry derived from the fixed one: the
   fixed CT, density and structures unchanged, the propagated structures added,
   a `propagate` operation recorded with the registration. A name that exists
   on the fixed geometry needs a suffix; radiarch never overwrites a
   clinician's contour with a propagated one.
6. **A mapped dose is a new dose.** `map-dose` pulls a dose on the moving
   geometry back through `T` onto the fixed grid and stores it as a dose of
   the fixed geometry, with `mapped_from` naming the source dose and the
   registration. Pull-back does not conserve energy where tissue is compressed
   or stretched; the error is the Jacobian's distance from 1, which the
   registration reports. Energy-conserving accumulation can come later if the
   4D cases show it matters.
7. **Lineage.** `registration` is a new version kind. A registration derives
   from its two geometries; a propagated geometry from the fixed geometry and
   the registration; a mapped dose from its source dose, the registration and
   the fixed geometry. An approved plan built on propagated contours therefore
   locks the registration it depends on.
8. **Synchronous routes.** `POST /registrations`, `GET /registrations/{id}`,
   `GET /registrations/{id}/field`, `POST /registrations/{id}/propagate`,
   `POST /registrations/{id}/map-dose`, `DELETE /registrations/{id}`. A CT pair
   at 3 mm registers in seconds to about a minute, so the routes run in the
   request (in FastAPI's thread pool) and cache by the inputs' cache keys, the
   request and the algorithm version.

9. **4D planning follows the ITV approach.** The phases of a 4DCT share one
   frame of reference and one grid, so the average-intensity CT is the
   voxelwise mean HU of the phases (converted with the reference phase's HU
   model, a derived geometry of the reference phase that keeps its
   structures), and the ITV is the union of the tumour as drawn on each phase.
   A phase on another grid or frame of reference contributes through a
   registration instead (its contour propagated). A plan with metersets is
   recomputed on each phase's CT with its isocenter in the shared patient
   coordinates, through the engine's aperture path for photon apertures (the
   path the VMAT dose itself uses). Accumulation pulls each phase dose back
   through its registration (the reference phase fixed) and sums the phases
   with their shares of the delivery, equal unless given: a regular breathing
   pattern spends about as long in each phase bin. The accumulated dose
   records its parts (`accumulated_from`), and the lineage follows them. Routes:
   `POST /four-d/average`, `/four-d/itv`, `/four-d/phase-doses`,
   `/four-d/accumulate`. Mid-ventilation and gated planning, and phase weights
   from a measured breathing trace, are not part of R9.

10. **Replanning starts from an assessment of the plan on the day.** The
    day's image (a re-planning CT or a cone-beam CT) is the fixed image and the
    planning CT the moving one, so everything is pulled onto the day's grid:
    the planning structures are propagated, and for a cone-beam CT, whose HU
    are not calibrated for dose, the planning CT's HU deformed onto it give the
    density (`deformed_planning_ct`, the default; `own` for a re-planning CT).
    The plan's isocenter moves by the rigid part of the registration, as the
    couch shift that sets the patient up does; the rigid rotation is reported
    and not corrected, as a couch without rotation leaves it. The plan's
    metersets are recomputed on the day's anatomy and the goals graded on the
    planned dose and the day's dose side by side, with the planned dose also
    mapped onto the day's grid. `POST /replan/assess`, `GET /replan/{id}`. B-spline
    is the default deformable method because a cone-beam CT's calibration
    differs (decision 2).
11. **A new plan names the plan it replaces, and the course sums both.** The
    RT export takes `predecessor_plan_uid` (written as `ReferencedRTPlanSequence`
    with `RTPlanRelationship` PREDECESSOR) and a MULTI_PLAN RT Dose that
    references every plan it sums (`dose_summation`, `summed_plan_uids`). The
    course itself is an accumulation with absolute weights: each plan's
    whole-course dose, mapped onto one geometry, times the fraction of it
    delivered (fractions given over the plan's fractions). A new plan is made
    on the day's geometry with the ordinary planning services; warm-starting
    from the old plan's weights works when the beams are the same.

12. **Registrations travel as DICOM, both ways.** A radiarch registration is
    written in the fixed geometry's frame of reference as a Spatial
    Registration with the rigid part (when the frames differ; its matrix moves
    source-frame points into the registered frame, the inverse of radiarch's
    fixed-to-moving matrix, PS3.3 C.20.2) and a Deformable Spatial Registration
    with the whole field, identity pre- and post-deformation matrices
    (`POST /registrations/{id}/dicom`). The standard applies the deformable
    object to points of the registered frame and yields source-frame points
    (C.20.3), which is ITK's direction and radiarch's: the field is written as
    it is. A plan made on another CT imports onto a geometry through either a
    radiarch registration (`registration_id`: this geometry fixed, that CT
    moving) or a DICOM Spatial Registration in this geometry's frame with a
    matrix for the plan's frame (`registration_path`): its isocenters move,
    its angles stay (the couch shift), and a rotation over 1 degree is logged.
    The R2 reader's docstring had the deformable direction backwards; it is
    corrected (no code depended on it).

13. **4D robustness is evaluated over the phases, not yet optimized.** An
    accumulation can keep each mapped phase dose as a scenario of the
    accumulated dose (`phases_as_scenarios`), each as if the whole course were
    delivered in that phase, on the reference anatomy; the evaluation service
    then grades every goal's worst phase as it grades R3's setup and range
    scenarios. Optimizing over the phases (a robust objective over per-phase
    influence matrices on the reference anatomy) needs every phase's influence
    matrix mapped through its registration; it is left for a later item.

## Findings

- **Derived geometries were stored with x and z swapped (fixed).** Writing the
  registration tests exposed that the geometry store's `save` takes arrays in
  (x, y, z) order, while the derive step (R4) passed its (z, y, x) arrays
  unchanged. Every derived geometry (PTVs, rings, density overrides) was
  stored transposed against its parent. Planning and evaluation then used the
  same transposed arrays, so plans were self-consistent and their checks
  passed, but the anatomy was mirrored relative to the beams and to the
  original CT, and exported structure sets were misplaced. The R4 regression
  test used a centred cube, where the swap is invisible. The derive step now
  transposes before saving; its cache key carries a derive version, so no
  transposed geometry is reused; a new test uses a non-cubic grid and an
  off-centre structure. Cases planned on derived geometries change: on the
  lung cases, spinal cord, oesophagus and heart doses rise from near 0 Gy to
  realistic values (10–20 Gy cord maximum), and every graded check still
  passes.

- **The B-spline diverged on cone-beam CTs until the metric was masked
  (registration 1.1.0).** On the first Pancreatic-CT-CBCT-SEG pair the
  unmasked, unbounded B-spline made the stomach-duodenum worse than rigid
  alignment (Dice 0.38 → 0.17), folded in 44 % of body voxels and ran 22
  minutes: the cone-beam CT, resampled onto the planning grid by the
  collection, is 83 % padding at −1000 outside its field of view, where the
  planning CT has tissue. With the body mask and the bounds (decision 2): rigid
  0.525, B-spline 0.635, no folding, 94 s. A mask of the body alone, or one that
  drops the image's minimum value as padding, let the rigid step slide 2 cm,
  because the collection clips real air at −1000 too and the skin boundary is
  what holds the rigid step. Demons, which assumes one calibration, is not for
  cone-beam CTs (Dice 0.06 on that pair). The synthetic tests had passed
  before the fix; one of them now pads its "cone-beam" image the same way.

## Consequences

- `services/registration.py`, `models/registration.py`,
  `api/routes/registration.py`; `services/four_d.py`, `models/four_d.py`,
  `api/routes/four_d.py`; `services/replan.py`, `models/replan.py`,
  `api/routes/replan.py`; `dicom/writers/reg.py`; SimpleITK is a runtime dependency (it already
  was, for the geometry store).
- `tests/test_r9_registration.py` covers a synthetic thorax: rigid recovery
  of a known rotation and shift, Demons undoing a breathing-like motion
  without folding, B-spline improving on rigid, volume and dose mapping, and
  the API with lineage.
- `registration_4d_lung` joins the harness (services document): five 4D-Lung
  patients, phase 50 % registered to 0 %, propagated contours against the
  clinician's 0 % contours and landmark errors (markers, carina), with
  unregistered and rigid-only baselines, graded on Demons against TG-132's
  tolerances (fiducial markers within 2 mm, Dice ≥ 0.80 for the tumour and
  0.90 for the lungs, mean surface distance within 3 mm; the carina, a
  contoured region rather than a point, informative). There is no
  ground-truth deformation: the reference contours carry their own
  variability, and where a patient's two tumour contours differ in volume
  (11 % in one) no registration reaches the tolerance.
- `lung_4d_itv` joins the harness (pb document): two 4D-Lung patients, the
  ten phases averaged, the ITV from the ten tumour contours, PTV = ITV + 5 mm,
  two VMAT arcs on the average CT, the plan recomputed on every phase and
  accumulated on the 50 % phase; graded on the tumour's D95 in each phase and
  in the accumulated dose (at least 95 % of the prescription).
- `replan_pancreas_cbct` joins the harness (services document): five
  Pancreatic-CT-CBCT-SEG patients, the planning CT registered to each
  contoured cone-beam CT (rigid only, B-spline, Demons), the planning
  stomach-duodenum and bowel propagated and compared with the cone-beam
  contours, the clinical dose mapped onto the day's anatomy; graded on the
  B-spline placing the stomach-duodenum better than rigid alignment alone,
  without folding. The collection has no RT Plan, so the plan recomputation
  on the day is covered by the tests, not this case.
- Open: robust optimization over the breathing phases (decision 13); mid-
  ventilation and gated planning; phase weights from a measured breathing
  trace; deformable image registration on the GPU.
