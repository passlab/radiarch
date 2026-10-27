# ADR 0018 — The viewer: an OHIF extension, standalone or embedded

Date: 2026-10-27. Status: accepted. Roadmap R13 ("Viewer integration").

## Context

Radiarch writes standard DICOM RT objects and pushes them to a DICOMweb server (R6, R13.1). OHIF, the
open web viewer most DICOMweb deployments use, draws the RT Structure Set. At 3.13.13 it has no
handler for RT Dose or RT Plan, so it shows neither the dose nor anything radiarch computes about a
plan: DVHs, clinical goals, the plan summary.

The viewer must serve two kinds of users:

- someone who runs radiarch alone and wants to look at its plans in a browser;
- a platform that already runs its own OHIF, with its own sign-in and data access, and wants
  radiarch's views in it.

Writing the viewer twice would split the effort and the tests.

## Decisions

1. **One OHIF extension and one mode, in radiarch's repository (`viewer/`), built only on OHIF's
   extension and mode interfaces.** No fork of OHIF. They are built and tested against one pinned
   OHIF release, 3.13.13, which every deployment of them uses.
2. **Three layers, each usable without the next.**
   - *Dose (DICOM only).* An RT Dose SOP class handler: the dose as a colour wash and isodose lines
     over the CT, and the DVH. It needs no radiarch server, so it works for any planning system's
     RT Dose. It is the part worth proposing to OHIF.
   - *Radiarch panel (radiarch's API).* The clinical goals, radiarch's DVH, the plan summary and
     actions such as evaluating against another goal template. It finds its export from the DICOM it
     shows (decision 4).
   - *Plan review mode.* The layout: CT, structures, dose, DVH and the panel.
3. **Two deliveries of the same packages.**
   - *Standalone:* an OHIF 3.13.13 build with the extension and mode, behind one web proxy that
     serves OHIF, Orthanc's DICOMweb and radiarch's API from one origin. It ships as a
     `radiarch-viewer` image and a docker-compose profile.
   - *Embedded:* a platform adds the packages to its own OHIF build of the same release.
   The extension takes two things from its host: the radiarch API base URL (configuration), and the
   request headers from OHIF's user authentication service. It contains nothing about any host.
4. **The viewer finds radiarch's results through DICOM UIDs.** `GET /api/v1/rt/exports` with
   `study_instance_uid`, `series_instance_uid` or `sop_instance_uid` returns the exports that wrote
   those objects, newest first. An export names the geometry, plan, dose and lineage it came from.
5. **Radiarch's DVH travels in the RT Dose.**
   - The plan dose of an export carries the RT DVH module: one cumulative DVH per ROI of the exported
     structure set, in cm³, with each ROI's minimum, maximum and mean dose.
   - It is computed from the dose as stored, on radiarch's grid, so any DICOM viewer can show
     radiarch's own DVH without the API.
   - Bins are uniform from 0 Gy, 1, 2 or 5 × 10^k Gy wide, at least 0.01 Gy, at most 1000 bins:
     DVH Data is DS, and the explicit-VR length field caps it at 64 KiB.
   - A DVH the browser computes is labelled as such. Radiarch's is the reference.
6. **No API key in the browser.** Radiarch's API is protected by one shared key (`X-API-Key`). A
   browser never holds it. The proxy in front of the API authenticates the user and adds the key:
   - in the standalone delivery, the bundled proxy;
   - when embedded, the host's gateway.
   Accepting OIDC bearer tokens in radiarch itself is a later option, not needed for either delivery.

## Consequences

- R13 tasks:
  - R13.2a: the lookup route and the DVH in the RT Dose;
  - R13.2b: the dose layer;
  - R13.2c: the panel and mode;
  - R13.2d: the standalone image, the proxy and a browser smoke test in CI;
  - R13.3: checks by hand in OHIF and 3D Slicer.
- Moving to a new OHIF release moves both deliveries. CI builds the packages against the pinned
  release on every push, so the move is a tested change.
- The extension needs its own loader for RT Dose volumes, because OHIF's image loader does not build
  one: it reads the multi-frame RT Dose, applies Dose Grid Scaling and builds a Cornerstone volume.
  OHIF's PET/CT fusion already overlays volumes this way.
- An RT Dose from another system may have no DVH module. The dose layer then computes the DVH in the
  browser and says so.
