# TrackRAD2025 → RadiArch Model — Input Compatibility Report

**Scope:** input-path check only. This establishes whether the model can *accept* a
TrackRAD case far enough to run a smoke test. It does **not** validate that any dose
output is correct — TrackRAD ships no dose ground truth.

---

## Verdict

> **Partial — needs an adapter + fabricated placeholders.** The analytic dose engine
> will consume a TrackRAD cine frame and emit a dose array, **but only after we invent
> the two hard-required inputs TrackRAD does not contain: a mass-density volume (normally
> derived from a CT in Hounsfield Units) and beam parameters.** The image-dimensionality
> gap (2D+t cine vs. static 3D volume) is trivially adaptable; the missing-inputs gap is
> not — it can only be filled with meaningless dummy data. The real physics engine
> (MCsquare) **rejects the input outright** because it hard-requires a CT.

Probe result (real run, `probe_trackrad_input.py`, analytic engine):

| Interpretation | Result | Output |
|---|---|---|
| `single_frame` (1 cine frame → `(1,H,W)`) | **ACCEPTED** (with placeholders) | dose `(1, 256, 256)` float32 |
| `time_stack` (whole `(T,H,W)` as depth) | **ACCEPTED** (with placeholders) | dose `(50, 256, 256)` float32 |
| MCsquare engine (any interpretation) | **REJECTED** | `EngineUnavailableError` — needs CT (`mcsquare.py:209,239`) |

> ⚠️ **No real TrackRAD case was present on this machine.** A whole-disk search found
> zero `.mha` files and no `trackrad`/`cine`/`_frames` data. The probe therefore ran
> against a **format-faithful synthetic stand-in** (2D+t `.mha` + mask `.mha` + JSON
> sidecars) so the loading→adaptation→model-call path is still exercised end-to-end.
> Every fabricated value is loudly flagged. The *code contract* findings below are from
> the real repository and are unaffected by the data absence.

---

## Evidence

### MODEL REQUIRES (Phase 1 — from code; analytic engine is the smoke-test target)

The model's input is **not** a raw image array. It is a structured `GeometryBundle` +
`BeamModelBundle` + `weights` vector (`services/dose_engines/protocol.py`).

- **`GeometryBundle.density` — 3D `(nz,ny,nx)` float32, mass density g/cm³** — `[hard-required]`
  - declared `protocol.py:62`; rank enforced `analytic.py:63` (`density.ndim != 3`);
    unpacked `analytic.py:95` (`nz, ny, nx = geometry.density.shape`); used *as density*
    `analytic.py:119` (`out = kernel * geometry.density`).
  - **Provenance:** density is produced by converting **CT HU → density**
    (`services/geometry.py:308-309` `hu_model.convert(ct_array)`; doc `geometry.py:11`).
    A physically-meaningful density therefore *requires a CT*. TrackRAD has none.
- **`GeometryBundle.masks` — 3D `(nz,ny,nx)` uint16, same shape as density** — `[hard-required]`
  - declared `protocol.py:63`; shape-match enforced `analytic.py:67-71`.
- **`GeometryBundle.spacing_mm` — `(sx,sy,sz)` 3-tuple** — `[hard-required]`
  - declared `protocol.py:64`; unpacked `analytic.py:96`; `sz` used `analytic.py:102`.
- **`GeometryBundle.result` — `GeometryResult`** (`grid_spec`, `structure_index`,
  `frame_of_reference_uid`, `ct_metadata`) — `[required object; constructible]`
  - `protocol.py:61`; model at `models/geometry.py:248`; `GridSpec.spacing_mm` required
    & positive `models/geometry.py:71,90`; `CTMetadata.num_slices ≥ 1` `geometry.py:243`.
- **`GeometryBundle.ct_hu` / `ct_image`** — `[optional / has-default None for analytic;
  HARD-required for MCsquare]`
  - `protocol.py:65-66` (default `None`); analytic never touches it. **MCsquare raises
    `EngineUnavailableError` when `ct_image is None`** (`mcsquare.py:209`, `:239-240`).
- **`BeamModelBundle.result.fluence_elements.total_count ≥ 1` — beam parameters** — `[hard-required]`
  - `BeamModelBundle` `protocol.py:70-74`; `FluenceElementSet.total_count`
    `models/beam_model.py:250`; enforced `analytic.py:72-73`; and `compute_dose` requires
    `weights.shape == (total_count,)` `analytic.py:136-140`.
- **`BeamModelBundle.plan`** — OpenTPS plan (or test double) — `[required field;
  analytic tolerates a stub `object()`; MCsquare dereferences it — `mcsquare.py:250,254`]`
- **`weights` — np.ndarray `(total_count,)`** — `[hard-required]` — `analytic.py:136-140`.

### TRACKRAD PROVIDES (Phase 2)

From the TrackRAD2025 format (real case not on disk; shapes below are from the
synthetic stand-in used by the probe and are representative, **not** a real download):

- **`<patient>_frames.mha`** — 2D+t sagittal cine-MRI: a 3D array where **axis 0 = time**
  (`(T, H, W)`; stand-in `(50, 256, 256)` float32, spacing `(1.5, 1.5, 0.25)`,
  intensity `[0, 400]`). Raw MR signal intensity — **not** HU, **not** g/cm³.
- **tumor mask `.mha`** — same shape/geometry as frames (stand-in: aligned `(50,256,256)`).
- **JSON sidecars** — field strength (0.35 T), frame rate (4 Hz), scanned region.
- **Absent:** CT, Hounsfield Units, beam parameters, energy/plan, dose.

### Compatibility matrix (Phase 3)

| Model requirement | Hard-required? | TrackRAD provides? | Gap | Adapter feasible? |
|---|---|---|---|---|
| Image volume (rank/shape) | Yes (3D) | 2D+t cine `(T,H,W)` | dimensionality/semantics: time-axis vs depth | **Yes** — take 1 frame `(1,H,W)` or stack `(T,H,W)`; both pass `validate()` |
| dtype / value range | float32; density g/cm³ | float32 MR intensity `[0,400]` | intensity ≠ density units | Only via **fabricated** intensity→density map |
| Spacing / geometry | `(sx,sy,sz)` positive | in-plane `(sx,sy)` real; 3rd axis = time | no real z/depth spacing | Placeholder `sz` (flagged) |
| Structure masks | tumor mask only used by analytic | tumor mask ✓ | none (aligns) | **Yes** — direct |
| Beam parameters | **Yes** (`total_count ≥ 1`) | **none** | no beams at all | **Placeholder only** (single trivial spot) |
| CT HU / density source | analytic: no; MCsquare: **yes** | **none** | no CT → no real density; MCsquare rejects | analytic: placeholder density; MCsquare: **infeasible** |
| Dose grid / ground truth | n/a for input | **none** | — | out of scope (correctness not tested) |

---

## Adapter (Phase 4)

Full runnable probe: [`probe_trackrad_input.py`](probe_trackrad_input.py). It (1) locates a
real case or writes a flagged stand-in, (2) loads via SimpleITK, (3) adapts to the model's
bundles, (4) calls `AnalyticEngine.validate()` then `compute_dose()`, capturing accept/break.

**Every synthetic/placeholder field, flagged (these must never leak into a real evaluation):**

| Field | Placeholder | Why it's fabricated |
|---|---|---|
| `density` | `PLACEHOLDER_DENSITY_FROM_MRI_INTENSITY` — MR intensity linearly mapped to `[0.9,1.1]` "g/cm³" | TrackRAD has no CT/HU; density is normally `hu_model.convert(ct)` (`geometry.py:308`) |
| beam model | `PLACEHOLDER_BEAM_SINGLE_TRIVIAL` — `FluenceElementSet(total_count=1, …)` | TrackRAD has no beam parameters |
| `plan` | `object()` test double | no plan; analytic ignores it (MCsquare would dereference) |
| `spacing_mm[2]` (`sz`) | `PLACEHOLDER_Z_SPACING = 1.0 mm` | a single cine frame has no depth spacing |
| `frame_of_reference_uid`, `structure_index`, grid ids | trivial constants | required by `GeometryResult`, no TrackRAD equivalent |
| weights | `np.ones((1,))` | no plan weights exist |

Adaptation core (see probe for context):

```python
# density: MR intensity is NOT mass density — fabricated band around 1.0 g/cm3
norm = (vol - vol.min()) / (vol.max() - vol.min() + 1e-9)
density = (0.9 + 0.2 * norm).astype(np.float32)          # PLACEHOLDER
# beams: TrackRAD has none — one trivial fluence element
fluence_elements = FluenceElementSet(total_count=1, per_beam=[...])  # PLACEHOLDER
weights = np.ones((1,), dtype=np.float32)                 # PLACEHOLDER
```

**Observed run:** `validate()` → PASS (no issues); `compute_dose()` → ACCEPTED, dose
`(1,256,256)` (single_frame) and `(50,256,256)` (time_stack), both float32.

---

## What this test validates — and what it does NOT

**Validates (the "it ran" half):**
- The real `.mha` loading path (SimpleITK read of 2D+t cine + mask) works on MRI-linac data.
- A TrackRAD frame can be *shaped* into the model's `GeometryBundle`/`BeamModelBundle`
  contract, and the **analytic** engine's `validate()` + `compute_dose()` accept it and
  emit a dose array of the expected rank/shape/dtype.

**Does NOT validate (the "it's correct" half):**
- **Dose correctness** — TrackRAD has no dose ground truth; the analytic engine is a toy
  physics model by design (`analytic.py:1-20`). No dose value here is meaningful.
- **Density realism** — the density is fabricated from MR intensity, not derived from CT.
- **Beam realism** — the single beam is invented; no TrackRAD beam exists.
- **The real physics engine** — MCsquare (and any CT-dependent engine) **rejects** this
  input (`mcsquare.py:209,239`), so "accepted" is specific to the analytic engine.
- **Time semantics** — feeding the cine time-axis as spatial depth is dimensionally legal
  but physically meaningless.

---

## Recommended next step

**The input/loading path works on MRI-linac 2D+t data, but TrackRAD alone cannot drive
the model — it is blocked on two fabricated inputs (density/CT and beams).** Concretely:

1. **For a pure "runs-clean" smoke test:** wire the `single_frame` adapter (placeholders
   loudly flagged) into a smoke test that asserts *only* "loads → adapts → analytic engine
   returns a dose array of the right shape." Never assert on dose values. Guard it so the
   placeholder density/beam can never reach a real evaluation path.
2. **For anything beyond input-path (real dose):** TrackRAD is the wrong dataset — it has
   no CT (→ no real density), no beams, and no dose ground truth. Pair TrackRAD MRI with a
   synthetic/registered CT + a real plan, or use a CT-based dataset, if the goal is a
   meaningful dose smoke test. Do **not** promote the placeholder path into dose validation.
3. **Before trusting any of the Phase-2 shape numbers**, re-run the probe against a real
   downloaded TrackRAD case (the probe auto-detects `*_frames.mha`); the stand-in exists
   only because no case was on disk.
