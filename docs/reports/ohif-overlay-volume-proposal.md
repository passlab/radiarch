# Draft proposal to OHIF: overlay volumes for any SOP class handler

Status: draft for review, not yet filed. Written 2026-10-27 against OHIF `v3.13.13`.

## The problem

An extension that adds a dose, a probability map or any other scalar volume drawn over its image volume must
today give its display sets `Modality: 'PMAP'`. `CornerstoneCacheService._getVolumeViewportData`
(`extensions/cornerstone/src/services/CornerstoneCacheService/CornerstoneCacheService.ts`) treats a display set
that has its own `load()` as a derived volume only when `Modality === 'PMAP'`. Any other modality with `load()` is
handled like SEG or RTSTRUCT: the display set is loaded, but no volume is passed on to the viewport.

radiarch's RT Dose extension (`viewer/ohif-extension-rt-dose`) therefore labels RT Dose display sets `PMAP`.
That has three costs:
- the series list shows the dose as "PMAP";
- the extension relies on an internal string;
- any change to that branch in OHIF silently stops the dose from being drawn.

## The proposal

A display-set flag next to the modality check, for example:

```ts
const isParametricMap = Modality === 'PMAP' || displaySet.isOverlayVolume === true;
```

With the flag, a SOP class handler can set `isOverlayVolume: true` and keep the true modality (`RTDOSE`). Nothing
changes for existing extensions. A sentence in the extension documentation would describe the contract:
- `load()` creates and caches the derived volume under `${VOLUME_LOADER_SCHEME}:${displaySetInstanceUID}`;
- the viewport passes `[referenced, overlay]` with the overlay's colormap and window, as the parametric map
  viewport does.

## Also worth raising

- **RT Dose in OHIF itself.** OHIF 3.13.13 has no RT Dose handler. radiarch's handler is Apache-2.0 and has no
  dependency on radiarch, so it could be offered as a basis:
  - the volume, resampled onto the referenced image volume;
  - isodose bands of the plan's prescription;
  - the RT DVH module, or DVHs computed from the structure set.
- **Derived volumes and the texture.** After `voxelManager.setCompleteScalarDataArray`, radiarch calls
  `invalidate()` and `modified()` on the derived volume so the GPU texture is refreshed. The parametric map loader
  does not. Is that needed, or does OHIF rely on the volume being set before its actor exists?

## Before filing

- Check OHIF's issues and discussions for an existing request.
- Test the one-line change on a fork of `v3.13.13` with radiarch's browser test (`tests/test_r13_viewer_browser.py`),
  with the RT Dose display sets set to `Modality: 'RTDOSE', isOverlayVolume: true`.
