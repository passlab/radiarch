# Validation record R8, 2026-10-23: guide for the reviewing physicist

Radiarch is a research treatment-planning system. These documents record how its dose
engines and evaluation services compare with independent references and with the
commissioning literature. **They are research evidence, not a clinical commissioning:
radiarch is not for clinical use, and signing records a review of research evidence,
not a clinical release.**

R8 adds radiarch's own photon engine (`pb`, a pencil beam on a Monte Carlo kernel),
volumetric-modulated arcs, and SBRT planning templates, and it corrects the collapsed-cone
engine's gantry direction (CCC 1.1.0). All documents in this folder come from one full run
of the validation harness, `20261023-110616-dcdc7f3`, with the pencil-beam cases rerun (item 9 below). The runs were made
at commit `dcdc7f3` with the R8 changes not yet committed; the record will be refreshed by a
run at the R8 commit, as R7's was, and a signature refers to that commit. Every check names its target
and its source; ADR 0015 (`docs/adr/0015-native-pencil-beam-and-vmat.md`) gives the
decisions and the findings in prose. The R7 record (`../2026-10-22-r7/`) remains the
record of CCC 1.0.0.

## What to review and sign

| Document | Contents | Signed by |
|---|---|---|
| [`2026-10-23-pb-v1.1.1-dcdc7f3.md`](2026-10-23-pb-v1.1.1-dcdc7f3.md) | The pencil-beam engine: depth dose, profile, penumbra, out-of-field dose, gamma and heterogeneity correction factors against the OpenGATE references; field-size dependence against Monte Carlo; the cross-engine comparison with CCC; influence matrix against forward dose; the narrow-field lung reference; lung SBRT with one arc, lung 60 Gy in 30 with two arcs and a head-and-neck 70/56 Gy integrated boost with two arcs, on public CTs, the lung arcs recomputed by CCC | medical physicist and project lead |
| [`2026-10-23-ccc-v1.1.0-dcdc7f3.md`](2026-10-23-ccc-v1.1.0-dcdc7f3.md) | The collapsed-cone engine at 1.1.0: the R7 cases rerun, the TG-119 and lung plans with the corrected gantry, and the R8 findings on its scatter cut-off | medical physicist and project lead |
| [`2026-10-23-mcsquare-v0.3.0-dcdc7f3.md`](2026-10-23-mcsquare-v0.3.0-dcdc7f3.md) | The proton engine, unchanged since R7 (rerun for completeness) | medical physicist and project lead |
| [`2026-10-23-services-v0.1.0-dcdc7f3.md`](2026-10-23-services-v0.1.0-dcdc7f3.md) | Engine-independent services, unchanged since R7 (rerun for completeness) | project lead (a physicist's look is welcome) |

`run-summary.md` lists every check of the run in one table, and `results.json` holds the
run's full numbers as the harness wrote them.

## What changed since R7, and why it matters for review

1. **A second photon engine, `pb` 1.1.1** (ADR 0015, decisions 1–6). A pencil beam on radiarch's own
   OpenGATE pencil kernel of the Mohan 6 MV spectrum. Against the Monte Carlo references
   (`pb_vs_mc`, 27 graded checks, all pass): water 10 x 10 cm PDD10 67.9 % against 68.0 %, gamma
   3 %/3 mm 99.7 %, penumbra 5.9 mm against 5.9 mm (the fluence penumbra was fitted to this reference),
   dose 2 cm outside the field 4.8 % against 5.1 %; field size at 10 cm (4 x 4 and 20 x 20 over
   10 x 10) 0.906 and 1.064 against 0.895 and 1.058; bone correction factors within 3 %.
2. **Lateral kernel scaling in lung, fitted** (decision 13). A pencil beam that scales depth only was
   22–27 % high inside lung for a 2 x 2 cm field (a new Monte Carlo reference, `lung_slab_2x2`).
   The kernel's short-range part now widens with the local density; its exponent (0.9) and radius
   (30 mm) were fitted to the two lung slabs, which it now matches within 2 % at every depth. The lung
   checks are therefore consistency checks, as the penumbra is.
3. **CCC 1.1.0 turns the gantry as IEC 61217.** CCC 1.0.0 entered gantry 90 from the patient's right.
   Gantry-0 results, and so the R7 water and slab results, are unchanged; plans inside radiarch were
   self-consistent, but DICOM imports and exports of lateral or oblique beams were mirrored.
   `pb_vs_ccc` now checks the side a lateral beam enters.
4. **CCC's shipped scatter cut-off** (findings). Against Monte Carlo, CCC gives a 4 x 4 cm field the
   10 x 10 cm dose at 10 cm (1.000 against 0.895) and a 20 x 20 cm field too little (1.000 against
   1.058); its PDD10 changes by 2.7 points between 5 and 10 mm beamlets; organs more than about 2 cm
   from every beamlet get no dose in its influence-matrix plans. The R7 graded results of CCC are
   unchanged (`photon_vs_mc` 14 failures, the same as R7).
5. **Arcs (VMAT)** (decisions 8–10, 12). Sector fluence swept by the leaves, control-point doses
   recomputed by `pb`, metersets re-optimized above the dose-rate floor, delivery timed per fraction.
   Three arc cases on public CTs: lung SBRT 54 Gy in 3 fractions with one arc, lung 60 Gy in 30 with
   two arcs, head and neck 70/56 Gy in 35 with two arcs; every arc is deliverable at the machine's
   limits. CCC recomputes the delivered lung arcs as the second engine, through coverage beamlets so
   that apertures narrower than one beamlet are dosed (they were dropped before, which made the first
   comparison meaningless). With the patients' bodies set to water the engines agree within 4–9 %
   (CCC's cut-off); with the lungs, PTV D95 CCC / `pb` is 0.86–1.02 and gamma 3 %/3 mm 80–91 %.
6. **SBRT** (decision 11). R100, R50, D2cm and lung V20 against the RTOG 0813/0915 table: R50 2.1 and
   2.4, D2cm 53.9 % (a minor deviation) and 51.0 %. The plans' far ring now reaches the skin: with
   the lung scaling, the optimizer had put heavily weighted beamlets' entrance dose 18–22 cm from
   the PTV, where nothing constrained it (D2cm 70–83 %, findings).
7. **The R7 lung case now evaluates its organs.** In R7 the synthetic GTV was written into a second
   structure set and the organ goals were silently skipped (2 checks); `lung_e2e_lctsc` now grades
   8, all pass.
8. **A GPU fault, found by this record and fixed (`pb` 1.1.1).** CuPy's interpolation with zeros
   outside the array read one element past the array for a coordinate just below its last index,
   which put garbage into a few voxels of about one GPU dose in three on a 192-sector arc plan (a CCC
   gamma of 0 % on one lung patient gave it away). GPU lookups now pad the array; repeated GPU doses
   are bit-identical, and the CPU path was never affected.
9. **This record merges two runs.** The full run `20261023-110616-dcdc7f3` was followed by a rerun of every
   pencil-beam case with `pb` 1.1.1 (`20261023-151703-dcdc7f3`), which also carries the SBRT far ring
   that reaches the skin and the corrected source text of the influence-matrix rows; its cases replace
   the full run's of the same name. CCC, MCsquare and the services do not use the pencil beam.
   `run-summary.md` and `results.json` are the merged run; the graded failures are the R7 ones (CCC
   against Monte Carlo, three DVH maxima, one oesophagus volume), explained in the R7 record.

## Questions we would most like answered

1. **The pencil kernel.** A 0.5 mm pencil of the Mohan 6 MV spectrum into water, scored to
   200 mm radius and 300 mm depth with the R7 references' step-converged physics, moved to
   the isocenter plane conserving each depth's integral, and split into four depth-weighted
   components; the field edge is blurred by a Gaussian whose width was fitted to the Monte
   Carlo penumbra. Is a kernel of this kind (no head, a fitted edge) an acceptable basis for
   a research second engine?
2. **Lung.** A pencil beam that scales depth only was 22–27 % high inside lung for a 2 x 2 cm
   field against Monte Carlo, and sliding-window arcs deliver through apertures a few millimetres
   wide. `pb` 1.1.0 stretches the kernel's short-range part laterally by the local density to the
   power -0.9; the exponent and the 30 mm radius were fitted to the two Monte Carlo lung slabs
   (2 x 2 and 10 x 10 cm), which it now matches within 2 %, so those checks are consistency checks.
   Is a fitted lateral scaling of this kind acceptable, and which independent lung reference
   (a tumour in lung, an anthropomorphic phantom, whole-plan Monte Carlo) would you want next?
3. **CCC's scatter cut-off.** Comparing the two engines (and both with Monte Carlo) shows that the
   shipped CCC setting gives small fields the 10 x 10 cm dose at depth, that its depth dose depends
   on the beamlet size, and that organs a few centimetres outside the field get zero dose. Should
   radiarch make `pb` the default photon engine for plan doses and keep CCC as the check, rather
   than the other way round?
4. **The arcs.** Control points every 4 degrees, leaf sweeps per sector, interval doses from the
   mean leaf positions at each interval's mid-angle, metersets re-optimized above the dose-rate floor,
   delivery timed per fraction against the machine's gantry, leaf and dose-rate limits. Is this
   discretization adequate for a research system, and what would you check first on a real machine?
5. **SBRT grading.** R100, R50, D2cm and lung V20 against the RTOG 0813/0915 table (interpolated by
   PTV volume; the minor-deviation limits checked against the NRG Oncology protocol template). Are
   these the right indices and limits for lung SBRT plans in a research system?

## How to sign

Either reply to the covering email with your comments and a statement that you reviewed the
named documents at the R8 commit, which we then record in the signature table of each
document with the date and a reference to your email; or print the signature section of a
document, sign and date it, and return a scan. Comments that lead to changes produce a new
run and new documents; a signature always refers to one commit.

## How to reproduce (optional)

```bash
git clone https://github.com/passlab/radiarch && cd radiarch && git checkout <the R8 commit>
python3 -m venv .venv && .venv/bin/pip install -e "./src[dev,validation]"     # Python 3.12 or later
.venv/bin/python -m radiarch.validation.run --all --fast    # smoke run; full mode drops --fast
.venv/bin/python -m radiarch.validation.report              # documents from the newest run
# the pencil kernel (about two hours on 18 threads) and the engine's table from it
uv run --no-project --python 3.12 --with opengate==10.1.1 --with itk \
  python src/radiarch/validation/mc_reference.py --pencil --primaries 3e7 --threads 18
.venv/bin/python -m radiarch.services.dose_engines.pb_kernel --mc src/radiarch/validation/references/mc/pencil_6mv.npz
```

The cases on public patient data (LCTSC, PDDCA, Pancreatic-CT-CBCT-SEG, the TG-119 package)
read them from a data directory outside the repository, `RADIARCH_VALIDATION_DATA` (default
`../data/public`); without them those cases are skipped. pymedphys and dicompyler-core run in
their own Python 3.12 environments through `uv`.
