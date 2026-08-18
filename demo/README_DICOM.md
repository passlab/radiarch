# Where to get a real DICOM study for the demo

Radiarch's Geometry Service needs **a CT series + an RTSTRUCT file** for the same patient. This document lists three sources, fastest to slowest. Pick one, end up with a single `.zip` of the patient folder, then run:

```bash
python demo/show_geometry.py --upload /path/to/your/study.zip
```

---

## Option 1 — The Cancer Imaging Archive (TCIA) — recommended

The cleanest free source of anonymized CT + RTSTRUCT data.

**Collection: LCTSC** (Lung CT Segmentation Challenge 2017). Small studies, well-curated, every patient has both a CT series and an RTSTRUCT with named OARs (Esophagus, Heart, Lung_L, Lung_R, SpinalCord).

1. Open <https://www.cancerimagingarchive.net/collection/lctsc/>.
2. Scroll to the **Data Access** table → click the **Download** button next to "Images (DICOM, 4.3 GB)". TCIA will hand you a tiny `.tcia` manifest file (a few KB).
3. Install the **NBIA Data Retriever**: <https://wiki.cancerimagingarchive.net/display/NBIA/Downloading+TCIA+Images>. macOS, Windows, and Linux builds available.
4. Open the `.tcia` manifest in NBIA Data Retriever. In the patient list, **uncheck "Select All"** and tick a single patient (e.g. `LCTSC-Test-S1-101`). Click **Start**.
5. After it finishes you'll have a folder structure like:
   ```
   LCTSC/
     LCTSC-Test-S1-101/
       <study UID>/
         <ct series UID>/   ← ~100 .dcm slices
         <rtstruct UID>/    ← 1 .dcm
   ```
6. Zip the patient folder:
   ```bash
   cd LCTSC
   zip -r LCTSC-Test-S1-101.zip LCTSC-Test-S1-101
   ```
7. Run the demo:
   ```bash
   python demo/show_geometry.py --upload LCTSC-Test-S1-101.zip --show
   ```

Total time: 10–15 minutes including download.

**Alternative TCIA collections** if LCTSC is overkill: `Head-Neck-PET-CT` has CT+RTSTRUCT, `QIN-HEADNECK` is also viable. The same flow works for any TCIA collection that includes the **RTSTRUCT** modality (check the collection's modality table before downloading).

---

## Option 2 — The bundled SimpleFantom, repackaged as a ZIP

Fastest path. Not "clinical" data — it's the synthetic phantom that already lives in the repo — but it does prove the upload pipeline end-to-end with zero downloads.

```bash
cd tests/opentps/core/opentps-testData
zip -r ~/simplefantom_upload.zip SimpleFantomWithStruct
python demo/show_geometry.py --upload ~/simplefantom_upload.zip
```

Useful as a smoke test before pulling a real TCIA study.

---

## Option 3 — An anonymized clinical study from your professor or collaborator

If you have access to an anonymized CT+RTSTRUCT pair from a research collaborator, the requirements are:

- All files must be valid DICOM Part 10 (`.dcm` extension preferred, but the upload endpoint will sniff for the `DICM` magic header at byte 128 if the extension is missing).
- The CT series and the RTSTRUCT must reference the same `FrameOfReferenceUID` — otherwise the contours won't line up with the voxel grid. The Geometry Service won't crash, but the structure masks will be all zeros.
- ZIP the whole patient or study folder. Subdirectories inside the ZIP are fine; the upload endpoint walks recursively.

Re-anonymize first if there's any doubt — Radiarch keeps the bytes you upload until you `DELETE /api/v1/uploads/{upload_id}`.

---

## What the upload endpoint expects

`POST /api/v1/uploads/dicom` accepts a single multipart file part named `file`, value type `application/zip`. Example with curl:

```bash
curl -F "file=@LCTSC-Test-S1-101.zip" \
     http://localhost:8000/api/v1/uploads/dicom
```

Response:

```json
{
  "upload_id": "8c2f3d4e-...",
  "file_count": 102,
  "dicom_count": 102,
  "ct_slice_count": 101,
  "rtstruct_count": 1,
  "total_bytes": 53412934,
  "storage_path": "/data/artifacts/uploads/8c2f3d4e-..."
}
```

You then pass that `upload_id` into a geometry build:

```bash
curl -X POST http://localhost:8000/api/v1/geometry/build \
     -H "Content-Type: application/json" \
     -d '{
       "patient_ref": {"upload_id": "8c2f3d4e-..."},
       "hu_to_density_model": "STOICHIOMETRIC"
     }'
```

Cleanup when you're done:

```bash
curl -X DELETE http://localhost:8000/api/v1/uploads/8c2f3d4e-...
```
