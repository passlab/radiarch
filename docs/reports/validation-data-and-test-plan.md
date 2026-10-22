# Radiarch validation: what data and tests the TPS services need, and when

Status: study, 2026-10-21. Question: which data and tests should evaluate and validate radiarch's planning services, and whether that has to be sorted out before the rest of the roadmap (R14 → R11 in [the evaluation and roadmap](tps-evaluation-and-roadmap.md)) or can wait for R7. Inputs: the radiarch test suite (718 tests after R1), the public datasets already on disk, the AAPM, IAEA and ESTRO guidance named below, and the licence and access state of the public datasets checked on 2026-10-21. File references are relative to this repository.

## 1. Answer in one paragraph

Sort out the **validation foundation now**, but only the part that the next roadmap items depend on, and leave the full validation report (R7) where it is. Concretely: a one-week item, **R7a**, inserted before R14, that (1) freezes regression references ("goldens") for every engine output while the vendored OpenTPS code paths still produce them — R14, R2 and R15 replace those paths and need something to be compared against; (2) fetches the small public datasets that every later test needs and whose licences allow it (TG-119, LCTSC, Pancreatic-CT-CBCT-SEG; 11 GB in all); (3) turns the physics checks written in R1 into a validation harness with cases, tolerances and a nightly run that later items extend (R14 adds the proton cases, R4 the aperture cases, R8 the second-engine cross-check). The expensive references — Monte Carlo doses from OpenGATE, the TG-119 planning results, the lung-case study — stay in R7, because they need R4–R6 to exist and they do not block anything before that. Two facts found on the way change earlier assumptions: **matRad is GPL v3, not BSD-3**, so its generic photon base data cannot be copied into radiarch (R8 must fit its beam model to published or self-generated data), and **no public dataset contains a photon plan radiarch could recompute** (RTPLAN + RTDOSE on CT) except controlled-access trial collections; the reference photon doses have to be made by us, with Monte Carlo, on phantoms and public CTs.

## 2. What "validated" means for a research TPS

Commercial TPS commissioning follows AAPM MPPG 5.a/5.b (photon and electron dose calculation), TG-53 (TPS QA), TG-119 (IMRT commissioning cases), TG-218 (IMRT QA gamma criteria), IAEA TECDOC-1583 (thorax-phantom test cases) and, for protons, TG-185 (IMPT commissioning), TG-224 (machine QA) and the ESTRO-EPTN pencil-beam modelling guidelines. Those documents assume a measured linac; radiarch has no linac, so measured data are replaced by three kinds of reference:

| Reference | What it proves | Where it comes from |
|---|---|---|
| **Published representative data** for a generic 6 MV beam | the engine's depth dose, profiles and output are those of a real 6 MV beam | TrueBeam representative beam data (PDD₁₀ = 66.1 % at 10 × 10 cm², SSD 100 cm; d_max ≈ 1.5 cm), the IROC-Houston reference dataset of Kerns et al. 2016 (116 Clinac + 11 TrueBeam machines; tables in the paper), the TG-119 planning goals and published institutional results |
| **An independent calculation** | two engines agree where they should and disagree where physics says they must (lung, bone, small fields) | OpenGATE 10 Monte Carlo (LGPL; ships Elekta Versa HD and Synergy head models with a caveat that they are approximate) for photons and protons; pyRadPlan (BSD-3) pencil beam offline; MCsquare's own validation literature (IROC lung phantom; TOPAS within 1.8 % on dose indices, > 99 % 3-D gamma in the target) |
| **Regression references** | nothing changed when code was replaced | radiarch's own outputs, frozen |

The acceptance numbers come from MPPG 5.a/5.b (2 % in-field, 3 % in penumbra and heterogeneity regions for basic photon tests; IMRT/VMAT end-to-end gamma at 2 %/2 mm and 3 %/3 mm with > 95 % passing), TG-218 (3 %/2 mm, 10 % threshold, 95 % pass, 90 % action) and TECDOC-1583's per-region criteria. Radiarch reports pass/fail against those numbers **as research targets**; it never claims commissioning, and every result keeps the "not for clinical use" statement.

## 3. The validation matrix

| Service | What to test | Data | Reference and criterion | Exists today? |
|---|---|---|---|---|
| Geometry | HU→density models, rasterization, resampling, structure volumes | LCTSC (volumes in the literature), TG-119 phantom, synthetic cubes | volumes within 1 % of a second rasterizer (dicompyler-core); density tables vs Schneider 2000 | partly (an early real-data note, `docs/REAL_DATA_VALIDATION.md` at commit `2f7b506`; unit tests) |
| Beam model | spot placement (proton), beamlet grids (photon), isocenter handling | synthetic PTV sphere; LCTSC with a synthetic PTV | spots within target + margin; counts stable; golden spot lists | yes for the sphere (R0 test); goldens no |
| CCC photon engine | PDD, profiles, output vs field size, SSD dependence, heterogeneity (lung slab, bone), small fields, oblique incidence; Dij–dose consistency; scenario sign conventions | synthetic water and slab phantoms; TECDOC-1583-like thorax geometry built synthetically (CIRS 002LFC materials) | PDD₁₀ = 66.1 ± 1.0 %, d_max 13–17 mm, profiles flat within 3 %, penumbra 80–20 % width 6–8 mm at 10 cm; MC reference from OpenGATE for slabs: gamma 3 %/3 mm ≥ 95 %, 2 %/2 mm reported | partly (R1: d_max, 1 cGy/MU, direction, symmetry); PDD₁₀ and heterogeneity not yet |
| MCsquare proton engine | range vs energy (R80), Bragg peak width, lateral spread, Dij–dose consistency (V4), range shifter, scenario sets | synthetic water; SimpleFantom (CT + structure set bundled with OpenTPS) | R80 vs PSTAR/ICRU 90 within 1 mm; V4 Dij-vs-dose p95 ≤ 5 % at 1e5 primaries (existing gate); OpenGATE proton MC on slabs | V4 nightly exists; range table not yet |
| Optimization | convergence, objective satisfaction, robust aggregation, warm start | TG-119 cases (CT + 4 structure sets, CC BY 4.0, 14 MB); OpenKBP (340 head-and-neck cases, internal use only) | TG-119 goals met (e.g. C-shape: PTV D95 ≥ 50 Gy, core D10 < 25 Gy; prostate; multi-target; head-and-neck); DVH metrics within the published TG-119 institutional spread; OpenKBP DVH scores | no |
| Beam-angle search | reproducibility, improvement over equispaced | TG-119 prostate, LCTSC lung | cost lower than the equispaced set; deterministic | unit tests only |
| Evaluation | DVH, D_x/V_x, CI/HI, gamma | Pancreatic-CT-CBCT-SEG clinical RTDOSE + RTSTRUCT (40 patients, CC BY 4.0); synthetic dose fields with known DVH | DVH identical to dicompyler-core within binning; gamma identical to pymedphys on the same grids (TG-218 criteria) | brute-force gamma, no cross-check |
| RT object writer (R6) | IOD conformance, referenced-SOP chains, round trips | our own outputs; Vestibular-Schwannoma-SEG RTPLAN/RTDOSE as structural templates (CC BY 4.0) | `dciodvfy` clean; re-import by OHIF, 3D Slicer, Orthanc; DVH from the written RTDOSE equals the in-memory DVH | n/a yet |
| End-to-end lung case | contour → plan → dose → evaluation on a real thorax | LCTSC (60 patients, CT + lungs, heart, esophagus, cord; CC BY 3.0; ~10 GB) with synthetic GTV/PTV; 4D-Lung on disk for motion later | plan meets RTOG 0617 / QUANTEC constraints; CCC vs OpenGATE MC gamma 3 %/3 mm ≥ 95 % in the body, lung region reported separately | no (one LCTSC patient was used once; data no longer on disk) |
| Pipeline regression | every service output on fixed inputs | SimpleFantom, synthetic phantoms, TG-119 | bit-for-bit (Dij, NIfTI) or 1e-5 relative, per engine version | no |

## 4. Data inventory

The datasets live in a data directory outside the repository (`RADIARCH_VALIDATION_DATA`, by default `../data/public`); cases whose data are missing are skipped.

| Dataset | Content | Licence | Size | Use | State |
|---|---|---|---|---|---|
| **TG-119 phantom** (AAPM, Zenodo 8037934) | 129-slice phantom CT + 4 RTSTRUCTs (C-shape, head-and-neck, multi-target, prostate), instructions, report form | CC BY 4.0 | 14 MB | optimizer and end-to-end IMRT cases, with published goals | fetched 2026-10-21 (`tg119/`) |
| **LCTSC** (TCIA) | 60 thoracic CTs with Lung_L/R, Heart, Esophagus, SpinalCord RTSTRUCT | CC BY 3.0 | ~10 GB (a 6-patient subset ≈ 1 GB) | lung photon and proton planning cases, geometry validation | six patients fetched 2026-10-21 (`lctsc/`, 529 MB) |
| **Pancreatic-CT-CBCT-SEG** (TCIA/IDC) | planning CT, CBCT, RTSTRUCT, clinical RTDOSE (ablative) | CC BY 4.0 | subset of 5 patients ≈ 1 GB | evaluation cross-check against a clinical TPS dose; RTDOSE reader | five patients fetched 2026-10-21 (`pancreatic-ct-cbct-seg/`, 1.9 GB with the CBCTs) |
| **Vestibular-Schwannoma-SEG** (TCIA/IDC) | MR, Gamma Knife RTPLAN, RTDOSE, RTSTRUCT | CC BY 4.0 | a few patients ≈ 100 MB | RT object structural templates only | not on disk |
| **TotalSegmentator v2** (Zenodo 10047292) | 1,228 CTs with 117 structures (lungs, heart, esophagus, cord, vertebrae…) | CC BY 4.0 | 23.6 GB zip | large pool of real anatomies for planning cases | not on disk; optional until R10 batch planning |
| 4D-Lung, NSCLC-Radiomics, PDDCA, CMB-LCA, LIDC-IDRI, BraTS-PEDs | already in the data directory | CC BY 3.0 / **CC BY-NC 3.0** (NSCLC-Radiomics) / public domain / CC BY 4.0 | 51 GB | 4D later (R9); PDDCA for head-and-neck cases; NSCLC-Radiomics internal only | on disk |
| **OpenKBP** (AAPM 2020) | 340 head-and-neck cases, 128³ tensors: CT, masks, KBP dose from 9-beam IMRT computed with CERR's IMRTP | no licence stated (TCIA terms apply to the CTs) | ~2 GB | internal optimizer benchmark only; never redistributed | not on disk |
| **DoseRAD2026** (AAPM 2026) | 115 patients CT + MR, 40,500 photon beams and 81,000 proton beamlets with Monte Carlo dose | CC BY-NC 4.0 | large; training set from April 2026 | the best public MC reference for both engines, but non-commercial: internal validation only | not on disk; decide |
| **SimpleFantom** (OpenTPS test data, in the radiarch repo) | 200-slice phantom CT + structure set | OpenTPS Apache-2.0 | 100 MB | proton regression goldens | on disk |
| Published numbers (no download) | TrueBeam representative beam data; Kerns 2016 IROC-H tables; PSTAR/ICRU 90 proton ranges; TG-119 goals and results; TECDOC-1583 cases and tolerances | papers | — | reference tables typed into `validation/references/*.json` with their citations | to do |

Not usable: every TCIA head-and-neck collection with RTPLAN/RTDOSE (HNSCC, Head-Neck-PET-CT, HNC-IMRT-70-33, TCGA-HNSC) and RTOG 0617 (NSCLC-Cetuximab) are controlled access since 2025; GDP-HMM's 3,700 Eclipse plans are CC BY-NC-SA with downloads disabled; matRad's `photons_Generic.mat` is GPL v3.

## 5. Tools

| Tool | Licence | Role |
|---|---|---|
| pymedphys 0.41 | Apache-2.0 | independent gamma (TG-218 criteria); DVH cross-check |
| dicompyler-core 0.5.6 | BSD | independent DVH from RTDOSE + RTSTRUCT |
| OpenGATE 10.1.1 (`opengate` on PyPI) | LGPL-3.0, separate process | Monte Carlo reference for photons (Versa HD / Synergy head models) and protons; Geant4 data download of several GB on first use; hours per case on CPU — run offline, store the results as references |
| pyRadPlan 0.5.0 | BSD-3 (confirmed from its LICENSE) | offline pencil-beam cross-check in its own environment |
| PRIMO | free binary, Windows | not needed; OpenGATE covers it |
| dciodvfy (dicom3tools) | BSD-style | DICOM IOD conformance for R6 |

## 6. The harness

A `src/radiarch/validation/` package, separate from `tests/` because its runs take minutes to hours and need data outside the repo:

- `phantoms.py` — water box, slab phantoms (lung 0.26 g/cm³, bone 1.85), a synthetic TECDOC-1583 thorax (the CIRS 002LFC layout: water-equivalent body with lung and bone inserts), the spherical-PTV cube already used in tests.
- `references/` — JSON tables with citations: 6 MV PDD and profile values, proton R80 vs energy, TG-119 goals, tolerance sets (MPPG 5.a/5.b, TG-218, TECDOC-1583).
- `cases/*.yaml` — one file per case: data source, geometry, plan, engine, metrics, tolerance set.
- `run.py` — runs the cases, writes `validation/results/<date>-<commit>/` with metrics, pass/fail and figures, and a Markdown summary; `--golden` captures references, `--check` compares.
- CI: the existing nightly `mcsquare-validation` job becomes `validation`, running the fast tier nightly and the MC tier weekly.

The regression tier fits in `tests/golden/` (small grids, a few MB) and runs in the normal suite, so R14's MCsquare driver and R15's loaders are compared against today's outputs on every push.

## 7. What to do now and what to leave for R7

*Status 2026-10-21: R7a started — harness skeleton (`src/radiarch/validation/`), reference tables, the three datasets, goldens for the CCC matrix and the SimpleFantom geometry and spots, nightly CI job. Remaining in R7a: the MCsquare input-file golden, the first full run and its results folder, and the PSTAR table transcription.*

**R7a, now, about one week:**

1. Goldens: Dij and dose for the analytic, CCC and MCsquare engines on SimpleFantom and the synthetic phantoms; spot lists; geometry volumes. Comparison test in the suite.
2. Data: the TG-119 package; six LCTSC patients and five Pancreatic-CT-CBCT-SEG patients from TCIA; all into the data directory.
3. Reference tables: 6 MV representative values, proton ranges, TG-119 goals, the three tolerance sets.
4. Harness skeleton with the photon physics cases (PDD₁₀, profiles, heterogeneity slabs, output vs field size) and the proton range case; CCC's PDD₁₀ and penumbra checked against the representative data.
5. Evaluation cross-checks: DVH vs dicompyler-core on the pancreatic RTDOSE; gamma vs pymedphys.

**R7, as scheduled (after R6):** OpenGATE photon and proton references on the slab phantoms and on two LCTSC patients; TG-119 planning on our optimizer against the published goals and institutional spread; the lung end-to-end case; the signed validation document per engine version. R8 adds the native-engine cross-check to the same harness.

**Questions the study raised:**

1. R7a before R14 (adopted: the roadmap table has it at order 3).
2. Whether non-commercial datasets (NSCLC-Radiomics, OpenKBP, DoseRAD2026) may be used for internal validation runs whose results are published as numbers only, never redistributed (open).
3. Whether to fetch TotalSegmentator (24 GB) now or when R10 batch planning needs many anatomies (open).
4. OpenGATE as the Monte Carlo reference (adopted: LGPL, run as a separate process, Geant4 data of several GB).

## 8. First results, 2026-10-21 (fast mode, workstation)

The harness ran the same evening. Fast mode uses 5 mm grids and one patient per data case; the numbers are indicative, the findings are not.

| Case | Result | What it says |
|---|---|---|
| photon_pdd_10x10 | PDD₁₀ 67.0 % (target 66.1 ± 1.5): pass; d_max 22.5 mm; PDD₂₀/PDD₁₀ 0.557 (6 MV ≈ 0.58) | the kernels are 6 MV-like at depth; the build-up is long because the engine transports no contamination electrons |
| photon_profile_10x10 | flatness 0.8 %, symmetry 0.4 %, penumbra 8.7 mm (measured 7.0) | pass |
| photon_output_vs_field | output factors 4×4, 20×20, 30×30 vs 10×10 all **exactly 1.000** | **engine limit found:** the WiscPlan binary discards each beamlet's dose below 0.5 % of its own peak (`doseCutoffThreshold`) and outside a 2 cm safety cylinder (`RSAFE`), so phantom scatter from more than ~2 cm away never reaches a voxel. Field-size dependence is lost and PDD₂₀/PDD₁₀ is slightly low. Rebuilt from source: with the original constants the build is bit-identical to the shipped binary; with a 10 cm mask alone nothing changes (the cutoff is what matters); with a 10 cm mask **and** a 0.01 % cutoff the 4×4 / 10×10 output factor becomes 0.969 (phantom scatter alone ≈ 0.95), but PDD₁₀ rises to 70.4 % and PDD₂₀/PDD₁₀ to 0.625 — harder than a 6 MV beam (≈ 66 % and 0.58). So the shipped combination of kernels and truncation only *looks* 6 MV-like on the axis; the scatter-complete kernels are not a 6 MV beam model. The run is also about 45× slower |
| photon_heterogeneity_slabs | lung 0.97–1.00, bone 1.00 of the path-length expectation | informative until the Monte Carlo references of R7 |
| proton_range_water | first run: 100 and 150 MeV pass, 200 and 225 fail | two test errors, both fixed: a single spot's central-axis dose is not a Bragg curve (the laterally integrated depth dose is), and MCsquare's clinical calibration maps HU 0 to a Schneider adipose/soft-tissue blend, not water (ranges 1.5–2.5 % short). With a water-only calibration all four energies pass: 76.9, 159.1, 260.4, 318.3 mm against the Bragg–Kleeman reference |
| geometry_volumes_lctsc | 5 structures within 1 % after the reference uses per-slice thickness (a missing heart slice is filled by the rasterizer) | pass |
| dvh_crosscheck_pancreatic | mean and max within 1 % of dicompyler-core; D95 of low-dose structures differs (DVH tail) | pass on mean/max; D95 informative |
| gamma_crosscheck_synthetic | identical / 2 % scaled / 1 mm shifted: 100 % both; 3 mm + 4 %: radiarch 30.5 %, pymedphys 55.8 % | **known gap:** radiarch's gamma has no sub-voxel interpolation (TG-218 asks for ≤ 1/3 of the DTA); borderline plans score lower. Scheduled for R5 |

Consequences for the roadmap:

1. **CCC scatter truncation** is the first physics defect the harness found, and removing it exposes a second: the kernel set is not a 6 MV beam once its scatter is complete. For optimization Dij the truncated engine is a tolerable approximation; for the final dose neither setting is a validated 6 MV beam. This raises the priority of the Monte Carlo reference (R7) and of the native engine with self-generated kernels (R8) relative to further CCC work. The plan: ship our own build of the GPLv2 engine (source and patch under `engines/ccc/`, R14/R15) with the mask radius and cutoff as run-time parameters, compute Dij with the fast settings and the final dose per segment aperture with the accurate settings (few large "beamlets", so the slower run stays affordable). This goes into R4 (apertures) and R7 (validation). Until then CCC doses carry the limitation note.
2. **Water needs water**: any MCsquare phantom test must use an explicit water calibration; clinical cases keep the Schneider tables. R14's driver exposes the calibration per run.
3. **Gamma interpolation** moves from "replace by pymedphys" (impossible on Python 3.14) to "implement interpolated gamma natively" in R5, validated against pymedphys through the harness.

## 9. R7 results, 2026-10-22 (full mode, workstation)

R7 turned the harness into a record: a Monte Carlo reference for the photon engine, the planning cases,
the influence-matrix check for every engine, and one signed document per engine version
(`validation/reports/`, generated by `python -m radiarch.validation.report`; ADR 0014 holds the
decisions). The record is the full run `20261022-123318` with one case rerun after a
grading fix.

| Area | Result |
|---|---|
| Monte Carlo reference | OpenGATE 10.1.1 (Geant4) in its own Python 3.12 environment; the Mohan 6 MV spectrum the CCC kernels were built from, as a point source through the Elekta Versa HD jaws and MLC; water, lung (0.26 g/cm³) and bone (1.85 g/cm³) slab phantoms; 5×10⁷ primaries each, 1.3–2.2 % per voxel on the axis |
| CCC in water | PDD10 68.1 % against 68.0 %; penumbra 5.8 against 5.9 mm; gamma 3 %/3 mm 98.0 %; too fast a fall-off beyond 15 cm (0.98, 0.95 and 0.93 of the reference at 15, 20 and 25 cm) |
| CCC heterogeneity | bone: correction factors within 3 % at every depth; lung: 5 % low deep inside the lung, 4 % high 20–25 cm deep, within 3 % elsewhere |
| CCC full-scatter setting | PDD10 71.4 %, 12 % high at 25 cm, gamma 78 %: complete scatter with these kernels is worse, so the shipped truncation stays the default |
| MCsquare | R80 within 1 mm of NIST PSTAR at 100–225 MeV; distal 80–20 % fall-off within Bortfeld's straggling plus the beam model's energy spread; spot sigma within about 0.1 mm of the beam model carried 410 mm from the nozzle; influence matrix against forward dose: integral 0.98, correlation 0.998, high-dose p95 7 % at 10⁶ primaries |
| CCC influence matrix | identical to the forward dose |
| TG-119 | 24 of 24 goals within the goal or the multi-institution spread (mean ± 2 SD, from the report as reproduced by Mynampati 2012); 21 met outright; fluence-level plans with rule-based reweighting |
| Lung end-to-end | two LCTSC thoraces with a synthetic 2 cm GTV in the right lung, CTV and PTV by expansion, seven fields: PTV V60 97–98 % (RTOG 0617 coverage met) |
| DVH, volumes, gamma | DVH means within 2.3 % of dicompyler-core (25 structures); 3 of 25 single-voxel maxima 3.5–4.6 % off; 29 of 30 LCTSC volumes within 5 % (one oesophagus +5.0 %); gamma within 0.5 points of pymedphys on all four synthetic pairs |

Findings that changed the plan:

1. **A Monte Carlo reference must be shown to be converged.** The first references (no step limit,
   0.5 mm production cut) moved 4.6 % near the surface when only the cut changed, and 4.5 % the other
   way with any geometric boundary in the beam, even between water and water. With electron and positron
   steps limited to 0.5 mm and a 0.1 mm cut, a single and a split water box agree within 0.5 %. The
   unconverged water reference had made the CCC engine look 3 points too penetrating.
2. **The CCC engine's remaining errors are in its kernel set**, not its truncation: the attenuation table
   matches NIST, TERMA is polyenergetic, the inverse-square correction is applied, and the error changes
   sign with the scatter setting. The remedy is new kernels from the OpenGATE reference now in place, or
   the native engine of R8 fitted to the same data.
3. **A defect in the geometry service**: a directory holding several structure sets was read whole and
   the named one ignored; TG-119's four sets share one folder, so the prostate case was planned on the
   head-and-neck PTV. Fixed in R7 for disk, upload and PACS loads.
4. **Tools age**: pymedphys and dicompyler-core no longer run on radiarch's Python 3.14 and pydicom 3; both
   run in their own uv environments. pyRadPlan's generic photon machine is a different beam (PDD10 64.6 %),
   so it is a second opinion, not a reference.

What is still open: a physicist's review and signature of the three documents; new CCC kernels or the
native engine for the deep-water and lung errors; output factors, which need a head model; matRad, which
needs MATLAB.

## 10. Sources

- AAPM MPPG 5.b: [Geurts et al., JACMP 2022](https://aapm.onlinelibrary.wiley.com/doi/10.1002/acm2.13641); implementation of MPPG 5.a tests: [PMC5689890](https://pmc.ncbi.nlm.nih.gov/articles/PMC5689890/).
- AAPM TG-119: [report](https://aapm.onlinelibrary.wiley.com/doi/10.1118/1.3238104); data package [Zenodo 8037934](https://zenodo.org/record/8037934) (CC BY 4.0); [instructions](https://www.aapm.org/pubs/tg119/TG119_Instructions_102109.pdf).
- IAEA TECDOC-1583: [IAEA page](https://www.iaea.org/publications/7889/commissioning-of-radiotherapy-treatment-planning-systems-testing-for-typical-external-beam-treatment-techniques).
- TrueBeam representative beam data and PDD₁₀: [Beyer 2013](https://aapm.onlinelibrary.wiley.com/doi/full/10.1120/jacmp.v14i1.4077); [Chang et al. 2019](https://pmc.ncbi.nlm.nih.gov/articles/PMC6370991/); IROC-H reference dataset via [PRIMO benchmark, PMC6081807](https://pmc.ncbi.nlm.nih.gov/articles/PMC6081807/) (Kerns et al., Med Phys 2016, 10.1118/1.4945697).
- OpenGATE linac models: [documentation](https://opengate-python.readthedocs.io/en/master/user_guide/user_guide_contrib_linac.html); [opengate on PyPI](https://pypi.org/project/opengate/).
- Proton: [TG-185](https://www.aapm.org/pubs/reports/detail.asp?docid=208), [TG-224](https://aapm.onlinelibrary.wiley.com/doi/10.1002/mp.13622), [ESTRO-EPTN PBS modelling data](https://www.sciencedirect.com/science/article/pii/S2405631624000915); MCsquare validation: [Huang et al. 2018](https://pubmed.ncbi.nlm.nih.gov/30295950/), [comparative study of fast MC engines](https://pmc.ncbi.nlm.nih.gov/articles/PMC12457214/).
- Datasets: [TotalSegmentator v2, Zenodo 10047292](https://zenodo.org/records/10047292); [LCTSC](https://www.cancerimagingarchive.net/collection/lctsc/); [Pancreatic-CT-CBCT-SEG](https://www.cancerimagingarchive.net/collection/pancreatic-ct-cbct-seg/); [OpenKBP](https://www.aapm.org/GrandChallenge/OpenKBP/) and [paper](https://arxiv.org/abs/2011.14076); [DoseRAD2026](https://arxiv.org/abs/2604.12778); matRad licence: [matRad on GitHub](https://github.com/e0404/matRad); pyRadPlan licence: [LICENSE](https://github.com/e0404/pyRadPlan/blob/main/LICENSE).
- This repository: `tests/test_ccc_engine.py`; the early real-data note `docs/REAL_DATA_VALIDATION.md` (in the git history, commit `2f7b506`).
