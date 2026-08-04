# BACKLOG

Adjacent work noticed but deliberately **not started** (Charter §4 anti-scope-creep).
Each entry names what it would serve before it's ever picked up.

## TrackRAD / MRI-linac related

- **MRI as a first-class geometry input modality.** Today `GeometryService` accepts
  only `CTImage` (`src/radiarch/services/geometry.py`, raises without a CT). A learned
  dose model that predicts from MRI+beams (a DoseRAD variant) would need the geometry
  path to carry an MR volume without fabricating a density. MC/CCC engines must still
  reject it (no HU). *Serves:* a future MRI-input DoseRAD task — only if that task is
  chosen. Not on the current paper path.

- **Cine tumour-tracking service.** TrackRAD's actual task (2D+t lesion
  segmentation/tracking). Fully out of the dose-prediction paper scope; would only make
  sense as a separate project. *Serves:* nothing in the current paper — do not build.

- **Promote the input-path probe onto the real loader.** `probe_trackrad_input.py`
  predates `adapters/trackrad.py`; it could import `to_smoke_test_bundles` instead of
  re-deriving the adaptation. Pure cleanup. *Serves:* maintenance, not a paper claim.
