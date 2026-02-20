# @radiarch/ohif-extension

OHIF v3 extension for the Radiarch Treatment Planning Service. Provides 4 interactive panels and 8 commands exposing all Phase 8 features.

## Panels

| Panel | Description |
|-------|-------------|
| **Treatment Plan** | Workflow selection, dynamic parameter form, dose objectives editor, robustness config, job progress tracking |
| **DVH** | Interactive dose-volume histogram chart with min/max/mean dose stats |
| **Dose Overlay** | RTDOSE visibility toggle, opacity slider, color map selector, isodose line controls |
| **Simulation** | Delivery simulation with motion/fractionation parameters (Phase 8D) |

## Commands

| Command | Description |
|---------|-------------|
| `radiarch.fetchWorkflows` | Fetch available workflow list |
| `radiarch.fetchWorkflowDetail` | Fetch workflow parameters for dynamic form |
| `radiarch.submitPlan` | Submit plan with full Phase 8 payload |
| `radiarch.pollJob` | Poll job status with progress callback |
| `radiarch.loadPlanResult` | Load plan QA summary and DVH data |
| `radiarch.loadDose` | Fetch RTDOSE artifact for overlay |
| `radiarch.submitSimulation` | Create delivery simulation |
| `radiarch.pollSimulation` | Poll simulation until complete |

## Installation

1. Copy this directory into your OHIF Viewers `extensions/` folder.
2. Add the extension to your `pluginConfig.json`:

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
  workflowId: 'proton-impt-optimized',
  beamCount: 3,
  objectives: [
    { structure_name: 'PTV', objective_type: 'DUniform', dose_gy: 2.0, weight: 100 },
    { structure_name: 'SpinalCord', objective_type: 'DMax', dose_gy: 0.5, weight: 50 },
  ],
});
const job = await RadiarchClientService.pollJob(plan.data.job_id);
```

## File Structure

```
src/
├── index.ts                 ← Extension entry (service + panels + commands)
├── id.js                    ← Extension ID
├── commandsModule.js        ← 8 registered commands
├── services/
│   └── RadiarchClient.js    ← HTTP client (axios)
└── panels/
    ├── PlanSubmissionPanel.js   ← Workflow config, objectives, robustness
    ├── DVHPanel.js              ← SVG dose-volume histogram
    ├── DoseOverlayPanel.js      ← Dose visualization controls
    └── SimulationPanel.js       ← Delivery simulation (Phase 8D)
```
