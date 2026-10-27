# SimpleFantomWithStruct: provenance

A synthetic phantom, not patient data: 200 CT slices and one RT Structure Set with a single ROI, `TargetVolume`.
The headers name the generator (Manufacturer `OpenTPS`, StudyDescription `OpenTPS simulation`) and an anonymous
patient (`ANONYMOUS`).

- **Upstream:** OpenTPS, https://gitlab.com/openmcsquare/opentps, directory `testData/SimpleFantomWithStruct`
  (in OpenTPS since its commit `37c8ed6b`, 2024-12-13). The files here are byte-identical to that directory.
- **Licence:** Apache License 2.0 (OpenTPS core). OpenTPS asks that each use be attributed to the OpenTPS
  consortium (http://opentps.org/); radiarch's `NOTICE` credits it.
- **Copied into radiarch:** commit `6fcb985` (2026-02-21); moved to this path in `3f5a866` (2026-10-21).
- **Used by:** the geometry, beam-model and MCsquare tests and the regression goldens in `tests/golden/`.

Known quirk of the upstream file: the structure set's Modality attribute reads `RTDOSE`; its SOP class is RT
Structure Set Storage, and radiarch's reader goes by the SOP class.
