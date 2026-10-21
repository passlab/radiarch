# ADR 0010 — Machine models, structure operations, deliverable apertures

Date: 2026-10-21. Status: accepted. Roadmap R4 ("Machine model and apertures").

## Context

Photon plans were open fields with one segment per beam and the optimizer
returned one weight per beamlet: a fluence, not a deliverable plan. The
photon machine was three numbers; the proton machine a BDL behind the
driver. Geometries held one structure per voxel, so a PTV expansion or a
spinal cord running through a target could not be represented, and there
was no way to make a PTV, a ring or a density override from the API.

## Decisions

1. **Machine models as data.** `models/machine.py` defines a photon machine:
   energies with output calibration and dose-rate range, the MLC (leaf
   boundaries along the bank, retraction and overtravel limits, tip
   difference, minimum gap, interdigitation, leaf speed, transmission), jaws,
   gantry speed, and the deliverability thresholds (minimum MU and area per
   segment, segments per beam). Two synthetic machines ship in
   `radiarch/machines/`: `synthetic-120` (40 central 5 mm pairs, 10 outer
   10 mm pairs each side; the default) and `synthetic-160` (80 pairs of
   5 mm, interdigitating). Custom machines are `{beam_library_dir}/{id}/machine.json`.
   `GET /beam-model/machines` lists them. The proton model exposes what the
   BDL says (energies, protons per MU, range shifters, nozzle distances).
2. **Structures overlap.** The mask volume is a `uint64` bitmask (bit
   `label - 1` per structure; 64 structures per geometry) instead of a
   label map; every consumer reads through `services/masks.structure_mask`,
   and geometries written before R4 (`mask_encoding: labels`) still read.
   A cord inside a PTV keeps its voxels; its DVH is right.
3. **Derived geometries.** `POST /geometry/{id}/derive` applies ordered
   operations — expand and erode (Euclidean, isotropic or per-axis), ring,
   union, intersection, subtract, density override (HU through the
   geometry's HU model, or a density), a couch slab — and persists a new
   geometry with `parent_geometry_id` and the operations, cached by the
   parent's key and the operations.
4. **Apertures.** `POST /optimize/{id}/sequence` turns a photon
   optimization into a step-and-shoot plan on a machine
   (`services/sequencing.py`): beamlet weights binned on the leaf pairs,
   the Bortfeld–Boyer decomposition into equal-weight segments (the i-th
   segment of a row opens at its i-th rising and closes at its i-th
   falling edge, so any profile decomposes exactly), leaf tips clipped to
   the travel limits, closed pairs parked, jaws around the open area,
   apertures under the minimum area dropped, interdigitation and tip
   differences reported. The segment metersets are then re-optimized
   against the plan's objectives with the segment dose columns `Dij · A`
   (`A`: the fraction of every open-field beamlet inside each aperture),
   segments under the minimum MU removed and the rest re-optimized. The
   result is a new beam model holding the aperture plan (segments with MLC
   rows, jaws and MU; its beamlets derive from the apertures, so any engine
   can recompute its dose), a dose result of the segments, and a
   deliverability report (segments, MU, areas, leaf travel, beam-on and
   leaf-travel time at the machine's limits).

## Consequences

- The RT writer (R6) gets control points with MLC positions, jaws and
  cumulative meterset weights from the aperture plan.
- The aperture dose is the sum of beamlet doses: no leaf transmission,
  tongue-and-groove, rounded ends or small-field head scatter. A final
  engine run on the aperture plan's own beamlets is the honest check and
  is one request away (`POST /dose/compute` on the new beam model).
- Direct aperture optimization, VMAT and fraction-wise delivery
  constraints stay with R8; structure operations with asymmetric margins
  and multi-layer segmentations are not modelled.
- `test_r4_*.py` cover the machines, masks, structure operations, derived
  geometries, the sequencer and the aperture service end to end on the
  analytic engine.
