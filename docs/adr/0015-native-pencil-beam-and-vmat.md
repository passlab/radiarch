# ADR 0015 — The native photon pencil-beam engine, VMAT arcs, SBRT templates

Date: 2026-10-22. Status: accepted. Roadmap R8 ("Native pencil-beam engine and VMAT").

## Context

R7 left radiarch with one photon engine, the WiscPlan collapsed cone (CCC),
run as a separate program, and a validation harness with OpenGATE references
of the CCC kernels' own spectrum. R8 asks for three things: a photon engine of
radiarch's own as the independent second engine (and the fast engine for
optimization), arcs (VMAT) with leaf-motion- and gantry-speed-constrained
sequencing and segment dose recomputation, and SBRT templates after AAPM
TG-101; the results it names are lung VMAT and SBRT plans, a head-and-neck
70/35 simultaneous integrated boost, and the second-engine check.

## Decisions

1. **The kernel is our own Monte Carlo, not matRad's base data.** matRad's
   photon base data is GPL v3. `validation/mc_reference.py --pencil` runs
   OpenGATE 10.1.1 with the Mohan 6 MV spectrum (the spectrum of the CCC
   kernels and of the R7 references) from a point source 1000 mm above a
   400 × 400 × 300 mm water box, a 0.5 mm pencil at the surface, the same
   step-converged physics as R7, scored on a 1 mm grid to ±40 mm and a 5 mm
   grid to ±200 mm. `services/dose_engines/pb_kernel.py` turns the annulus
   means into the shipped table `engines/pb/pb_6mv_kernel.npz`: the fine and
   coarse annuli stitched between 28 and 36 mm; moved to the isocenter plane
   by integrating the piecewise-constant kernel over each isocenter-plane
   cell, so every depth keeps its integral exactly; tabulated over radius bins
   of a 1 mm grid with their cell counts; continued exponentially beyond the
   last 30 mm of the phantom (no backscatter there) to 500 mm.
2. **The decomposition is of the cumulative kernel.** The SVD is taken of the
   fraction of each depth's dose within radius R, which is a circular field's
   dose up to a constant. An SVD of the kernel itself errs point by point, and
   those errors add up over a broad field: with three components it was 6 %
   off at 20 cm and 30 % in the build-up of a 30 cm field. Of the cumulative
   kernel, three components stay within about 1 % for every field, four
   within 0.5–1 %, five within 0.3 %. The default is four.
3. **Two paths through one model.** Dose at a point is the output factor ×
   the inverse square × Σ_i A_i(d_rad) (Φ ⊛ k_i)(u, w) (Bortfeld, Schlegel and
   Rhein 1993), with (u, w) in the isocenter plane of the IEC beam frame and
   d_rad from a divergent ray grid in the beam's-eye view, anchored on the beam
   axis. The **dose path** convolves each beam's fluence (beamlets × weights,
   or the apertures as they are) with the full 200 mm kernel by FFT. The
   **influence matrix** convolves each beamlet size once with each component
   and evaluates columns within 80 mm of the beamlet. The fluence penumbra of a
   real source and collimator is a Gaussian applied to the kernel planes, so
   both paths share the edge; its width is fitted to the Monte Carlo field edge.
4. **The influence matrix is thinned without bias.** Below 0.3 % of a column's
   maximum, an entry v is kept with probability v / T and set to T (matRad's
   Dij sampling). The numbers are a Weyl sequence over the beamlets for each
   voxel rather than independent draws, which halves the per-voxel noise. On a
   10 × 10 cm field: 90 million entries become 21 million, the mean in-field
   dose is unchanged and the per-voxel spread is 0.7 %. CCC's shipped matrix is
   smaller because it stops scatter about 2 cm from each beamlet (see the
   findings).
5. **Absolute dose as CCC's.** 1 cGy per MU at d_max of a 10 × 10 cm field at
   SSD 100 cm, computed from the engine's own components and penumbra.
6. **NumPy, with CuPy behind a switch.** `params["device"]` (`cpu`, `gpu`,
   `auto`; `RADIARCH_PB_DEVICE`) chooses the backend; the code is written once
   against the array API both share (the `gpu` extra installs CuPy). On a
   workstation GPU the doses agree with the CPU's to 3 × 10⁻⁶ and are up to
   25 times faster; influence and segment matrices differ only in a few
   entries at the sampling threshold. `test_gpu_matches_cpu` checks this
   where a device is present.
7. **Air outside the patient gets no dose; cavities do.** Voxels below
   0.05 g/cm³ get no dose unless an axial slice encloses them, as a planning
   system's external contour would: airways and sinuses inside targets are
   dosed (the synthetic oropharynx target found this).
8. **VMAT is arc sequencing of sector fluence maps** (Craft, McQuaid, Wala,
   Chen, Salari and Bortfeld, Med Phys 39:686, 2012), built on R4's
   unidirectional sliding-window decomposition. An arc is cut into sectors;
   the fluence optimization uses one static beam at each sector's centre (with
   the arc's couch and collimator); each sector's map becomes as many leaf
   states as the sector has control-point intervals (2–4°), the leaves sweeping
   left to right and right to left in turn so one sweep ends where the next
   begins; the jaws stay fixed for the arc. Each interval takes the longest of
   its gantry, leaf and beam-on times; the machine cannot lower the dose rate
   below its minimum, so an interval's meterset has a floor. The interval
   doses are recomputed by `pb` at their mid-angles with the mean leaves
   (`segment_dose_matrix`), and the metersets re-optimized against the plan's
   objectives above their floors. Progressive sampling and PortPy's sequential
   convex programming, the roadmap's examples, optimize the leaf positions
   directly; arc sequencing was chosen because it reuses R4 and keeps the
   leaf trajectories deliverable by construction. Direct leaf optimization is
   the natural next step if plan quality asks for it.
9. **An arc is control points in the plan model.** `PhotonArc` (direction,
   collimator, control points with gantry angle, cumulative meterset, jaws and
   leaves); `PhotonBeam.arc` with the arc's sectors as its segments, each with
   its own `gantry_deg`. Engines see sectors; the RT Plan writer writes the
   control points as a DYNAMIC beam (`GantryRotationDirection` CW or CC), and
   the reader reads a dynamic beam back as an arc (an interval that does not
   turn the gantry, or turns it more than 30°, falls back to one static beam
   per interval as before).
10. **Delivery is per fraction.** Plans optimize the course dose; the arc
    request carries the fraction count, the meterset floors apply to each
    fraction's meterset, and the report gives MU, time and speeds per fraction.
11. **SBRT: templates plus the RTOG indices.** `sbrt-lung-54gy-3fx` and
    `sbrt-lung-50gy-5fx` add the prescription and target goals (PTV V100 % ≥ 95 %,
    V90 % ≥ 99 %, lungs minus GTV V20 ≤ 10 %) to the TG-101 limits of R5.
    `services/sbrt.py` computes R100, R50, D2cm, Paddick's gradient index and
    lung V20, graded against the RTOG 0813/0915 conformality table
    (interpolated by PTV volume; the minor-deviation limits checked against
    the NRG Oncology protocol template).
12. **A delivered plan is recomputed through coverage beamlets.** The beamlet
    cut that defines the optimizer's columns keeps a leaf pair only when its
    opening exceeds one beamlet, and a beamlet only when its centre is inside
    the opening. That is right for fluence optimization and wrong for
    recomputing a sequenced plan: most sliding-window arc apertures are a
    single beamlet wide and vanish. `PhotonSegment.coverage_beamlets()` keeps
    every beamlet cell the aperture touches, with the fraction of its area
    that is open, and `CCCEngine.compute_delivered_dose` weights each cell by
    its segment's meterset times that fraction. The optimizer's beamlets, the
    R4 coverage matrix and the goldens are unchanged.
13. **The kernel is scaled laterally in low density (`pb` 1.1.0).** A pencil
    beam that scales depth only overdoses narrow fields in lung by about
    25 % (findings). The kernel's part within 30 mm of the axis, which
    secondary electrons carry, is stretched by s = ρ_eff^−0.9, k(r / s) / s²,
    so its integral and the broad-field dose stay as they were; the photon
    scatter beyond (a cosine taper from 30 to 45 mm) is left as it is.
    ρ_eff is the body's density smoothed by a 5 mm Gaussian (normalised
    inside the body), clipped to at most 1, so water and bone use the
    unscaled kernel and the calibration and water results do not change. The
    planes are precomputed at five scales from 1 to 5, geometrically spaced;
    each voxel interpolates between the two nearest in log scale, in the dose
    path, the segment matrix and the influence matrix alike. The exponent and
    the radius were fitted to the two Monte Carlo lung slabs (2 × 2 and
    10 × 10 cm): with an exponent of 1 the narrow field came out 3–7 % low,
    with 0.9 and 30 mm both slabs are within 2 % at every depth. The lung
    checks are therefore consistency checks, like the penumbra. The influence
    matrix agrees with the full dose in the slab within 0.6 % (its 80 mm
    cutoff truncates little of the stretched kernel) and costs about a third
    more time. Interface build-down and re-build-up are not modelled.
    (Scaling kernels by density follows O'Connor's theorem; superposition
    engines and some commercial pencil beams scale laterally in the same
    spirit.)

## Findings

- **CCC turned the gantry the wrong way (fixed, CCC 1.1.0).** The versors
  inherited with the engine's file protocol rotated the gantry opposite to
  IEC 61217: gantry 90 entered from the patient's right. The proton engine and
  the DRRs were right. Plans optimized inside radiarch were self-consistent,
  but DICOM imports, exports and DRRs of lateral or oblique beams were
  mirrored. The driver now builds the IEC frame (the DRRs' `beam_frame`) and
  maps it into the engine's axes; gantry-0 goldens are unchanged.
- **Cache keys named the engine "default".** A request that did not pin the
  engine version was cached under the literal "default", so an engine fix
  would have kept serving old doses. `EngineSpec.key_version()` now resolves it
  to the registered engine's version in every dose, influence, optimization and
  beam-angle cache key.
- **CCC's shipped scatter cut-off has three consequences.** R7a found its
  output factors flat. R8 adds that the central dose at 10 cm does not change
  with field size either: CCC gives a 4 × 4 or 6 × 6 cm field the 10 × 10 cm
  dose, where the pencil beam gives 0.91 and 0.95 of it, so small fields are
  overdosed at depth by up to about 10 %. The depth dose depends on the
  beamlet size: PDD10 is about 2.5 points lower with the 5 mm beamlets planning
  uses than with the 10 mm beamlets R7 validated. And organs more than about
  2 cm from every beamlet get exactly zero dose in CCC influence-matrix plans,
  so their goals pass trivially. The pencil beam is the engine for plans whose
  out-of-field doses matter.
- **The R7 lung case evaluated no organ.** It wrote the synthetic GTV into a
  second structure set and the geometry read only that one, so the RTOG 0617
  organ goals were silently skipped. The GTV is now written into one structure
  set with the original contours, and the lung objectives use the lungs minus
  the PTV (the template evaluates the lungs minus the GTV).
- **The collimator angle was dropped** when a beam model built its open-field
  plan. It is now carried, and the VMAT step refuses sector beams whose
  collimator or couch differs from their arc's. A beam set now holds up to 180
  beams (it held 9), enough for the sector beams of several arcs.
- **Lung objectives fought the target.** The harness turns an organ's DVH goal
  into a DVH-maximum term and a maximum-dose term at 1.25 times its level; for
  the lungs, which wrap the PTV, a 25 Gy maximum next to a 60 Gy target cooled
  the PTV edge, and normalisation then made a hot core (PTV D5/D95 1.4–1.5).
  Parallel organs around the target now opt out of the maximum term.
- **CCC dropped narrow arc apertures.** The first full run recomputed the
  arcs with CCC's ordinary plan dose and found a PTV D95 of 0.63–0.72 of
  `pb`'s and a gamma pass rate of 44–59 %. A sliding window in water traced
  it to the beamlet cut (decision 12): a 4 mm window had no beamlets at all,
  while windows of 8–40 mm were fully covered and agreed with `pb` to within
  8 % at 10 cm depth. With coverage beamlets the 4 mm window is covered too,
  and CCC / `pb` is 1.07. On the lung arcs the gamma pass rate rose to
  69–83 % and the PTV D95 ratio to 0.70–0.87; the rest is lung transport
  (next finding).
- **The pencil beam overdoses narrow fields in lung.** The kernel is scaled
  in depth only, so it ignores the lateral loss of electrons in low density.
  Recomputing the same arcs and metersets with the body set to water gives
  CCC / `pb` PTV D95 of 1.04–1.09 (CCC's scatter cut-off overdoses small
  fields in water, finding above); with the patient's lungs it is 0.70–0.87.
  So in lung `pb` gives a PTV dose 20–35 % higher than CCC for sliding-window
  arcs, whose apertures are a few millimetres wide: the arcs' lung target
  doses, and their normalisation, are not to be trusted from `pb` alone. The
  same effect makes `pb`'s gradient indices optimistic: R50 of 1.6–2.3 for a
  16 cc PTV is better than lung SBRT achieves in practice (about 3 is typical).
  A Monte Carlo reference of a 2 × 2 cm field through the lung slab settles
  which engine is nearer: relative to the dose at 2 cm in the water above,
  `pb` is 22–27 % above Monte Carlo inside the lung (5–10 cm deep) and right
  beyond it, CCC 8 % below to 1 % above inside and 10 % above beyond. For
  narrow fields in lung CCC was the nearer engine. Lateral kernel scaling
  (decision 13) brings `pb` to 0.99–1.02 of Monte Carlo inside the lung and
  1.00 beyond it.
- **The SBRT plans' fall-off was unchecked beyond 45 mm.** With lateral
  scaling, narrow apertures deliver less dose per MU to a target in lung,
  and the fluence optimization answered with heavily weighted beamlets
  whose entrance dose, 18–22 cm from the PTV at the edge of the body, was
  under no objective: the far ring ran from 20 to 45 mm. D2cm, the maximum
  anywhere in the body beyond 2 cm, rose to 70–83 % of the prescription
  (major deviations). The far ring now reaches the skin; on the second
  patient D2cm fell to 49 %, its maximum 20 mm from the PTV. The earlier
  passes (49 and 59 %) owed something to `pb` 1.0's overly steep fall-off
  in lung.
- **CuPy's constant-mode interpolation read past its array (fixed, `pb`
  1.1.1).** On a float32 array, CuPy 14 takes the cell from the coordinate
  rounded to float32 and the fraction from the float64 coordinate, so a
  coordinate just below the last index reads one element beyond the array
  with a small negative weight. In the dose path this put garbage (up to
  10³⁰) into a few voxels of about one GPU dose in three on a 192-sector arc
  plan, and differences of up to 0.004 Gy between identical runs. It showed
  as a CCC gamma of 0 % on one patient and an invalid dose in another run;
  the CPU path was never affected. GPU lookups now pad the array with zeros
  and zero what lies outside it, which is SciPy's behaviour exactly; repeated
  GPU doses are bit-identical. Version 1.1.1 keeps cached GPU doses of 1.1.0
  from being reused.
- **The Monte Carlo provenance recorded the host name** in a public repository;
  references and run records now record the processor instead.

- **Derived geometries were stored with x and z swapped (found 2026-10-24, fixed in
  `d458e46`).** The geometry store takes (x, y, z) arrays and the derive step (R4) handed it
  (z, y, x) ones, so every PTV, ring or override geometry was transposed against its parent.
  Plans on them were self-consistent and their checks ran, but the anatomy was mirrored against
  the beams. The four planning cases of the R8 record that derive geometries were rerun on the fix
  (`docs/validation/2026-10-23-r8/2026-10-24-correction-d458e46/`): every graded check still
  passes; organ doses change, most where the swapped anatomy had put organs outside the fields.
  The R4 test used a centred cube, where the swap is invisible; the new one uses a non-cubic grid
  and an off-centre structure.

## Consequences

- Photon plans can use either engine; VMAT control-point doses need `pb`.
- `pb_vs_mc`, `pb_vs_ccc`, `photon_*_pb`, `lung_sbrt_vmat` (54 Gy in 3
  fractions, one arc), `lung_vmat_lctsc` (60 Gy in 30, two arcs) and
  `hn_sib_vmat` (70/56 Gy in 35, two arcs) join the harness; `dij_consistency` covers `pb`; the report writes a fourth
  document for `pb`; `tests/test_r8_*.py` cover the engine, arcs, VMAT and SBRT,
  with the cross-engine gamma against CCC in CI.
- CCC remains a weak second engine for small lung fields: its scatter
  cut-off overdoses them at depth while its lung transport is more realistic
  `pb` 1.0's. Its arc comparisons are informative, not graded; whole-plan
  Monte Carlo recomputation is the stronger check.
- CuPy's first CUDA use sets the thread's locale to C (driver 580), after
  which Python reads and writes text as ASCII; the GPU backend restores the
  locale, and the harness passes explicit encodings.
- Open: a Monte Carlo reference of a tumour in lung (interfaces, build-up
  inside the target) and whole-plan Monte Carlo recomputation; direct leaf
  optimization for VMAT; the physicist's review of the R8 record.
