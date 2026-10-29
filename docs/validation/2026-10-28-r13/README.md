# Validation record R13, 2026-10-28: the RT objects and the viewer checked by hand

Radiarch is a research treatment-planning system. This record states how its DICOM RT objects and its OHIF
extension were checked by hand in a viewer. **It is research evidence, not a clinical commissioning: radiarch is not
for clinical use.**

R13 brings radiarch's results to a viewer without making viewing part of radiarch: the RT objects go to a DICOMweb
server (Orthanc), and OHIF reads them there, with radiarch's extensions for what OHIF cannot show by itself (the
dose) and what radiarch computes (DVHs, goals). ADR 0018 (`docs/adr/0018-viewer-extension.md`) gives the decisions;
`docs/viewing.md` the set-up. Automated checks run in CI (the Viewer job's browser test, the DICOMweb round trip
against Orthanc); this record covers what only a person at a screen can judge. It closes R6's hand check in OHIF; the check in 3D Slicer is
open (below).

## The cases

| Case | Data | Plan | Where |
|---|---|---|---|
| Lung VMAT | LCTSC `LCTSC-Test-S1-101` (thorax CT and organ contours), a synthetic 20 mm GTV in the right lung | `lung-60gy-30fx-vmat`: 60 Gy in 30 fractions, two arcs, pencil-beam engine; every goal met | a hand-check stack: Orthanc, the API and the viewer image, 2026-10-27 |
| Lung IMRT demo | NSCLC-Radiomics `LUNG1-002` (planning CT, the clinic's GTV, lungs, heart, oesophagus, cord) | `demo-lung-imrt`: CTV and PTV grown from the GTV, 60 Gy in 30 fractions, seven static fields; every RTOG 0617 goal met | the Docker Compose stack from a fresh clone, `scripts/demo-lung.sh`, 2026-10-28 |

The demo plan's goals as radiarch evaluated them: PTV D95 60.12 Gy, cord maximum 35.71 Gy, oesophagus mean 9.59 Gy,
heart D33 20.17 Gy, lungs minus PTV D37 6.33 Gy.

## OHIF (3.13.13 with radiarch's extensions)

Checked by the project lead in the plan review mode (`/plan-review?StudyInstanceUIDs=...`), result reported good on
2026-10-28:

| What | Result |
|---|---|
| The CT, scrolled through, with window and level | shown |
| The dose as isodose colour bands over the CT, on the slice through the dose maximum | shown |
| The structure set as contours in the dose viewport: GTV, CTV, PTV and the organs; planning aids hidden | shown |
| The dose panel: DVHs and the dose statistics | shown |
| The radiarch plan panel: summary, a goal template, Evaluate | shown |
| The RT Plan series | not drawn by OHIF, which has no RT Plan display; the plan panel shows the plan |

Browser: Firefox on an Ubuntu workstation with an NVIDIA GPU. In Chrome on the same workstation the CT and the dose
were black while contours and panels showed (see the findings).

### Findings, and what changed

Each was found during the hand checks, fixed, and covered by a test where a test can see it.

| Found | Cause | Change |
|---|---|---|
| No dose colour wash on a GPU browser | Cornerstone scales a volume's opacity by its sample distance; on the thin MPR slab the dose was nearly transparent | the dose actor's opacity unit distance (`340ef3b`) |
| Still little colour seen | the viewport opened on the middle slice, at the tumour's edge, where only the low bands showed | opens on the dose maximum; lighter low bands (`5e64d0f`) |
| A fresh clone could not fetch from or push to Orthanc | the Orthanc adapter's DICOMweb root, basic authentication on the push | fixed, with a phantom demo (`bd0982d`) |
| The phantom demo showed little | no tumour, no organs | the lung demo from a public patient (`6ba1105`) |
| Contours missing from the dose viewport | the structure set was not drawn there | drawn as contours once the volumes are mounted (`6ba1105`) |
| CT and dose black in Chrome on Linux | Chrome's default ANGLE-on-OpenGL backend draws every volume viewport black (OHIF's own MPR too); ANGLE on Vulkan and Firefox draw them | the viewport detects a blank image and names the fix; documented (`e3adcd2`) |
| The planning command silent for minutes | no progress was printed | each planning round printed (`e3adcd2`); a reused result said so (`ffece91`) |
| Duplicate plan, dose and structure set series after reruns | every export wrote new UIDs | the same plan and settings return the stored export; a copy only when asked, marked (`737d2c5`) |

## 3D Slicer with SlicerRT

**Open: the project lead is to check this by hand.** R13.3 was closed on 2026-10-29 with the OHIF check; this part
stays open until the table below is filled in and signed.

Steps:
1. Install 3D Slicer (5.x) and, from its Extensions Manager, SlicerRT; restart Slicer.
2. Get the demo's export of `LUNG1-002`: the structure set, plan, dose and seven DRR series of the study in Orthanc
   (Orthanc Explorer, the study, Download ZIP), with the planning CT. Running `scripts/demo-lung.sh` again returns the
   same export and pushes the same objects, so the UIDs match the OHIF check.
3. In the DICOM module, import the folder and load the patient: the CT, `RS`, `RP`, `RD` and the `RI_B*` images.
4. Check each row below. For the DVHs, open the Dose Volume Histogram module, choose the dose and radiarch's structure
   set, Compute DVH, and read Dmean, D98, D95, D50, D2 and Dmax per structure from its metrics table (D values via
   "Dose metrics" with V% 98, 95, 50, 2). Compare them with the DVHs radiarch wrote into the RT Dose, which OHIF's dose
   panel shows. Small differences are expected: Slicer voxelises the structures on the dose grid itself.

| What | Check | Result |
|---|---|---|
| Structure set | loaded as a segmentation; the segment names are the ROI names radiarch wrote | |
| RT Dose | loaded as a dose volume; its maximum equals the file's | |
| RT Plan | loaded as a plan with seven beams at the gantry angles radiarch wrote | |
| DVHs | SlicerRT's DVHs against the DVHs radiarch wrote into the RT Dose: Dmean, D98, D95, D50, D2, Dmax per structure | |
| DRRs | loaded as RT images of their beams | |

## Signatures

| Role | Name | Date | Reference |
|---|---|---|---|
| Project lead (OHIF hand check) | | | |
| Reviewer (3D Slicer check) | | | |
