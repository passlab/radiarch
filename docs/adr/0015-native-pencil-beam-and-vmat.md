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
   against the array API both share. The GPU path is not yet tested on
   hardware: the workstation's NVIDIA driver and library versions disagree
   until it is rebooted.
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
- **The Monte Carlo provenance recorded the host name** in a public repository;
  references and run records now record the processor instead.

## Consequences

- Photon plans can use either engine; VMAT control-point doses need `pb`.
- `pb_vs_mc`, `pb_vs_ccc`, `photon_*_pb`, `lung_sbrt_vmat` (54 Gy in 3
  fractions, one arc), `lung_vmat_lctsc` (60 Gy in 30, two arcs) and
  `hn_sib_vmat` (70/56 Gy in 35, two arcs) join the harness; `dij_consistency` covers `pb`; the report writes a fourth
  document for `pb`; `tests/test_r8_*.py` cover the engine, arcs, VMAT and SBRT,
  with the cross-engine gamma against CCC in CI.
- Open: the GPU path on hardware; lateral kernel scaling (or a collapsed-cone
  engine of our own) for lung; direct leaf optimization for VMAT; the
  physicist's review of the R8 record.
