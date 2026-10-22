# ADR 0014 — The validation report: Monte Carlo references, engine records, signed documents

Date: 2026-10-22. Status: accepted. Roadmap R7 ("Validation report"); builds on the R7a harness.

## Context

R7a gave radiarch a harness with reference tables, goldens and a nightly
run, and found two things about the CCC engine: the shipped binary
truncates scatter, and with the truncation removed its kernels are not a
6 MV beam on the axis. R7 has to turn the harness into evidence: an
independent Monte Carlo reference for the photon engine, planning cases
against the commissioning literature, the Dij-versus-forward check for
every engine in the record, the proton engine against its literature, and
a document per engine version that a physicist can sign.

## Decisions

1. **OpenGATE 10 is the Monte Carlo reference, run as a separate program.**
   `validation/mc_reference.py` is a standalone script executed through
   `uv run --python 3.12 --with opengate==10.1.1` (OpenGATE does not build
   on 3.14, and Geant4 stays out of radiarch's environment). It writes the
   harness phantoms' doses per primary in radiarch's `(z, y, x)` convention
   with the statistical uncertainty and a provenance sidecar into
   `validation/references/mc/`, which ships with the package. The references
   are computed once and committed; the nightly run compares against them.
2. **The reference beam is what the engine assumes.** A point source of the
   Mohan 6 MV spectrum (EGSnrc distribution, CC-licensed data file in
   `references/spectra/`) with a flat angular fluence, collimated by the
   Elekta Versa HD jaws and Agility MLC of OpenGATE's linac contribution;
   no flattening filter, no head scatter, no contamination electrons; slab
   materials are water at the slab density. The CCC engine has generic
   kernels and no head model, so this isolates transport in the phantom,
   which is what the engine computes. The full Versa head from its electron
   source is available (`--source versa`) for a record of the difference,
   not for the nightly.
3. **The CCC engine is radiarch's own build with the truncation as
   run-time parameters.** `engines/ccc/CCC_DoseEngine` is rebuilt from the
   WiscPlan GPLv2 source; the dose cutoff and the dose-mask safety radius
   are read from `CCC_DOSE_CUTOFF` and `CCC_RSAFE_CM`, with the shipped
   constants as defaults, so the default build is bit-identical to the
   shipped binary (the goldens prove it). The driver exposes
   `params["scatter"]`: `shipped` (the default) or `full` (0.01 % cutoff,
   10 cm mask, about 45× slower), with `RADIARCH_CCC_SCATTER` as the
   installation default; the output-factor calibration is keyed by the
   setting so a factor never crosses settings. The Monte Carlo comparison
   (below) found the full setting no closer to the reference, so `shipped`
   stays the default for influence matrices and final doses alike.
4. **Planning cases are real plans through the services.** TG-119's four
   structure sets are planned by radiarch (open-field beam models, CCC
   influence matrix, L-BFGS-B fluence optimization) and scored against the
   goals of the TG-119 instructions, with the institutional means and
   standard deviations of the report (transcribed from Mynampati 2012,
   open access, because the report is paywalled) as context: within 2 SD
   is reported, the goals are graded. The lung end-to-end case writes a
   synthetic GTV into an LCTSC thorax with radiarch's own RT Structure Set
   writer, expands CTV and PTV, plans seven fields and evaluates the RTOG
   0617 goal template. Both are fluence-level plans; the TG-119 means are
   deliverable plans, so that comparison is informative.
5. **Every engine's Dij-versus-forward check is in the record.**
   `dij_consistency` repeats the nightly MCsquare gate (two Monte Carlo
   runs: integral ratio, correlation, high-dose p95) and the deterministic
   CCC identity through the dose service on SimpleFantom.
6. **MCsquare against its literature.** Beyond the PSTAR ranges (R7a), the
   distal 80–20 % fall-off is compared with Bortfeld's range straggling
   plus the beam-data library's energy spread, the entrance spot sigma
   with the library's two-Gaussian spot size, and the lateral growth and
   peak-to-entrance ratio are recorded.
7. **A signed document per engine version.** `radiarch.validation.report`
   compiles the newest run into one document per engine (CCC, MCsquare)
   and one for the engine-independent services, with the engine identity
   (binary SHA-256, kernel fingerprint, version, build notes, scatter
   settings), the radiarch commit, every check with its source, the known
   limitations and a signature block. The nightly job writes them beside
   the results. The document says on its first line that it is research
   evidence and grants no acceptance level; the SMIS B2 levels are granted
   against it, not by it.

## Findings while building the record

- **Geometry service defect (fixed).** A geometry built from a directory read
  every RT Structure Set in it, ignoring the patient reference's named
  structure set and CT series; with two sets sharing a ROI name the first
  file's contours won. TG-119 ships four sets in one folder, so the
  prostate case was planned on the head-and-neck PTV. The disk, upload and
  PACS paths now pass the CT series and the structure set to the loader,
  select by SOP Instance UID before series UID, and refuse a named
  structure set that is not there. (The PACS path also read a misspelled
  attribute for the CT series and never selected one.)
- **Expectations corrected, engines unchanged.** The MCsquare Dij gate needs
  1e6 primaries for its 15 % high-dose tolerance (at 1e5 the two runs'
  counting noise alone exceeds it); the beam data library gives spot sizes
  at the nozzle exit, so the expected size at the isocenter is propagated
  410 mm with the library's divergence and correlation; with both, every
  proton check passes (spot sigma within about 0.1 mm, R80 within 1 mm of
  PSTAR, distal fall-off within Bortfeld straggling).
- **Planning cases needed what planners do.** Fields cover every target of a
  case (the multi-target fields covered only the central one), plans are
  normalised 0.2 % above the coverage goal (exactly on it, percentile
  rounding fails it), and up to four goal-driven reweighting rounds run
  (a failed goal gets three times the weight and, for a limit, a 10 % lower
  dose level; warm start from the previous weights): the rule-based
  automation of ESAPI-style scripts, not a learned model. A TG-119 goal the
  participating institutions did not meet on average passes within their
  mean ± 2 SD, which is how the report asks an institution to compare.
- **pyRadPlan in practice** needs `pydantic<2.12` (its beam serializer
  breaks on 2.12) and an external VOI over the phantom (it computes dose
  only inside structures).

- **The Monte Carlo reference must be step-converged.** The first
  references (no step limit, 0.5 mm cut) were not: in a single water box
  the dose 5–25 mm deep moved 4.6 % when only the production cut changed
  (0.5 to 1 mm), and any geometric boundary in the beam (a nested box, a
  voxelised image, or sibling boxes, all of water) moved it 4.5 % the
  other way with a spike just past the boundary, under option 3 and
  option 4 alike. With electron and positron steps limited to 0.5 mm and a
  0.1 mm cut, a single box and a split box agree within 0.5 % at every
  depth, and the converged dose matches the bounded runs, not the plain
  box: the plain water reference was about 3.7 % high near the surface and
  1.2 % high at 4–8 cm, which pulled its PDD10 down. The references are
  regenerated with the converged settings, and the phantoms are stacked
  sibling boxes with one dose actor each (a voxelised image is 15 times
  slower). The diagnostic runs are in `validation/mc/diag/`.
- **The CCC engine against Monte Carlo (the main result).** The Monte Carlo
  beam carries the spectrum the CCC kernels were built from (Mohan 6 MV,
  mean 1.90 MeV; kernel fluence mean 1.89 MeV), and the engine's
  attenuation table matches NIST to 0.1 % with a properly polyenergetic
  TERMA and the inverse-square correction applied, so the comparison
  isolates the kernels and their convolution. Against the converged
  references (full run `20261022-123318`), normalised at 10 cm depth:

  | Water, 10 × 10 cm² | Monte Carlo | CCC shipped (default) | CCC full scatter |
  |---|---|---|---|
  | PDD10 | 68.0 % | 68.1 % | 71.4 % |
  | dose at 15 / 20 / 25 cm, CCC ÷ MC | | 0.98 / 0.95 / 0.93 | 1.05 / 1.10 / 1.12 |
  | penumbra 80–20 % at 10 cm | 5.9 mm | 5.8 mm | 6.6 mm |
  | gamma 3 %/3 mm | | 98.0 % | 78.3 % |

  Heterogeneity correction factors (slab dose over water dose at the same
  depth, each engine against its own water): behind and in the **bone**
  slab both settings agree with Monte Carlo within 3 % at every depth; in
  the **lung** slab the shipped setting matches at 5 cm and 13 cm but is
  5 % low deep inside the lung (8 cm) and 4 % high far beyond it
  (20–25 cm), while the full setting matches inside the lung and is 3–5 %
  low beyond it. So the default engine reproduces the reference in water
  to 15 cm, in profile, penumbra and gamma, and behind bone; its known
  errors are the too-fast fall-off beyond 15 cm (7 % at 25 cm) and about
  5 % in and far behind lung. The full-scatter setting overshoots at depth
  and fails gamma, so `shipped` stays the default. Removing the remaining
  errors needs new kernels (monoenergetic point kernels from the
  OpenGATE reference that is now in place) or the native engine of R8
  fitted to the same Monte Carlo data, not new parameters.
- **pyRadPlan is a second opinion, not a reference.** Its generic photon
  machine is a different beam (water PDD10 64.6 % against the Monte Carlo
  68.0 %), so its differences from CCC say nothing about CCC; the
  comparison is recorded as informative.
- **Remaining differences of the services, all known since R7a.** Three
  single-voxel maximum doses differ from dicompyler-core by 3.5–4.6 % (the
  two rasterizers assign the boundary voxels differently; means agree
  within 2.3 %), and one LCTSC oesophagus volume is 5.0 % above the polygon
  volume, at the edge of its tolerance.
- **The record.** MCsquare: every graded check passes (ranges, fall-off,
  spot size, influence matrix). TG-119: 24 of 24 goals within the goal or
  the institutional spread (21 goals met outright). Lung end-to-end: both
  LCTSC patients meet RTOG 0617 coverage (PTV V60 97–98 %).

## Consequences

- `validation/common.py` holds what the runner and the case modules
  share, so `python -m radiarch.validation.run` never imports a second
  copy of the result classes.
- Monte Carlo references cost hours of CPU per phantom; they are
  regenerated only when the beam definition or the phantoms change, and
  the sidecar records the primaries, seed and OpenGATE version that made
  them.
- pyRadPlan is the offline second opinion: `validation/pyradplan_crosscheck.py`
  runs its photon pencil-beam (SVD kernel) engine on the generic 6 MV machine
  in its own uv environment (BSD-3, never a runtime dependency) over the same
  phantoms and writes `references/pyradplan/`; `photon_vs_pyradplan` records
  central-axis depth doses (informative). matRad needs MATLAB and is not in
  the record.
- dicompyler-core 0.5.6 predates pydicom 3; the DVH cross-check runs it in
  its own uv environment (Python 3.12, pydicom 2), like pymedphys.
- The native photon engine (R8) joins the same cases: cross-engine gamma
  against CCC and the Monte Carlo references, in the same documents.
