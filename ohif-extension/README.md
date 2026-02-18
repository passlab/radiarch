# @radiarch/ohif-extension

OHIF v3 extension for the Radiarch Treatment Planning Service.

## Status

**Scaffold** — provides `RadiarchClientService` for HTTP communication with the Radiarch API. React panels for plan submission, dose overlay, and DVH display will be added in a follow-up iteration.

## Installation

1. Copy this directory into your OHIF Viewers `extensions/` folder.
2. Add the extension to your `pluginConfig.json`:

```json
{
  "extensions": [
    { "packageName": "@radiarch/ohif-extension" }
  ]
}
```

3. Configure the Radiarch server URL:

```json
{
  "extensions": [
    {
      "packageName": "@radiarch/ohif-extension",
      "configuration": {
        "radiarchServerUrl": "http://localhost:8000/api/v1"
      }
    }
  ]
}
```

## Client Usage (from other extensions/modes)

```js
const { RadiarchClientService } = servicesManager.services;
const info = await RadiarchClientService.info();
const plan = await RadiarchClientService.createPlan({
  studyInstanceUid: '1.2.3.4',
  prescriptionGy: 2.0,
  beamCount: 3,
});
const job = await RadiarchClientService.pollJob(plan.data.job_id);
```

## Planned Panels

- **PlanSubmissionPanel** — workflow selection, prescription, beam config
- **DoseOverlayPanel** — RTDOSE visualization controls  
- **DVHPanel** — dose-volume histogram chart
