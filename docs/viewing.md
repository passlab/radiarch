# Viewing radiarch's RT objects (OHIF, 3D Slicer)

Radiarch does not include a viewer. It writes standard DICOM RT objects and pushes them by DICOMweb
STOW-RS to a server that a viewer reads, such as Orthanc with its DICOMweb plugin, read by OHIF.
Research use only; nothing here is for clinical use.

## What each viewer shows

| Object radiarch writes | OHIF 3.13.13 | 3D Slicer with SlicerRT |
|---|---|---|
| CT (from the source PACS) | yes | yes |
| RT Structure Set | yes: contours over the CT (`cornerstone-dicom-rt`) | yes |
| RT Dose | **no**: OHIF has no RT Dose handler; the series is listed but not drawn | yes: dose colour wash, isodoses, DVH (radiarch's, from the file) |
| RT Plan, RT Ion Plan | no (no handler) | yes: beams |
| RT Image (DRR) | as an image series | yes |
| RT treatment records | no | no |

The OHIF column was read from OHIF's source at tag `v3.13.13`: its SOP class handlers cover the RT
Structure Set (`extensions/cornerstone-dicom-rt`), segmentations, parametric maps and structured
reports, not RT Dose or RT Plan. Showing the dose, the DVH and the clinical goals in OHIF is the
second part of roadmap item R13: a radiarch OHIF extension and panel.

The 3D Slicer column is what SlicerRT supports for these objects. It has not been checked by hand on
radiarch's objects yet.

## What OHIF reads from the structure set

OHIF finds the CT a structure set belongs to through Referenced Frame of Reference Sequence → RT
Referenced Study Sequence → RT Referenced Series Sequence → Contour Image Sequence. It iterates the
contour images without a guard, so a structure set without them does not load. Radiarch writes every
level, each CT image of the series, closed planar contours and a display colour per ROI.

Contours are written on the geometry's grid. When the geometry was resampled from the CT, contour
planes can fall between CT slices; on the CT's own grid they lie on the slices.

`tests/test_r13_viewer.py` checks all of this on every push to GitHub.

## What a viewer gets beyond the objects (R13.2a)

- **Radiarch's DVH in the RT Dose.** The plan dose of an export carries the RT DVH module:
  - one cumulative DVH per ROI of the exported structure set, in cm³, with each ROI's minimum,
    maximum and mean dose;
  - computed from the dose as stored, on radiarch's grid;
  - bins 1, 2 or 5 × 10^k Gy wide, at most 1000.
  3D Slicer and the radiarch OHIF extension read it from the file. Turn it off with `"dvh": false` on
  the export.
- **The export behind what is on screen.** `GET /api/v1/rt/exports?sop_instance_uid=<uid>` returns the
  export that wrote that instance. `series_instance_uid` and `study_instance_uid` work the same way,
  and every filter given must match. Results are newest first; the SDK call is `rx.find_exports(...)`.
  An export names its geometry, plan and dose, from which the evaluation and the lineage follow.

The design of the viewer itself, one OHIF extension used standalone or inside another OHIF, is
ADR 0018.

## The standalone viewer (R13.2d)

One container serves OHIF 3.13.13 with radiarch's dose extension, radiarch plan panel and plan review
mode. Its nginx proxy puts Orthanc's DICOMweb (`/dicom-web`) and radiarch's API (`/radiarch/api`) on
the same origin and adds radiarch's API key to every API request, so the browser never holds the key.

```bash
docker compose --profile viewer up -d          # api, worker, orthanc, and the viewer on 127.0.0.1:3000
# push an export (RADIARCH_DICOMWEB_URL=http://orthanc:8042/dicom-web), then open
#   http://localhost:3000/plan-review?StudyInstanceUIDs=<study>
```

The image is `viewer/standalone/Dockerfile` (built from `viewer/`). It is configured by these
environment variables:

| Variable | What it sets |
|---|---|
| `ORTHANC_URL` | Orthanc's base URL |
| `ORTHANC_AUTHORIZATION` | an Authorization header for Orthanc, or empty |
| `RADIARCH_URL` | radiarch's base URL |
| `RADIARCH_API_KEY` | the key the proxy adds to API requests |
| `VIEWER_PORT` | the port nginx listens on |

Whoever reaches the viewer uses radiarch with that key. Compose therefore publishes it on localhost
only. To serve it to more people, put an authenticating proxy in front of it.

`./scripts/demo-lung.sh` makes a plan to look at (docs/demo.md, section 5.1):
1. It downloads a public lung-cancer patient (NSCLC-Radiomics `LUNG1-002`: CT, tumour and organ contours) from TCIA
   and pushes it to the stack's Orthanc (`radiarch fetch-tcia --push` in the API container).
2. It plans it with the shipped `demo-lung-imrt` protocol (`radiarch plan --push` in the API container).
3. It prints the link.

`./scripts/demo-viewer.sh` does the same with the bundled phantom and `demo-phantom-imrt`, without a download.

The compose file sets `RADIARCH_VIEWER_ROUTE=plan-review`, so radiarch's own links open this mode.

The plan review mode opens the plan dose over its CT, on the slice through the dose maximum, with the contours of
the structure set the dose belongs to (for a radiarch plan: radiarch's, with the CTV and PTV it derived). Planning
aids start hidden: rings, optimisation helpers and organ-minus-target structures such as `Lungs-PTV`, and ROIs
interpreted as avoidance or control. On the right are three panels:
- the dose's DVHs (planning aids on request) and isodose legend;
- the radiarch plan: summary, a goal template, Evaluate;
- the structures, each of which can be shown or hidden.

## Setting it up

1. **A DICOMweb server holding the CT.** Orthanc with its DICOMweb plugin
   (`orthancteam/orthanc`, `DICOM_WEB_PLUGIN_ENABLED=true`) answers STOW-RS, QIDO-RS and WADO-RS
   at `/dicom-web`. Radiarch's objects go into the CT's study, so the server must also hold that CT.
2. **Radiarch pushes there.** Set `RADIARCH_DICOMWEB_URL=http://<orthanc>:8042/dicom-web`
   (authentication: `PRODUCTION.md`, "Pushing RT objects"). Push while exporting
   (`"push": true` on `POST /api/v1/rt/export`) or later (`POST /api/v1/rt/exports/{id}/push`).
3. **OHIF reads the same server.** The OHIF image (`ohif/app:v3.13.13`) ships
   `config/local_orthanc.js`; select it with `APP_CONFIG=config/local_orthanc.js`. That file expects
   Orthanc's `/dicom-web` on OHIF's own origin, so serve both behind one reverse proxy (Orthanc has
   no CORS support). Otherwise, point `qidoRoot`, `wadoRoot` and `wadoUriRoot` at a proxied URL.
4. **A link to the study.** Set `RADIARCH_VIEWER_URL` to OHIF's base URL. A successful push then
   returns `viewer_url`, `<base>/viewer?StudyInstanceUIDs=<study>`, on the push result and on the
   export. The link assumes the viewer reads the server the export was pushed to.

```bash
curl -H "X-API-Key: $KEY" -X POST $API/rt/exports/<export id>/push
# {"export_id": "...", "pushed": 4, "url": "http://orthanc:8042/dicom-web",
#  "viewer_url": "http://localhost:3000/viewer?StudyInstanceUIDs=1.2.826...."}
```

## Tests

`tests/test_r13_viewer.py`:

- The structure set carries what OHIF's RT loader reads, and its contour planes are CT slice positions.
- A push links to the study when a viewer is configured, and only after a successful push.
- With `RADIARCH_TEST_DICOMWEB_URL` set, a CT and an export are stored by STOW-RS and read back by
  QIDO-RS and WADO-RS in one study:
  - every object arrives in its own series, with its modality;
  - the structure set's contour images, the plan's structure set and the dose's plan all resolve to
    instances on the server.

The Full Tests job in CI runs an Orthanc service container with the DICOMweb plugin for this test.

`tests/test_r13_viewer_browser.py` is the browser test (CI's Viewer job, on every push). It
assembles the whole deployment:
- a CT (water in air) and an export are pushed to Orthanc;
- radiarch's API is served with an API key required;
- the viewer image is put in front of both.
Headless Chromium then opens the plan review mode and checks:
- the hanging protocol opens the dose over its CT, labelled with the 2 Gy prescription;
- the dose panel shows the RT Dose's own DVHs, named by the structure set;
- the CT is drawn;
- inside OHIF, the dose is a second volume on the CT's grid:
  - its values are the file's dose in % of the prescription;
  - its opacity unit distance is 0.15 mm (see "How the dose is shown" in `viewer/README.md`);
  - the colour map is the isodose map, transparent below 30 %;
  - the window runs from 0 to 120 %;
  - each isodose band has its own colour;
- the radiarch panel finds the plan, and Evaluate grades the RTOG 0617 goals and draws radiarch's DVHs.

On failure it keeps screenshots, the page and the console.

The test also checks the colour wash in pixels. It takes screenshots of the viewport with the dose shown
and hidden, and the dose must change at least a quarter of the viewport's pixels. Headless Chromium on the
runner draws through software WebGL (SwiftShader).
Locally it skips unless the variable points at a server, for example a throwaway
`docker run --rm -p 127.0.0.1:18042:8042 -e DICOM_WEB_PLUGIN_ENABLED=true -e ORTHANC__AUTHENTICATION_ENABLED=false orthancteam/orthanc:24.6.2`
with `RADIARCH_TEST_DICOMWEB_URL=http://127.0.0.1:18042/dicom-web`.
